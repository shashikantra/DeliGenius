"""End-to-end agent-eval CLI.

Usage:
    python -m deli_rag.eval.run_agent \
        --golden eval/golden/phase2_v1.yaml \
        --base-url http://localhost:8000 \
        --out eval/reports/agent-$(date +%Y%m%d).json

Design constraints, in priority order:
  1. **Read-only.** Only GET /health and POST /ask. No DB session,
     no audit_log write, no imports from deli_rag.agent.*. If /ask
     breaks, this CLI fails the same way a browser would, and the
     caller can tell "the harness is broken" apart from "the app is
     broken" by whether /health returns 200.
  2. **Rate-limit-aware by default.** Groq's Free Tier is ~10-15 req/min.
     `--sleep-seconds` defaults to 65 so a full run of ~18 golden items
     takes ~20 minutes and never trips the limit. `--sleep-seconds 0`
     is available for local Ollama runs, but the *default* is safe.
  3. **Deterministic.** Fixed `k`, fixed `rerank`, fixed `model=None`.
     Model selection is deliberately *not* asserted on day 1: routes.py
     has a latent `prefer_local` bug where non-Ollama model IDs are
     dropped (see `prefer_local=req.model.startswith("ollama:")`),
     so asserting `model_used` would false-fail.
  4. **Report-on-failure.** A single 500 from /ask does not abort the
     run. It records the HTTP status and body for that item, keeps
     going, and the final report shows N pass / M fail.
  5. **No retries.** Retries hide flakiness and inflate the Free Tier.
     If an item fails, it is recorded as failed; the human decides
     whether to re-run.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from deli_rag.eval.golden_agent import (
    GoldenAgentItem,
    GoldenAgentSet,
    load_golden_agent_set,
)
from deli_rag.eval.scorers_agent import (
    abstain_match,
    route_match,
    substring_match,
)


@dataclass
class AgentPerItem:
    id: str
    question: str
    passed: bool
    reason: str = ""
    elapsed_s: float = 0.0
    http_status: int | None = None
    # Record the observable bits of the response so a failure report is
    # actionable without re-running. Trimmed to what we assert on — the
    # full AskResponse lives in the live server; we do not duplicate it.
    observed_route: str | None = None
    observed_abstained: bool | None = None
    observed_answer_excerpt: str = ""
    observed_citation_kinds: list[str] = field(default_factory=list)


@dataclass
class AgentEvalReport:
    golden_version: str
    base_url: str
    model_used: str | None
    started_at: str
    finished_at: str
    n_items: int = 0
    n_pass: int = 0
    n_fail: int = 0
    items: list[AgentPerItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "golden_version": self.golden_version,
            "base_url": self.base_url,
            "model_used": self.model_used,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "n_items": self.n_items,
            "n_pass": self.n_pass,
            "n_fail": self.n_fail,
            "items": [asdict(i) for i in self.items],
        }


def _ask_one(
    client: httpx.Client,
    item: GoldenAgentItem,
    *,
    acl: str,
    timeout_s: float,
) -> tuple[dict[str, Any] | None, int | None, str]:
    """POST /ask for one item; return (body, status, error-string).

    Any transport error or non-2xx status is captured and returned, not
    raised. The caller records it as a failed item.
    """
    payload = {
        "question": item.question,
        "acl": acl,
        "k": 8,
        "rerank": False,
        "model": None,          # day-1 choice; see module docstring
        "history": [],
    }
    try:
        resp = client.post("/ask", json=payload, timeout=timeout_s)
    except httpx.HTTPError as e:
        return None, None, f"transport error: {e!r}"
    if not resp.is_success:
        return None, resp.status_code, f"http {resp.status_code}: {resp.text[:200]!r}"
    try:
        return resp.json(), resp.status_code, ""
    except json.JSONDecodeError as e:
        return None, resp.status_code, f"non-json response: {e!r}"


def _score(
    item: GoldenAgentItem,
    body: dict[str, Any],
) -> tuple[bool, str, dict[str, Any]]:
    """Apply all three scorers. Returns (pass, reason, observed).

    `reason` is a compact human string for the report; empty on pass.
    `observed` is a dict of the fields a failure investigation needs.
    """
    answer: str = str(body.get("answer", ""))
    abstained: bool = bool(body.get("abstained", False))
    needs_clarification = body.get("needs_clarification")
    citations_raw = body.get("citations", [])
    # CitationOut shape → plain dicts; ensure it's a list of mappings.
    citations: list[dict[str, Any]] = [
        dict(c) for c in citations_raw if isinstance(c, dict)
    ]
    observed = {
        "observed_route": (
            "sql" if any(c.get("kind") == "sql" for c in citations)
            else "doc" if any(c.get("kind") == "doc" for c in citations)
            else "none"
        ),
        "observed_abstained": abstained,
        "observed_answer_excerpt": answer[:160],
        "observed_citation_kinds": [str(c.get("kind")) for c in citations],
    }

    # Hard-fail first: if the response shape is wrong, the other scorers
    # would produce misleading "false" answers.
    if not isinstance(citations_raw, list):
        return False, "response.citations is not a list", observed

    if not route_match(citations, item.expected_route):
        return False, f"route: expected {item.expected_route!r}, got {observed['observed_route']!r}", observed
    if not substring_match(answer, item.expected_substrings):
        return False, f"substrings missing from answer: {item.expected_substrings!r}", observed
    if item.should_abstain and not abstained:
        return False, "expected abstain, got answer", observed
    if (not item.should_abstain) and abstained:
        return False, "unexpected abstain", observed
    if not abstain_match(
        abstained=abstained,
        needs_clarification=needs_clarification,
        answer=answer,
        citations=citations,
        expect=item.expect_abstain_reason,
    ):
        return False, f"abstain reason mismatch: expected {item.expect_abstain_reason!r}", observed
    return True, "", observed


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="deli_rag.eval.run_agent")
    p.add_argument("--golden", required=True, type=Path,
                   help="Path to phase2_v1.yaml (or any agent-shape golden set).")
    p.add_argument("--base-url", default="http://localhost:8000",
                   help="FastAPI base URL (default: %(default)s).")
    p.add_argument("--out", type=Path, default=None,
                   help="Report path (JSON). Default: eval/reports/agent-<UTC>.json")
    p.add_argument("--only", default="",
                   help="Comma-separated item ids to run (default: all).")
    p.add_argument("--sleep-seconds", type=float, default=65.0,
                   help="Sleep between /ask calls (default: %(default)s). "
                        "Set to 0 for local Ollama runs.")
    p.add_argument("--timeout", type=float, default=120.0,
                   help="Per-request timeout in seconds (default: %(default)s).")
    args = p.parse_args(argv)

    golden: GoldenAgentSet = load_golden_agent_set(args.golden)
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    items = [it for it in golden.items if not only or it.id in only]
    if not items:
        print(f"error: no golden items matched --only={args.only!r}", file=sys.stderr)
        return 2

    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report = AgentEvalReport(
        golden_version=golden.version,
        base_url=args.base_url,
        model_used=None,  # populated from first successful response if available
        started_at=started_at,
        finished_at="",
        n_items=len(items),
    )

    with httpx.Client(base_url=args.base_url.rstrip("/")) as client:
        for idx, item in enumerate(items, start=1):
            t0 = time.perf_counter()
            body, status, err = _ask_one(
                client, item, acl=item.acl_levels[0], timeout_s=args.timeout
            )
            dt = time.perf_counter() - t0

            if err:
                report.items.append(AgentPerItem(
                    id=item.id, question=item.question, passed=False,
                    reason=err, elapsed_s=dt, http_status=status,
                ))
            else:
                assert body is not None  # err == "" implies body is not None
                if report.model_used is None and body.get("model_used"):
                    report.model_used = str(body["model_used"])
                passed, reason, observed = _score(item, body)
                report.items.append(AgentPerItem(
                    id=item.id, question=item.question, passed=passed,
                    reason=reason, elapsed_s=dt, http_status=status,
                    **observed,
                ))

            ok = report.items[-1].passed
            report.n_pass += int(ok)
            report.n_fail += int(not ok)
            mark = "PASS" if ok else "FAIL"
            print(f"[{idx}/{len(items)}] {mark}  {item.id}  ({dt*1000:.0f}ms)"
                  + (f"  — {report.items[-1].reason}" if not ok else ""))

            # No sleep after the last item.
            if idx < len(items) and args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

    report.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    out = args.out
    if out is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = Path("eval") / "reports" / f"agent-{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(f"\nreport: {out}")
    print(f"{report.n_pass}/{report.n_items} passed, {report.n_fail} failed")

    return 0 if report.n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
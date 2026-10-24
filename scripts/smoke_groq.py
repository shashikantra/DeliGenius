"""One-shot smoke test: pipeline -> prompt -> Groq -> print raw JSON reply."""
from __future__ import annotations

import json
import sys

from deli_rag.agent.pipeline import Pipeline
from deli_rag.agent.prompt import build_prompt
from deli_rag.agent.llm import GroqClient, parse_json_object
from deli_rag.db.writer import session_scope
from deli_rag.embeddings.base import get_embedder
from deli_rag.schemas import Filters


def main() -> None:
    print("smoke: start", flush=True)
    query = "what was our RIA commission for May 2026?"
    filters = Filters(acl_levels=["public", "internal"], tenant="default")

    session = session_scope()
    try:
        embedder = get_embedder()
        pipe = Pipeline(session, embedder)
        result = pipe.run(query, filters=filters, k=8)
    finally:
        session.close()

    print("=== TRACE ===", flush=True)
    for line in result.trace:
        print(" ", line, flush=True)
    print(flush=True)

    system, user, index = build_prompt(query, result.doc_chunks, result.sql_evidence)
    print("=== SYSTEM (first 200 chars) ===", flush=True)
    print(system[:200], flush=True)
    print(flush=True)
    print("=== USER (first 500 chars) ===", flush=True)
    print(user[:500], flush=True)
    print(flush=True)

    print("=== GROQ CALL ===", flush=True)
    reply = GroqClient().complete_json(system=system, user=user)
    print(f"model_used={reply.model_used} fallback={reply.fallback_used}", flush=True)
    print(f"tokens_in={reply.tokens_in} tokens_out={reply.tokens_out} "
          f"latency_ms={reply.latency_ms:.0f}", flush=True)
    print(f"raw content:\n{reply.content}", flush=True)
    print(flush=True)

    print("=== PARSED ===", flush=True)
    try:
        parsed = parse_json_object(reply.content)
        print(json.dumps(parsed, indent=2), flush=True)
    except Exception as e:
        print(f"PARSE FAILED: {e}", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Importing the parser modules triggers @register so the registry is populated.
from deli_rag.config.settings import get_env
from deli_rag.ingestion.parsers import get_parser_for
from deli_rag.ingestion.parsers.csv_parser import CsvParser  # noqa: F401
from deli_rag.ingestion.parsers.docx_parser import DocxParser  # noqa: F401
from deli_rag.ingestion.parsers.lottery_parser import LotteryParser  # noqa: F401
from deli_rag.ingestion.parsers.pdf_parser import PdfParser  # noqa: F401
from deli_rag.ingestion.parsers.ria_parser import RiaParser  # noqa: F401
from deli_rag.ingestion.parsers.sales_csv_parser import SalesCsvParser  # noqa: F401
from deli_rag.ingestion.parsers.xlsx_parser import XlsxParser  # noqa: F401
from deli_rag.llm.groq_models import validate_and_filter_llms


def main() -> int:
    env = get_env()
    logging.basicConfig(level=env.log_level.upper())

    # Silence HuggingFace / httpx chatter.
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    for noisy in ("httpx", "sentence_transformers", "huggingface_hub",
                  "urllib3", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    p = argparse.ArgumentParser(prog="deli-rag")
    sub = p.add_subparsers(dest="cmd", required=True)

    # --- read-only utilities ---
    sub.add_parser("models", help="validate Groq model IDs against live endpoint")

    p_inspect = sub.add_parser("inspect", help="parse a file and dump structure as JSON")
    p_inspect.add_argument("file", type=Path)
    p_inspect.add_argument("--compact", action="store_true",
                           help="one-line JSON instead of pretty-printed")

    # --- writers ---
    p_ingest = sub.add_parser("ingest", help="parse a file and write it to documents/chunks")
    p_ingest.add_argument("file", type=Path)
    p_ingest.add_argument("--acl", default=None,
                          choices=["public", "internal", "confidential"],
                          help="override the default ACL level")

    p_load = sub.add_parser("load", help="parse a file and load numeric tables into Postgres")
    p_load.add_argument("file", type=Path)

    p_index = sub.add_parser("index", help="embed all chunks lacking an embedding")
    p_index.add_argument("--doc-id", action="append", default=None,
                         help="restrict to a specific doc_id (repeatable)")

    p_query = sub.add_parser("query", help="retrieval-only: show top chunks for a query")
    p_query.add_argument("text", type=str)
    p_query.add_argument("--k", type=int, default=None, help="number of chunks to return")
    p_query.add_argument("--acl", default="internal",
                         choices=["public", "internal", "confidential"],
                         help="requesting user's ACL level")

    p_trace = sub.add_parser("trace", help="show each pipeline stage's decision for a query")
    p_trace.add_argument("text", type=str)
    p_trace.add_argument("--acl", default="internal",
                         choices=["public", "internal", "confidential"])
    p_trace.add_argument("--k", type=int, default=8)
    p_trace.add_argument("--rerank", action="store_true", default=False)

    p_eval = sub.add_parser("eval", help="run the golden-set eval harness")
    p_eval.add_argument("--golden", type=Path,
                        default=Path("eval/golden/phase2_v1.yaml"))
    p_eval.add_argument("--rerank", action="store_true", default=False,
                        help="enable cross-encoder reranker")
    p_eval.add_argument("--k", type=int, default=8)

    p_ask = sub.add_parser("ask", help="end-to-end RAG: retrieve, generate, cite")
    p_ask.add_argument("text", type=str)
    p_ask.add_argument("--acl", default="internal",
                       choices=["public", "internal", "confidential"])
    p_ask.add_argument("--k", type=int, default=8)
    p_ask.add_argument("--rerank", action="store_true", default=False)
    p_ask.add_argument("--trace", action="store_true", default=False,
                       help="show pipeline stages (understand/transform/route)")

    args = p.parse_args()

    if args.cmd == "models":
        enabled = validate_and_filter_llms()
        print("Enabled LLMs:", enabled or "(none — check GROQ_API_KEY)")
        return 0

    if args.cmd == "inspect":
        if not args.file.exists():
            print(f"Not found: {args.file}", file=sys.stderr)
            return 2
        parser = get_parser_for(args.file)
        doc = parser.parse(args.file)
        payload = doc.model_dump()
        print(json.dumps(payload, indent=None if args.compact else 2, default=str))
        return 0

    if args.cmd == "ingest":
        if not args.file.exists():
            print(f"Not found: {args.file}", file=sys.stderr)
            return 2
        from deli_rag.db.writer import DocumentWriter, existing_versions, session_scope
        from deli_rag.ingestion.chunker import Chunker
        from deli_rag.ingestion.dedup import decide
        from deli_rag.ingestion.metadata import build_document

        parser = get_parser_for(args.file)
        parsed = parser.parse(args.file)
        doc = build_document(path=args.file, parsed=parsed, acl_level=args.acl)

        session = session_scope()
        try:
            prior = existing_versions(session, doc.doc_id)
            decision = decide(candidate=doc, existing_versions=prior)
            if decision.decision == "skip_identical":
                print(f"Skipped (identical to v{decision.doc_version}): {args.file.name}")
                return 0
            doc.doc_version = decision.doc_version
            chunks = Chunker().chunk(parsed, doc_id=doc.doc_id, doc_title=args.file.stem)
            DocumentWriter(session).write_document(
                doc=doc, chunks=chunks, supersedes_doc_id=decision.supersedes_doc_id,
            )
            session.commit()
            print(f"Ingested: doc_id={doc.doc_id} v{doc.doc_version} "
                  f"({len(chunks)} chunks) [{decision.decision}]")
        finally:
            session.close()
        return 0

    if args.cmd == "load":
        if not args.file.exists():
            print(f"Not found: {args.file}", file=sys.stderr)
            return 2
        from deli_rag.db.writer import session_scope
        from deli_rag.structured.loaders import StructuredLoader
        parser = get_parser_for(args.file)
        parsed = parser.parse(args.file)
        session = session_scope()
        try:
            loader = StructuredLoader(session)
            counts = loader.load(parsed)
            session.commit()
            print(f"Loaded rows into: {counts}")
        finally:
            session.close()
        return 0

    if args.cmd == "index":
        from deli_rag.db.writer import session_scope
        from deli_rag.embeddings.base import get_embedder
        from deli_rag.embeddings.indexer import Indexer
        embedder = get_embedder()
        session = session_scope()
        try:
            indexer = Indexer(session, embedder)
            report = indexer.index_all(doc_ids=args.doc_id)
            session.commit()
            print(f"Indexed: {report.chunks_embedded} / {report.chunks_scanned} chunks "
                  f"(~{report.tokens_estimated} tokens)")
        finally:
            session.close()
        return 0

    if args.cmd == "query":
        from deli_rag.db.writer import session_scope
        from deli_rag.embeddings.base import get_embedder
        from deli_rag.retrieval.hybrid import HybridRetriever
        from deli_rag.schemas import Filters

        acl_levels = (["public"] if args.acl == "public"
                      else ["public", "internal"] if args.acl == "internal"
                      else ["public", "internal", "confidential"])
        filters = Filters(acl_levels=acl_levels, tenant="default")

        session = session_scope()
        try:
            embedder = get_embedder()
            retriever = HybridRetriever(session, embedder)
            result = retriever.search(args.text, filters=filters, k=args.k)
        finally:
            session.close()

        print(f"Query: {args.text!r}")
        print(f"Candidates: dense={result.dense_candidates} "
              f"keyword={result.keyword_candidates} "
              f"fused={result.fused_candidates}")
        print("-" * 78)
        for i, c in enumerate(result.chunks, start=1):
            score = c.rrf_score or 0
            header = f"[{i}] {c.filename or c.doc_id} p.{c.page or '?'} — {c.section or '(no section)'}"
            print(header)
            print(f"    rrf={score:.4f}  dense={c.dense_score}  keyword={c.keyword_score}")
            body = (c.text[:300] + "...") if len(c.text) > 300 else c.text
            print(f"    {body.replace(chr(10), ' / ')}")
            print()
        return 0

    if args.cmd == "trace":
        from deli_rag.agent.pipeline import Pipeline
        from deli_rag.db.writer import session_scope
        from deli_rag.embeddings.base import get_embedder
        from deli_rag.reranking.base import get_reranker
        from deli_rag.schemas import Filters

        acl_levels = (["public"] if args.acl == "public"
                      else ["public", "internal"] if args.acl == "internal"
                      else ["public", "internal", "confidential"])
        filters = Filters(acl_levels=acl_levels, tenant="default")

        session = session_scope()
        try:
            embedder = get_embedder()
            reranker = get_reranker() if args.rerank else None
            pipe = Pipeline(session, embedder, reranker=reranker)
            result = pipe.run(args.text, filters=filters, k=args.k)
        finally:
            session.close()

        print(f"Query: {args.text!r}")
        print("=" * 78)
        for line in result.trace:
            print(" ", line)
        print("=" * 78)
        print(f"Doc chunks: {len(result.doc_chunks)}")
        for i, c in enumerate(result.doc_chunks, start=1):
            print(f"  [{i}] {c.filename or c.doc_id} p.{c.page or '?'} "
                  f"rrf={c.rrf_score} rk={c.rerank_score}")
        print(f"SQL evidence blocks: {len(result.sql_evidence)}")
        for ev in result.sql_evidence:
            print(f"  - {ev.kind}: {ev.summary}")
        return 0

    if args.cmd == "eval":
        from deli_rag.db.writer import session_scope
        from deli_rag.embeddings.base import get_embedder
        from deli_rag.eval.golden import load_golden_set
        from deli_rag.eval.runner import run_eval
        from deli_rag.reranking.base import get_reranker

        golden = load_golden_set(args.golden)
        session = session_scope()
        try:
            embedder = get_embedder()
            reranker = get_reranker() if args.rerank else None
            report = run_eval(session, embedder, golden, reranker=reranker, k=args.k)
        finally:
            session.close()

        print(f"Golden set: {args.golden} ({len(report.items)} items)")
        print(f"Reranker: {'on' if report.reranker_used else 'off'}")
        print("-" * 60)
        for item in report.items:
            print(f"  {item.id:30s}  recall@5={item.recall_at_5:.2f}  "
                  f"rr={item.rr:.2f}  ndcg@5={item.ndcg_at_5:.2f}  "
                  f"{item.latency_ms:6.1f}ms")
        print("-" * 60)
        for k, v in report.to_dict().items():
            print(f"  {k}: {v}")
        return 0 if report.recall_at_5 >= 0.5 else 1

    if args.cmd == "ask":
        from deli_rag.agent.ask import Asker
        from deli_rag.db.writer import session_scope
        from deli_rag.embeddings.base import get_embedder
        from deli_rag.reranking.base import get_reranker
        from deli_rag.schemas import Filters

        acl_levels = (["public"] if args.acl == "public"
                      else ["public", "internal"] if args.acl == "internal"
                      else ["public", "internal", "confidential"])
        filters = Filters(acl_levels=acl_levels, tenant="default")

        session = session_scope()
        try:
            embedder = get_embedder()
            reranker = get_reranker() if args.rerank else None
            asker = Asker(session, embedder, reranker=reranker)
            result = asker.ask(args.text, filters=filters, k=args.k)
        finally:
            session.close()

        if args.trace and result.pipeline:
            print("--- pipeline trace ---")
            for line in result.pipeline.trace:
                print(" ", line)
            print()

        a = result.answer
        if a.abstained:
            print(f"[abstained] {a.reason or 'no answer'}")
            return 1

        print(f"Answer: {a.answer}")
        if a.citations:
            print()
            print("Citations:")
            for c in result.citations:
                if c.kind == "doc":
                    bits = [f"[{c.id}]", c.filename or c.chunk_id or "?"]
                    if c.page:
                        bits.append(f"p.{c.page}")
                    if c.section:
                        bits.append(f"· {c.section}")
                    print("  " + " ".join(str(b) for b in bits))
                else:
                    print(f"  [{c.id}] SQL — {c.sql_kind}: {c.sql_summary}")
        if a.assumptions:
            print()
            print("Assumptions:")
            for x in a.assumptions:
                print(f"  - {x}")
        print()
        print(f"Confidence: {a.confidence:.2f}")
        if result.llm:
            print(f"Model: {result.llm.model_used}"
                  + ("  (fallback)" if result.llm.fallback_used else ""))
        if result.validation and not result.validation.ok:
            print(f"Validation issues: {result.validation.issues}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
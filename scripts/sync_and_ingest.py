import shutil
from pathlib import Path
import logging

# Import your existing pipeline components
from deli_rag.ingestion.parsers import get_parser_for
from deli_rag.db.writer import DocumentWriter, session_scope
from deli_rag.ingestion.chunker import Chunker
from deli_rag.ingestion.dedup import decide
from deli_rag.ingestion.metadata import build_document
from deli_rag.embeddings.base import get_embedder
from deli_rag.embeddings.indexer import Indexer
from deli_rag.structured.loaders import StructuredLoader

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger(__name__)

INBOX_DIR = Path("inbox")
ARCHIVE_DIR = Path("archive")


def process_inbox():
    """Scans the inbox, ingests new files, and moves them to archive."""
    if not INBOX_DIR.exists():
        log.info("Inbox folder is empty.")
        return

    files = [f for f in INBOX_DIR.iterdir() if f.is_file()]
    if not files:
        log.info("No new files to ingest.")
        return

    ARCHIVE_DIR.mkdir(exist_ok=True)

    session = session_scope()
    embedder = get_embedder()

    try:
        for file_path in files:
            log.info(f"Processing: {file_path.name}")

            try:
                # 1. Parse the file
                parser = get_parser_for(file_path)
                parsed = parser.parse(file_path)

                # 2. Load structured data (Sales/Inventory/RIA) into SQL tables
                if parsed.tables:
                    loader = StructuredLoader(session)
                    counts = loader.load(parsed)
                    if counts:
                        log.info(f"  -> Loaded SQL rows: {counts}")

                # 3. Build document + chunk for RAG (Doc search)
                doc = build_document(path=file_path, parsed=parsed, acl_level="internal")

                from deli_rag.db.writer import existing_versions
                prior = existing_versions(session, doc.doc_id)
                decision = decide(candidate=doc, existing_versions=prior)

                if decision.decision == "skip_identical":
                    log.info(f"  -> Skipped (identical to v{decision.doc_version})")
                else:
                    doc.doc_version = decision.doc_version
                    chunks = Chunker().chunk(parsed, doc_id=doc.doc_id, doc_title=file_path.stem)

                    # Write to DB
                    DocumentWriter(session).write_document(
                        doc=doc, chunks=chunks, supersedes_doc_id=decision.supersedes_doc_id
                    )
                    session.commit()
                    log.info(f"  -> Ingested document ({len(chunks)} chunks)")

                    # 4. Embed the new chunks
                    indexer = Indexer(session, embedder)
                    report = indexer.index_all(doc_ids=[doc.doc_id])
                    session.commit()
                    log.info(f"  -> Embedded {report.chunks_embedded} chunks")

                # 5. Move to archive
                shutil.move(str(file_path), str(ARCHIVE_DIR / file_path.name))
                log.info(f"  -> Moved to archive.")

            except Exception as e:
                log.error(f"  -> FAILED: {e}")

    finally:
        session.close()


if __name__ == "__main__":
    process_inbox()
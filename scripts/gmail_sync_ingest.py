from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add the scripts folder to sys.path so we can import sync_and_ingest
sys.path.insert(0, str(Path(__file__).parent))
# Add src to sys.path so we can import deli_rag
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import the downloader and the ingestion pipeline
from deli_rag.ingestion.sources.gmail_source import run_daily_sync, INBOX_DIR
from sync_and_ingest import process_inbox

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("gmail_sync_ingest")


def main():
    log.info("=== Starting Gmail Sync ===")

    # 1. Download files from Gmail into the INBOX_DIR
    run_daily_sync()

    # 2. Check if we got any files
    if not INBOX_DIR.exists():
        log.error(f"Inbox folder not found: {INBOX_DIR}")
        return

    downloaded = [f for f in INBOX_DIR.iterdir() if f.is_file()]
    if not downloaded:
        log.info("No new files downloaded from Gmail. Exiting.")
        return

    log.info(f"Found {len(downloaded)} files in inbox. Handing off to ingestion pipeline...")

    # 3. Hand off to your existing pipeline!
    # process_inbox() will parse, chunk, embed, load SQL, and move to archive
    process_inbox()

    log.info("=== Gmail sync and ingestion complete! ===")


if __name__ == "__main__":
    main()
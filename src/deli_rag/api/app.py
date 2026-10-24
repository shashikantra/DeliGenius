from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .middleware import AccessLogMiddleware, ErrorHandlingMiddleware, RequestIDMiddleware
from .routes import router

from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from deli_rag.ingestion.sources.gmail_source import run_daily_sync
import logging

log = logging.getLogger("deli_rag.api")


# ... existing imports ...

def create_app() -> FastAPI:
    # ... existing setup ...

    # 1. Create the scheduler
    scheduler = BackgroundScheduler()

    # 2. Add the daily job at Midnight (00:00)
    scheduler.add_job(run_daily_sync, 'cron', hour=0, minute=0)
    scheduler.start()
    log.info("Gmail daily sync scheduler started.")

    # 3. Define lifespan to shut down scheduler gracefully
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        scheduler.shutdown()
        log.info("Scheduler shut down.")

    # 4. Recreate the app with the lifespan (replace the existing FastAPI instance)
    app = FastAPI(
        title="DeliGenius RAG API",
        version="0.1.0",
        description="Evidence-first RAG agent for Deli & Grocery.",
        lifespan=lifespan,
    )

def create_app() -> FastAPI:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = FastAPI(
        title="DeliGenius RAG API",
        version="0.1.0",
        description="Evidence-first RAG agent for Deli & Grocery.",
    )

    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app


app = create_app()
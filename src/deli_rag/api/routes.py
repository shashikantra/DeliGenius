from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from sqlalchemy import text
from sse_starlette.sse import EventSourceResponse

from deli_rag.agent.agent import Agent
from deli_rag.config.settings import get_config, get_env
from deli_rag.db.writer import session_scope
from deli_rag.db.models import AuditLogRow
from deli_rag.embeddings.base import get_embedder
from deli_rag.reranking.base import get_reranker
from deli_rag.schemas import Filters

from pathlib import Path

from deli_rag.db.models import DocumentRow, ChunkRow
from sqlalchemy import func, select

from .models import (
    AskRequest, AskResponse, CitationOut,
    FeedbackRequest, FeedbackResponse,
    ModelInfo, ModelsResponse,
    HealthResponse,
    DebugInfo, AskResponseWithDebug, DocumentOut, DocumentsResponse,
    DocumentDetailResponse, ChunkOut, FeedbackOut, FeedbackListResponse,
)

log = logging.getLogger("deli_rag.api.routes")
router = APIRouter()

# ---- Documents ----

@router.get("/documents", response_model=DocumentsResponse)
async def list_documents(request: Request) -> DocumentsResponse:
    rid = getattr(request.state, "request_id", "unknown")
    session = session_scope()
    try:
        # one query for documents + a join for chunk counts
        stmt = (
            select(
                DocumentRow.doc_id,
                DocumentRow.doc_version,
                DocumentRow.filename,
                DocumentRow.doc_type,
                DocumentRow.mime,
                DocumentRow.acl_level,
                DocumentRow.superseded_by,
                DocumentRow.source_ref,
                DocumentRow.created_at,
                func.count(ChunkRow.chunk_id).label("chunk_count"),
            )
            .outerjoin(ChunkRow, ChunkRow.doc_pk == DocumentRow.id)
            .group_by(DocumentRow.id)
            .order_by(DocumentRow.created_at.desc())
        )
        rows = session.execute(stmt).all()
    finally:
        session.close()

    docs = []
    for r in rows:
        size_bytes = 0
        try:
            p = Path(r.source_ref)
            if p.exists():
                size_bytes = p.stat().st_size
        except Exception:
            pass
        docs.append(DocumentOut(
            doc_id=r.doc_id,
            doc_version=r.doc_version,
            filename=r.filename,
            doc_type=r.doc_type,
            mime=r.mime,
            acl_level=r.acl_level,
            chunk_count=r.chunk_count or 0,
            superseded_by=r.superseded_by,
            created_at=r.created_at.isoformat() if r.created_at else "",
            size_bytes=size_bytes,
        ))
    return DocumentsResponse(documents=docs, total=len(docs))


@router.get("/documents/{doc_id}", response_model=DocumentDetailResponse)
async def get_document(doc_id: str, request: Request) -> DocumentDetailResponse:
    rid = getattr(request.state, "request_id", "unknown")
    session = session_scope()
    try:
        stmt = (
            select(
                DocumentRow.doc_id,
                DocumentRow.doc_version,
                DocumentRow.filename,
                DocumentRow.doc_type,
                DocumentRow.mime,
                DocumentRow.acl_level,
                DocumentRow.superseded_by,
                DocumentRow.source_ref,
                DocumentRow.created_at,
                DocumentRow.id,
            )
            .where(DocumentRow.doc_id == doc_id)
            .order_by(DocumentRow.doc_version.desc())
            .limit(1)
        )
        doc_row = session.execute(stmt).first()
        if doc_row is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=f"document {doc_id!r} not found")

        chunk_stmt = (
            select(ChunkRow)
            .where(ChunkRow.doc_pk == doc_row.id)
            .order_by(ChunkRow.parent_id.asc().nullsfirst(), ChunkRow.chunk_id)
        )
        chunk_rows = session.execute(chunk_stmt).scalars().all()
    finally:
        session.close()

    size_bytes = 0
    try:
        p = Path(doc_row.source_ref)
        if p.exists():
            size_bytes = p.stat().st_size
    except Exception:
        pass

    doc_out = DocumentOut(
        doc_id=doc_row.doc_id,
        doc_version=doc_row.doc_version,
        filename=doc_row.filename,
        doc_type=doc_row.doc_type,
        mime=doc_row.mime,
        acl_level=doc_row.acl_level,
        chunk_count=len(chunk_rows),
        superseded_by=doc_row.superseded_by,
        created_at=doc_row.created_at.isoformat() if doc_row.created_at else "",
        size_bytes=size_bytes,
    )
    chunks_out = [
        ChunkOut(
            chunk_id=c.chunk_id,
            parent_id=c.parent_id,
            page=c.page,
            section=c.section,
            text=c.text,
            token_count=c.token_count,
            is_table=c.is_table,
            context_line=c.context_line or "",
        )
        for c in chunk_rows
    ]
    return DocumentDetailResponse(
        document=doc_out,
        chunks=chunks_out,
        total_chunks=len(chunks_out),
    )


# ---- Feedback history ----

@router.get("/feedback/recent", response_model=FeedbackListResponse)
async def recent_feedback(request: Request, limit: int = 20) -> FeedbackListResponse:
    limit = max(1, min(limit, 200))
    session = session_scope()
    try:
        stmt = (
            select(AuditLogRow)
            .where(AuditLogRow.action.in_(["feedback_up", "feedback_down"]))
            .order_by(AuditLogRow.created_at.desc())
            .limit(limit)
        )
        rows = session.execute(stmt).scalars().all()
    finally:
        session.close()

    items = []
    for r in rows:
        d = r.detail or {}
        items.append(FeedbackOut(
            request_id=r.request_id or "",
            vote="up" if r.action == "feedback_up" else "down",
            question=d.get("question", ""),
            answer=d.get("answer", ""),
            comment=d.get("comment"),
            created_at=r.created_at.isoformat() if r.created_at else "",
        ))
    return FeedbackListResponse(feedback=items, total=len(items))

def _acl_levels(acl: str) -> list[str]:
    return (
        ["public"] if acl == "public"
        else ["public", "internal"] if acl == "internal"
        else ["public", "internal", "confidential"]
    )


@router.post("/ask", response_model=AskResponseWithDebug)
async def ask(req: AskRequest, request: Request, debug: bool = False) -> AskResponseWithDebug:
    rid = getattr(request.state, "request_id", "unknown")
    filters = Filters(acl_levels=_acl_levels(req.acl), tenant="default")

    session = session_scope()
    try:
        embedder = get_embedder()
        reranker = get_reranker() if req.rerank else None
        agent = Agent(session, embedder, reranker=reranker)
        result = agent.ask(
            req.question,
            filters=filters,
            history=req.history or None,
            k=req.k,
            prefer_local=req.model.startswith("ollama:") if req.model else False  # <--- ADDED THIS
        )
        print(f"🟢 [ROUTE] Agent returned: abstained={result.final.answer.abstained}")  # <--- ADD

        chunk_ids = []
        if result.final.pipeline and result.final.pipeline.doc_chunks:
            chunk_ids = [c.chunk_id for c in result.final.pipeline.doc_chunks]

        session.add(AuditLogRow(
            request_id=rid,
            actor="anonymous",
            action="ask",
            doc_id=None,
            chunk_ids=chunk_ids,
            detail={
                "question": req.question,
                "acl": req.acl,
                "k": req.k,
                "iterations": result.iterations_used,
                "abstained": result.final.answer.abstained,
                "confidence": result.final.answer.confidence,
                "model_used": result.final.llm.model_used if result.final.llm else None,
            },
        ))
        session.commit()
    finally:
        session.close()

    answer = result.final.answer
    citations = [
        CitationOut(
            id=c.id, kind=c.kind,
            chunk_id=c.chunk_id, filename=c.filename,
            page=c.page, section=c.section,
            sql_kind=c.sql_kind, sql_summary=c.sql_summary,
            sql_query=c.sql_query,  # <--- ADD THIS
            sql_data=c.sql_data,    # <--- ADD THIS
        )
        for c in result.final.citations
    ]
    debug_info = None
    if debug:
        from .models import DebugInfo
        debug_info = DebugInfo(
            trace=result.final.pipeline.trace if result.final.pipeline else [],
            iterations_used=result.iterations_used,
            elapsed_s=result.elapsed_s,
        )

    return AskResponseWithDebug(
        request_id=rid,
        answer=answer.answer,
        citations=citations,
        confidence=answer.confidence,
        abstained=answer.abstained,
        needs_clarification=answer.needs_clarification,
        assumptions=answer.assumptions,
        reason=answer.reason,
        model_used=result.final.llm.model_used if result.final.llm else None,
        iterations_used=result.iterations_used,
        elapsed_s=result.elapsed_s,
        debug=debug_info,
    )


@router.post("/ask/stream")
async def ask_stream(req: AskRequest, request: Request) -> EventSourceResponse:
    rid = getattr(request.state, "request_id", "unknown")

    async def gen():
        try:
            yield {"event": "start", "data": json.dumps({"request_id": rid})}
            body = await ask(req, request)
            text = body.answer
            chunk_size = max(1, len(text) // 8)
            for i in range(0, len(text), chunk_size):
                yield {"event": "token",
                       "data": json.dumps({"text": text[i:i + chunk_size]})}
            yield {"event": "final", "data": body.model_dump_json()}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"detail": str(e)})}

    return EventSourceResponse(gen())


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(req: FeedbackRequest, request: Request) -> FeedbackResponse:
    rid = getattr(request.state, "request_id", "unknown")
    session = session_scope()
    try:
        session.add(AuditLogRow(
            request_id=req.request_id,
            actor="anonymous",
            action=f"feedback_{req.vote}",
            doc_id=None,
            chunk_ids=[],
            detail={
                "question": req.question,
                "answer": req.answer,
                "vote": req.vote,
                "comment": req.comment,
                "client_request_id": rid,
            },
        ))
        session.commit()
    finally:
        session.close()
    return FeedbackResponse(ok=True, request_id=rid)


@router.get("/models", response_model=ModelsResponse)
async def models(request: Request) -> ModelsResponse:
    cfg = get_config().llm
    entries: list[ModelInfo] = []

    # 1. Add Groq models
    for entry, is_primary in [
        (cfg.primary, True),
        (cfg.fallback_1, False),
        (cfg.fallback_2, False),
    ]:
        entries.append(ModelInfo(id=entry.id, primary=is_primary, verified=entry.verified))

    # 2. Add Ollama model if configured
    ollama_cfg = getattr(cfg, "ollama", None)
    if ollama_cfg and getattr(ollama_cfg, "id", None):
        entries.append(ModelInfo(
            id=f"ollama:{ollama_cfg.id}",
            primary=False,
            verified=True
        ))

    return ModelsResponse(models=entries)

@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    rid = getattr(request.state, "request_id", "unknown")

    db_ok = False
    try:
        s = session_scope()
        try:
            s.execute(text("SELECT 1"))
            db_ok = True
        finally:
            s.close()
    except Exception:
        db_ok = False

    groq_ok = bool(get_env().groq_api_key)

    embedder_loaded = True
    try:
        get_embedder()
    except Exception:
        embedder_loaded = False

    status = "ok" if (db_ok and groq_ok and embedder_loaded) else "degraded"
    return HealthResponse(
        status=status,
        db=db_ok,
        groq=groq_ok,
        embedder_loaded=embedder_loaded,
        request_id=rid,
    )


@router.get("/chunks/{chunk_id}")
async def get_chunk(chunk_id: str, request: Request):
    from fastapi import HTTPException
    session = session_scope()
    try:
        stmt = select(ChunkRow).where(ChunkRow.chunk_id == chunk_id)
        chunk = session.execute(stmt).scalars().first()
        if chunk is None:
            raise HTTPException(status_code=404, detail="Chunk not found")

        return {
            "chunk_id": chunk.chunk_id,
            "doc_id": chunk.doc_id,
            "page": chunk.page,
            "section": chunk.section,
            "text": chunk.text,
            "context_line": chunk.context_line,
            "is_table": chunk.is_table,
        }
    finally:
        session.close()
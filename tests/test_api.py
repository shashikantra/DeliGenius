from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from deli_rag.config.settings import get_env


@pytest.fixture(scope="module")
def client():
    from deli_rag.api.app import app
    try:
        engine = create_engine(get_env().database_url, future=True)
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:
        pytest.skip(f"Postgres not reachable: {e}")
    return TestClient(app)


def test_health_returns_status(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body
    assert "db" in body
    assert "groq" in body
    assert "request_id" in body
    assert r.headers["X-Request-ID"] == body["request_id"]


def test_models_returns_list(client):
    r = client.get("/models")
    assert r.status_code == 200
    body = r.json()
    assert "models" in body
    assert any(m["primary"] for m in body["models"])


def test_feedback_requires_request_id(client):
    r = client.post("/feedback", json={
        "request_id": "test-rid-1",
        "question": "test q",
        "answer": "test a",
        "vote": "up",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True


def test_ask_validation_rejects_empty_question(client):
    r = client.post("/ask", json={"question": ""})
    assert r.status_code == 422


def test_ask_end_to_end_optional(client):
    if not os.getenv("GROQ_API_KEY") and not get_env().groq_api_key:
        pytest.skip("no GROQ_API_KEY")
    engine = create_engine(get_env().database_url, future=True)
    with engine.connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM embeddings")).scalar()
    if n == 0:
        pytest.skip("no embeddings")

    r = client.post("/ask", json={
        "question": "what was our RIA commission for May 2026?",
        "acl": "internal",
        "k": 8,
    })
    assert r.status_code == 200
    body = r.json()
    assert "request_id" in body
    assert body["abstained"] is False
    assert "216.56" in body["answer"]
    assert len(body["citations"]) > 0

def test_documents_list(client):
    r = client.get("/documents")
    assert r.status_code == 200
    body = r.json()
    assert "documents" in body
    assert body["total"] >= 0
    if body["total"] > 0:
        doc = body["documents"][0]
        for key in ("doc_id", "filename", "doc_type", "acl_level", "chunk_count"):
            assert key in doc


def test_document_detail_or_404(client):
    r = client.get("/documents/does_not_exist_at_all")
    assert r.status_code == 404

    # If we have any real document, fetch its detail
    r2 = client.get("/documents")
    docs = r2.json()["documents"]
    if not docs:
        pytest.skip("no documents ingested")
    doc_id = docs[0]["doc_id"]
    r3 = client.get(f"/documents/{doc_id}")
    assert r3.status_code == 200
    body = r3.json()
    assert body["document"]["doc_id"] == doc_id
    assert isinstance(body["chunks"], list)
    assert body["total_chunks"] == len(body["chunks"])


def test_ask_with_debug_flag(client):
    if not os.getenv("GROQ_API_KEY") and not get_env().groq_api_key:
        pytest.skip("no GROQ_API_KEY")
    engine = create_engine(get_env().database_url, future=True)
    with engine.connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM embeddings")).scalar()
    if n == 0:
        pytest.skip("no embeddings")

    r = client.post(
        "/ask?debug=true",
        json={"question": "what is the refund policy?", "acl": "internal", "k": 4},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("debug") is not None
    assert isinstance(body["debug"]["trace"], list)
    assert len(body["debug"]["trace"]) >= 1
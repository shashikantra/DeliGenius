from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from deli_rag.config.settings import get_env


@pytest.fixture(scope="module")
def session():
    try:
        engine = create_engine(get_env().database_url, future=True)
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:
        pytest.skip(f"Postgres not reachable: {e}")
        return   # ← ensures engine is unbound only after skip
    s = Session(engine)
    yield s
    s.close()


def test_ask_end_to_end(session):
    if session.execute(text("SELECT COUNT(*) FROM embeddings")).scalar() == 0:
        pytest.skip("no embeddings")
    if session.execute(text("SELECT COUNT(*) FROM ria_daily_summary")).scalar() == 0:
        pytest.skip("ria_daily_summary is empty")
    import os
    if not os.getenv("GROQ_API_KEY") and not get_env().groq_api_key:
        pytest.skip("GROQ_API_KEY not set")

    from deli_rag.agent.ask import Asker
    from deli_rag.embeddings.base import get_embedder
    from deli_rag.schemas import Filters

    asker = Asker(session, get_embedder())
    result = asker.ask(
        "what was our RIA commission paid for May 2026?",
        filters=Filters(acl_levels=["public", "internal"], tenant="default"),
        k=8,
    )
    a = result.answer
    assert a.abstained is False, f"unexpected abstain: {a.reason}"
    assert a.confidence >= 0.5
    assert "216.56" in a.answer
    assert result.citations, "expected at least one citation"


def test_ask_abstains_on_empty_evidence(session):
    if session.execute(text("SELECT COUNT(*) FROM chunks WHERE acl_level='public'")).scalar() > 0:
        pytest.skip("public chunks exist; can't force empty")
    from deli_rag.agent.ask import Asker
    from deli_rag.embeddings.base import get_embedder
    from deli_rag.schemas import Filters

    asker = Asker(session, get_embedder())
    result = asker.ask(
        "anything",
        filters=Filters(acl_levels=["public"], tenant="default"),
        k=4,
    )
    assert result.answer.abstained is True
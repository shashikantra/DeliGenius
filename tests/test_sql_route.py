from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from deli_rag.agent.sql_route import SqlRoute
from deli_rag.config.settings import get_env
from deli_rag.schemas.query import Entities


@pytest.fixture(scope="module")
def session():
    try:
        engine = create_engine(get_env().database_url, future=True)
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:
        pytest.skip(f"Postgres not reachable: {e}")
    s = Session(engine)
    yield s
    s.close()


def _has(session, table: str) -> bool:
    return session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() > 0


def test_reorder_candidates_runs(session):
    if not _has(session, "inventory_snapshot"):
        pytest.skip("inventory_snapshot is empty")
    ev = SqlRoute(session).run("reorder_candidates", Entities())
    assert ev is not None
    assert ev.columns[0] == "upc"
    assert "reorder" in ev.summary.lower()


def test_ria_summary_returns_overview(session):
    if not _has(session, "ria_daily_summary"):
        pytest.skip("ria_daily_summary is empty")
    ev = SqlRoute(session).run("ria_summary", Entities())
    assert ev is not None
    labels = [row[0] for row in ev.rows]
    assert any("Previous Balance" in str(l).title() or "Previous Balance" in str(l)
               for l in labels)


def test_sales_by_category(session):
    if not _has(session, "sales_daily"):
        pytest.skip("sales_daily is empty")
    ev = SqlRoute(session).run("sales_by_category", Entities())
    assert ev is not None
    assert ev.columns == ["category", "total_qty", "total_amount"]


def test_sql_route_returns_none_for_unknown_kind(session):
    ev = SqlRoute(session).run("does_not_exist", Entities())
    assert ev is None


def test_sql_route_is_read_only(session):
    """Ensure no handler accidentally mutates. Run a handler and confirm row counts
    before/after are identical for a couple of tables."""
    before_sales = session.execute(text("SELECT COUNT(*) FROM sales_daily")).scalar()
    before_inv = session.execute(text("SELECT COUNT(*) FROM inventory_snapshot")).scalar()
    SqlRoute(session).run("reorder_candidates", Entities())
    SqlRoute(session).run("sales_by_category", Entities())
    after_sales = session.execute(text("SELECT COUNT(*) FROM sales_daily")).scalar()
    after_inv = session.execute(text("SELECT COUNT(*) FROM inventory_snapshot")).scalar()
    assert before_sales == after_sales
    assert before_inv == after_inv
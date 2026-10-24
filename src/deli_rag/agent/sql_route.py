from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from deli_rag.schemas.query import Entities


@dataclass
class SqlEvidence:
    """One row of evidence from a SQL query, formatted for the LLM prompt."""
    kind: str
    columns: list[str]
    rows: list[list[Any]]
    sql: str
    summary: str          # one-line human-readable description


class SqlRoute:
    """Read-only, allow-listed SQL handlers.

    Each handler:
    - takes the query's extracted entities
    - runs a parameterized query (never string-interpolated)
    - returns a SqlEvidence with a compact summary
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def run(self, kind: str, entities: Entities) -> SqlEvidence | None:
        handler = getattr(self, f"_handle_{kind}", None)
        if handler is None:
            return None
        return handler(entities)

    # --- handlers ---
    def _handle_total_sales(self, entities: Entities) -> SqlEvidence:
        """Calculates the total sales amount and quantity across all SKUs."""
        query = """
            SELECT 
                SUM(total_qty) as total_items_sold, 
                SUM(total_amount) as total_revenue
            FROM sales_daily
            WHERE kind = 'sku'
        """
        params = {}
        # Filter by date if mentioned
        if entities.dates:
            import re
            match = re.search(r'([A-Za-z]+)\s+(\d{1,2})', entities.dates[0])
            if match:
                month = match.group(1)[:3].capitalize()
                day = match.group(2)
                query += " AND source_file ILIKE :date_filter"
                params["date_filter"] = f"%{month}_{day}%"

        sql = text(query)
        rows = self.session.execute(sql, params).all()
        data = [list(r) for r in rows]

        # Format the numbers nicely for the LLM
        if data and data[0][0] is not None:
            data[0][0] = int(data[0][0])
            data[0][1] = f"${float(data[0][1]):,.2f}"
        else:
            data = [[0, "$0.00"]]

        return SqlEvidence(
            kind="total_sales",
            columns=["total_items_sold", "total_revenue"],
            rows=data,
            sql=str(sql),
            summary=f"Total revenue is {data[0][1]} across {data[0][0]} items."
        )

    def _handle_reorder_candidates(self, entities: Entities) -> SqlEvidence:
        sql = text("""
            SELECT upc, name, department, in_stock, predicted_days,
                   count_threshold, days_threshold
            FROM inventory_snapshot
            WHERE needs_reorder = TRUE
            ORDER BY in_stock ASC NULLS LAST, name
            LIMIT 10
        """)
        rows = self.session.execute(sql).all()
        data = [list(r) for r in rows]
        return SqlEvidence(
            kind="reorder_candidates",
            columns=["upc", "name", "department", "in_stock",
                     "predicted_days", "count_threshold", "days_threshold"],
            rows=data,
            sql=str(sql),
            summary=f"{len(data)} items currently flagged for reorder",
        )

    def _handle_inventory_for_sku(self, entities: Entities) -> SqlEvidence:
        upcs = entities.skus
        name_hint = entities.vendors[0] if entities.vendors else None

        # We will group by name to make the LLM's life easier
        query = """
            SELECT name, SUM(in_stock) as total_in_stock
            FROM inventory_snapshot
            WHERE 1=1
        """
        params = {}

        if upcs:
            query += " AND upc = ANY(:upcs)"
            params["upcs"] = upcs
        elif name_hint:
            query += " AND name ILIKE :hint"
            params["hint"] = f"%{name_hint}%"

        # Filter by date if mentioned
        if entities.dates:
            import re
            match = re.search(r'([A-Za-z]+)\s+(\d{1,2})', entities.dates[0])
            if match:
                month = match.group(1)[:3].capitalize()
                day = match.group(2)
                query += " AND source_file ILIKE :date_filter"
                params["date_filter"] = f"%{month}_{day}%"

        # Group by product name so the LLM gets a clean list
        query += " GROUP BY name ORDER BY name LIMIT 15"

        sql = text(query)
        rows = self.session.execute(sql, params).all()
        data = [list(r) for r in rows]

        return SqlEvidence(
            kind="inventory_for_sku",
            columns=["name", "total_in_stock"],
            rows=data,
            sql=str(sql),
            summary=f"{len(data)} inventory rows matched",
        )

    def _handle_sales_for_sku(self, entities: Entities) -> SqlEvidence:
        upcs = entities.skus
        name_hint = entities.vendors[0] if entities.vendors else None

        if upcs:
            sql = text("""
                SELECT upc, name, total_qty, total_amount
                FROM sales_daily
                WHERE kind = 'sku' AND upc = ANY(:upcs)
                ORDER BY total_amount DESC NULLS LAST
            """)
            rows = self.session.execute(sql, {"upcs": upcs}).all()
        elif name_hint:
            sql = text("""
                SELECT upc, name, total_qty, total_amount
                FROM sales_daily
                WHERE kind = 'sku' AND name ILIKE :hint
                ORDER BY total_amount DESC NULLS LAST
                LIMIT 10
            """)
            rows = self.session.execute(sql, {"hint": f"%{name_hint}%"}).all()
        else:
            # Fallback: If no specific item is mentioned, return the top 15 selling items overall
            sql = text("""
                SELECT upc, name, total_qty, total_amount
                FROM sales_daily
                WHERE kind = 'sku'
                ORDER BY total_amount DESC NULLS LAST
                LIMIT 10
            """)
            rows = self.session.execute(sql).all()

        data = [list(r) for r in rows]
        return SqlEvidence(
            kind="sales_for_sku",
            columns=["upc", "name", "total_qty", "total_amount"],
            rows=data, sql=str(sql),
            summary=f"{len(data)} sales rows matched",
        )
    def _handle_sales_by_category(self, entities: Entities) -> SqlEvidence:
        sql = text("""
            SELECT name AS category, total_qty, total_amount
            FROM sales_daily
            WHERE kind = 'category'
            ORDER BY total_amount DESC NULLS LAST
        """)
        rows = self.session.execute(sql).all()
        data = [list(r) for r in rows]
        return SqlEvidence(
            kind="sales_by_category",
            columns=["category", "total_qty", "total_amount"],
            rows=data, sql=str(sql),
            summary=f"{len(data)} category rows",
        )

    def _handle_ria_summary(self, entities: Entities) -> SqlEvidence:
        branch = entities.branches[0] if entities.branches else None
        if branch:
            sql = text("""
                SELECT label, value1, value2, value3
                FROM ria_daily_summary
                WHERE branch = :branch
                ORDER BY id
            """)
            rows = self.session.execute(sql, {"branch": branch}).all()
        else:
            sql = text("""
                SELECT label, value1, value2, value3
                FROM ria_daily_summary
                ORDER BY id
            """)
            rows = self.session.execute(sql).all()
        data = [list(r) for r in rows]
        return SqlEvidence(
            kind="ria_summary",
            columns=["label", "value1", "value2", "value3"],
            rows=data, sql=str(sql),
            summary=f"{len(data)} RIA summary rows",
        )

    def _handle_ria_transactions_for_ref(self, entities: Entities) -> SqlEvidence:
        sql = text("""
            SELECT txn_date, activity, ref_no, description,
                   amount, fee, tax, comm, running_balance
            FROM ria_transactions
            ORDER BY id
        """)
        rows = self.session.execute(sql).all()
        data = [list(r) for r in rows]
        return SqlEvidence(
            kind="ria_transactions_for_ref",
            columns=["txn_date", "activity", "ref_no", "description",
                     "amount", "fee", "tax", "comm", "running_balance"],
            rows=data, sql=str(sql),
            summary=f"{len(data)} RIA transaction rows",
        )

    def _handle_ria_commission(self, entities: Entities) -> SqlEvidence:
        sql = text("""
            SELECT SUM(comm) as total_commission
            FROM ria_transactions
            WHERE activity NOT ILIKE '%Total%' 
              AND activity NOT ILIKE '%Previous%'
        """)
        rows = self.session.execute(sql).all()
        data = [list(r) for r in rows]

        if data and data[0][0] is not None:
            # Make it a string with the label so the LLM understands
            data = [["Total Commission", f"${float(data[0][0]):,.2f}"]]
        else:
            data = [["Total Commission", "$0.00"]]

        return SqlEvidence(
            kind="ria_commission",
            columns=["metric", "amount"],  # Changed column names
            rows=data, sql=str(sql),
            summary=f"Total RIA commission is {data[0][1]}."
        )
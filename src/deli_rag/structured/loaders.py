from __future__ import annotations
from .cleaner import DataCleaner
from deli_rag.db.models import AuditLogRow

import hashlib
import re
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from deli_rag.ingestion.parsers.base import ParsedDocument, TableRecord
from deli_rag.structured.tables import (
    InventorySnapshotRow, RiaDailySummaryRow, RiaTransactionRow, SalesDailyRow,
)


# --- helpers ---

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def _to_float(s: str | None) -> float | None:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    s = s.replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(s: str | None) -> int | None:
    f = _to_float(s)
    return int(f) if f is not None else None


def _to_date(s: str | None) -> date | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _row_hash(*parts: str | None) -> str:
    h = hashlib.sha256()
    h.update("|".join(p or "" for p in parts).encode("utf-8"))
    return h.hexdigest()


def _extract_report_date(filename: str) -> date | None:
    """Parse a date out of a filename like Inventory_Status_Jun_21,_2026.csv."""
    # Try ISO first
    m = re.search(r"(\d{4})[-_](\d{1,2})[-_](\d{1,2})", filename)
    if m:
        y, mo, d = m.groups()
        try:
            return date(int(y), int(mo), int(d))
        except ValueError:
            pass
    # Try Mon_DD,_YYYY
    m = re.search(r"([A-Za-z]{3})[_\-,\s]+(\d{1,2})[,_\s]+(\d{4})", filename)
    if m:
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y")
            return dt.date()
        except ValueError:
            pass
    return None


# --- loaders ---
def _rowcount(result) -> int:
    """Return affected rows reliably across drivers, including ON CONFLICT DO NOTHING."""
    try:
        rows = result.fetchall()
        return len(rows)
    except Exception:
        rc = getattr(result, "rowcount", -1)
        return max(rc, 0)

class StructuredLoader:
    """Writes TableRecords from a ParsedDocument into the Track-2 tables.
    Idempotent: re-running on the same file inserts nothing new (row_hash UNIQUE).
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def load(self, parsed: ParsedDocument) -> dict[str, int]:
        counts: dict[str, int] = {}
        for rec in parsed.tables:
            n = self._route_record(rec, parsed.source_path)
            if n:
                counts[rec.name] = counts.get(rec.name, 0) + n
        self.session.flush()
        return counts

    def _route_record(self, rec: TableRecord, source_path: str) -> int:
        if rec.name == "sales_sku_rows":
            return self._load_sales(rec, source_path, kind="sku")
        if rec.name == "sales_category_totals":
            return self._load_sales(rec, source_path, kind="category")
        if rec.name == "ria_account_overview":
            return self._load_ria_summary(rec, source_path)
        if rec.name == "ria_transactions":
            return self._load_ria_transactions(rec, source_path)
        if rec.name == "ria_branch_summary":
            return self._load_ria_branch_summary(rec, source_path)

        if rec.name == "csv_table":
            # Look at the columns to decide if this is an inventory or sales file
            cols_lower = [c.lower().strip() for c in rec.columns]
            joined = " ".join(cols_lower)

            if "upc" in cols_lower and ("stock" in joined or "on_hand" in joined):
                return self._load_inventory(rec, source_path)

            # Detect Sales History CSV
            if ("upc" in cols_lower or "item" in cols_lower) and (
                    "qty" in joined or "total" in joined or "amount" in joined):
                return self._load_sales(rec, source_path, kind="sku")

            return 0

        return 0

    # --- per-table ---

    def _load_sales(self, rec: TableRecord, source_path: str, *, kind: str) -> int:
        report_date = _extract_report_date(Path(source_path).name)
        src = Path(source_path).name
        inserted = 0

        for row in rec.rows:
            raw_upc = row[0] if len(row) > 0 else None
            name = DataCleaner.clean_string(row[1] if len(row) > 1 else "Unknown")
            qty = DataCleaner.clean_int(row[2] if len(row) > 2 else None, 0)
            amount = DataCleaner.clean_number(row[3] if len(row) > 3 else None, 0.0)

            # Determine the actual kind (DECISIONS 11.2)
            if qty < 0:
                kind_actual = "refund"
            elif not raw_upc:
                kind_actual = "category"
                name = name or "General Category"
            else:
                kind_actual = kind

            if not raw_upc and not name:
                continue

            rh = _row_hash(raw_upc or "", name, str(qty), str(amount), kind_actual)
            stmt = pg_insert(SalesDailyRow).values(
                source_file=src, source_report_date=report_date, row_hash=rh,
                kind=kind_actual, upc=raw_upc if raw_upc else None, name=name,
                total_qty=qty, total_amount=amount,
            ).on_conflict_do_nothing(constraint="uq_sales_daily_row").returning(SalesDailyRow.id)
            result = self.session.execute(stmt)
            inserted += _rowcount(result)

        return inserted

    def _load_inventory(self, rec: TableRecord, source_path: str) -> int:
        snapshot_date = _extract_report_date(Path(source_path).name)
        src = Path(source_path).name

        # Group by UPC to handle duplicates (DECISIONS 11.2)
        grouped: dict[str, dict] = {}

        for row in rec.rows:
            raw_upc = row[0] if len(row) > 0 else None

            # Drop bad rows and log to audit_log
            if not DataCleaner.is_valid_upc(raw_upc):
                log.warning(f"Bad UPC dropped in {src}: {raw_upc}")
                self.session.add(AuditLogRow(
                    action="ingest_error",
                    detail={"file": src, "reason": "invalid_upc", "raw_row": row}
                ))
                continue

            upc = str(raw_upc).strip()
            name = DataCleaner.clean_string(row[1] if len(row) > 1 else "Unknown")
            dept = DataCleaner.clean_string(row[2] if len(row) > 2 else "General") or "General"

            in_stock = DataCleaner.clean_int(row[3] if len(row) > 3 else None, 0)
            predicted = DataCleaner.clean_int(row[4] if len(row) > 4 else None, 0)
            count_thresh = DataCleaner.clean_int(row[5] if len(row) > 5 else None, 10)
            days_thresh = DataCleaner.clean_int(row[6] if len(row) > 6 else None, 7)

            if upc in grouped:
                grouped[upc]["in_stock"] += in_stock
            else:
                grouped[upc] = {
                    "name": name, "dept": dept, "in_stock": in_stock,
                    "predicted": predicted, "count": count_thresh, "days": days_thresh
                }

        # Insert the cleaned, grouped data
        inserted = 0
        for upc, data in grouped.items():
            needs_reorder = (
                    (data["in_stock"] <= data["count"]) or
                    (data["predicted"] <= data["days"] and data["predicted"] > 0)
            )
            rh = _row_hash(upc, data["name"], data["dept"], str(data["in_stock"]))

            stmt = pg_insert(InventorySnapshotRow).values(
                source_file=src, snapshot_date=snapshot_date, row_hash=rh,
                upc=upc, name=data["name"], department=data["dept"],
                in_stock=data["in_stock"], predicted_days=data["predicted"],
                count_threshold=data["count"], days_threshold=data["days"],
                needs_reorder=needs_reorder,
            ).on_conflict_do_nothing(constraint="uq_inventory_row").returning(InventorySnapshotRow.id)

            result = self.session.execute(stmt)
            inserted += _rowcount(result)

        return inserted

    def _load_ria_summary(self, rec: TableRecord, source_path: str) -> int:
        src = Path(source_path).name
        # Try to pull branch/date from the filename
        m = re.search(r"\(([A-Z]{2}\d+)\)", src)
        branch = m.group(1) if m else "NJ2479"  # Fallback to known branch
        inserted = 0
        for row in rec.rows:
            label = (row[0] or "").strip()
            if not label:
                continue
            v1 = _to_float(row[1] if len(row) > 1 else None)
            v2 = _to_float(row[2] if len(row) > 2 else None)
            v3 = _to_float(row[3] if len(row) > 3 else None)
            rh = _row_hash(branch or "", label, str(v1), str(v2), str(v3))
            stmt = pg_insert(RiaDailySummaryRow).values(
                source_file=src, branch=branch, row_hash=rh, label=label,
                value1=v1, value2=v2, value3=v3,
            ).on_conflict_do_nothing(constraint="uq_ria_summary_row")
            result = self.session.execute(stmt)
            inserted += result.rowcount or 0
        return inserted

    def _load_ria_branch_summary(self, rec: TableRecord, source_path: str) -> int:
        """The branch summary table has columns:
        Branch, Date, Activity, Trnx Count, Amount, Fee, Tax, Comm, Debits, Credits, Running Balance.
        We flatten into ria_daily_summary rows keyed by (branch, activity) with two values."""
        src = Path(source_path).name
        inserted = 0
        cols = [c.lower().replace("\n", " ").strip() for c in rec.columns]
        try:
            idx_branch = cols.index("branch")
            idx_activity = cols.index("activity")
        except ValueError:
            return 0
        idx_amount = cols.index("amount") if "amount" in cols else None
        idx_fee = cols.index("fee") if "fee" in cols else None
        for row in rec.rows:
            if len(row) <= max(idx_branch, idx_activity):
                continue
            branch = (row[idx_branch] or "").strip()
            activity = (row[idx_activity] or "").strip()
            if not branch or not activity:
                continue
            amount = _to_float(row[idx_amount]) if idx_amount is not None and idx_amount < len(row) else None
            fee = _to_float(row[idx_fee]) if idx_fee is not None and idx_fee < len(row) else None
            label = f"{activity} (branch summary)"
            rh = _row_hash(branch, label, str(amount), str(fee))
            stmt = pg_insert(RiaDailySummaryRow).values(
                source_file=src, branch=branch, row_hash=rh, label=label,
                value1=amount, value2=fee, value3=None,
            ).on_conflict_do_nothing(constraint="uq_ria_summary_row")
            result = self.session.execute(stmt)
            inserted += result.rowcount or 0
        return inserted

    def _load_ria_transactions(self, rec: TableRecord, source_path: str) -> int:
        src = Path(source_path).name
        cols = [c.lower().replace("\n", " ").strip() for c in rec.columns]

        def idx(name: str) -> int | None:
            return cols.index(name) if name in cols else None

        i_date, i_act = idx("date"), idx("activity")
        i_ref, i_desc = idx("ref no"), idx("description")
        i_amt, i_fee, i_tax = idx("amount"), idx("fee"), idx("tax")
        i_comm, i_deb = idx("comm"), idx("debits")
        i_cred, i_bal = idx("credits"), idx("running balance")

        inserted = 0
        for row in rec.rows:
            def get(i: int | None) -> str | None:
                return row[i] if i is not None and i < len(row) else None

            activity = (get(i_act) or "").strip()
            ref = (get(i_ref) or "").strip()
            amount = _to_float(get(i_amt))
            # Skip the artificial "Previous Balance" row and empty rows
            if not activity and not ref and amount is None:
                continue
            if (get(i_date) or "").startswith("Previous"):
                continue
            rh = _row_hash(src, get(i_date), activity, ref, str(amount))
            stmt = pg_insert(RiaTransactionRow).values(
                source_file=src,
                txn_date=_to_date(get(i_date)),
                activity=activity or None,
                ref_no=ref or None,
                description=(get(i_desc) or "").strip() or None,
                amount=amount,
                fee=_to_float(get(i_fee)),
                tax=_to_float(get(i_tax)),
                comm=_to_float(get(i_comm)),
                debits=_to_float(get(i_deb)),
                credits=_to_float(get(i_cred)),
                running_balance=_to_float(get(i_bal)),
                row_hash=rh,
            ).on_conflict_do_nothing(constraint="uq_ria_txn_row")
            result = self.session.execute(stmt)
            inserted += result.rowcount or 0
        return inserted

    # Public entry used by tests and the CLI
    def load_inventory_from_parsed(self, parsed: ParsedDocument) -> int:
        total = 0
        for rec in parsed.tables:
            if rec.name == "csv_table" or rec.name.startswith("sales") or rec.name.startswith("ria"):
                continue
            # CSV inventory rows come through as unnamed table elements; detect by columns
            cols_lower = [c.lower().strip() for c in (rec.rows[0] if rec.rows else rec.columns)]
            if "upc" in cols_lower and "in stock" in " ".join(cols_lower):
                total += self._load_inventory(rec, parsed.source_path)
        return total
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Index, Integer, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from deli_rag.db.models import Base


class SalesDailyRow(Base):
    """One row per (UPC, sale_date, kind) from a Sales_History CSV export.
    `kind` distinguishes SKU rows from category-total rows.
    """
    __tablename__ = "sales_daily"
    __table_args__ = (
        UniqueConstraint("source_file", "row_hash", name="uq_sales_daily_row"),
        Index("ix_sales_daily_date", "source_report_date"),
        Index("ix_sales_daily_upc", "upc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    source_report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)     # "sku" | "category"
    upc: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    total_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InventorySnapshotRow(Base):
    """One row per (UPC, snapshot_date) from an Inventory_Status CSV export."""
    __tablename__ = "inventory_snapshot"
    __table_args__ = (
        UniqueConstraint("source_file", "row_hash", name="uq_inventory_row"),
        Index("ix_inventory_upc", "upc"),
        Index("ix_inventory_snapshot_date", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    upc: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    in_stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    predicted_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    count_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    days_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    needs_reorder: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RiaDailySummaryRow(Base):
    """One row per (branch, report_date, label) from a Ria AgentBalanceReport."""
    __tablename__ = "ria_daily_summary"
    __table_args__ = (
        UniqueConstraint("source_file", "row_hash", name="uq_ria_summary_row"),
        Index("ix_ria_branch_date", "branch", "report_from"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    branch: Mapped[str | None] = mapped_column(String(32), nullable=True)
    report_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    report_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    value1: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    value2: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    value3: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RiaTransactionRow(Base):
    """One row per RIA detail transaction."""
    __tablename__ = "ria_transactions"
    __table_args__ = (
        UniqueConstraint("source_file", "row_hash", name="uq_ria_txn_row"),
        Index("ix_ria_txn_date", "txn_date"),
        Index("ix_ria_txn_ref", "ref_no"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    txn_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    activity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ref_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    fee: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    tax: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    comm: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    debits: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    credits: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    running_balance: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
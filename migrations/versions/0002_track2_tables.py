"""track2 tables: sales_daily, inventory_snapshot, ria_daily_summary, ria_transactions"""
from alembic import op
import sqlalchemy as sa

revision = "0002_track2_tables"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sales_daily",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_file", sa.Text, nullable=False),
        sa.Column("source_report_date", sa.Date, nullable=True),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("upc", sa.String(32), nullable=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("total_qty", sa.Integer, nullable=True),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_file", "row_hash", name="uq_sales_daily_row"),
    )
    op.create_index("ix_sales_daily_date", "sales_daily", ["source_report_date"])
    op.create_index("ix_sales_daily_upc", "sales_daily", ["upc"])

    op.create_table(
        "inventory_snapshot",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_file", sa.Text, nullable=False),
        sa.Column("snapshot_date", sa.Date, nullable=True),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("upc", sa.String(32), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("department", sa.Text, nullable=True),
        sa.Column("in_stock", sa.Integer, nullable=True),
        sa.Column("predicted_days", sa.Integer, nullable=True),
        sa.Column("count_threshold", sa.Integer, nullable=True),
        sa.Column("days_threshold", sa.Integer, nullable=True),
        sa.Column("needs_reorder", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_file", "row_hash", name="uq_inventory_row"),
    )
    op.create_index("ix_inventory_upc", "inventory_snapshot", ["upc"])
    op.create_index("ix_inventory_snapshot_date", "inventory_snapshot", ["snapshot_date"])

    op.create_table(
        "ria_daily_summary",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_file", sa.Text, nullable=False),
        sa.Column("branch", sa.String(32), nullable=True),
        sa.Column("report_from", sa.Date, nullable=True),
        sa.Column("report_to", sa.Date, nullable=True),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("value1", sa.Numeric(14, 2), nullable=True),
        sa.Column("value2", sa.Numeric(14, 2), nullable=True),
        sa.Column("value3", sa.Numeric(14, 2), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_file", "row_hash", name="uq_ria_summary_row"),
    )
    op.create_index("ix_ria_branch_date", "ria_daily_summary", ["branch", "report_from"])

    op.create_table(
        "ria_transactions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_file", sa.Text, nullable=False),
        sa.Column("txn_date", sa.Date, nullable=True),
        sa.Column("activity", sa.String(32), nullable=True),
        sa.Column("ref_no", sa.String(32), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("fee", sa.Numeric(12, 2), nullable=True),
        sa.Column("tax", sa.Numeric(12, 2), nullable=True),
        sa.Column("comm", sa.Numeric(12, 2), nullable=True),
        sa.Column("debits", sa.Numeric(12, 2), nullable=True),
        sa.Column("credits", sa.Numeric(12, 2), nullable=True),
        sa.Column("running_balance", sa.Numeric(12, 2), nullable=True),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_file", "row_hash", name="uq_ria_txn_row"),
    )
    op.create_index("ix_ria_txn_date", "ria_transactions", ["txn_date"])
    op.create_index("ix_ria_txn_ref", "ria_transactions", ["ref_no"])


def downgrade() -> None:
    op.drop_table("ria_transactions")
    op.drop_table("ria_daily_summary")
    op.drop_table("inventory_snapshot")
    op.drop_table("sales_daily")
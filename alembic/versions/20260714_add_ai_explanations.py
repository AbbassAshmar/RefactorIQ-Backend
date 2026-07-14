"""Persist generated AI explanations for scans and files.

Revision ID: 20260714_ai_explanations
Revises: 20260713_scan_errors
Create Date: 2026-07-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20260714_ai_explanations"
down_revision = "20260713_scan_errors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "ai_explanations" in inspector.get_table_names():
        return

    op.create_table(
        "ai_explanations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("file_id", sa.UUID(), nullable=True),
        sa.Column("scan_id", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "(file_id IS NOT NULL AND scan_id IS NULL) OR "
            "(file_id IS NULL AND scan_id IS NOT NULL)",
            name="ck_ai_explanations_single_parent",
        ),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_id", "type", name="uq_ai_explanations_file_type"),
        sa.UniqueConstraint("scan_id", "type", name="uq_ai_explanations_scan_type"),
    )
    op.create_index("ix_ai_explanations_file_id", "ai_explanations", ["file_id"])
    op.create_index("ix_ai_explanations_scan_id", "ai_explanations", ["scan_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if "ai_explanations" not in sa.inspect(bind).get_table_names():
        return
    op.drop_index("ix_ai_explanations_scan_id", table_name="ai_explanations")
    op.drop_index("ix_ai_explanations_file_id", table_name="ai_explanations")
    op.drop_table("ai_explanations")

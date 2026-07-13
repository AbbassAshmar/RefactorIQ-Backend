"""Add persisted terminal scan errors and analytics indexes.

Revision ID: 20260713_scan_errors
Revises: 20260710_rm_node_id
Create Date: 2026-07-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260713_scan_errors"
down_revision = "20260710_rm_node_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "scans" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("scans")}
    if "error_message" not in columns:
        op.add_column("scans", sa.Column("error_message", sa.Text(), nullable=True))

    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("scans")}
    if "ix_scans_created_at" not in indexes:
        op.create_index("ix_scans_created_at", "scans", ["created_at"])
    if "ix_scans_status_finished_at" not in indexes:
        op.create_index(
            "ix_scans_status_finished_at",
            "scans",
            ["status", "finished_at"],
        )
    if "ix_scans_project_id" not in indexes:
        op.create_index("ix_scans_project_id", "scans", ["project_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "scans" not in inspector.get_table_names():
        return

    indexes = {index["name"] for index in inspector.get_indexes("scans")}
    if "ix_scans_project_id" in indexes:
        op.drop_index("ix_scans_project_id", table_name="scans")
    if "ix_scans_status_finished_at" in indexes:
        op.drop_index("ix_scans_status_finished_at", table_name="scans")
    if "ix_scans_created_at" in indexes:
        op.drop_index("ix_scans_created_at", table_name="scans")

    columns = {column["name"] for column in sa.inspect(bind).get_columns("scans")}
    if "error_message" in columns:
        op.drop_column("scans", "error_message")

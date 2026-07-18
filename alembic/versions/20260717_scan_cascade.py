"""Cascade scan visualization records with their scan.

Revision ID: 20260717_scan_cascade
Revises: 20260714_refactor_queue
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa


revision = "20260717_scan_cascade"
down_revision = "20260714_refactor_queue"
branch_labels = None
depends_on = None


CONSTRAINT_NAME = "fk_scan_visualization_records_scan_id_scans"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "scan_visualization_records" not in inspector.get_table_names():
        return

    # Remove legacy rows that cannot satisfy the new relationship before the
    # constraint is installed.
    op.execute(
        sa.text(
            """
            DELETE FROM scan_visualization_records AS visualization
            WHERE visualization.scan_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM scans
                  WHERE scans.id = visualization.scan_id
              )
            """
        )
    )

    existing = {
        foreign_key.get("name")
        for foreign_key in inspector.get_foreign_keys("scan_visualization_records")
    }
    if CONSTRAINT_NAME not in existing:
        op.create_foreign_key(
            CONSTRAINT_NAME,
            "scan_visualization_records",
            "scans",
            ["scan_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "scan_visualization_records" not in inspector.get_table_names():
        return
    existing = {
        foreign_key.get("name")
        for foreign_key in inspector.get_foreign_keys("scan_visualization_records")
    }
    if CONSTRAINT_NAME in existing:
        op.drop_constraint(
            CONSTRAINT_NAME,
            "scan_visualization_records",
            type_="foreignkey",
        )

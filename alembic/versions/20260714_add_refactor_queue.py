"""Add project-scoped refactor queue items.

Revision ID: 20260714_refactor_queue
Revises: 20260714_ai_explanations
Create Date: 2026-07-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20260714_refactor_queue"
down_revision = "20260714_ai_explanations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "refactor_queue_items" in inspector.get_table_names():
        return

    queue_status = sa.Enum(
        "pending",
        "in_progress",
        "completed",
        name="refactor_queue_status_enum",
    )
    op.create_table(
        "refactor_queue_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("status", queue_status, server_default="pending", nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "file_path", name="uq_refactor_queue_project_file_path"),
    )
    op.create_index(
        "ix_refactor_queue_project_status_position",
        "refactor_queue_items",
        ["project_id", "status", "position"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "refactor_queue_items" not in sa.inspect(bind).get_table_names():
        return
    op.drop_index("ix_refactor_queue_project_status_position", table_name="refactor_queue_items")
    op.drop_table("refactor_queue_items")
    if bind.dialect.name == "postgresql":
        sa.Enum(name="refactor_queue_status_enum").drop(bind, checkfirst=True)

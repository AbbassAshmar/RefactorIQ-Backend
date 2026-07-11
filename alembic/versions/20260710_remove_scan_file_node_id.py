"""Remove the redundant ScanFile graph-node identity.

Revision ID: 20260710_rm_node_id
Revises:
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260710_rm_node_id"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # file_path already contains the canonical repository-relative identity.
    # Do not transform legacy values here: a leading slash may be a genuine
    # absolute filesystem path in data produced by an older buggy scan.
    bind = op.get_bind()
    if "files" not in sa.inspect(bind).get_table_names():
        return
    columns = {column["name"] for column in sa.inspect(bind).get_columns("files")}
    if "node_id" in columns:
        op.drop_column("files", "node_id")


def downgrade() -> None:
    bind = op.get_bind()
    if "files" not in sa.inspect(bind).get_table_names():
        return
    columns = {column["name"] for column in sa.inspect(bind).get_columns("files")}
    if "node_id" not in columns:
        op.add_column("files", sa.Column("node_id", sa.Text(), nullable=True))
        op.execute("UPDATE files SET node_id = file_path")
        op.alter_column("files", "node_id", nullable=False)

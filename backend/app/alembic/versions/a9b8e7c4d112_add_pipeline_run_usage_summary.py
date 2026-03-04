"""add pipeline run usage summary

Revision ID: a9b8e7c4d112
Revises: b7a3c1d9e5f2
Create Date: 2026-03-04 12:30:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "a9b8e7c4d112"
down_revision = "b7a3c1d9e5f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    before_count = bind.execute(sa.text("SELECT COUNT(*) FROM pipeline_runs")).scalar_one()

    op.add_column(
        "pipeline_runs",
        sa.Column(
            "usage_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    after_count = bind.execute(sa.text("SELECT COUNT(*) FROM pipeline_runs")).scalar_one()
    if before_count != after_count:
        raise RuntimeError("Pipeline run row count changed unexpectedly")

    null_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM pipeline_runs WHERE usage_summary IS NULL")
    ).scalar_one()
    if null_count != 0:
        raise RuntimeError("Pipeline run usage summary backfill verification failed")


def downgrade() -> None:
    op.drop_column("pipeline_runs", "usage_summary")

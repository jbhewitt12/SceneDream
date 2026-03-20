"""add stage_progress to pipeline_runs

Revision ID: e5f7a8b9c012
Revises: c4d6e7f8a901
Create Date: 2026-03-20 10:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e5f7a8b9c012"
down_revision = "c4d6e7f8a901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pipeline_runs",
        sa.Column(
            "stage_progress",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("pipeline_runs", "stage_progress")

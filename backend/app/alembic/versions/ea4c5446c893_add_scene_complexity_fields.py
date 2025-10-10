"""add_scene_complexity_fields

Revision ID: ea4c5446c893
Revises: 759bd0b1450a
Create Date: 2025-10-10 13:29:35.731113

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ea4c5446c893'
down_revision = '759bd0b1450a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scene_rankings",
        sa.Column("recommended_prompt_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "scene_rankings",
        sa.Column("complexity_rationale", sa.Text(), nullable=True),
    )
    op.add_column(
        "scene_rankings",
        sa.Column("distinct_visual_moments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scene_rankings", "distinct_visual_moments")
    op.drop_column("scene_rankings", "complexity_rationale")
    op.drop_column("scene_rankings", "recommended_prompt_count")

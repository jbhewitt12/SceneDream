"""Add scene rankings table

Revision ID: b1e4df9374e4
Revises: 72f61d671c88
Create Date: 2025-10-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b1e4df9374e4"
down_revision = "72f61d671c88"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scene_rankings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "scene_extraction_id",
            sa.Uuid(),
            sa.ForeignKey("scene_extractions.id"),
            nullable=False,
        ),
        sa.Column(
            "model_vendor",
            sqlmodel.sql.sqltypes.AutoString(length=128),
            nullable=False,
        ),
        sa.Column(
            "model_name",
            sqlmodel.sql.sqltypes.AutoString(length=128),
            nullable=False,
        ),
        sa.Column(
            "prompt_version",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("overall_priority", sa.Float(), nullable=False),
        sa.Column("weight_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "weight_config_hash",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("character_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column(
            "llm_request_id",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scene_extraction_id",
            "model_name",
            "prompt_version",
            "weight_config_hash",
            name="uq_scene_ranking_unique_run",
        ),
    )
    op.create_index(
        op.f("ix_scene_rankings_scene_extraction_id"),
        "scene_rankings",
        ["scene_extraction_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_scene_rankings_scene_extraction_id"), table_name="scene_rankings")
    op.drop_table("scene_rankings")

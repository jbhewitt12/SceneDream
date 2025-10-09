"""Create image prompts table

Revision ID: 3b8d621aa59a
Revises: b1e4df9374e4
Create Date: 2025-10-12 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "3b8d621aa59a"
down_revision = "b1e4df9374e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "image_prompts",
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
        sa.Column("variant_index", sa.Integer(), nullable=False),
        sa.Column(
            "title",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=True),
        sa.Column("style_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "context_window",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "llm_request_id",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scene_extraction_id",
            "model_name",
            "prompt_version",
            "variant_index",
            name="uq_image_prompt_unique_variant",
        ),
    )
    op.create_index(
        op.f("ix_image_prompts_scene_extraction_id"),
        "image_prompts",
        ["scene_extraction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_image_prompts_model_name"),
        "image_prompts",
        ["model_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_image_prompts_prompt_version"),
        "image_prompts",
        ["prompt_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_image_prompts_prompt_version"), table_name="image_prompts")
    op.drop_index(op.f("ix_image_prompts_model_name"), table_name="image_prompts")
    op.drop_index(op.f("ix_image_prompts_scene_extraction_id"), table_name="image_prompts")
    op.drop_table("image_prompts")

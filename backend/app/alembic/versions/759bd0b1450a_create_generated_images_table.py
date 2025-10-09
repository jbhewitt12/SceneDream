"""create_generated_images_table

Revision ID: 759bd0b1450a
Revises: 3b8d621aa59a
Create Date: 2025-10-09 14:54:26.583105

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '759bd0b1450a'
down_revision = '3b8d621aa59a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generated_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "scene_extraction_id",
            sa.Uuid(),
            sa.ForeignKey("scene_extractions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "image_prompt_id",
            sa.Uuid(),
            sa.ForeignKey("image_prompts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "book_slug",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("variant_index", sa.Integer(), nullable=False),
        sa.Column(
            "provider",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column(
            "model",
            sqlmodel.sql.sqltypes.AutoString(length=128),
            nullable=False,
        ),
        sa.Column(
            "size",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=False,
        ),
        sa.Column(
            "quality",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=False,
        ),
        sa.Column(
            "style",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=False,
        ),
        sa.Column(
            "aspect_ratio",
            sqlmodel.sql.sqltypes.AutoString(length=16),
            nullable=True,
        ),
        sa.Column(
            "response_format",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=False,
        ),
        sa.Column(
            "storage_path",
            sqlmodel.sql.sqltypes.AutoString(length=1024),
            nullable=False,
        ),
        sa.Column(
            "file_name",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("bytes_approx", sa.Integer(), nullable=True),
        sa.Column(
            "checksum_sha256",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
        sa.Column(
            "request_id",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "image_prompt_id",
            "variant_index",
            "provider",
            "model",
            "size",
            "quality",
            "style",
            name="uq_generated_image_idempotency",
        ),
    )
    op.create_index(
        op.f("ix_generated_images_scene_extraction_id"),
        "generated_images",
        ["scene_extraction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_images_image_prompt_id"),
        "generated_images",
        ["image_prompt_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_images_book_slug"),
        "generated_images",
        ["book_slug"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_images_chapter_number"),
        "generated_images",
        ["chapter_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_images_created_at"),
        "generated_images",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_generated_images_created_at"), table_name="generated_images")
    op.drop_index(op.f("ix_generated_images_chapter_number"), table_name="generated_images")
    op.drop_index(op.f("ix_generated_images_book_slug"), table_name="generated_images")
    op.drop_index(op.f("ix_generated_images_image_prompt_id"), table_name="generated_images")
    op.drop_index(op.f("ix_generated_images_scene_extraction_id"), table_name="generated_images")
    op.drop_table("generated_images")

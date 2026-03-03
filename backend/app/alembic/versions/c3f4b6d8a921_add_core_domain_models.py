"""add core domain models

Revision ID: c3f4b6d8a921
Revises: 4df9d25b460c
Create Date: 2026-03-03 10:45:00.000000

"""

from datetime import datetime, timezone
from pathlib import Path
import uuid

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c3f4b6d8a921"
down_revision = "4df9d25b460c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column(
            "display_name",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column(
            "source_path",
            sqlmodel.sql.sqltypes.AutoString(length=1024),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=False,
        ),
        sa.Column(
            "ingestion_state",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=False,
        ),
        sa.Column("ingestion_error", sa.Text(), nullable=True),
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_documents_slug"),
    )
    op.create_index(op.f("ix_documents_slug"), "documents", ["slug"], unique=False)
    op.create_index(
        op.f("ix_documents_source_type"), "documents", ["source_type"], unique=False
    )
    op.create_index(
        op.f("ix_documents_ingestion_state"),
        "documents",
        ["ingestion_state"],
        unique=False,
    )
    op.create_index(
        op.f("ix_documents_created_at"), "documents", ["created_at"], unique=False
    )

    op.add_column("scene_extractions", sa.Column("document_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_scene_extractions_document_id"),
        "scene_extractions",
        ["document_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_scene_extractions_document_id_documents",
        "scene_extractions",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column(
            "book_slug",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column(
            "current_stage",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "config_overrides",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_pipeline_runs_document_id_documents",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pipeline_runs_document_id"), "pipeline_runs", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_pipeline_runs_book_slug"), "pipeline_runs", ["book_slug"], unique=False
    )
    op.create_index(
        op.f("ix_pipeline_runs_status"), "pipeline_runs", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_pipeline_runs_current_stage"),
        "pipeline_runs",
        ["current_stage"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pipeline_runs_created_at"),
        "pipeline_runs",
        ["created_at"],
        unique=False,
    )

    op.add_column("scene_rankings", sa.Column("pipeline_run_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_scene_rankings_pipeline_run_id"),
        "scene_rankings",
        ["pipeline_run_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_scene_rankings_pipeline_run_id_pipeline_runs",
        "scene_rankings",
        "pipeline_runs",
        ["pipeline_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("image_prompts", sa.Column("pipeline_run_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_image_prompts_pipeline_run_id"),
        "image_prompts",
        ["pipeline_run_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_image_prompts_pipeline_run_id_pipeline_runs",
        "image_prompts",
        "pipeline_runs",
        ["pipeline_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("generated_images", sa.Column("pipeline_run_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_generated_images_pipeline_run_id"),
        "generated_images",
        ["pipeline_run_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_generated_images_pipeline_run_id_pipeline_runs",
        "generated_images",
        "pipeline_runs",
        ["pipeline_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "generated_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("pipeline_run_id", sa.Uuid(), nullable=True),
        sa.Column("scene_extraction_id", sa.Uuid(), nullable=True),
        sa.Column("image_prompt_id", sa.Uuid(), nullable=True),
        sa.Column(
            "asset_type",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=False,
        ),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column(
            "provider",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
        sa.Column(
            "model",
            sqlmodel.sql.sqltypes.AutoString(length=128),
            nullable=True,
        ),
        sa.Column(
            "storage_path",
            sqlmodel.sql.sqltypes.AutoString(length=1024),
            nullable=True,
        ),
        sa.Column(
            "file_name",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column(
            "mime_type",
            sqlmodel.sql.sqltypes.AutoString(length=128),
            nullable=True,
        ),
        sa.Column(
            "asset_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_generated_assets_document_id_documents",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            ["pipeline_runs.id"],
            name="fk_generated_assets_pipeline_run_id_pipeline_runs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["scene_extraction_id"],
            ["scene_extractions.id"],
            name="fk_generated_assets_scene_extraction_id_scene_extractions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["image_prompt_id"],
            ["image_prompts.id"],
            name="fk_generated_assets_image_prompt_id_image_prompts",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_generated_assets_document_id"),
        "generated_assets",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_assets_pipeline_run_id"),
        "generated_assets",
        ["pipeline_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_assets_scene_extraction_id"),
        "generated_assets",
        ["scene_extraction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_assets_image_prompt_id"),
        "generated_assets",
        ["image_prompt_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_assets_asset_type"),
        "generated_assets",
        ["asset_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_generated_assets_status"), "generated_assets", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_generated_assets_created_at"),
        "generated_assets",
        ["created_at"],
        unique=False,
    )

    op.add_column(
        "generated_images", sa.Column("generated_asset_id", sa.Uuid(), nullable=True)
    )
    op.create_index(
        op.f("ix_generated_images_generated_asset_id"),
        "generated_images",
        ["generated_asset_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_generated_images_generated_asset_id_generated_assets",
        "generated_images",
        "generated_assets",
        ["generated_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )

    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    documents_table = sa.table(
        "documents",
        sa.column("id", sa.Uuid()),
        sa.column("slug", sqlmodel.sql.sqltypes.AutoString(length=255)),
        sa.column("display_name", sqlmodel.sql.sqltypes.AutoString(length=255)),
        sa.column("source_path", sqlmodel.sql.sqltypes.AutoString(length=1024)),
        sa.column("source_type", sqlmodel.sql.sqltypes.AutoString(length=32)),
        sa.column("ingestion_state", sqlmodel.sql.sqltypes.AutoString(length=32)),
        sa.column("ingestion_error", sa.Text()),
        sa.column("source_metadata", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    rows = connection.execute(
        sa.text(
            """
            SELECT
                book_slug,
                MIN(source_book_path) AS source_book_path,
                MIN(extracted_at) AS first_seen_at
            FROM scene_extractions
            GROUP BY book_slug
            """
        )
    ).mappings()
    for row in rows:
        slug = row["book_slug"]
        if not slug:
            continue
        source_path = row["source_book_path"] or f"books/{slug}.epub"
        source_suffix = Path(source_path).suffix.strip(".").lower()
        source_type = source_suffix or "epub"
        created_at = row["first_seen_at"] or now
        connection.execute(
            documents_table.insert().values(
                id=uuid.uuid4(),
                slug=slug,
                display_name=None,
                source_path=source_path,
                source_type=source_type,
                ingestion_state="ingested",
                ingestion_error=None,
                source_metadata={"legacy_book_slug": slug},
                created_at=created_at,
                updated_at=now,
            )
        )

    connection.execute(
        sa.text(
            """
            UPDATE scene_extractions AS se
            SET document_id = d.id
            FROM documents AS d
            WHERE se.book_slug = d.slug
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_generated_images_generated_asset_id_generated_assets",
        "generated_images",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_generated_images_generated_asset_id"),
        table_name="generated_images",
    )
    op.drop_column("generated_images", "generated_asset_id")

    op.drop_index(op.f("ix_generated_assets_created_at"), table_name="generated_assets")
    op.drop_index(op.f("ix_generated_assets_status"), table_name="generated_assets")
    op.drop_index(op.f("ix_generated_assets_asset_type"), table_name="generated_assets")
    op.drop_index(
        op.f("ix_generated_assets_image_prompt_id"), table_name="generated_assets"
    )
    op.drop_index(
        op.f("ix_generated_assets_scene_extraction_id"), table_name="generated_assets"
    )
    op.drop_index(
        op.f("ix_generated_assets_pipeline_run_id"), table_name="generated_assets"
    )
    op.drop_index(op.f("ix_generated_assets_document_id"), table_name="generated_assets")
    op.drop_table("generated_assets")

    op.drop_constraint(
        "fk_generated_images_pipeline_run_id_pipeline_runs",
        "generated_images",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_generated_images_pipeline_run_id"), table_name="generated_images")
    op.drop_column("generated_images", "pipeline_run_id")

    op.drop_constraint(
        "fk_image_prompts_pipeline_run_id_pipeline_runs",
        "image_prompts",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_image_prompts_pipeline_run_id"), table_name="image_prompts")
    op.drop_column("image_prompts", "pipeline_run_id")

    op.drop_constraint(
        "fk_scene_rankings_pipeline_run_id_pipeline_runs",
        "scene_rankings",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_scene_rankings_pipeline_run_id"), table_name="scene_rankings"
    )
    op.drop_column("scene_rankings", "pipeline_run_id")

    op.drop_index(op.f("ix_pipeline_runs_created_at"), table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_current_stage"), table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_status"), table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_book_slug"), table_name="pipeline_runs")
    op.drop_index(op.f("ix_pipeline_runs_document_id"), table_name="pipeline_runs")
    op.drop_table("pipeline_runs")

    op.drop_constraint(
        "fk_scene_extractions_document_id_documents",
        "scene_extractions",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_scene_extractions_document_id"),
        table_name="scene_extractions",
    )
    op.drop_column("scene_extractions", "document_id")

    op.drop_index(op.f("ix_documents_created_at"), table_name="documents")
    op.drop_index(op.f("ix_documents_ingestion_state"), table_name="documents")
    op.drop_index(op.f("ix_documents_source_type"), table_name="documents")
    op.drop_index(op.f("ix_documents_slug"), table_name="documents")
    op.drop_table("documents")

"""add document stage status fields

Revision ID: c8d9e0f1a234
Revises: a9b8e7c4d112
Create Date: 2026-03-11 17:05:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c8d9e0f1a234"
down_revision = "a9b8e7c4d112"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "extraction_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.add_column(
        "documents",
        sa.Column("extraction_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("extraction_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "ranking_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.add_column(
        "documents",
        sa.Column("ranking_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("ranking_error", sa.Text(), nullable=True),
    )

    op.create_index(
        op.f("ix_documents_extraction_status"),
        "documents",
        ["extraction_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_documents_ranking_status"),
        "documents",
        ["ranking_status"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            WITH extraction_counts AS (
                SELECT d.id AS document_id, COUNT(se.id)::int AS extracted_count
                FROM documents AS d
                LEFT JOIN scene_extractions AS se
                    ON se.document_id = d.id
                GROUP BY d.id
            ),
            ranking_counts AS (
                SELECT
                    d.id AS document_id,
                    COUNT(DISTINCT CASE
                        WHEN LOWER(COALESCE(se.refinement_decision, '')) <> 'discard'
                        THEN sr.scene_extraction_id
                        ELSE NULL
                    END)::int AS ranked_scene_count,
                    COUNT(DISTINCT CASE
                        WHEN LOWER(COALESCE(se.refinement_decision, '')) <> 'discard'
                        THEN se.id
                        ELSE NULL
                    END)::int AS rankable_scene_count
                FROM documents AS d
                LEFT JOIN scene_extractions AS se
                    ON se.document_id = d.id
                LEFT JOIN scene_rankings AS sr
                    ON sr.scene_extraction_id = se.id
                GROUP BY d.id
            )
            UPDATE documents AS d
            SET
                extraction_status = CASE
                    WHEN ec.extracted_count > 0 THEN 'completed'
                    ELSE 'pending'
                END,
                extraction_completed_at = CASE
                    WHEN ec.extracted_count > 0 THEN COALESCE(d.extraction_completed_at, NOW())
                    ELSE NULL
                END,
                extraction_error = NULL,
                ranking_status = CASE
                    WHEN ec.extracted_count = 0 THEN 'pending'
                    WHEN rc.rankable_scene_count = 0 THEN 'completed'
                    WHEN rc.ranked_scene_count = 0 THEN 'pending'
                    WHEN rc.ranked_scene_count < rc.rankable_scene_count THEN 'stale'
                    ELSE 'completed'
                END,
                ranking_completed_at = CASE
                    WHEN ec.extracted_count > 0
                         AND (
                             rc.rankable_scene_count = 0
                             OR rc.ranked_scene_count >= rc.rankable_scene_count
                         )
                        THEN COALESCE(d.ranking_completed_at, NOW())
                    ELSE NULL
                END,
                ranking_error = NULL
            FROM extraction_counts AS ec
            JOIN ranking_counts AS rc
                ON rc.document_id = ec.document_id
            WHERE d.id = ec.document_id
            """
        )
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_documents_ranking_status"), table_name="documents")
    op.drop_index(op.f("ix_documents_extraction_status"), table_name="documents")

    op.drop_column("documents", "ranking_error")
    op.drop_column("documents", "ranking_completed_at")
    op.drop_column("documents", "ranking_status")
    op.drop_column("documents", "extraction_error")
    op.drop_column("documents", "extraction_completed_at")
    op.drop_column("documents", "extraction_status")

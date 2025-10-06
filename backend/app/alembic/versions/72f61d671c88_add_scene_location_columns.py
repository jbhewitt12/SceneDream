"""Add structural scene location columns and migrate props

Revision ID: 72f61d671c88
Revises: 90b99ad3e9cf
Create Date: 2025-02-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "72f61d671c88"
down_revision = "90b99ad3e9cf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scene_extractions",
        sa.Column("provisional_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "scene_extractions",
        sa.Column("location_marker_normalized", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "scene_extractions",
        sa.Column("scene_paragraph_start", sa.Integer(), nullable=True),
    )
    op.add_column(
        "scene_extractions",
        sa.Column("scene_paragraph_end", sa.Integer(), nullable=True),
    )
    op.add_column(
        "scene_extractions",
        sa.Column("scene_word_start", sa.Integer(), nullable=True),
    )
    op.add_column(
        "scene_extractions",
        sa.Column("scene_word_end", sa.Integer(), nullable=True),
    )
    op.add_column(
        "scene_extractions",
        sa.Column("refinement_has_refined_excerpt", sa.Boolean(), nullable=True),
    )

    op.execute("""
        UPDATE scene_extractions
        SET props = COALESCE(props, '{}'::jsonb)
    """)

    op.execute(
        """
        UPDATE scene_extractions
        SET provisional_id = CASE
                WHEN (props ->> 'provisional_id') IS NULL THEN provisional_id
                WHEN (props ->> 'provisional_id') ~ '^[0-9]+$'
                    THEN (props ->> 'provisional_id')::integer
                ELSE provisional_id
            END,
            location_marker_normalized = COALESCE(
                props ->> 'location_marker_normalized',
                LOWER(BTRIM(location_marker))
            ),
            scene_paragraph_start = COALESCE(
                (props -> 'chunk_paragraph_span' ->> 0)::integer,
                chunk_paragraph_start
            ),
            scene_paragraph_end = COALESCE(
                (props -> 'chunk_paragraph_span' ->> 1)::integer,
                chunk_paragraph_end
            ),
            refinement_has_refined_excerpt = CASE
                WHEN props ? 'refinement_summary' THEN
                    (props -> 'refinement_summary' ->> 'has_refined_excerpt')::boolean
                ELSE refinement_has_refined_excerpt
            END
        """
    )

    op.execute(
        """
        UPDATE scene_extractions
        SET props = props
            - 'provisional_id'
            - 'chunk_paragraph_span'
            - 'location_marker_normalized'
            - 'refinement_summary'
    """
    )


def downgrade() -> None:
    op.execute("""
        UPDATE scene_extractions
        SET props = jsonb_strip_nulls(
            COALESCE(props, '{}'::jsonb)
            || CASE
                WHEN provisional_id IS NOT NULL THEN jsonb_build_object('provisional_id', provisional_id)
                ELSE '{}'::jsonb
            END
            || jsonb_build_object(
                'chunk_paragraph_span',
                jsonb_build_array(chunk_paragraph_start, chunk_paragraph_end)
            )
            || jsonb_build_object(
                'location_marker_normalized',
                COALESCE(location_marker_normalized, LOWER(BTRIM(location_marker)))
            )
            || CASE
                WHEN refinement_has_refined_excerpt IS NOT NULL OR refinement_decision IS NOT NULL THEN
                    jsonb_build_object(
                        'refinement_summary',
                        jsonb_strip_nulls(jsonb_build_object(
                            'decision', refinement_decision,
                            'has_refined_excerpt', refinement_has_refined_excerpt
                        ))
                    )
                ELSE '{}'::jsonb
            END
        )
    """)

    op.drop_column("scene_extractions", "refinement_has_refined_excerpt")
    op.drop_column("scene_extractions", "scene_word_end")
    op.drop_column("scene_extractions", "scene_word_start")
    op.drop_column("scene_extractions", "scene_paragraph_end")
    op.drop_column("scene_extractions", "scene_paragraph_start")
    op.drop_column("scene_extractions", "location_marker_normalized")
    op.drop_column("scene_extractions", "provisional_id")

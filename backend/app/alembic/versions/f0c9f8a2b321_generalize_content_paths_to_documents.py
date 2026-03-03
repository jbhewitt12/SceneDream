"""generalize_content_paths_to_documents

Revision ID: f0c9f8a2b321
Revises: d7766efb0e08
Create Date: 2026-03-03 10:40:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "f0c9f8a2b321"
down_revision = "d7766efb0e08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH normalized AS (
            SELECT
                id,
                source_path AS old_path,
                CASE
                    WHEN source_path IS NULL OR source_path = '' THEN source_path
                    WHEN regexp_replace(source_path, '^\\./+', '') LIKE 'documents/%' THEN regexp_replace(source_path, '^\\./+', '')
                    WHEN regexp_replace(source_path, '^\\./+', '') LIKE 'books/%' THEN 'documents/' || substring(regexp_replace(source_path, '^\\./+', '') FROM 7)
                    WHEN regexp_replace(source_path, '^\\./+', '') ~ '.*/documents/.*' THEN regexp_replace(regexp_replace(source_path, '^\\./+', ''), '^.*/documents/', 'documents/')
                    WHEN regexp_replace(source_path, '^\\./+', '') ~ '.*/books/.*' THEN 'documents/' || substring(regexp_replace(regexp_replace(source_path, '^\\./+', ''), '^.*/books/', 'books/') FROM 7)
                    ELSE regexp_replace(source_path, '^\\./+', '')
                END AS new_path
            FROM documents
        )
        UPDATE documents AS d
        SET
            source_path = n.new_path,
            source_metadata = CASE
                WHEN n.old_path <> n.new_path THEN jsonb_set(
                    COALESCE(d.source_metadata, '{}'::jsonb),
                    '{legacy_source_path}',
                    to_jsonb(n.old_path),
                    true
                )
                ELSE d.source_metadata
            END
        FROM normalized AS n
        WHERE d.id = n.id
          AND n.new_path IS NOT NULL
          AND n.old_path <> n.new_path
        """
    )

    op.execute(
        """
        WITH normalized AS (
            SELECT
                id,
                source_book_path AS old_path,
                CASE
                    WHEN source_book_path IS NULL OR source_book_path = '' THEN source_book_path
                    WHEN regexp_replace(source_book_path, '^\\./+', '') LIKE 'documents/%' THEN regexp_replace(source_book_path, '^\\./+', '')
                    WHEN regexp_replace(source_book_path, '^\\./+', '') LIKE 'books/%' THEN 'documents/' || substring(regexp_replace(source_book_path, '^\\./+', '') FROM 7)
                    WHEN regexp_replace(source_book_path, '^\\./+', '') ~ '.*/documents/.*' THEN regexp_replace(regexp_replace(source_book_path, '^\\./+', ''), '^.*/documents/', 'documents/')
                    WHEN regexp_replace(source_book_path, '^\\./+', '') ~ '.*/books/.*' THEN 'documents/' || substring(regexp_replace(regexp_replace(source_book_path, '^\\./+', ''), '^.*/books/', 'books/') FROM 7)
                    ELSE regexp_replace(source_book_path, '^\\./+', '')
                END AS new_path
            FROM scene_extractions
        )
        UPDATE scene_extractions AS se
        SET
            source_book_path = n.new_path,
            props = CASE
                WHEN n.old_path <> n.new_path THEN jsonb_set(
                    COALESCE(se.props, '{}'::jsonb),
                    '{legacy_source_book_path}',
                    to_jsonb(n.old_path),
                    true
                )
                ELSE se.props
            END
        FROM normalized AS n
        WHERE se.id = n.id
          AND n.new_path IS NOT NULL
          AND n.old_path <> n.new_path
        """
    )


def downgrade() -> None:
    op.execute(
        """
        WITH restored AS (
            SELECT
                id,
                source_path AS current_path,
                COALESCE(
                    NULLIF(source_metadata ->> 'legacy_source_path', ''),
                    CASE
                        WHEN source_path LIKE 'documents/%' THEN 'books/' || substring(source_path FROM 11)
                        ELSE source_path
                    END
                ) AS restored_path
            FROM documents
        )
        UPDATE documents AS d
        SET
            source_path = r.restored_path,
            source_metadata = CASE
                WHEN COALESCE(d.source_metadata, '{}'::jsonb) ? 'legacy_source_path'
                THEN COALESCE(d.source_metadata, '{}'::jsonb) - 'legacy_source_path'
                ELSE d.source_metadata
            END
        FROM restored AS r
        WHERE d.id = r.id
          AND r.restored_path IS NOT NULL
          AND r.restored_path <> d.source_path
        """
    )

    op.execute(
        """
        WITH restored AS (
            SELECT
                id,
                source_book_path AS current_path,
                COALESCE(
                    NULLIF(props ->> 'legacy_source_book_path', ''),
                    CASE
                        WHEN source_book_path LIKE 'documents/%' THEN 'books/' || substring(source_book_path FROM 11)
                        ELSE source_book_path
                    END
                ) AS restored_path
            FROM scene_extractions
        )
        UPDATE scene_extractions AS se
        SET
            source_book_path = r.restored_path,
            props = CASE
                WHEN COALESCE(se.props, '{}'::jsonb) ? 'legacy_source_book_path'
                THEN COALESCE(se.props, '{}'::jsonb) - 'legacy_source_book_path'
                ELSE se.props
            END
        FROM restored AS r
        WHERE se.id = r.id
          AND r.restored_path IS NOT NULL
          AND r.restored_path <> se.source_book_path
        """
    )

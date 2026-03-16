"""add social posting enabled toggle to app settings

Revision ID: c4d6e7f8a901
Revises: 4e2a5f8b7c91
Create Date: 2026-03-16 11:30:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c4d6e7f8a901"
down_revision = "4e2a5f8b7c91"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column(
            "social_posting_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE app_settings
            SET social_posting_enabled = FALSE
            WHERE social_posting_enabled IS NULL
            """
        )
    )
    op.alter_column(
        "app_settings",
        "social_posting_enabled",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("app_settings", "social_posting_enabled")

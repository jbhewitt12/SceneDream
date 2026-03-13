"""Introduce prompt art style mode/text app settings fields.

Revision ID: 4e2a5f8b7c91
Revises: c8d9e0f1a234
Create Date: 2026-03-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4e2a5f8b7c91"
down_revision = "c8d9e0f1a234"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column(
            "default_prompt_art_style_mode",
            sa.String(length=32),
            nullable=False,
            server_default="random_mix",
        ),
    )
    op.add_column(
        "app_settings",
        sa.Column(
            "default_prompt_art_style_text",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.execute(
        sa.text(
            """
            UPDATE app_settings
            SET default_prompt_art_style_mode = 'random_mix',
                default_prompt_art_style_text = NULL
            """
        )
    )

    op.drop_index(
        op.f("ix_app_settings_default_art_style_id"),
        table_name="app_settings",
    )
    op.drop_constraint(
        "fk_app_settings_default_art_style_id_art_styles",
        "app_settings",
        type_="foreignkey",
    )
    op.drop_column("app_settings", "default_art_style_id")


def downgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("default_art_style_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_app_settings_default_art_style_id_art_styles",
        "app_settings",
        "art_styles",
        ["default_art_style_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_app_settings_default_art_style_id"),
        "app_settings",
        ["default_art_style_id"],
        unique=False,
    )

    op.drop_column("app_settings", "default_prompt_art_style_text")
    op.drop_column("app_settings", "default_prompt_art_style_mode")

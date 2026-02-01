"""Add target_provider to image_prompts

Revision ID: 152af98f7667
Revises: 705b42b7e831
Create Date: 2026-02-02

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "152af98f7667"
down_revision = "705b42b7e831"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add target_provider column
    op.add_column(
        "image_prompts",
        sa.Column(
            "target_provider",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_image_prompts_target_provider"),
        "image_prompts",
        ["target_provider"],
        unique=False,
    )

    # Backfill existing prompts with 'openai' since they were generated for DALL-E 3
    op.execute("UPDATE image_prompts SET target_provider = 'openai' WHERE target_provider IS NULL")


def downgrade() -> None:
    op.drop_index(op.f("ix_image_prompts_target_provider"), table_name="image_prompts")
    op.drop_column("image_prompts", "target_provider")

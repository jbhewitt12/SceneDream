"""add_flavour_text_to_image_prompts

Revision ID: 5ce7538a9f6b
Revises: e0b5484b6ee6
Create Date: 2025-10-26 09:33:52.257408

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '5ce7538a9f6b'
down_revision = 'e0b5484b6ee6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "image_prompts",
        sa.Column("flavour_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("image_prompts", "flavour_text")

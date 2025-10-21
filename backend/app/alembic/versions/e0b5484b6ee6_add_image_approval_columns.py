"""add_image_approval_columns

Revision ID: e0b5484b6ee6
Revises: ea4c5446c893
Create Date: 2025-10-21 11:52:34.850556

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'e0b5484b6ee6'
down_revision = 'ea4c5446c893'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "generated_images",
        sa.Column("user_approved", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "generated_images",
        sa.Column("approval_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("generated_images", "approval_updated_at")
    op.drop_column("generated_images", "user_approved")

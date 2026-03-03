"""add_file_deleted_columns

Revision ID: d7766efb0e08
Revises: c3f4b6d8a921
Create Date: 2026-03-02 18:37:11.807651

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7766efb0e08'
down_revision = 'c3f4b6d8a921'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('generated_images', sa.Column('file_deleted', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('generated_images', sa.Column('file_deleted_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('generated_images', 'file_deleted_at')
    op.drop_column('generated_images', 'file_deleted')

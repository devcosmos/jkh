"""model_version artifact sha256

Revision ID: b338f001508f
Revises: 9cb5c6b99664
Create Date: 2026-09-22 17:00:16.350312

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b338f001508f'
down_revision: Union[str, None] = '9cb5c6b99664'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('model_versions', sa.Column('artifact_sha256', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('model_versions', 'artifact_sha256')

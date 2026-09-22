"""channel retention watermark

Revision ID: 36d57d1932f2
Revises: b2c3d4e5f6a7
Create Date: 2026-09-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '36d57d1932f2'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('channel_retention_watermark',
    sa.Column('channel_id', sa.Integer(), nullable=False),
    sa.Column('last_pruned_state', sa.String(length=32), nullable=False),
    sa.Column('last_pruned_event_time', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ),
    sa.PrimaryKeyConstraint('channel_id')
    )


def downgrade() -> None:
    op.drop_table('channel_retention_watermark')

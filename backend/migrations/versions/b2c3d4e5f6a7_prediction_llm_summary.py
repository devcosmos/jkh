"""predictions.llm_summary — кешированное резюме для диспетчера

Причина: карточка риска добавляет краткое объяснение прогноза на естественном языке
(генерируется LLM по explanation) — считается лениво по первому просмотру и кешируется
здесь, чтобы не дёргать внешний API повторно на каждый повторный визит на карточку.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-21 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('predictions', sa.Column('llm_summary', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('predictions', 'llm_summary')

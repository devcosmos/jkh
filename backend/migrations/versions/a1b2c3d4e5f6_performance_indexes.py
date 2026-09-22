"""performance indexes on predictions.created_at / risk_cases.status,opened_at,closed_at

Причина: /dashboard/summary и /predictions делали full scan по predictions (8.7M+ строк
после многочасовой работы воркера) и risk_cases (120k+ строк) — 16.7 сек и 7.5 сек на
проде соответственно (см. docs/documentation/Технические_заметки.md, инцидент 21 сентября 2026). Локально/на малом
объёме данных этого не было видно.

Revision ID: a1b2c3d4e5f6
Revises: 6a9f6ccefc49
Create Date: 2026-09-21 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '6a9f6ccefc49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_predictions_created_at'), 'predictions', ['created_at'], unique=False)
    # Составной индекс — обслуживает частый паттерн "последний прогноз по риск-кейсу"
    # (risks.py: latest_probability, dashboard.py: open_with_anomaly): без него Postgres
    # находит нужные строки по risk_case_id, но всё равно сортирует все прогнозы кейса в
    # памяти, чтобы найти top-1 по created_at (~0.6мс x 1200+ кейсов только на этот шаг).
    op.create_index(
        op.f('ix_predictions_risk_case_id_created_at'), 'predictions',
        ['risk_case_id', sa.text('created_at DESC')], unique=False,
    )
    # dashboard.py: последний прогноз по каждому направлению — GROUP BY category без этого
    # индекса даёт Parallel Seq Scan по всей таблице (~1.4 сек на 10M+ строк), т.к. Postgres
    # не умеет loose index scan по одному только ix_predictions_created_at при малом числе
    # различных category. С этим индексом запрос переписан на по-категорийный поиск (см.
    # backend/app/api/dashboard.py) — каждый использует Index Scan Backward + LIMIT 1.
    op.create_index(
        op.f('ix_predictions_category_created_at'), 'predictions',
        ['category', sa.text('created_at DESC')], unique=False,
    )
    op.create_index(op.f('ix_risk_cases_status'), 'risk_cases', ['status'], unique=False)
    op.create_index(op.f('ix_risk_cases_opened_at'), 'risk_cases', ['opened_at'], unique=False)
    op.create_index(op.f('ix_risk_cases_closed_at'), 'risk_cases', ['closed_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_risk_cases_closed_at'), table_name='risk_cases')
    op.drop_index(op.f('ix_risk_cases_opened_at'), table_name='risk_cases')
    op.drop_index(op.f('ix_risk_cases_status'), table_name='risk_cases')
    op.drop_index(op.f('ix_predictions_category_created_at'), table_name='predictions')
    op.drop_index(op.f('ix_predictions_risk_case_id_created_at'), table_name='predictions')
    op.drop_index(op.f('ix_predictions_created_at'), table_name='predictions')

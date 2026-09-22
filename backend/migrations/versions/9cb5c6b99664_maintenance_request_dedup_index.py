"""maintenance request dedup partial unique index

Revision ID: 9cb5c6b99664
Revises: 36d57d1932f2
Create Date: 2026-09-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = '9cb5c6b99664'
down_revision: Union[str, None] = '36d57d1932f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ловит гонку двух одновременных «направить на проверку» на одном риск-кейсе — раньше
    # ensure_request_for_dispatch делала find-then-insert без блокировки: обе транзакции могли
    # пройти find_active_request до того, как любая из них закоммитит insert, и создать дубль.
    op.execute(
        """
        CREATE UNIQUE INDEX ix_maintenance_requests_active_dedup
        ON maintenance_requests (risk_case_id, work_type)
        WHERE status NOT IN ('rejected', 'cancelled')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_maintenance_requests_active_dedup")

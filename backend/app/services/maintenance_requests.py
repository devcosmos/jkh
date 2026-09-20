"""Общая логика автосоздания заявки на обслуживание — используется и живым воркером
(app.workers.replay_worker, автоматически по правилу при открытии риск-кейса), и API решений
диспетчера (app.api.risks, при явном «направить на проверку»). Вынесено сюда, а не в
replay_worker.py, потому что тот модуль тянет catboost/pandas — тяжёлые зависимости,
которых нет (и не должно быть) в лёгком образе backend (см. backend/requirements-worker.txt
и Dockerfile.worker против Dockerfile).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AuditLog, Channel, MaintenanceRequest, RiskCase, User
from app.models.enums import MaintenanceRequestStatus

# Раздел 10 плана реализации: шаблон рекомендации по типу датчика — обязательное условие
# автосоздания заявки ("существует подходящий шаблон рекомендации").
WORK_TYPE_BY_SENSOR_TYPE = {
    "Состояние насоса": "Диагностика и техническое обслуживание насоса",
    "Состояние вентилятора": "Диагностика и техническое обслуживание вентилятора",
    "Датчик дыма": "Диагностика дымового извещателя",
    "Газовый датчик": "Диагностика газового датчика",
}


def find_active_request(db: Session, risk_case_id: int, work_type: str) -> MaintenanceRequest | None:
    return db.scalar(
        select(MaintenanceRequest).where(
            MaintenanceRequest.risk_case_id == risk_case_id,
            MaintenanceRequest.work_type == work_type,
            MaintenanceRequest.status.not_in(
                [MaintenanceRequestStatus.rejected, MaintenanceRequestStatus.cancelled]
            ),
        )
    )


def ensure_request_for_dispatch(
    db: Session, risk_case: RiskCase, channel: Channel, user: User, reason: str | None
) -> MaintenanceRequest | None:
    """Явное решение диспетчера «направить на проверку» должно быть видно в разделе
    «Заявки» — раньше решение (Decision) и заявка (MaintenanceRequest) были не связаны:
    диспетчер жал «направить», а в «Заявках» ничего не появлялось, если авто-правило по
    порогу вероятности не сработало раньше (см. docs/Статус.md). Идемпотентно: если для
    этого риск-кейса уже есть незакрытая заявка того же вида работ (созданная автоматически
    worker'ом или предыдущим решением), новую не создаёт — просто возвращает существующую.
    """
    work_type = WORK_TYPE_BY_SENSOR_TYPE.get(channel.sensor_type)
    if work_type is None:
        return None  # нет подходящего шаблона рекомендации для этого типа датчика

    existing = find_active_request(db, risk_case.id, work_type)
    if existing is not None:
        return existing

    object_name = channel.object.name if channel.object is not None else "не определён"
    justification = (
        f"Заявка создана по решению диспетчера (действие «направить на проверку») "
        f"по риск-кейсу #{risk_case.id}.\n"
        f"Канал: {channel.display_name or channel.external_channel_id} ({channel.sensor_type}).\n"
        f"Объект: {object_name}.\n"
        f"Категория риска: {risk_case.category}.\n"
        + (f"Комментарий диспетчера: {reason}\n" if reason else "")
        + "Срок: нормативный регламент не определён — требуется назначение диспетчером."
    )
    request = MaintenanceRequest(
        risk_case_id=risk_case.id,
        work_type=work_type,
        justification=justification,
        priority=risk_case.priority,
        status=MaintenanceRequestStatus.draft,
    )
    db.add(request)
    db.flush()
    db.add(
        AuditLog(
            user_id=user.id,
            role=user.role.value,
            entity_type="maintenance_request",
            entity_id=request.id,
            old_state=None,
            new_state={"status": request.status.value, "source": "dispatcher_decision"},
            reason=f"Создано по решению диспетчера на риск-кейсе #{risk_case.id}",
        )
    )
    return request

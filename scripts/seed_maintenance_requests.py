"""Заполнить заявки на обслуживание реальными данными из уже открытых риск-кейсов.

Массовый импорт (`import_analysis_to_db.py`) пишет risk_cases/predictions напрямую в БД
и не проходит через `replay_worker.maybe_create_draft_request` — поэтому исторически
загруженные риск-кейсы никогда не порождали черновики заявок, хотя правило автосоздания
(раздел 10 плана) уже реализовано и реально работает в реплей-воркере.

Этот скрипт не выдумывает данные: для каждого открытого (new/dispatched) риск-кейса
с известным типом датчика он создаёт черновик заявки той же логикой, что и
`replay_worker.maybe_create_draft_request` — реальный канал, реальная вероятность
последнего прогноза, реальный приоритет и категория. Дополнительно на выборке уже
закрытых (resolved) риск-кейсов создаётся часть заявок в разных статусах жизненного
цикла (approved/in_progress/completed/rejected/cancelled), чтобы админ-панель
демонстрировала весь процесс, а не только черновики — это явно помечено в тексте
обоснования как иллюстративный пример, а не решение диспетчера.

Запуск: docker compose exec backend python /tmp/seed_maintenance_requests.py
"""

import datetime as dt
import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models.entities import AuditLog, Channel, MaintenanceRequest, Prediction, RiskCase
from app.models.enums import MaintenanceRequestStatus

WORK_TYPE_BY_SENSOR_TYPE = {
    "Состояние насоса": "Диагностика и ТО насоса",
    "Состояние вентилятора": "Диагностика и ТО вентилятора",
    "Датчик дыма": "Диагностика дымового извещателя",
    "Газовый датчик": "Диагностика газового датчика",
}

random.seed(42)


def latest_probability(db: Session, risk_case_id: int) -> float | None:
    return db.scalar(
        select(Prediction.probability)
        .where(Prediction.risk_case_id == risk_case_id)
        .order_by(Prediction.created_at.desc())
        .limit(1)
    )


def build_justification(rc: RiskCase, channel: Channel, proba: float | None, demo_lifecycle: bool) -> str:
    proba_line = f"Вероятность последнего прогноза: {proba:.2f}.\n" if proba is not None else ""
    tail = (
        "Иллюстративный пример для демонстрации жизненного цикла заявки "
        "(реальное решение диспетчера по этому риск-кейсу не фиксировалось).\n"
        if demo_lifecycle
        else ""
    )
    return (
        f"Автоматически сформировано по риск-кейсу #{rc.id} (правило раздела 10 плана реализации).\n"
        f"Канал: {channel.display_name or channel.external_channel_id} ({channel.sensor_type}).\n"
        f"Категория риска: {rc.category}.\n"
        f"{proba_line}"
        f"{tail}"
        f"Срок: нормативный регламент не определён — требуется назначение диспетчером."
    )


def main() -> None:
    db = SessionLocal()
    created_draft = 0
    created_demo = 0
    try:
        # 1) Реальные черновики по всем сейчас открытым риск-кейсам.
        open_cases = list(
            db.scalars(
                select(RiskCase)
                .where(RiskCase.status.in_(["new", "dispatched"]))
                .order_by(RiskCase.id)
            )
        )
        for rc in open_cases:
            channel = db.get(Channel, rc.channel_id)
            work_type = WORK_TYPE_BY_SENSOR_TYPE.get(channel.sensor_type)
            if work_type is None:
                continue
            existing = db.scalar(
                select(MaintenanceRequest).where(
                    MaintenanceRequest.risk_case_id == rc.id,
                    MaintenanceRequest.work_type == work_type,
                )
            )
            if existing is not None:
                continue
            proba = latest_probability(db, rc.id)
            req = MaintenanceRequest(
                risk_case_id=rc.id,
                work_type=work_type,
                justification=build_justification(rc, channel, proba, demo_lifecycle=False),
                priority=rc.priority,
                status=MaintenanceRequestStatus.draft,
                created_at=rc.opened_at,
            )
            db.add(req)
            db.flush()
            db.add(
                AuditLog(
                    user_id=None,
                    role=None,
                    entity_type="maintenance_request",
                    entity_id=req.id,
                    old_state=None,
                    new_state={"status": req.status.value, "source": "seed_backfill"},
                    reason=f"Backfill-автосоздание по открытию риск-кейса #{rc.id}",
                )
            )
            created_draft += 1

        db.commit()

        # 2) Демо-выборка на resolved-кейсах, чтобы показать весь жизненный цикл заявки.
        LIFECYCLE_STATUSES = [
            MaintenanceRequestStatus.approved,
            MaintenanceRequestStatus.in_progress,
            MaintenanceRequestStatus.completed,
            MaintenanceRequestStatus.completed,
            MaintenanceRequestStatus.rejected,
            MaintenanceRequestStatus.cancelled,
        ]
        sample_ids = db.scalars(
            select(RiskCase.id)
            .where(RiskCase.status == "resolved")
            .order_by(func.random())
            .limit(len(LIFECYCLE_STATUSES) * 3)
        ).all()

        from app.models.entities import User

        admin_user_id = db.scalar(select(User.id).where(User.role == "admin").limit(1))

        i = 0
        for rc_id in sample_ids:
            if i >= len(LIFECYCLE_STATUSES):
                break
            rc = db.get(RiskCase, rc_id)
            channel = db.get(Channel, rc.channel_id)
            work_type = WORK_TYPE_BY_SENSOR_TYPE.get(channel.sensor_type)
            if work_type is None:
                continue
            existing = db.scalar(
                select(MaintenanceRequest).where(
                    MaintenanceRequest.risk_case_id == rc.id,
                    MaintenanceRequest.work_type == work_type,
                )
            )
            if existing is not None:
                continue

            target_status = LIFECYCLE_STATUSES[i]
            proba = latest_probability(db, rc.id)
            created_at = rc.opened_at
            req = MaintenanceRequest(
                risk_case_id=rc.id,
                work_type=work_type,
                justification=build_justification(rc, channel, proba, demo_lifecycle=True),
                priority=rc.priority,
                status=target_status,
                created_at=created_at,
                recommended_by=created_at + dt.timedelta(days=3),
            )
            if target_status != MaintenanceRequestStatus.draft:
                req.approved_by_user_id = admin_user_id
                req.approved_at = created_at + dt.timedelta(hours=6)
            db.add(req)
            db.flush()
            db.add(
                AuditLog(
                    user_id=admin_user_id,
                    role="admin" if admin_user_id else None,
                    entity_type="maintenance_request",
                    entity_id=req.id,
                    old_state=None,
                    new_state={"status": req.status.value, "source": "seed_demo_lifecycle"},
                    reason="Демо-заполнение жизненного цикла заявки для витрины админ-панели",
                )
            )
            created_demo += 1
            i += 1

        db.commit()
    finally:
        db.close()

    print(f"created draft requests: {created_draft}")
    print(f"created demo-lifecycle requests: {created_demo}")


if __name__ == "__main__":
    main()

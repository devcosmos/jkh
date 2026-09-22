"""Минимальные синтетические данные для E2E (OPS-03 в analys_and_todo.md) — не настоящий
демонстрационный набор (тот требует закрытого датасета, см. README.md, раздел «Быстрый
старт») и не пересекается с ним по содержанию. Идемпотентен: повторный запуск на уже
заполненной этими фикстурами БД не падает на уникальных ограничениях (проверяет наличие по
username/external_channel_id перед вставкой).

Создаёт:
- пользователя admin/demo-local-2026 (совпадает с DEMO_USERNAME/DEMO_PASSWORD в
  frontend/src/pages/LoginPage.tsx — форма логина в E2E ничего вводить не должна);
- пользователя dispatcher-a/dispatcher-a-pass с доступом только к объекту A
  (для сценария «запрет чужого объекта»);
- два объекта (A, B), по одному каналу насос/вентилятор на каждый;
- риск-кейс на объекте A (status=new, priority=high) — для сценария риск → решение → заявка;
- риск-кейс на объекте B (status=new) — диспетчер объекта A не должен его видеть/получить.

Запуск: JKH_DATABASE_URL=... python3 scripts/demo/seed_e2e_fixtures.py
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.entities import Channel, Object, RiskCase, User, UserObjectAccess  # noqa: E402
from app.models.enums import RiskCaseStatus, UserRole  # noqa: E402

NOW = dt.datetime.now(dt.timezone.utc)


def get_or_create_user(db, username: str, password: str, role: UserRole) -> User:
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        user = User(username=username, password_hash=hash_password(password), role=role, is_active=True)
        db.add(user)
        db.flush()
    return user


def get_or_create_object(db, external_id: str, name: str) -> Object:
    obj = db.scalar(select(Object).where(Object.external_id == external_id))
    if obj is None:
        obj = Object(external_id=external_id, hierarchy_level=1, kind="объект", name=name)
        db.add(obj)
        db.flush()
    return obj


def get_or_create_channel(db, external_channel_id: int, object_id: int, display_name: str) -> Channel:
    channel = db.scalar(select(Channel).where(Channel.external_channel_id == external_channel_id))
    if channel is None:
        channel = Channel(
            external_channel_id=external_channel_id,
            sensor_type="Состояние насоса",
            object_id=object_id,
            display_name=display_name,
            location_group="e2e-group",
        )
        db.add(channel)
        db.flush()
    return channel


def get_or_create_risk_case(db, channel_id: int, priority: str, opened_at: dt.datetime) -> RiskCase:
    rc = db.scalar(
        select(RiskCase).where(RiskCase.channel_id == channel_id, RiskCase.status == RiskCaseStatus.new)
    )
    if rc is None:
        rc = RiskCase(
            channel_id=channel_id,
            category="sensor_failure_pump_fan",
            status=RiskCaseStatus.new,
            priority=priority,
            opened_at=opened_at,
        )
        db.add(rc)
        db.flush()
    return rc


def main() -> None:
    db = SessionLocal()
    try:
        get_or_create_user(db, "admin", "demo-local-2026", UserRole.admin)
        dispatcher_a = get_or_create_user(db, "dispatcher-a", "dispatcher-a-pass", UserRole.dispatcher)

        object_a = get_or_create_object(db, "e2e-object-a", "E2E объект A")
        object_b = get_or_create_object(db, "e2e-object-b", "E2E объект B")

        if db.scalar(
            select(UserObjectAccess).where(
                UserObjectAccess.user_id == dispatcher_a.id, UserObjectAccess.object_id == object_a.id
            )
        ) is None:
            db.add(UserObjectAccess(user_id=dispatcher_a.id, object_id=object_a.id))

        channel_a = get_or_create_channel(db, 900001, object_a.id, "E2E Насос A")
        channel_b = get_or_create_channel(db, 900002, object_b.id, "E2E Насос B")

        risk_a = get_or_create_risk_case(db, channel_a.id, "high", NOW - dt.timedelta(hours=2))
        risk_b = get_or_create_risk_case(db, channel_b.id, "medium", NOW - dt.timedelta(hours=1))

        db.commit()
        print(f"seeded: object_a={object_a.id} object_b={object_b.id} risk_a={risk_a.id} risk_b={risk_b.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

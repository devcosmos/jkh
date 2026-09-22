"""Иерархическая схема объектов вместо GPS-карты (координаты объектов не будут
предоставлены никогда — см. docs/deliverables/Матрица_соответствия_ТЗ.md). Дерево строится по
Object.parent_id, риск агрегируется снизу вверх по открытым риск-кейсам."""
import datetime as dt

from app.models.entities import Channel, Object, RiskCase, UserObjectAccess
from app.models.enums import RiskCaseStatus, UserRole


def _channel_with_case(db_session, obj: Object, ext_channel_id: int, priority: str, status: RiskCaseStatus):
    channel = Channel(external_channel_id=ext_channel_id, sensor_type="Состояние насоса", object_id=obj.id)
    db_session.add(channel)
    db_session.flush()
    rc = RiskCase(
        channel_id=channel.id,
        status=status,
        priority=priority,
        opened_at=dt.datetime.now(dt.timezone.utc),
    )
    db_session.add(rc)
    db_session.commit()
    return channel, rc


def test_risk_aggregates_up_the_hierarchy(client, db_session, auth_headers):
    root = Object(name="Коллектор")
    db_session.add(root)
    db_session.flush()
    child = Object(name="Насосная", parent_id=root.id)
    db_session.add(child)
    db_session.commit()

    _channel_with_case(db_session, child, 9001, priority="high", status=RiskCaseStatus.new)

    headers = auth_headers(UserRole.dispatcher)  # без назначений -> не ограничен
    r = client.get("/api/objects/tree", headers=headers)
    assert r.status_code == 200
    roots = r.json()["roots"]
    root_node = next(n for n in roots if n["id"] == root.id)
    assert root_node["own_max_priority_rank"] == 0  # риск не на самом объекте-корне
    assert root_node["aggregated_max_priority"] == "high"  # а на потомке
    assert root_node["aggregated_open_risk_count"] == 1
    child_node = root_node["children"][0]
    assert child_node["own_open_risk_count"] == 1
    assert child_node["aggregated_max_priority"] == "high"


def test_resolved_case_does_not_count_as_open_risk(client, db_session, auth_headers):
    obj = Object(name="Объект без открытого риска")
    db_session.add(obj)
    db_session.commit()
    _channel_with_case(db_session, obj, 9002, priority="high", status=RiskCaseStatus.resolved)

    headers = auth_headers(UserRole.dispatcher)
    r = client.get("/api/objects/tree", headers=headers)
    node = next(n for n in r.json()["roots"] if n["id"] == obj.id)
    assert node["aggregated_open_risk_count"] == 0
    assert node["aggregated_max_priority"] == "none"


def test_restricted_user_only_sees_assigned_object_in_tree(client, db_session, auth_headers):
    from app.models.entities import User

    obj_a = Object(name="Доступный объект")
    obj_b = Object(name="Недоступный объект")
    db_session.add_all([obj_a, obj_b])
    db_session.commit()

    headers = auth_headers(UserRole.dispatcher, username="tree-restricted")
    user = db_session.query(User).filter_by(username="tree-restricted").one()
    db_session.add(UserObjectAccess(user_id=user.id, object_id=obj_a.id))
    db_session.commit()

    r = client.get("/api/objects/tree", headers=headers)
    ids = {n["id"] for n in r.json()["roots"]}
    assert ids == {obj_a.id}

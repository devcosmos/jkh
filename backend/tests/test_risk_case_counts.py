"""GET /risk-cases/counts: счётчики по статусу/приоритету должны считаться по всей
отфильтрованной выборке, а не только по первой странице (лимит списка — 20 строк на
странице «Риски» админ-панели, плашки над списком раньше вводили в заблуждение на
выборках больше 20). Путь — /counts, не /stats: см. комментарий в app/api/risks.py —
часть блокировщиков рекламы молча режет любой URL с /stats как аналитику."""
import datetime as dt

from app.models.entities import Channel, RiskCase
from app.models.enums import RiskCaseStatus, UserRole

NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def _make_case(db_session, ext_id: int, status: RiskCaseStatus, priority: str | None) -> RiskCase:
    channel = Channel(external_channel_id=ext_id, sensor_type="Состояние насоса")
    db_session.add(channel)
    db_session.flush()
    rc = RiskCase(channel_id=channel.id, status=status, priority=priority, opened_at=NOW)
    db_session.add(rc)
    db_session.commit()
    db_session.refresh(rc)
    return rc


def test_stats_counts_beyond_default_page_size(client, db_session, auth_headers):
    # 25 критичных кейсов — больше дефолтного лимита страницы (20) на фронте.
    for i in range(25):
        _make_case(db_session, 9301 + i, RiskCaseStatus.new, "high")

    r = client.get("/api/risk-cases/counts", headers=auth_headers(UserRole.dispatcher))
    assert r.status_code == 200
    body = r.json()
    assert body["critical"] == 25
    assert body["fresh"] == 25

    # Список той же выборки с дефолтным лимитом видит только 20 — счётчик не должен совпадать
    # со страницей.
    r2 = client.get("/api/risk-cases?limit=20", headers=auth_headers(UserRole.dispatcher))
    assert len(r2.json()) == 20
    assert body["critical"] != len(r2.json())


def test_stats_respects_filters(client, db_session, auth_headers):
    _make_case(db_session, 9401, RiskCaseStatus.new, "high")
    _make_case(db_session, 9402, RiskCaseStatus.observing, "medium")
    _make_case(db_session, 9403, RiskCaseStatus.resolved, "high")

    r = client.get(
        "/api/risk-cases/counts", params={"status": "new"}, headers=auth_headers(UserRole.dispatcher)
    )
    body = r.json()
    assert body["critical"] == 1
    assert body["fresh"] == 1
    assert body["open"] == 1  # исключён фильтром status=new — observing/resolved не в счёте

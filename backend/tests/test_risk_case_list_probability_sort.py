"""GET /risk-cases: вероятность последнего прогноза в списке и сортировка по ней
(раздел «Риски» админ-панели — диспетчер должен видеть и сортировать по вероятности
отказа прямо в таблице, не открывая каждую карточку)."""
import datetime as dt

from app.models.entities import Channel, ModelVersion, Prediction, RiskCase
from app.models.enums import RiskCaseStatus, UserRole

NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def _make_case_with_predictions(db_session, ext_id: int, probabilities: list[float]) -> RiskCase:
    channel = Channel(external_channel_id=ext_id, sensor_type="Состояние насоса")
    db_session.add(channel)
    db_session.flush()
    mv = ModelVersion(
        name="test", sensor_types="Состояние насоса", trained_at=NOW, train_period_start=NOW, train_period_end=NOW,
        is_active=True,
    )
    db_session.add(mv)
    db_session.flush()
    rc = RiskCase(channel_id=channel.id, status=RiskCaseStatus.new, priority="medium", opened_at=NOW)
    db_session.add(rc)
    db_session.flush()
    for i, proba in enumerate(probabilities):
        db_session.add(
            Prediction(
                channel_id=channel.id,
                risk_case_id=rc.id,
                model_version_id=mv.id,
                category="sensor_failure_pump_fan",
                probability=proba,
                window_start=NOW,
                window_end=NOW,
                created_at=NOW + dt.timedelta(hours=i),
            )
        )
    db_session.commit()
    db_session.refresh(rc)
    return rc


def test_list_returns_latest_prediction_probability(client, db_session, auth_headers):
    rc = _make_case_with_predictions(db_session, 9101, [0.6, 0.75])
    r = client.get("/api/risk-cases", headers=auth_headers(UserRole.dispatcher))
    assert r.status_code == 200
    body = next(x for x in r.json() if x["id"] == rc.id)
    assert body["latest_probability"] == 0.75  # последний по времени, не первый/максимум


def test_sort_by_probability_desc(client, db_session, auth_headers):
    low = _make_case_with_predictions(db_session, 9102, [0.55])
    high = _make_case_with_predictions(db_session, 9103, [0.91])

    r = client.get("/api/risk-cases?sort_by=probability&sort_dir=desc", headers=auth_headers(UserRole.dispatcher))
    ids = [x["id"] for x in r.json()]
    assert ids.index(high.id) < ids.index(low.id)


def test_sort_by_probability_asc(client, db_session, auth_headers):
    low = _make_case_with_predictions(db_session, 9104, [0.55])
    high = _make_case_with_predictions(db_session, 9105, [0.91])

    r = client.get("/api/risk-cases?sort_by=probability&sort_dir=asc", headers=auth_headers(UserRole.dispatcher))
    ids = [x["id"] for x in r.json()]
    assert ids.index(low.id) < ids.index(high.id)


def test_opened_after_filters_out_older_cases(client, db_session, auth_headers):
    """Поллинг критических уведомлений (RiskAlerts.tsx) раньше брал top-10 по opened_at и
    сравнивал ID с предыдущим опросом — при всплеске больше 10 новых критических кейсов за
    один интервал опроса лишние никогда бы не попали ни в один последующий ответ. opened_after
    даёт водораздел: «всё новее X», а не «последние N», независимо от размера всплеска."""
    older = _make_case_with_predictions(db_session, 9106, [0.6])
    newer = _make_case_with_predictions(db_session, 9107, [0.6])
    newer.opened_at = NOW + dt.timedelta(hours=1)
    db_session.commit()

    watermark = (NOW + dt.timedelta(minutes=30)).isoformat()
    r = client.get(
        "/api/risk-cases", params={"opened_after": watermark}, headers=auth_headers(UserRole.dispatcher)
    )
    assert r.status_code == 200
    ids = {x["id"] for x in r.json()}
    assert ids == {newer.id}
    assert older.id not in ids


def test_opened_after_with_same_timestamp_tie_break_by_id(client, db_session, auth_headers):
    """APP-02: несколько риск-кейсов одного тика replay делят opened_at. Без тай-брейка по ID
    строгий фильтр opened_at > watermark либо теряет строки за пределами первой страницы
    (watermark = opened_at последней показанной строки исключает соседей с тем же opened_at,
    показанных или ещё нет — одинаково), либо повторяет уже показанные. opened_after + after_id
    должны показать оставшиеся кейсы той же группы ровно один раз, без повторов и пропусков."""
    same_ts = NOW + dt.timedelta(hours=2)
    cases = []
    for i, ext_id in enumerate([9201, 9202, 9203, 9204]):
        rc = _make_case_with_predictions(db_session, ext_id, [0.6])
        rc.opened_at = same_ts
        cases.append(rc)
    db_session.commit()
    cases.sort(key=lambda c: c.id)

    # Первая "страница" опроса — только первые два кейса той же группы уже показаны клиенту,
    # курсор — последний из них (opened_at, id).
    seen_first = cases[:2]
    watermark_id = seen_first[-1].id

    r = client.get(
        "/api/risk-cases",
        params={"opened_after": same_ts.isoformat(), "after_id": watermark_id, "sort_dir": "asc"},
        headers=auth_headers(UserRole.dispatcher),
    )
    assert r.status_code == 200
    ids = [x["id"] for x in r.json() if x["id"] in {c.id for c in cases}]
    remaining_ids = [c.id for c in cases[2:]]
    assert ids == remaining_ids  # ровно оставшиеся два, без повторов и без потери

    # Без after_id (старое поведение) строгое сравнение по opened_at одинаково исключает и уже
    # показанные, и ещё не показанные кейсы группы — regression guard на старую логику.
    r_no_tiebreak = client.get(
        "/api/risk-cases",
        params={"opened_after": same_ts.isoformat(), "sort_dir": "asc"},
        headers=auth_headers(UserRole.dispatcher),
    )
    ids_no_tiebreak = {x["id"] for x in r_no_tiebreak.json()}
    assert not ids_no_tiebreak & {c.id for c in cases}

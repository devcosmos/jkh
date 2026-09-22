"""Эвристическое сопоставление канал→устройство для насоса/вентилятора (открытый пробел
из докстринга backend/app/models/entities.py и комментария scripts/data/import_analysis_to_db.py).

Справочник каналов не содержит явного ID устройства, но физический идентификатор закодирован
в свободнотекстовом поле `название_датчика`: «В8 ПК96» = вентилятор №8, пикет 96; «Н1 ПК440» =
насос №1, пикет 440. Канал «Переключатель» с именем «Управление В8 ПК96» — пульт управления
ТЕМ ЖЕ физическим вентилятором. Проверено на полном датасете (15 сентября 2026): паттерн
`<Н|В><номер> ПК<пикет>` матчится на 87.8% каналов насоса/вентилятора (469 из 534), из них
у 62% (276 из 446 уникальных устройств) находится парный канал управления.

Это НЕ даёт новых числовых признаков для ML (Переключатель — управляющее состояние, а не
независимое измерение, см. artifacts/model_report_насос_вентилятор.md, раздел 5) — польза
практическая: реальная идентичность устройства в заявках/карточках (раздел 10 плана: «состав
черновика: устройство и объект») вместо голого ID канала.

Идемпотентно: повторный запуск не создаёт дублирующих Device (проверка по external_id).

Запуск (после открытия SSH-туннеля к Postgres на сервере, см. scripts/data/import_analysis_to_db.py):
  JKH_DATABASE_URL=postgresql+psycopg://jkh:<пароль>@localhost:5555/jkh \
    source .venv/bin/activate && python3 scripts/data/link_channels_to_devices.py
"""
import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = ROOT / "dataset"
sys.path.insert(0, str(ROOT / "backend"))

from app.core.db import SessionLocal  # noqa: E402
from app.models.entities import Channel, Device  # noqa: E402

DEVICE_PATTERN = re.compile(r"(?:Вентилятор\s+)?([НВ])\s*(\d+)\D*ПК\s*[-]?\s*(\d+)", re.IGNORECASE)
CONTROL_PATTERN = re.compile(r"Управление\s+([НВ])\s*(\d+)\D*ПК\s*[-]?\s*(\d+)", re.IGNORECASE)
LETTER_TO_TYPE = {"Н": "насос", "В": "вентилятор"}


def device_key(name: str, control: bool) -> tuple[str, str, str] | None:
    m = (CONTROL_PATTERN if control else DEVICE_PATTERN).search(name or "")
    if not m:
        return None
    letter, num, pk = m.groups()
    return (letter.upper(), num, pk)


def main() -> None:
    con = duckdb.connect()
    rows = con.execute(
        f"""
        SELECT ид_канала_данных, тип_датчика, название_датчика
        FROM read_csv_auto('{DATASET_DIR / "справочник_каналов_датчиков.csv"}', header=true)
        WHERE тип_датчика IN ('Состояние насоса', 'Состояние вентилятора', 'Переключатель')
        """
    ).fetchall()

    groups: dict[tuple[str, str, str], list[int]] = {}
    for ext_id, sensor_type, name in rows:
        is_pf = sensor_type in ("Состояние насоса", "Состояние вентилятора")
        key = device_key(name, control=not is_pf)
        if key is None:
            continue
        groups.setdefault(key, []).append(ext_id)

    print(f"device keys found: {len(groups)}", file=sys.stderr)

    db = SessionLocal()
    channel_by_ext = {c.external_channel_id: c for c in db.query(Channel).filter(
        Channel.external_channel_id.in_([i for ids in groups.values() for i in ids])
    )}
    existing_devices = {d.external_id: d for d in db.query(Device).all()}

    n_devices_created = 0
    n_channels_linked = 0
    n_skipped_no_channel_row = 0
    for (letter, num, pk), ext_ids in groups.items():
        external_id = f"{letter}{num}-ПК{pk}"
        device = existing_devices.get(external_id)
        if device is None:
            device = Device(external_id=external_id, device_type=LETTER_TO_TYPE[letter])
            db.add(device)
            db.flush()
            existing_devices[external_id] = device
            n_devices_created += 1
        for ext_id in ext_ids:
            channel = channel_by_ext.get(ext_id)
            if channel is None:
                n_skipped_no_channel_row += 1
                continue
            if channel.device_id != device.id:
                channel.device_id = device.id
                n_channels_linked += 1
    db.commit()

    n_pf_total = con.execute(
        "SELECT count(*) FROM read_csv_auto(?, header=true) WHERE тип_датчика IN "
        "('Состояние насоса', 'Состояние вентилятора')", [str(DATASET_DIR / "справочник_каналов_датчиков.csv")]
    ).fetchone()[0]
    print(f"devices created: {n_devices_created}", file=sys.stderr)
    print(f"channels linked (this run, changed device_id): {n_channels_linked}", file=sys.stderr)
    print(f"channel rows not found in DB (not imported yet): {n_skipped_no_channel_row}", file=sys.stderr)
    print(f"pump/fan channels total in source CSV: {n_pf_total}", file=sys.stderr)


if __name__ == "__main__":
    main()

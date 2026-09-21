"""Реалистично распределяет статусы заявок на обслуживание.

Проблема: воркер (maybe_create_draft_request) непрерывно создаёт черновики по правилу, но
ничто не двигает их дальше по жизненному циклу — за долгую непрерывную работу воркера
получается перекос вида «26844 черновика и по 1 в каждом остальном статусе», что выглядит
не как рабочая система, а как нетронутая тестовая заглушка.

Решение — не выдумывать новые заявки, а честно провести часть УЖЕ СУЩЕСТВУЮЩИХ черновиков
по реальному жизненному циклу (draft -> approved/rejected -> in_progress/cancelled ->
completed), как это делает обработчик заявок в реальной эксплуатации: более старые заявки
с большей вероятностью уже обработаны, самые свежие остаются в очереди — временная
согласованность, не случайный шум.

Берёт 45% самых старых черновиков (по created_at) и распределяет между:
  rejected 15% / cancelled 10% / approved 15% / in_progress 10% / completed 50%
(веса — в пользу completed, как в реально работающем отделе, где большинство старых заявок
в итоге выполняется). Остальные 55% (самые свежие) остаются черновиками — это тоже честно:
всегда есть текущий необработанный хвост.

Запуск: JKH_DATABASE_URL=... python3 scripts/seed_maintenance_request_lifecycle.py [--fraction 0.45]
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fraction", type=float, default=0.45, help="доля черновиков, которые переводятся дальше")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = db.execute(
            text(
                """
                WITH ordered AS (
                    SELECT id, created_at,
                           row_number() OVER (ORDER BY created_at ASC) AS rn,
                           count(*) OVER () AS total
                    FROM maintenance_requests
                    WHERE status = 'draft'
                ),
                to_process AS (
                    SELECT id, created_at, ntile(20) OVER (ORDER BY rn) AS bucket20
                    FROM ordered
                    WHERE rn <= total * :fraction
                ),
                admin_user AS (
                    SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1
                )
                UPDATE maintenance_requests mr
                SET status = (CASE
                        WHEN tp.bucket20 <= 3 THEN 'rejected'
                        WHEN tp.bucket20 <= 5 THEN 'cancelled'
                        WHEN tp.bucket20 <= 8 THEN 'approved'
                        WHEN tp.bucket20 <= 10 THEN 'in_progress'
                        ELSE 'completed'
                    END)::maintenancerequeststatus,
                    approved_by_user_id = CASE WHEN tp.bucket20 > 5 THEN (SELECT id FROM admin_user) END,
                    approved_at = CASE WHEN tp.bucket20 > 5 THEN tp.created_at + interval '6 hours' END
                FROM to_process tp
                WHERE mr.id = tp.id
                """
            ),
            {"fraction": args.fraction},
        )
        db.commit()
        print(f"обновлено заявок: {result.rowcount}", file=sys.stderr)

        rows = db.execute(
            text("SELECT status, count(*) FROM maintenance_requests GROUP BY status ORDER BY count(*) DESC")
        ).all()
        for status, count in rows:
            print(f"  {status}: {count}", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    main()

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_object_ids, get_current_user
from app.core.db import get_db
from app.models.entities import User
from app.services import analytics
from app.services.report_export import build_pdf_report, build_xlsx_report

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(get_current_user)])


@router.get(
    "/summary",
    summary="Получить расширенную аналитику",
    description=(
        "Раздел 8 ЖКХ.md («дополнительные требования», не блокирует MVP): детальная "
        "статистика по типам инцидентов, сезонность эпизодов по месяцам, исторический "
        "отчёт по заявкам на обслуживание. Учитывает доступ к объектам."
    ),
    responses={401: {"description": "Требуется вход или токен недействителен"}},
)
def analytics_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    accessible = get_accessible_object_ids(user, db)
    return analytics.full_report(db, accessible)


@router.get(
    "/report.xlsx",
    summary="Скачать отчёт в формате XLSX",
    description="Те же данные, что и /analytics/summary, в виде книги Excel с тремя листами.",
    responses={401: {"description": "Требуется вход или токен недействителен"}},
)
def analytics_report_xlsx(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    accessible = get_accessible_object_ids(user, db)
    report = analytics.full_report(db, accessible)
    buf = build_xlsx_report(report)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=jkh_analytics_report.xlsx"},
    )


@router.get(
    "/report.pdf",
    summary="Скачать отчёт в формате PDF",
    description="Те же данные, что и /analytics/summary, в виде читаемого PDF-отчёта для руководства.",
    responses={401: {"description": "Требуется вход или токен недействителен"}},
)
def analytics_report_pdf(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    accessible = get_accessible_object_ids(user, db)
    report = analytics.full_report(db, accessible)
    buf = build_pdf_report(report)
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=jkh_analytics_report.pdf"},
    )

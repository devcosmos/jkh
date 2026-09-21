"""Формирование аналитических отчётов для руководства в PDF и XLSX (раздел 8 ЖКХ.md,
«дополнительные интерфейсы») — настоящие форматы, не CSV, который приходится открывать
в Excel вручную. Данные — те же агрегаты, что отдаёт /analytics/summary, никакой
отдельной логики специально для отчёта."""

import io
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HEADER_FONT = Font(bold=True)

# reportlab по умолчанию знает только латинские Type1-шрифты (Helvetica и т.п.) — кириллица
# на них рендерится пустыми квадратами. DejaVu Sans (публичный домен, идёт в комплекте с
# matplotlib именно для таких случаев) — растровые формы для кириллицы у него есть.
_FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_FONT_REGULAR = "DejaVuSans"
_FONT_BOLD = "DejaVuSans-Bold"
if _FONT_REGULAR not in pdfmetrics.getRegisteredFontNames():
    pdfmetrics.registerFont(TTFont(_FONT_REGULAR, str(_FONTS_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(_FONT_BOLD, str(_FONTS_DIR / "DejaVuSans-Bold.ttf")))


def _autosize(ws) -> None:
    for col in ws.columns:
        width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(width + 2, 50)


def build_xlsx_report(report: dict) -> io.BytesIO:
    wb = Workbook()

    ws = wb.active
    ws.title = "Типы инцидентов"
    ws.append(["Тип датчика", "Эпизодов (без флаппинга)", "Риск-кейсов всего", "Открыто сейчас", "Средняя вероятность (открытые)"])
    for cell in ws[1]:
        cell.font = HEADER_FONT
    for row in report["incident_types"]:
        ws.append([
            row["sensor_type"],
            row["episode_count"],
            row["risk_case_count"],
            row["open_risk_case_count"],
            row["avg_open_probability"],
        ])
    _autosize(ws)

    ws2 = wb.create_sheet("Сезонность")
    ws2.append(["Месяц", "Эпизодов (без флаппинга)"])
    for cell in ws2[1]:
        cell.font = HEADER_FONT
    for row in report["seasonal"]:
        ws2.append([row["month_name"], row["episode_count"]])
    _autosize(ws2)

    ws3 = wb.create_sheet("Заявки — виды работ")
    ws3.append(["Вид работы", "Количество"])
    for cell in ws3[1]:
        cell.font = HEADER_FONT
    for row in report["maintenance"]["by_work_type"]:
        ws3.append([row["work_type"], row["count"]])
    _autosize(ws3)

    ws4 = wb.create_sheet("Заявки — статусы")
    ws4.append(["Статус", "Количество"])
    for cell in ws4[1]:
        cell.font = HEADER_FONT
    for row in report["maintenance"]["by_status"]:
        ws4.append([row["status"], row["count"]])
    if report["maintenance"]["avg_hours_to_approval"] is not None:
        ws4.append([])
        ws4.append(["Среднее время до утверждения, часов", report["maintenance"]["avg_hours_to_approval"]])
    _autosize(ws4)

    ws5 = wb.create_sheet("Заявки по месяцам")
    ws5.append(["Месяц", "Создано заявок"])
    for cell in ws5[1]:
        cell.font = HEADER_FONT
    for row in report["maintenance"]["monthly"]:
        ws5.append([row["month"], row["request_count"]])
    _autosize(ws5)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _table(headers: list[str], rows: list[list], col_widths: list[float] | None = None) -> Table:
    data = [headers] + rows
    t = Table(data, colWidths=col_widths)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E2761")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
                ("FONTNAME", (0, 1), (-1, -1), _FONT_REGULAR),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def build_pdf_report(report: dict) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm
    )
    styles = getSampleStyleSheet()
    styles["Normal"].fontName = _FONT_REGULAR
    styles["Title"].fontName = _FONT_BOLD
    styles["Heading2"].fontName = _FONT_BOLD
    story = [
        Paragraph("Аналитический отчёт — сервис прогнозирования отказов датчиков", styles["Title"]),
        Paragraph(f"Сформирован: {report['generated_at']}", styles["Normal"]),
        Spacer(1, 0.6 * cm),
        Paragraph("Детальная статистика по типам инцидентов", styles["Heading2"]),
        _table(
            ["Тип датчика", "Эпизодов", "Риск-кейсов", "Открыто", "Ср. вероятность"],
            [
                [
                    r["sensor_type"],
                    str(r["episode_count"]),
                    str(r["risk_case_count"]),
                    str(r["open_risk_case_count"]),
                    f"{r['avg_open_probability']:.0%}" if r["avg_open_probability"] is not None else "—",
                ]
                for r in report["incident_types"]
            ],
        ),
        Spacer(1, 0.6 * cm),
        Paragraph("Сезонность (эпизоды по месяцам, без флаппинга)", styles["Heading2"]),
        _table(
            ["Месяц", "Эпизодов"],
            [[r["month_name"], str(r["episode_count"])] for r in report["seasonal"]],
        ),
        Spacer(1, 0.6 * cm),
        Paragraph("Заявки на обслуживание — по виду работ", styles["Heading2"]),
        _table(
            ["Вид работы", "Количество"],
            [[r["work_type"], str(r["count"])] for r in report["maintenance"]["by_work_type"]],
        ),
        Spacer(1, 0.4 * cm),
        Paragraph("Заявки на обслуживание — по статусу", styles["Heading2"]),
        _table(
            ["Статус", "Количество"],
            [[r["status"], str(r["count"])] for r in report["maintenance"]["by_status"]],
        ),
    ]
    if report["maintenance"]["avg_hours_to_approval"] is not None:
        story.append(Spacer(1, 0.3 * cm))
        story.append(
            Paragraph(
                f"Среднее время от создания заявки до утверждения: "
                f"{report['maintenance']['avg_hours_to_approval']:.1f} ч.",
                styles["Normal"],
            )
        )

    doc.build(story)
    buf.seek(0)
    return buf

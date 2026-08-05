import io
import datetime
import csv
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


def generate_monthly_report_excel(project, month: str, results_summary: list[dict]) -> bytes:
    """
    project: ProjectRead or ORM model with .name, .branch, .work_type
    month: "YYYY-MM"
    results_summary: list of dicts with keys: category, item_name, quantity, unit, factor_value, co2_kg
    Returns bytes of xlsx file.
    """
    wb = Workbook()

    # --- Sheet 1: 月次CO2レポート ---
    ws1 = wb.active
    ws1.title = "月次CO2レポート"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2E75B6", end_color="2E75B6", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    # Project info section
    ws1["A1"] = "プロジェクト名"
    ws1["B1"] = getattr(project, "name", "")
    ws1["A2"] = "支店"
    ws1["B2"] = getattr(project, "branch", "")
    ws1["A3"] = "工種"
    ws1["B3"] = getattr(project, "work_type", "")
    ws1["A4"] = "対象月"
    ws1["B4"] = month
    ws1["A5"] = "レポート作成日"
    ws1["B5"] = datetime.date.today().strftime("%Y-%m-%d")

    for row in range(1, 6):
        ws1[f"A{row}"].font = Font(bold=True)

    # Summary table by category
    ws1["A7"] = "カテゴリ別CO2排出量サマリー"
    ws1["A7"].font = Font(bold=True, size=12)

    headers = ["カテゴリ", "CO2排出量 (kg-CO2)"]
    for col, h in enumerate(headers, start=1):
        cell = ws1.cell(row=8, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    # Aggregate by category
    category_totals: dict[str, float] = {}
    for r in results_summary:
        cat = r.get("category", "other")
        category_totals[cat] = category_totals.get(cat, 0.0) + r.get("co2_kg", 0.0)

    row_num = 9
    total_co2 = 0.0
    for cat, co2 in sorted(category_totals.items()):
        ws1.cell(row=row_num, column=1, value=cat).border = thin_border
        co2_cell = ws1.cell(row=row_num, column=2, value=round(co2, 3))
        co2_cell.border = thin_border
        co2_cell.alignment = Alignment(horizontal="right")
        co2_cell.number_format = "#,##0.000"
        total_co2 += co2
        row_num += 1

    # Total row
    total_label = ws1.cell(row=row_num, column=1, value="合計")
    total_label.font = Font(bold=True)
    total_label.border = thin_border
    total_value = ws1.cell(row=row_num, column=2, value=round(total_co2, 3))
    total_value.font = Font(bold=True)
    total_value.border = thin_border
    total_value.alignment = Alignment(horizontal="right")
    total_value.number_format = "#,##0.000"

    # Set column widths
    ws1.column_dimensions["A"].width = 25
    ws1.column_dimensions["B"].width = 25

    # --- Sheet 2: 活動量詳細 ---
    ws2 = wb.create_sheet(title="活動量詳細")

    detail_headers = ["カテゴリ", "品目", "数量", "単位", "排出係数 (kg-CO2/unit)", "CO2排出量 (kg-CO2)"]
    for col, h in enumerate(detail_headers, start=1):
        cell = ws2.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    for row_idx, r in enumerate(results_summary, start=2):
        ws2.cell(row=row_idx, column=1, value=r.get("category", "")).border = thin_border
        ws2.cell(row=row_idx, column=2, value=r.get("item_name", "")).border = thin_border
        qty_cell = ws2.cell(row=row_idx, column=3, value=r.get("quantity", 0))
        qty_cell.border = thin_border
        qty_cell.number_format = "#,##0.000"
        ws2.cell(row=row_idx, column=4, value=r.get("unit", "")).border = thin_border
        fv_cell = ws2.cell(row=row_idx, column=5, value=r.get("factor_value", 0))
        fv_cell.border = thin_border
        fv_cell.number_format = "0.000"
        co2_cell = ws2.cell(row=row_idx, column=6, value=round(r.get("co2_kg", 0), 3))
        co2_cell.border = thin_border
        co2_cell.number_format = "#,##0.000"

    # Set column widths
    col_widths = [15, 20, 12, 10, 25, 22]
    for col_idx, width in enumerate(col_widths, start=1):
        ws2.column_dimensions[get_column_letter(col_idx)].width = width

    # Save to bytes
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def generate_monthly_report_csv(project, month: str, results_summary: list[dict]) -> bytes:
    """Generate a UTF-8 BOM CSV report (Excel-compatible)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(["プロジェクト名", getattr(project, "name", "")])
    writer.writerow(["支店", getattr(project, "branch", "")])
    writer.writerow(["工種", getattr(project, "work_type", "")])
    writer.writerow(["対象月", month])
    writer.writerow(["レポート作成日", datetime.date.today().strftime("%Y-%m-%d")])
    writer.writerow([])
    writer.writerow(["カテゴリ", "品目", "数量", "単位", "排出係数 (kg-CO2/unit)", "CO2排出量 (kg-CO2)"])
    for r in results_summary:
        writer.writerow([
            r.get("category", ""),
            r.get("item_name", ""),
            r.get("quantity", 0),
            r.get("unit", ""),
            r.get("factor_value", 0),
            round(r.get("co2_kg", 0), 3),
        ])
    total = sum(r.get("co2_kg", 0) for r in results_summary)
    writer.writerow(["合計", "", "", "", "", round(total, 3)])
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def generate_activity_import_template() -> bytes:
    """Generate an Excel template for bulk activity import."""
    wb = Workbook()
    ws = wb.active
    ws.title = "活動量"
    headers = ["project_id", "target_month", "category", "item_name", "quantity", "unit", "source_file", "note"]
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="2E75B6", end_color="2E75B6", fill_type="solid")
        cell.font = Font(bold=True, color="FFFFFF")
    examples = [
        ["<プロジェクトID>", "2026-08", "fuel", "軽油", 500.0, "L", "給油伝票-202608-001", "現場タンク給油"],
        ["<プロジェクトID>", "2026-08", "power", "電力", 1200.0, "kWh", "電力検針票", ""],
        ["<プロジェクトID>", "2026-08", "material", "生コン", 12.5, "t", "納品書", ""],
        ["<プロジェクトID>", "2026-08", "transport", "一般輸送", 320.0, "t-km", "運送依頼書", ""],
    ]
    for row in examples:
        ws.append(row)
    for col_idx, width in enumerate([22, 12, 14, 22, 12, 10, 26, 18], start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    ws2 = wb.create_sheet(title="カテゴリ一覧")
    ws2.append(["カテゴリ", "説明"])
    for cat, desc in [
        ("fuel", "燃料 (軽油・A重油・ガソリン等)"),
        ("power", "電力 (kWh)"),
        ("material", "材料 (t/kg)"),
        ("transport", "輸送 (t-km)"),
        ("machine", "建機稼働"),
        ("ship", "船舶稼働"),
        ("waste", "廃棄物"),
    ]:
        ws2.append([cat, desc])
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()

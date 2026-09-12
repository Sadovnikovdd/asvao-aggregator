#!/usr/bin/env python3
"""Complete the execution-variant axis space vs existing fixtures."""
from __future__ import annotations

import json
import os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.table import Table, TableStyleInfo

OUT = os.path.dirname(os.path.abspath(__file__))
HEAD = PatternFill("solid", fgColor="1F4E79")
HEADF = Font(bold=True, color="FFFFFF")
JUNK = PatternFill("solid", fgColor="FFF2CC")
thin = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)

# Axes already covered by V01–V09 / 01–03 (do not regenerate)
COVERED = {
    "F_EX_chain_full_v1_v2_delta": ["V01", "V02", "V08"],
    "P3_two_prices_one_row": ["V03", "01_ТехСнаб"],
    "P1_hidden_live_row": ["V04", "01_ТехСнаб"],
    "P4_second_island": ["V05", "02_HONGXING", "03_Мега"],
    "P2_neg_price": ["V06", "01_ТехСнаб"],
    "P5_empty_price": ["V06", "01_ТехСнаб"],
    "C1_dup_sku": ["V06", "01_ТехСнаб"],
    "C5_total_formula": ["V06", "01_ТехСнаб"],
    "C8_empty_article_and_name": ["V06"],
    "G4_tdsheet_false_friend": ["V07", "ASVAO vs ASVAO3"],
    "C3_two_packings": ["V09", "03_Мега CB-419"],
    "L9_sci_barcode_int_sku": ["V06", "02_HONGXING"],
    "autofilter_on_empty": ["V07", "ASVAO3", "03_Мега"],
    "hidden_cost_col_P6": ["01_ТехСнаб G"],
    "letterhead_header_not_row1": ["01_ТехСнаб", "V04", "V07"],
    "currency_in_header_not_column": ["ASVAO E1", "V01 footer"],
}


def paint_row(ws, row, c0, c1):
    for c in range(c0, c1 + 1):
        cell = ws.cell(row, c)
        cell.fill = HEAD
        cell.font = HEADF
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = thin


def save(wb, name):
    path = os.path.join(OUT, name)
    wb.save(path)
    return path


def v10_native_table():
    wb = Workbook()
    ws = wb.active
    ws.title = "Table"
    headers = ["Артикул", "Наименование", "Бренд", "Остаток", "Цена"]
    for i, h in enumerate(headers, 1):
        ws.cell(1, i, h)
    paint_row(ws, 1, 1, 5)
    data = [
        ("NT-01", "Щетка 6.5", "Makita", 10, 180),
        ("NT-02", "Якорь", "Makita", 2, 2100),
        ("NT-03", "Патрон", "Dewalt", 5, 560),
        ("NT-04", "Статор", "Bosch", 1, 1900),
        ("NT-05", "Кабель", "NoName", 8, 210),
    ]
    for r, rec in enumerate(data, 2):
        for c, v in enumerate(rec, 1):
            ws.cell(r, c, v)
            ws.cell(r, c).border = thin
    tab = Table(displayName="PriceTable", ref="A1:E6")
    tab.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(tab)
    ws.column_dimensions["B"].width = 20
    p = save(wb, "V10_native_Excel_Table.xlsx")
    return {
        "id": "V10",
        "file": p,
        "basename": os.path.basename(p),
        "axis": "DetectLayout native Table (Ctrl+T) выше эвристики шапки",
        "quotes": {"table": "PriceTable A1:E6", "A2": "NT-01"},
        "expected_items": 5,
        "forces": ["DetectLayout source=native_table"],
    }


def v11_vertical():
    wb = Workbook()
    ws = wb.active
    ws.title = "Vertical"
    # headers in column A, one item per column B–F
    labels = ["Артикул", "Наименование", "Бренд", "Остаток", "Цена"]
    items = [
        ("VT-01", "Щетка", "Makita", 4, 180),
        ("VT-02", "Якорь", "Makita", 1, 2100),
        ("VT-03", "Патрон", "Dewalt", 3, 560),
        ("VT-04", "Статор", "Bosch", 2, 1900),
    ]
    for r, lab in enumerate(labels, 1):
        ws.cell(r, 1, lab)
        ws.cell(r, 1).font = HEADF
        ws.cell(r, 1).fill = HEAD
        for i, rec in enumerate(items):
            ws.cell(r, 2 + i, rec[r - 1])
    ws.column_dimensions["A"].width = 16
    p = save(wb, "V11_вертикальная_шапка.xlsx")
    return {
        "id": "V11",
        "file": p,
        "basename": os.path.basename(p),
        "axis": "DetectLayout vertical (заголовки в колонке A, позиции = колонки)",
        "quotes": {"A1": "Артикул", "B1": "VT-01", "E1": "VT-04"},
        "expected_items": 4,
        "forces": ["vertical layout", "не читать как 5 строк-позиций"],
        "wrong_if": "parser treats each row as an item → 5 garbage items",
    }


def v12_crosstab():
    wb = Workbook()
    ws = wb.active
    ws.title = "Crosstab"
    ws["A1"] = "Артикул"
    ws["B1"] = "Наименование"
    ws["C1"] = "Makita"
    ws["D1"] = "Bosch"
    ws["E1"] = "Dewalt"
    paint_row(ws, 1, 1, 5)
    rows = [
        ("CX-SH", "Щетка 6.5", 180, 190, None),
        ("CX-AR", "Якорь", 2100, None, 2400),
        ("CX-CH", "Патрон 13мм", None, 540, 560),
        ("CX-ST", "Статор", 1900, 1950, None),
    ]
    for r, rec in enumerate(rows, 2):
        for c, v in enumerate(rec, 1):
            ws.cell(r, c, v)
    ws["A7"] = "Кросстаб: бренд=колонка цены. Не одна цена, не P3 опт/РРЦ."
    ws.column_dimensions["B"].width = 18
    p = save(wb, "V12_кросстаб_бренды_колонками.xlsx")
    return {
        "id": "V12",
        "file": p,
        "basename": os.path.basename(p),
        "axis": "crosstab brand×price — отдельная семья layout, не P3",
        "quotes": {"C1": "Makita", "C2": 180, "E2": None, "A2": "CX-SH"},
        "expected_items": {
            "unpivot_nonnull_prices": 8,
            "wrong_one_price_col": "4 items with brand lost",
        },
        "forces": ["unpivot", "plugin likely", "не путать с P3"],
    }


def v13_three_sheets():
    wb = Workbook()
    headers = ["Артикул", "Наименование", "Бренд", "Остаток", "Цена"]

    def fill(ws, brand, rows):
        for i, h in enumerate(headers, 1):
            ws.cell(1, i, h)
        paint_row(ws, 1, 1, 5)
        for r, rec in enumerate(rows, 2):
            for c, v in enumerate(rec, 1):
                ws.cell(r, c, v)

    ws = wb.active
    ws.title = "Makita"
    fill(ws, "Makita", [
        ("MS-01", "Щетка CB-419", "Makita", 10, 180),
        ("MS-02", "Якорь HR2450", "Makita", 2, 2100),
        ("MS-03", "Щеткодержатель", "Makita", 5, 310),
    ])
    ws2 = wb.create_sheet("Bosch")
    fill(ws2, "Bosch", [
        ("BS-01", "Редуктор GBH", "Bosch", 1, 4300),
        ("BS-02", "Статор GBH", "Bosch", 2, 1900),
    ])
    ws3 = wb.create_sheet("Прочее")
    fill(ws3, "x", [
        ("OT-01", "Патрон", "Dewalt", 4, 560),
        ("OT-02", "Кабель", "NoName", 9, 210),
        ("OT-03", "Подшипник", "NSK", 40, 45),
    ])
    p = save(wb, "V13_три_валидных_листа.xlsx")
    return {
        "id": "V13",
        "file": p,
        "basename": os.path.basename(p),
        "axis": "N валидных прайсов в одном workbook (не мусорный Лист1)",
        "quotes": {"Makita!A2": "MS-01", "Bosch!A2": "BS-01", "Прочее!A2": "OT-01"},
        "expected_items": {
            "parse_all_sheets": 8,
            "only_active": 3,
            "quarantine_if_policy_one_sheet": "file or 3 master cards",
        },
        "forces": ["workbook-level P4 analogue", "3 detect hits same fingerprint F_EX-like"],
    }


def v14_header_only():
    wb = Workbook()
    ws = wb.active
    ws.title = "Empty"
    for i, h in enumerate(["Артикул", "Наименование", "Цена"], 1):
        ws.cell(1, i, h)
    paint_row(ws, 1, 1, 3)
    ws["A2"] = None
    ws["A5"] = "Файл с шапкой без позиций. Карантин ФАЙЛА, не 0 items success."
    p = save(wb, "V14_только_шапка_0_позиций.xlsx")
    return {
        "id": "V14",
        "file": p,
        "basename": os.path.basename(p),
        "axis": "0 data rows → quarantine FILE not success empty warehouse",
        "quotes": {"A1": "Артикул", "data": "none"},
        "expected_items": 0,
        "file_status": "quarantine_zero_rows",
        "forces": ["G7 0 rows", "не current_shipment от пустого успеха"],
    }


def v15_ambiguous():
    wb = Workbook()
    ws = wb.active
    ws.title = "Short"
    # ambiguous short headers — micro-LLM / master, not autonomous YAML
    for i, h in enumerate(["Код", "Наим", "Кол", "Ст", "Пр", "К"], 1):
        ws.cell(1, i, h)
    paint_row(ws, 1, 1, 6)
    data = [
        ("AM-01", "Щетка", 10, 180, 270, 1),
        ("AM-02", "Якорь", 2, 2100, 3150, 1),
        ("AM-03", "Патрон", 4, 560, 840, 1),
        ("AM-04", "Р", 1, 10, 15, 1),
    ]
    for r, rec in enumerate(data, 2):
        for c, v in enumerate(rec, 1):
            ws.cell(r, c, v)
    ws["A7"] = "Кол=qty? Ст=стоимость/статус? Пр=цена/производитель? К=кратность/код. Без мастера не автономно."
    p = save(wb, "V15_короткие_неоднозначные_заголовки.xlsx")
    return {
        "id": "V15",
        "file": p,
        "basename": os.path.basename(p),
        "axis": "MapColumns ambiguous → master + слот микро-LLM, не silent map",
        "quotes": {"A1": "Код", "D1": "Ст", "E1": "Пр", "F1": "К", "A2": "AM-01", "D2": 180, "E2": 270},
        "expected": "unknown/ambiguous fingerprint, 0 autonomy clicks forbidden",
        "forces": ["G10 unknown card", "LLM slot input=headers+3 rows", "P3 maybe Ст/Пр"],
    }


def v16_fx():
    wb = Workbook()
    ws = wb.active
    ws.title = "FX"
    for i, h in enumerate(["Артикул", "Наименование", "Цена RUB", "Цена USD", "Цена EUR", "Остаток"], 1):
        ws.cell(1, i, h)
    paint_row(ws, 1, 1, 6)
    data = [
        ("FX-01", "Щетка", 180, 2.0, 1.8, 10),
        ("FX-02", "Якорь", 2100, 23.0, 21.0, 2),
        ("FX-03", "Патрон", 560, 6.1, 5.5, 4),
        ("FX-04", "Статор", 1900, None, 19.0, 1),  # missing USD
    ]
    for r, rec in enumerate(data, 2):
        for c, v in enumerate(rec, 1):
            ws.cell(r, c, v)
    ws["A7"] = "Три валюты колонками. Не P3 опт/РРЦ (тот же рубль). currency на item."
    p = save(wb, "V16_три_валюты_колонками.xlsx")
    return {
        "id": "V16",
        "file": p,
        "basename": os.path.basename(p),
        "axis": "multi-currency columns ≠ P3 price_type",
        "quotes": {"C1": "Цена RUB", "D1": "Цена USD", "E1": "Цена EUR", "D5": None},
        "expected_items": {
            "one_item_extra_fx": 4,
            "N_items_per_currency": 11,
        },
        "forces": ["нужна политика P8 currency-columns", "не смешивать с P3"],
    }


def v17_merged_block():
    wb = Workbook()
    ws = wb.active
    ws.title = "MergeBlock"
    for i, h in enumerate(["Артикул", "Размер", "Наименование", "Цена", "Остаток"], 1):
        ws.cell(1, i, h)
    paint_row(ws, 1, 1, 5)
    # one SKU merged A2:A4, three sizes
    ws.merge_cells("A2:A4")
    ws.merge_cells("C2:C4")
    ws["A2"] = "MB-BRUSH"
    ws["C2"] = "Щетка угольная (три размера)"
    ws["B2"] = "6.5x7.5"
    ws["D2"] = 180
    ws["E2"] = 10
    ws["B3"] = "5x8"
    ws["D3"] = 170
    ws["E3"] = 8
    ws["B4"] = "7x11"
    ws["D4"] = 190
    ws["E4"] = 4
    ws["A5"] = "MB-ARM"
    ws["B5"] = "-"
    ws["C5"] = "Якорь HR2450"
    ws["D5"] = 2100
    ws["E5"] = 2
    ws.column_dimensions["C"].width = 32
    p = save(wb, "V17_merge_артикул_на_три_размера.xlsx")
    return {
        "id": "V17",
        "file": p,
        "basename": os.path.basename(p),
        "axis": "merged_fill вниз: 1 артикул × 3 размера = 3 items (не 1)",
        "quotes": {"A2:A4": "MB-BRUSH", "B2": "6.5x7.5", "B4": "7x11", "A5": "MB-ARM"},
        "expected_items": {
            "with_merged_fill": 4,
            "without_fill": "1 or 2 (B3/B4 orphan) — bug",
        },
        "forces": ["merged_fill convention from prototype OK", "DetectLayout merge in probe pass"],
    }


def v18_named_range():
    wb = Workbook()
    ws = wb.active
    ws.title = "Named"
    ws.merge_cells("A1:E1")
    ws["A1"] = "Мусор сверху. Прайс в именованном диапазоне PriceData."
    ws["A1"].fill = JUNK
    for i, h in enumerate(["Артикул", "Наименование", "Бренд", "Остаток", "Цена"], 1):
        ws.cell(4, i, h)
    paint_row(ws, 4, 1, 5)
    data = [
        ("NR-01", "Щетка", "Makita", 6, 180),
        ("NR-02", "Якорь", "Makita", 1, 2100),
        ("NR-03", "Патрон", "Dewalt", 3, 560),
        ("NR-04", "Кабель", "NoName", 7, 210),
    ]
    for r, rec in enumerate(data, 5):
        for c, v in enumerate(rec, 1):
            ws.cell(r, c, v)
    wb.create_named_range("PriceData", ws, "A4:E8")
    p = save(wb, "V18_named_range_PriceData.xlsx")
    return {
        "id": "V18",
        "file": p,
        "basename": os.path.basename(p),
        "axis": "DetectLayout named_range выше скоринга шапки",
        "quotes": {"defined_name": "PriceData A4:E8", "A4": "Артикул", "A5": "NR-01"},
        "expected_items": 4,
        "forces": ["named range priority"],
    }


def v21_combo_p3_p1():
    """Combination fork: two prices AND a hidden live row — matrix P1×P3."""
    wb = Workbook()
    ws = wb.active
    ws.title = "P1xP3"
    for i, h in enumerate(["Артикул", "Наименование", "Опт", "РРЦ", "Остаток"], 1):
        ws.cell(1, i, h)
    paint_row(ws, 1, 1, 5)
    rows = [
        ("XP-01", "Щетка", 180, 270, 10),
        ("XP-HIDDEN", "Скрытый якорь", 2100, 3150, 1),
        ("XP-02", "Патрон", 560, 840, 4),
        ("XP-03", "Статор", 1900, 2850, 2),
    ]
    hidden = None
    for r, rec in enumerate(rows, 2):
        for c, v in enumerate(rec, 1):
            ws.cell(r, c, v)
        if rec[0] == "XP-HIDDEN":
            hidden = r
            ws.row_dimensions[r].hidden = True
    p = save(wb, "V21_комбо_P1_скрытая_×_P3_две_цены.xlsx")
    return {
        "id": "V21",
        "file": p,
        "basename": os.path.basename(p),
        "axis": "комбо P1×P3 — counts перемножаются, не складываются от отдельных файлов",
        "quotes": {"A2": "XP-01", "C2": 180, "D2": 270, "hidden": f"A{hidden}='XP-HIDDEN'"},
        "notes": {"hidden_row": hidden},
        "expected_items": {
            "P1_include_P3_N_items": 8,
            "P1_include_P3_extra_prices": 4,
            "P1_skip_P3_N_items": 6,
            "P1_skip_P3_extra_prices": 3,
        },
        "forces": ["матрица P* не независима", "G2 combo"],
    }


def main():
    new = [
        v10_native_table(),
        v11_vertical(),
        v12_crosstab(),
        v13_three_sheets(),
        v14_header_only(),
        v15_ambiguous(),
        v16_fx(),
        v17_merged_block(),
        v18_named_range(),
        v21_combo_p3_p1(),
    ]
    still_open = [
        {"axis": "P8 currency-columns", "why": "открыт V16, политика не выбрана"},
        {"axis": "pivot left+top header (двумерная шапка чисел)", "why": "V12 упрощённый кросстаб; полный pivot с итогами — plugin"},
        {"axis": ".xls BIFF / .xlsb / HTML-xls / XML Spreadsheet 2003", "why": "не xlsx; FileNormalize, отдельный конверт"},
        {"axis": "csv cp1251 ; delimiter", "why": "не Excel layout"},
        {"axis": "password-encrypted workbook", "why": "не sheet protection; карантин файла"},
        {"axis": "macro xlsm execute", "why": "запрет исполнять, только данные"},
        {"axis": "matching OEM vs supplier sku across sources", "why": "слот фазы 3, не ingest"},
        {"axis": "P3×P4 combo file", "why": "можно догенерить позже; логика = произведение политик"},
        {"axis": "same fingerprint synonym rename Цена→Прайс", "why": "fingerprint miss → master, не V_profile"},
        {"axis": "winmail.dat / zip кириллица / file без расширения", "why": "MailIngest/FileNormalize, не xlsx-фикстура"},
        {"axis": "300k rows RAM", "why": "генератор отдельный, не класть в git"},
        {"axis": "formula article ='EX'&row", "why": "нужен recalc LibreOffice — отдельный G9"},
    ]
    man = {
        "purpose": "Completion осей исполнения: закрыть дыры, которых нет в V01–V09",
        "covered_before": COVERED,
        "new_files": new,
        "still_open_not_xlsx_or_deferred": still_open,
        "new_policies_to_add_to_prompt": [
            "P8: несколько колонок валют → N items с currency XOR extra.fx[] (не путать с P3)",
            "P9: несколько валидных листов → parse all XOR first XOR master-per-sheet",
            "P10: кросстаб/unpivot → plugin, не YAML",
            "P11: 0 data rows → quarantine file, не пустой success shipment",
        ],
    }
    path = os.path.join(OUT, "MANIFEST_completion_осей.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    print(json.dumps({
        "manifest": path,
        "new": [{"id": x["id"], "basename": x["basename"], "axis": x["axis"]} for x in new],
        "still_open": len(still_open),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

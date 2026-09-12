#!/usr/bin/env python3
"""Generate 3 hostile Excel price lists for parser golden-tests."""
from __future__ import annotations

import json
import os
from datetime import date

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUT = os.path.dirname(os.path.abspath(__file__))

thin = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)
fill_head = PatternFill("solid", fgColor="1F4E79")
fill_head2 = PatternFill("solid", fgColor="D6DCE4")
fill_warn = PatternFill("solid", fgColor="FFC7CE")
fill_junk = PatternFill("solid", fgColor="FFF2CC")
font_head = Font(bold=True, color="FFFFFF")
font_title = Font(bold=True, size=16, color="1F4E79")


def paint_header(ws, row: int, col_from: int, col_to: int) -> None:
    for c in range(col_from, col_to + 1):
        cell = ws.cell(row, c)
        cell.fill = fill_head
        cell.font = font_head
        cell.alignment = Alignment(horizontal="center", wrap_text=True, vertical="center")
        cell.border = thin


def border_row(ws, row: int, col_from: int, col_to: int) -> None:
    for c in range(col_from, col_to + 1):
        ws.cell(row, c).border = thin


def build_file1() -> dict:
    wb = Workbook()
    ws = wb.active
    ws.title = "Прайс с 01.09"

    ws.merge_cells("A1:I1")
    ws["A1"] = "ООО «ТехСнаб-Восток»  ИНН 7700123456  /  PRICE LIST  /  конфиденциально"
    ws["A1"].font = font_title
    ws.merge_cells("A2:I2")
    ws["A2"] = (
        "Запчасти для электроинструмента. Действует с 01.09.2026. "
        "Курсы: 1 EUR = 98,50 руб. Не оферта."
    )
    ws["A3"] = "Менеджер:"
    ws["B3"] = "Иванов П.С.  +7 495 000-00-00"
    ws["A4"] = "email:"
    ws["B4"] = "price@techsnab-vostok.example"
    ws.merge_cells("A5:I5")
    ws["A5"] = "ВНИМАНИЕ: колонка G скрыта (внутренняя себестоимость). Не удалять."
    ws["A5"].fill = fill_junk

    # rows 6–7 empty; two-level header on 8–9; data from 10
    tops = [
        "№",
        "Код поставщика",
        "Наименование / описание",
        "Бренд",
        "Остаток",
        "Цена",
        "себест",
        "РРЦ",
        "Ед.",
    ]
    bots = ["", "SKU", "full name", "brand", "qty", "опт, руб.", "cost", "руб.", "uom"]
    for i, h in enumerate(tops, 1):
        ws.cell(8, i, h)
    for i, h in enumerate(bots, 1):
        ws.cell(9, i, h)
    for rng in ("A8:A9", "B8:B9", "C8:C9", "D8:D9", "E8:E9", "I8:I9"):
        ws.merge_cells(rng)
    ws["F8"] = "Цена"
    ws["F9"] = "опт, руб."
    ws["H8"] = "РРЦ"
    ws["H9"] = "руб."
    paint_header(ws, 8, 1, 9)
    paint_header(ws, 9, 1, 9)
    ws["F8"].fill = PatternFill("solid", fgColor="C65911")
    ws["H8"].fill = PatternFill("solid", fgColor="548235")
    ws.column_dimensions["G"].hidden = True

    records = [
        (1, "TS-01001", "Щетка угольная 6.5x7.5x13 Makita CB-419", "Makita", "много", "1 240,50", 800, 1860, "шт"),
        (2, "TS-01002", "  Якорь в сборе HR2450  (уценка)", "Makita", "+", "890,00", 510, 1335, "шт"),
        (3, "TS-01003", "Редуктор перфоратора GBH 2-26", "Bosch", "нет", "4 320,00", 2900, 6480, "шт"),
        (4, "TS-01004", "Патрон ключевой 13 мм 1/2-20UNF", "Dewalt", "<5", "560,5", 300, 840, "шт"),
        (5, "TS-HIDDEN", "Ротор скрытый (hidden row) — позиция существует", "Makita", "1", "999,00", 400, 1498, "шт"),
        (6, "TS-01001", "Щетка угольная 6.5x7.5x13 Makita CB-419 / ДУБЛЬ", "Makita", "3", "1 240,50", 800, 1860, "шт"),
        (7, "0004451", "Выключатель FA2-6/2BW", "Китай", "12", "150 руб.", 40, 225, "шт"),
        (8, "TS-01007", "Статор 220В для УШМ 125", "", "0", "", 0, None, "шт"),
        (9, "TS-01008", "Подшипник 607 ZZ", "NSK", "21", "-15", 10, 45, "шт"),
        (10, None, "Комплект щёток (артикул потерян)", "Bosch", "2", "330,00", 180, 495, "компл"),
        (11, "TS-01010", "Р", "Makita", "1", "100,00", 50, 150, "шт"),
    ]
    r = 10
    hidden_row = None
    for rec in records:
        n, sku, name, brand, stock, opt, cost, rrc, uom = rec
        ws.cell(r, 1, n)
        ws.cell(r, 2, sku)
        ws.cell(r, 3, name)
        ws.cell(r, 4, brand or None)
        ws.cell(r, 5, stock)
        ws.cell(r, 6, opt)
        ws.cell(r, 7, cost)
        ws.cell(r, 8, rrc)
        ws.cell(r, 9, uom)
        border_row(ws, r, 1, 9)
        if sku == "TS-HIDDEN":
            hidden_row = r
            ws.row_dimensions[r].hidden = True
        if opt in ("", "-15") or sku is None:
            ws.cell(r, 6).fill = fill_warn
        r += 1

    r += 1  # blank
    for i, h in enumerate(
        ["№", "Код поставщика", "Наименование / описание", "Бренд", "Остаток", "Цена опт, руб.", "себест", "РРЦ", "Ед."],
        1,
    ):
        ws.cell(r, i, h)
        ws.cell(r, i).fill = fill_head2
        ws.cell(r, i).font = Font(bold=True)
    repeated_header_row = r
    r += 1
    extra = [
        (12, "TS-01011", "Щеткодержатель CB-204", "Makita", "8", "210,00", 90, 315, "шт"),
        (13, "TS-01012", "Кабель питания 2м 2x1.0 с вилкой", "NoName", "много", "1 050,00", 400, 1575, "шт"),
        (14, "TS-01013", "Крышка редуктора левая GBH 2-24", "Bosch", "1", "2 100,00", 1100, 3150, "шт"),
    ]
    for rec in extra:
        n, sku, name, brand, stock, opt, cost, rrc, uom = rec
        ws.cell(r, 1, n)
        ws.cell(r, 2, sku)
        ws.cell(r, 3, name)
        ws.cell(r, 4, brand)
        ws.cell(r, 5, stock)
        ws.cell(r, 6, opt)
        ws.cell(r, 7, cost)
        ws.cell(r, 8, rrc)
        ws.cell(r, 9, uom)
        r += 1

    last_data = r - 1
    ws.cell(r, 3, "ИТОГО (не позиция)")
    ws.cell(r, 3).font = Font(bold=True, italic=True)
    ws.cell(r, 6, f"=SUM(F10:F{last_data})")
    ws.cell(r, 8, f"=SUM(H10:H{last_data})")
    footer_formula_row = r
    r += 2
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=9)
    ws.cell(r, 1, "Цены с НДС 20%. Отрицательная цена — корректировка. Пустая цена = под заказ.")

    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 55
    ws.auto_filter.ref = "A8:I8"
    ws.freeze_panes = "A10"

    ws2 = wb.create_sheet("Реквизиты")
    ws2["A1"] = "ООО ТехСнаб-Восток"
    ws2["A2"] = "Не прайс. Не парсить."
    ws2["A3"] = "р/с 40702810100000000000"
    wb.create_sheet("Лист1")

    path = os.path.join(OUT, "01_ТехСнаб-Восток_прайс_с_ошибками.xlsx")
    wb.save(path)
    return {
        "file": path,
        "supplier": "ООО ТехСнаб-Восток",
        "notes": {
            "header_rows": [8, 9],
            "data_start_row": 10,
            "hidden_row": hidden_row,
            "repeated_header_row": repeated_header_row,
            "footer_formula_row": footer_formula_row,
            "hidden_column": "G",
        },
        "planted_errors": [
            "шапка не на 1-й строке (letterhead 1–5, данные с 10)",
            "двухуровневая шапка + merge A8:A9…",
            "скрытая колонка G (себестоимость)",
            "скрытая строка с реальной позицией TS-HIDDEN",
            "остаток текстом: много / + / нет / <5 / 0",
            "цена текстом с пробелом тысяч и десятичной запятой: «1 240,50»",
            "цена «150 руб.» в одной ячейке",
            "пустая цена, отрицательная цена",
            "дубль артикула TS-01001 с другим именем",
            "пустой артикул, пустой бренд, имя «Р»",
            "повтор шапки посреди данных",
            "строка ИТОГО с формулой SUM без кэша",
            "autofilter на A8:I8, freeze A10",
            "мусорный лист «Реквизиты» и пустой «Лист1»",
            "две колонки цен: опт и РРЦ",
            "валюта/НДС только в футере",
        ],
    }


def build_file2() -> dict:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    ws.merge_cells("A1:G1")
    ws["A1"] = "HONGXING TOOLS CO., LTD  // Spare parts for power tools  // EXW Ningbo"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Date"
    ws["B2"] = date(2026, 9, 1)
    ws["B2"].number_format = "YYYY-MM-DD"
    ws["C2"] = "Excel serial also in D2"
    ws["D2"] = 45901
    ws["D2"].number_format = "0"
    ws["A3"] = "Currency: USD. Колонка F = штрихкод, не число."

    for i, h in enumerate(["Item No.", "Product Name", "Brand", "MOQ", "Price USD", "Barcode", "Stock"], 1):
        ws.cell(5, i, h)
    paint_header(ws, 5, 1, 7)

    table1 = [
        {"A": 1234, "B": "Carbon brush 5x8x12", "C": "Makita", "D": 50, "E": 0.35, "F": 4800123456789, "G": 1200, "Fsci": True},
        {"A": "001234", "B": "Carbon brush 5x8x12 SAME as 1234 but sku text with zeros", "C": "Makita", "D": 50, "E": 0.35, "F": "4800123456789", "G": 1200},
        {"A": 4451000123.0, "B": "Armature HR2470", "C": "Makita", "D": 10, "E": 12.5, "F": 460712345678, "G": "N/A", "Afloat": True, "Fsci": True},
        {"A": "HX-088", "B": "   GEAR BOX ANGLE GRINDER 125MM", "C": "HX", "D": 20, "E": 8.0, "F": None, "G": 0, "merge_bc": True},
        {"A": "HX-089", "B": "Switch FA2-8/2BE 10A", "C": None, "D": 100, "E": None, "F": 2109876543210, "G": 500, "Fsci": True},
        {"A": "HX-090", "B": "Chuck 13mm keyless", "C": "Dewalt", "D": 5, "E": -2.0, "F": 2200000000001, "G": 3, "Fsci": True},
        {"A": "HX-091", "B": "Stator 220V 50Hz УШМ", "C": "Bosch", "D": "10 pcs", "E": "3,75", "F": "000123", "G": "yes"},
        {"A": "HX-092", "B": "Bearing 608-2RS", "C": "NSK", "D": 200, "E": 0.12, "F": 8.8e12, "G": 10000, "Fsci": True},
    ]
    merge_row = None
    for i, row in enumerate(table1, start=6):
        ws.cell(i, 1, row["A"])
        ws.cell(i, 2, row["B"])
        ws.cell(i, 3, row.get("C"))
        ws.cell(i, 4, row["D"])
        ws.cell(i, 5, row["E"])
        ws.cell(i, 6, row.get("F"))
        ws.cell(i, 7, row["G"])
        if row.get("Afloat"):
            ws.cell(i, 1).number_format = "0.00"
        if row.get("Fsci") and isinstance(row.get("F"), (int, float)):
            ws.cell(i, 6).number_format = "0.00E+00"
        if row.get("merge_bc"):
            merge_row = i

    if merge_row:
        ws.merge_cells(start_row=merge_row, start_column=2, end_row=merge_row, end_column=3)

    ws.merge_cells("A17:E17")
    ws["A17"] = "DISCONTINUED / снято с производства — вторая таблица на том же листе, другие колонки"
    ws["A17"].fill = fill_junk
    for i, h in enumerate(["sku", "name_ru", "price_rub", "note"], 1):
        ws.cell(18, i, h)
    paint_header(ws, 18, 1, 4)
    ws["A19"] = "OLD-01"
    ws["B19"] = "Щетка устаревшая CB-100"
    ws["C19"] = 90
    ws["D19"] = "не возить"
    ws["A20"] = "OLD-02"
    ws["B20"] = "Якорь снятый"
    ws["C20"] = 0
    ws["D20"] = "остаток 0"

    wsb = wb.create_sheet("Archive 2024")
    wsb["A1"] = "Item No."
    wsb["B1"] = "Product Name"
    wsb["C1"] = "Price USD"
    wsb["A2"] = "DO-NOT-IMPORT"
    wsb["B2"] = "old junk"
    wsb["C2"] = 1

    wsc = wb.create_sheet("Инструкция")
    wsc["A1"] = "How to read this file"
    wsc["A2"] = "Table 1 rows 5–13. Table 2 rows 18–20. Archive sheet = ignore."

    for col, w in zip("ABCDEFG", [16, 48, 12, 10, 12, 18, 10]):
        ws.column_dimensions[col].width = w

    path = os.path.join(OUT, "02_HONGXING_TOOLS_spare_parts_USD.xlsx")
    wb.save(path)
    return {
        "file": path,
        "supplier": "HONGXING TOOLS",
        "notes": {
            "table1": "A5:G13",
            "table2": "A18:D20",
            "merged_data_row": merge_row,
        },
        "planted_errors": [
            "английские заголовки Item No. / Price USD / Barcode",
            "две таблицы на одном листе с разными колонками (основная + DISCONTINUED)",
            "артикул 1234 как число — потеря ведущих нулей; рядом текстовый 001234",
            "артикул float 4451000123.0",
            "штрихкод int + scientific 0.00E+00",
            "штрихкод float 8.8e12",
            "merge имени в бренд в данных",
            "MOQ текстом «10 pcs», цена текстом «3,75»",
            "пустые brand/price, отрицательная цена, stock N/A / yes / 0",
            "имя с ведущими пробелами и ALL CAPS",
            "дата в шапке и число-serial 45901",
            "листы Archive 2024 (похожая шапка) и Инструкция",
            "валюта USD в тексте, не в колонке",
        ],
    }


def build_file3() -> dict:
    wb = Workbook()
    ws = wb.active
    ws.title = "TDSheet"

    ws["A1"] = "Прайс-лист"
    ws["B1"] = "МегаИнструмент"
    ws.merge_cells("C2:K2")
    ws["C2"] = "Выгрузка № 17-44 от 11.09.2026   Организация: ИП Сидоров"
    ws["C3"] = "rub"

    ws.merge_cells("C4:C6")
    ws["C4"] = "Производитель"
    ws.merge_cells("D4:D6")
    ws["D4"] = "Артикул"
    ws.merge_cells("E4:E6")
    ws["E4"] = "Штрих-код"
    ws.merge_cells("F4:F6")
    ws["F4"] = "Номенклатура"
    ws.merge_cells("G4:H4")
    ws["G4"] = "Количество"
    ws["G5"] = "свободный"
    ws["H5"] = "в резерве"
    ws["G6"] = "шт"
    ws["H6"] = "шт"
    ws.merge_cells("I4:J4")
    ws["I4"] = "Цена"
    ws["I5"] = "закуп"
    ws["J5"] = "розн"
    ws["I6"] = "Цена (руб.)"
    ws["J6"] = "Цена (руб.)"
    ws.merge_cells("K4:K6")
    ws["K4"] = "Кратность / фасовка"
    for col in range(3, 12):
        for row in range(4, 7):
            cell = ws.cell(row, col)
            cell.fill = fill_head
            cell.font = font_head
            cell.alignment = Alignment(horizontal="center", wrap_text=True, vertical="center")
            cell.border = thin

    ws.auto_filter.ref = "C7:K7"

    rows3 = [
        ("Bosch", "1 609 203 243", "3165140589411", "Щетка угольная GBH 2-26 (комплект 2 шт)", 12, 0, 450, 690, "2"),
        ("Bosch", "1609203243", "3165140589411", "Щетка угольная GBH 2-26 — тот же товар, артикул без пробелов", 4, 2, 450, 690, "2"),
        ("Makita", "CB-419", "0088381067780", "Щётка 6.5×7.5×13", 0, 0, 180, 270, "1"),
        (None, "000000123", 123, "Выключатель 6А с кнопкой блокировки", 3, 0, 95, 150, "1"),
        ("Interskol", "УШМ-125/1100Э.01.01.00", None, "Якорь УШМ-125/1100Э  (с вентилятором)", "под заказ", None, "1\u00a0250,00", 1900, "1"),
        ("Dewalt", "N027139", "0033531928471", "   РЕДУКТОР В СБОРЕ DCD771", 1, 1, 3200, 4800, "1"),
        ("", "МИ-0001", "", "Р", 1, 0, 10, 15, "1"),
        ("Makita", "HR2450-ARM", "0088381000001", "Якорь HR2450 / armature / 转子  / очень длинное наименование с пробелами в конце     ", 2, 0, 2100, 3150, "1"),
        ("Bosch", "GBH2-26-ST", None, "Статор 220В; 50Гц; для GBH 2-26 DRE; аналог 1 609 201 xxx", 1, 0, 4100, 6150, "1"),
        ("NoName", "Китай-щ-01", "4,80123E+12", "Щетка 5x8x11 no name", 50, 0, 25, 40, "10"),
        ("Makita", "CB-419", "0088381067780", "Щётка 6.5×7.5×13 фасовка 10 шт", 5, 0, 1600, 2400, "10"),
    ]
    r = 8
    for rec in rows3:
        brand, art, bar, name, qty, res, buy, retail, pack = rec
        ws.cell(r, 3, brand or None)
        ws.cell(r, 4, art)
        ws.cell(r, 5, bar)
        ws.cell(r, 6, name)
        ws.cell(r, 7, qty)
        ws.cell(r, 8, res)
        ws.cell(r, 9, buy)
        if not isinstance(buy, str):
            ws.cell(r, 9).number_format = "#,##0"
        ws.cell(r, 10, retail)
        ws.cell(r, 11, pack)
        if r == 8:
            ws.cell(r, 6).comment = Comment("В ячейке примечание, не данные", "1C")
        r += 1

    last_data = r - 1
    ws.cell(r, 6, "Итого")
    ws.cell(r, 9, f"=SUM(I8:I{last_data})")
    ws.cell(r, 10, f"=SUM(J8:J{last_data})")
    r += 1
    ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=11)
    ws.cell(r, 3, "Гарантия 14 дней. Позиции «под заказ» не резервировать. Кратность обязательна.")

    r += 3
    ws.cell(r, 3, "Дополнительно (ещё одна таблица ниже футера)")
    ws.cell(r, 3).fill = fill_junk
    r += 1
    island_header = r
    ws.cell(r, 3, "Артикул")
    ws.cell(r, 4, "Наименование")
    ws.cell(r, 5, "Цена")
    paint_header(ws, r, 3, 5)
    r += 1
    ws.cell(r, 3, "АКЦИЯ-1")
    ws.cell(r, 4, "Набор щёток микс 20 шт")
    ws.cell(r, 5, 500)

    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].hidden = True
    ws.column_dimensions["D"].width = 22
    ws.column_dimensions["F"].width = 60
    ws.protection.sheet = True
    ws.protection.enable()

    wb.create_sheet("Лист1")
    wsx = wb.create_sheet("TDSheet_2")
    wsx["A1"] = "Производитель"
    wsx["B1"] = "Артикул"
    wsx["C1"] = "Номенклатура"
    wsx["D1"] = "Цена"
    wsx["A2"] = "ЭТО НЕ ПРАЙС — копия шапки без данных / print leftover"

    path = os.path.join(OUT, "03_МегаИнструмент_1С_выгрузка_враждебная.xlsx")
    wb.save(path)
    return {
        "file": path,
        "supplier": "ИП Сидоров / МегаИнструмент",
        "notes": {
            "sheet": "TDSheet",
            "header_rows": [4, 5, 6],
            "autofilter": "C7:K7 (empty)",
            "data": f"C8:K{last_data}",
            "second_table_header_row": island_header,
            "sheet_protection": True,
        },
        "planted_errors": [
            "лист TDSheet как у реальных A/B — ложный друг fingerprint, другой формат",
            "таблица со сдвига C–K, колонка B скрыта",
            "трёхэтажная шапка с merge групп Количество и Цена",
            "autofilter на пустой строке C7:K7",
            "две колонки qty и две цены",
            "один товар два написания артикула: «1 609 203 243» vs «1609203243»",
            "один артикул CB-419 две фасовки",
            "бренд пустой",
            "штрихкод int 123; штрихкод строка «4,80123E+12»",
            "qty «под заказ»; цена с nbsp «1 250,00»",
            "имя с 转子 и trailing spaces; имя «Р»; comment в ячейке",
            "Итого + формула без кэша",
            "вторая таблица ниже футера (акция)",
            "защита листа (не шифрование книги)",
            "пустой Лист1 + TDSheet_2 с шапкой без данных",
            "валюта rub в C3, не колонка",
        ],
    }


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    files = [build_file1(), build_file2(), build_file3()]
    for item in files:
        item["bytes"] = os.path.getsize(item["file"])
        item["basename"] = os.path.basename(item["file"])
    man = os.path.join(OUT, "MANIFEST_ошибки.json")
    with open(man, "w", encoding="utf-8") as f:
        json.dump({"files": files}, f, ensure_ascii=False, indent=2)
    print(json.dumps({"manifest": man, "files": [{"basename": x["basename"], "bytes": x["bytes"]} for x in files]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

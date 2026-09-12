from aggregator.engine import inspect_file, parse_file
from test_engine import ROOT, profile


def test_hostile_01_techsnab_vostok():
    path = ROOT / "01_ТехСнаб-Восток_прайс_с_ошибками.xlsx"
    targets = [
        "extra.index",
        "article",
        "name",
        "brand",
        "qty",
        "price",
        "drop",
        "price",
        "extra.unit",
    ]
    p = profile(
        path,
        targets,
        header=8,
        header_end=9,
        start=10,
        end=28,
        first_col=1,
        source="01_techsnab",
    )
    p["policies"].update(
        {
            "hidden_rows": "include",
            "negative_price": "accept",
            "empty_price": "accept",
            "hidden_cost": "drop",
            "multiple_prices": "items",
        }
    )
    p["tables"][0]["currency"] = "RUB"
    cols = p["tables"][0]["columns"]
    cols[5]["price_kind"] = "opt"
    cols[7]["price_kind"] = "rrc"
    cols[6]["reason"] = "hidden_cost"
    result = parse_file(path, p)
    assert result["status"] == "accepted"
    assert result["counts"]["source_rows"] == 14
    assert result["counts"]["items"] == 26
    qtys_raw = {item.get("qty_raw") for item in result["items"] if item.get("qty_raw")}
    assert {"много", "+", "нет", "<5"} <= qtys_raw
    arts = [item["article"] for item in result["items"]]
    assert {
        item["source_row"] for item in result["items"] if item["article"] == "TS-01001"
    } == {10, 15}
    assert "0004451" in arts
    neg = [item for item in result["items"] if item.get("price") == "-15"]
    assert len(neg) == 1
    hidden = [item for item in result["items"] if item["article"] == "TS-HIDDEN"]
    assert hidden and hidden[0]["flags"].get("hidden_row") is True
    missing = [item for item in result["items"] if item["article"] == "TS-01007"]
    assert len(missing) == 2
    assert all(item["price"] is None and item["flags"]["no_price"] for item in missing)
    lost = [q for q in result["quarantine"] if "missing_article" in q.get("reason", "")]
    assert len(lost) == 1
    assert lost[0]["name"] == "Комплект щёток (артикул потерян)"
    assert lost[0]["raw_row"].get("B19") is None and lost[0]["raw_row"].get("C19")
    assert all(
        item["raw_row"].get(f"G{item['source_row']}") == "[dropped]"
        for item in result["items"]
    )
    assert all("hidden_cost" not in item["extra"] for item in result["items"])
    assert any(item["price"] == "1240.50" for item in result["items"])
    assert any(
        item["article"] == "0004451"
        and item["price"] == "150"
        and item["currency"] == "RUB"
        for item in result["items"]
    )
    # dropped has reason + column for column-scoped drops
    column_drops = [d for d in result["dropped"] if d.get("scope") == "column"]
    assert len(column_drops) == 1  # one record per column, not per row
    assert all(d.get("column") and d.get("reason") for d in column_drops)
    assert any(d["reason"] == "hidden_cost" for d in column_drops)
    r_item = [item for item in result["items"] if item.get("name") == "Р"]
    assert r_item
    # repeated header / total not in items
    dropped_reasons = {d.get("reason") for d in result["dropped"]}
    assert "repeated_header" in dropped_reasons
    assert "total_row" in dropped_reasons


def test_hostile_02_hongxing_tools():
    path = ROOT / "02_HONGXING_TOOLS_spare_parts_USD.xlsx"
    targets1 = [
        "article",
        "name",
        "brand",
        "extra.moq",
        "price",
        "extra.barcode",
        "qty",
    ]
    p = profile(
        path,
        targets1,
        header=5,
        header_end=5,
        start=6,
        end=13,
        first_col=1,
        source="02_hongxing",
    )
    p["policies"].update(
        {
            "hidden_rows": "include",
            "negative_price": "accept",
            "empty_price": "accept",
            "hidden_cost": "drop",
            "multiple_prices": "items",
        }
    )
    p["tables"][0]["currency"] = "USD"
    p["tables"][0]["columns"][4]["currency"] = "USD"
    # second table on same sheet
    targets2 = ["article", "name", "price", "extra.note"]
    t2 = profile(
        path,
        targets2,
        header=18,
        header_end=18,
        start=19,
        end=20,
        first_col=1,
        source="02_hongxing",
    )["tables"][0]
    t2["currency"] = "RUB"
    p["tables"].append(t2)
    result = parse_file(path, p)
    assert result["status"] == "accepted"
    assert result["counts"]["items"] == 10
    assert len([item for item in result["items"] if item["source_table"] == 1]) == 8
    arts = [item["article"] for item in result["items"]]
    # numeric 4451000123 vs string 001234
    assert "4451000123" in arts
    assert "001234" in arts
    barcodes = [item.get("extra", {}).get("barcode") for item in result["items"]]
    assert "000123" in barcodes
    assert 4800123456789 in barcodes  # numeric barcode keeps exact digits
    # merge B9:C9
    merged_items = [
        item for item in result["items"] if "merged_cells" in item.get("flags", {})
    ]
    assert any("B9:C9" in item["flags"]["merged_cells"] for item in merged_items)
    # missing brand allowed
    assert any(item.get("brand") is None for item in result["items"])
    # second table RUB, separate table, no archive sheet
    rub_items = [item for item in result["items"] if item.get("currency") == "RUB"]
    assert len(rub_items) == 2
    assert all(item.get("source_sheet") == "Sheet1" for item in rub_items)
    assert not any(
        "Archive" in str(item.get("source_sheet", "")) for item in result["items"]
    )


def test_hostile_03_megainstrument_1c():
    path = ROOT / "03_МегаИнструмент_1С_выгрузка_враждебная.xlsx"
    targets = [
        "brand",
        "article",
        "extra.barcode",
        "name",
        "qty",
        "extra.reserve",
        "price",
        "price",
        "extra.size",
    ]
    p = profile(
        path,
        targets,
        header=4,
        header_end=6,
        start=8,
        end=18,
        first_col=3,
        source="03_megainstrument",
    )
    p["policies"].update(
        {
            "hidden_rows": "include",
            "negative_price": "accept",
            "empty_price": "accept",
            "hidden_cost": "drop",
            "multiple_prices": "items",
        }
    )
    p["tables"][0]["currency"] = "RUB"
    cols = p["tables"][0]["columns"]
    # priceunknown to avoid unsupported semantic
    cols[6]["price_kind"] = "unknown"
    cols[7]["price_kind"] = "unknown"
    result = parse_file(path, p)
    assert result["status"] == "accepted"
    assert result["counts"]["source_rows"] == 11
    assert result["counts"]["items"] == 22
    # qty from G not H or K
    qty_coords = [item["coordinates"].get("qty", "") for item in result["items"]]
    assert all(c.startswith("G") for c in qty_coords if c)
    # NBSP 1250 preserved (in price raw)
    prices_raw = [item.get("raw_row", {}).get("I12", "") for item in result["items"]]
    assert any("\xa0" in str(v) for v in prices_raw if v)
    # scientific literal 4,80123E+12 preserved extra
    barcodes = [item.get("extra", {}).get("barcode") for item in result["items"]]
    assert "4,80123E+12" in barcodes
    # two CB-419 packs 1 and 10 distinct
    cb = [item for item in result["items"] if item.get("article") == "CB-419"]
    sizes = {item.get("extra", {}).get("size") for item in cb}
    assert sizes == {"1", "10"}
    # short Р preserved
    assert any(
        item.get("name") == "Р" or item.get("article") == "Р"
        for item in result["items"]
    )
    # identifier spaces preserved
    arts = [item["article"] for item in result["items"]]
    assert "1 609 203 243" in arts
    # island below the footer is surfaced as its own wizard candidate
    islands = [
        c
        for c in inspect_file(str(path))["sheets"][0]["candidates"]
        if c["header_start"] == 24
    ]
    assert len(islands) == 1
    assert (islands[0]["start_col"], islands[0]["end_col"]) == (3, 5)

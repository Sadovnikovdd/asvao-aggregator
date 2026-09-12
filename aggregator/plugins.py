"""Layout plugins enumerate source records; normalization is shared by every layout."""

from collections.abc import Callable, Iterator

_registry: dict[str, Callable] = {}


def register_layout(name: str, handler: Callable) -> None:
    if not name or name in _registry:
        raise ValueError("layout_already_registered_or_empty")
    _registry[name] = handler


def get_handler(name: str) -> Callable:
    if name not in _registry:
        raise ValueError("unsupported_layout:" + name)
    return _registry[name]


def list_layouts() -> list[str]:
    return list(_registry)


def row_records(sheet, table) -> Iterator[tuple]:
    end = table.get("data_end") or sheet.max_row
    for row in range(table["data_start"], end + 1):
        yield (
            row,
            None,
            [(column, sheet.cell(row, column["col"])) for column in table["columns"]],
        )


def vertical_records(sheet, table) -> Iterator[tuple]:
    for col in range(table["start_col"], table["end_col"] + 1):
        fields = [
            (column, sheet.cell(column["row"], col)) for column in table["columns"]
        ]
        yield min(c["row"] for c in table["columns"]), col, fields


register_layout("rows", row_records)
register_layout("crosstab", row_records)
register_layout("vertical", vertical_records)

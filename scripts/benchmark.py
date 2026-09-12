"""Run from repo root: uv run python scripts/benchmark.py --rows 100000."""

import argparse
import json
from pathlib import Path
import resource
import sys
import tempfile
import time

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aggregator.storage import Storage

parser = argparse.ArgumentParser()
parser.add_argument("--rows", type=int, default=100000)
args = parser.parse_args()
if not 1 <= args.rows <= 100000:
    parser.error("--rows must be 1..100000")
with tempfile.TemporaryDirectory(prefix="aggregator-benchmark-") as directory:
    directory = Path(directory)
    path = directory / "generated.xlsx"
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("Benchmark")
    ws.append(["Артикул", "Наименование", "Количество", "Цена"])
    for row in range(args.rows):
        ws.append([f"{row:010d}", "Проверочный товар", 5, 123.45])
    wb.save(path)
    start = time.perf_counter()
    store = Storage(directory / "data")
    file_id = store.upload_files([(path.name, path.read_bytes())], "benchmark")[0][
        "file_id"
    ]
    table = store.get_file(file_id)["inspection"]["sheets"][0]["candidates"][0]
    profile = {
        "name": "Benchmark",
        "source": "benchmark",
        "ingest_mode": "replace_all",
        "policies": {},
        "tables": [table],
    }
    result = store.approve_file(file_id, profile)
    assert result["counts"]["items"] == args.rows
    elapsed = time.perf_counter() - start
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = peak if sys.platform == "darwin" else peak * 1024
    report = {
        "rows": args.rows,
        "items": result["counts"]["items"],
        "seconds": round(elapsed, 3),
        "peak_rss_mib": round(peak_bytes / 1024**2, 2),
        "budget_gib": 14,
        "within_budget": peak_bytes < 14 * 1024**3,
    }
    print(json.dumps(report, ensure_ascii=False))
    if not report["within_budget"]:
        raise SystemExit(1)

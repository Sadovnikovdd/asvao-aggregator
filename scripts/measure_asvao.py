"""One-off measurement: full ASVAO import via Storage (upload + approve), time + peak RSS."""

import resource
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from aggregator.storage import Storage
from test_engine import asvao_profile

with tempfile.TemporaryDirectory(prefix="asvao-measure-") as d:
    path = ROOT / "ASVAO.xlsx"
    if not path.exists():
        sys.exit(
            "ASVAO.xlsx не найден: реальные прайсы не входят в репозиторий. "
            "Положите локальную копию в корень проекта и повторите замер."
        )
    start = time.perf_counter()
    store = Storage(Path(d) / "data")
    file_id = store.upload_files([(path.name, path.read_bytes())], "measure")[0][
        "file_id"
    ]
    p = asvao_profile()
    p["source"] = "measure"
    result = store.approve_file(file_id, p)
    elapsed = time.perf_counter() - start
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = peak if sys.platform == "darwin" else peak * 1024
    print(
        {
            "file": path.name,
            "items": result["counts"]["items"],
            "seconds": round(elapsed, 3),
            "peak_rss_mib": round(peak_bytes / 1024**2, 2),
            "below_16gib": peak_bytes < 16 * 1024**3,
        }
    )

"""Entry point for aggregator module. Supports `uv run python -m aggregator` or python -m aggregator."""

import os
from pathlib import Path
from .app import create_app
import uvicorn


def main() -> None:
    data_dir = os.environ.get("AGGREGATOR_DATA_DIR", str(Path.home() / ".aggregator"))
    port = int(os.environ.get("AGGREGATOR_PORT", "8000"))
    host = os.environ.get("AGGREGATOR_HOST", "127.0.0.1")  # loopback default
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("Локальное приложение можно слушать только на loopback")

    # Ensure data dir
    Path(data_dir).mkdir(parents=True, exist_ok=True)

    app = create_app(data_dir=data_dir)

    print(f"Starting aggregator on {host}:{port} (data_dir={data_dir})")
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()

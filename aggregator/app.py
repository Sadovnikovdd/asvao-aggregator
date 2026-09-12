"""Loopback web application; workbook work runs outside the async event loop."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .storage import Storage


def create_app(data_dir=None):
    storage = Storage(
        data_dir
        or os.environ.get("AGGREGATOR_DATA_DIR", str(Path.home() / ".aggregator"))
    )
    app = FastAPI(title="Универсальный агрегатор прайсов", version="0.1.0")
    app.state.storage = storage

    @app.middleware("http")
    async def local_guard(request: Request, call_next):
        host = request.url.hostname
        if host not in {"127.0.0.1", "localhost", "::1", "testserver"}:
            return JSONResponse({"detail": "host_not_allowed"}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
                return JSONResponse(
                    {"detail": "cross_origin_mutation_forbidden"}, status_code=403
                )
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse(
                    {"detail": "cross_site_mutation_forbidden"}, status_code=403
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        return response

    @app.exception_handler(ValueError)
    async def invalid_value(request, error):
        text = str(error)
        return JSONResponse(
            {"detail": text}, status_code=404 if text.endswith("_not_found") else 400
        )

    @app.get("/health")
    def health():
        return storage.get_health()

    @app.get("/api/state")
    def state():
        return storage.get_state()

    @app.post("/api/upload")
    async def upload(
        files: list[UploadFile] = File(...), source: str = Form("default")
    ):
        if len(files) > 100:
            raise HTTPException(413, "too_many_files")
        uploads = []
        total = 0
        for file in files:
            try:
                content = await file.read(storage.MAX_UPLOAD_BYTES + 1)
                total += len(content)
                if (
                    len(content) > storage.MAX_UPLOAD_BYTES
                    or total > storage.MAX_ARCHIVE_BYTES
                ):
                    raise HTTPException(413, "upload_limit_exceeded")
                uploads.append((file.filename or "unnamed", content))
            finally:
                await file.close()
        return {
            "results": await run_in_threadpool(storage.upload_files, uploads, source)
        }

    @app.get("/api/files/{file_id}")
    def get_file(file_id: str):
        return storage.get_file(file_id)

    @app.get("/api/files/{file_id}/raw")
    def raw(file_id: str):
        row = storage.file_row(file_id)
        return FileResponse(
            storage.path(row),
            filename=row["original_name"],
            media_type="application/octet-stream",
        )

    @app.post("/api/files/{file_id}/preview")
    def preview(file_id: str, profile: dict):
        return storage.preview_file(file_id, profile)

    @app.post("/api/files/{file_id}/approve")
    def approve(file_id: str, profile: dict):
        return storage.approve_file(file_id, profile)

    @app.post("/api/files/{file_id}/reprocess")
    def reprocess(file_id: str, body: dict):
        return storage.reprocess_file(file_id, body.get("profile_id"))

    @app.get("/api/shipments/{shipment_id}")
    def shipment(
        shipment_id: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
    ):
        return storage.get_shipment(shipment_id, offset, limit)

    @app.post("/api/shipments/{shipment_id}/activate")
    def activate(shipment_id: str, body: dict):
        return storage.activate_shipment(shipment_id, body.get("reason"))

    @app.get("/api/catalog")
    def catalog(
        source: str | None = None,
        q: str | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
    ):
        return storage.get_catalog(source, q, offset, limit)

    @app.get("/api/profiles/{profile_id}")
    def profile(profile_id: str, revision: int | None = None):
        saved = storage.get_profile(profile_id, revision)
        if not saved:
            raise HTTPException(404, "profile_not_found")
        return saved

    @app.get("/api/profiles/{profile_id}/yaml")
    def profile_yaml(profile_id: str, revision: int | None = None):
        saved = storage.get_profile(profile_id, revision)
        if not saved:
            raise HTTPException(404, "profile_not_found")
        body = {**saved["body"], "id": saved["id"], "revision": saved["revision"]}
        return PlainTextResponse(
            yaml.safe_dump(body, allow_unicode=True, sort_keys=False),
            media_type="application/yaml",
            headers={
                "Content-Disposition": f'attachment; filename="profile-r{saved["revision"]}.yaml"'
            },
        )

    @app.get("/api/audit")
    def audit(limit: int = Query(50, ge=1, le=200)):
        return storage.get_audit(limit)

    @app.get("/api/jobs")
    def jobs(limit: int = Query(100, ge=1, le=200)):
        return {"jobs": storage.jobs.list(limit)}

    @app.get("/api/settings")
    def settings():
        return storage.get_state()["settings"]

    @app.get("/api/capabilities")
    def capabilities():
        return storage.get_state()["capabilities"]

    @app.get("/metrics")
    def metrics():
        return PlainTextResponse(storage.get_metrics())

    static = Path(__file__).parent / "static"
    if static.exists():

        @app.get("/")
        def index_page():
            return FileResponse(static / "index.html")

        app.mount("/static", StaticFiles(directory=static), name="static")
    return app

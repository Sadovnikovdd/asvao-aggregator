"""Local transactional storage. Raw blobs and shipment snapshots are immutable."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import logging
import os
from pathlib import Path, PurePosixPath
import sqlite3
import threading
import uuid
import zipfile
from datetime import datetime, timezone

from .engine import fingerprint, inspect_file, parse_file
from .jobs import JobJournal

logger = logging.getLogger("aggregator")


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, default=str)


class Storage:
    MAX_UPLOAD_BYTES = 50 * 1024 * 1024
    MAX_ARCHIVE_BYTES = 200 * 1024 * 1024

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).resolve()
        self.cas_dir = self.data_dir / "cas"
        self.cas_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "aggregator.db"
        self._lock = threading.RLock()
        with self.connection() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY, content_hash TEXT UNIQUE NOT NULL,
                    original_name TEXT NOT NULL, size INTEGER NOT NULL,
                    source TEXT NOT NULL, status TEXT NOT NULL, reason TEXT,
                    inspection TEXT NOT NULL, uploaded_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS receipts (
                    id TEXT PRIMARY KEY, inbound_id TEXT NOT NULL,
                    file_id TEXT NOT NULL REFERENCES files(id), original_name TEXT NOT NULL,
                    created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT NOT NULL, revision INTEGER NOT NULL, source TEXT NOT NULL,
                    name TEXT NOT NULL, body TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL, PRIMARY KEY(id, revision));
                CREATE TABLE IF NOT EXISTS shipments (
                    id TEXT PRIMARY KEY, file_id TEXT NOT NULL REFERENCES files(id),
                    profile_id TEXT NOT NULL, profile_revision INTEGER NOT NULL,
                    source TEXT NOT NULL, generation INTEGER NOT NULL,
                    status TEXT NOT NULL, counts TEXT NOT NULL, created_at TEXT NOT NULL,
                    base_shipment_id TEXT REFERENCES shipments(id),
                    FOREIGN KEY(profile_id, profile_revision) REFERENCES profiles(id,revision),
                    UNIQUE(source, generation));
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY, shipment_id TEXT NOT NULL REFERENCES shipments(id),
                    article TEXT, name TEXT, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS items_shipment ON items(shipment_id);
                CREATE TABLE IF NOT EXISTS current (
                    source TEXT PRIMARY KEY, shipment_id TEXT NOT NULL REFERENCES shipments(id),
                    activated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS dispositions (
                    id INTEGER PRIMARY KEY, file_id TEXT NOT NULL REFERENCES files(id),
                    shipment_id TEXT REFERENCES shipments(id), kind TEXT NOT NULL,
                    payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY, event_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL);
            """)
        self.jobs = JobJournal(self.connection, self._journal_runner)
        self.jobs.recover()

    @contextlib.contextmanager
    def connection(self, write=False):
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.commit()
        except BaseException:
            if write:
                conn.rollback()
            raise
        finally:
            conn.close()

    def audit(self, conn, event, entity, details):
        conn.execute(
            "INSERT INTO audit(event_type,entity_id,details,created_at) VALUES(?,?,?,?)",
            (event, entity, encode(details), datetime.now(timezone.utc).isoformat()),
        )
        logger.info(encode({"schema_version": 1, "event": event, "entity_id": entity}))

    def path(self, file_row):
        return self.cas_dir / file_row["content_hash"]

    def _record(self, name, content, source, inbound):
        digest = hashlib.sha256(content).hexdigest()
        dest = self.cas_dir / digest
        temporary = self.cas_dir / (".upload-" + uuid.uuid4().hex)
        try:
            with temporary.open("xb") as out:
                out.write(content)
                out.flush()
                os.fsync(out.fileno())
            try:
                os.link(temporary, dest)
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)
        with self.connection(write=True) as conn:
            existing = conn.execute(
                "SELECT * FROM files WHERE content_hash=?", (digest,)
            ).fetchone()
            replay = existing is not None
            file_id = existing["id"] if replay else uuid.uuid4().hex
            if not replay:
                conn.execute(
                    "INSERT INTO files (id,content_hash,original_name,size,source,status,reason,inspection,uploaded_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        file_id,
                        digest,
                        name,
                        len(content),
                        source,
                        "review",
                        None,
                        encode({}),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            conn.execute(
                "INSERT INTO receipts VALUES(?,?,?,?,?)",
                (
                    uuid.uuid4().hex,
                    inbound,
                    file_id,
                    name,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self.audit(
                conn,
                "file.replay" if replay else "raw.stored",
                file_id,
                {"inbound_id": inbound},
            )
        return file_id, replay

    def _quarantine_file(self, file_id, reason, result=None):
        with self.connection(write=True) as conn:
            conn.execute(
                "UPDATE files SET status='quarantine',reason=? WHERE id=?",
                (reason, file_id),
            )
            for row in (result or {}).get("quarantine", []):
                conn.execute(
                    "INSERT INTO dispositions(file_id,kind,payload) VALUES(?,'quarantine',?)",
                    (file_id, encode(row)),
                )
            self.audit(conn, "file.quarantined", file_id, {"reason_code": reason})
        return {"file_id": file_id, "status": "quarantine", "reason": reason}

    def upload_files(self, file_tuples, source=None):
        results = []
        inbound = uuid.uuid4().hex
        source = str(source or "default").strip() or "default"
        expanded = []
        total = 0
        for name, content in file_tuples:
            if len(content) > self.MAX_UPLOAD_BYTES:
                raise ValueError("upload_limit_exceeded")
            name = Path(str(name).replace("\\", "/")).name[:240] or "unnamed"
            total += len(content)
            if zipfile.is_zipfile(io.BytesIO(content)):
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    entries = archive.infolist()
                    # OOXML itself is an archive, not an attachment bundle.
                    if "[Content_Types].xml" not in archive.namelist():
                        if (
                            len(entries) > 100
                            or sum(e.file_size for e in entries)
                            > self.MAX_ARCHIVE_BYTES
                        ):
                            raise ValueError("archive_limit_exceeded")
                        for entry in entries:
                            part = PurePosixPath(entry.filename.replace("\\", "/"))
                            if entry.is_dir():
                                continue
                            if (
                                part.is_absolute()
                                or ".." in part.parts
                                or entry.flag_bits & 1
                            ):
                                raise ValueError("unsafe_or_encrypted_archive")
                            if (
                                entry.file_size > self.MAX_UPLOAD_BYTES
                                or entry.file_size > max(entry.compress_size, 1) * 1000
                                or total + entry.file_size > self.MAX_ARCHIVE_BYTES
                                or len(expanded) >= 100
                            ):
                                raise ValueError("archive_limit_exceeded")
                            blob = archive.read(entry)
                            total += len(blob)
                            expanded.append((part.name, blob))
                        continue
            expanded.append((name, content))
        if total > self.MAX_ARCHIVE_BYTES or len(expanded) > 100:
            raise ValueError("upload_batch_limit_exceeded")
        with self._lock:
            for name, content in expanded:
                file_id, replay = self._record(name, content, source, inbound)
                if replay:
                    results.append(
                        {
                            "file_id": file_id,
                            "status": "replay",
                            "reason": "same_sha256",
                        }
                    )
                    continue
                file_row = self.file_row(file_id)
                try:
                    inspection = inspect_file(str(self.path(file_row)))
                    if not inspection.get("sheets"):
                        raise ValueError("unsupported_or_empty_workbook")
                    with self.connection(write=True) as conn:
                        conn.execute(
                            "UPDATE files SET inspection=? WHERE id=?",
                            (encode(inspection), file_id),
                        )
                    matches = []
                    for saved in self.list_profiles(source=source):
                        try:
                            if (
                                fingerprint(str(self.path(file_row)), saved["body"])
                                == saved["fingerprint"]
                            ):
                                matches.append(saved)
                        except (ValueError, KeyError, TypeError):
                            continue
                    if len(matches) == 1:
                        saved = matches[0]
                        result = parse_file(str(self.path(file_row)), saved["body"])
                        if result["status"] != "accepted":
                            results.append(
                                self._quarantine_file(
                                    file_id,
                                    result.get("reason") or "parse_quarantine",
                                    result,
                                )
                            )
                        else:
                            if saved["body"].get("ingest_mode") == "replace_all":
                                with self.connection() as conn:
                                    current_count = conn.execute(
                                        "SELECT count(*) FROM items WHERE shipment_id=(SELECT shipment_id FROM current WHERE source=?)",
                                        (source,),
                                    ).fetchone()[0]
                                if (
                                    current_count
                                    and result["counts"]["items"] < current_count
                                ):
                                    results.append(
                                        {
                                            "file_id": file_id,
                                            "status": "review",
                                            "reason": "replace_all_shrink_requires_explicit_mode",
                                        }
                                    )
                                    continue
                            results.append(
                                self._commit(
                                    file_id, saved["body"], result, saved=saved
                                )
                            )
                    else:
                        results.append(
                            {
                                "file_id": file_id,
                                "status": "review",
                                "reason": "ambiguous_profile"
                                if matches
                                else "unknown_layout",
                            }
                        )
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    results.append(self._quarantine_file(file_id, str(exc)))
        return results

    def file_row(self, file_id):
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
            if row is None:
                raise ValueError("file_not_found")
            return dict(row)

    def get_file(self, file_id):
        row = self.file_row(file_id)
        inspection = json.loads(row.pop("inspection"))
        with self.connection() as conn:
            issues = [
                json.loads(r[0])
                for r in conn.execute(
                    "SELECT payload FROM dispositions WHERE file_id=? AND kind='quarantine' ORDER BY id DESC LIMIT 100",
                    (file_id,),
                )
            ]
        return {
            "file": row,
            "inspection": inspection,
            "profile": None,
            "quarantine": issues,
        }

    def get_raw_bytes(self, file_id):
        return self.path(self.file_row(file_id)).read_bytes()

    def preview_file(self, file_id, profile):
        path = str(self.path(self.file_row(file_id)))
        try:
            result = parse_file(path, profile, limit=100)
            result["fingerprint"] = fingerprint(path, profile)
            result["valid"] = (
                result["status"] == "accepted" and not result["quarantine"]
            )
            return result
        except (ValueError, KeyError, TypeError) as exc:
            return {
                "status": "quarantine",
                "valid": False,
                "reason": str(exc),
                "items": [],
                "quarantine": [],
                "dropped": [],
                "counts": {"items": 0},
            }

    def _journal_runner(self, file_id, profile, saved, reprocess, job_id):
        with self._lock:
            preview = self.preview_file(file_id, profile)
            if not preview["valid"]:
                self._quarantine_file(
                    file_id, preview.get("reason") or "dry_run_failed", preview
                )
                raise ValueError("dry_run_failed: профиль не сохранён")
            result = parse_file(str(self.path(self.file_row(file_id))), profile)
            if result["status"] != "accepted":
                outcome = self._quarantine_file(
                    file_id, result.get("reason") or "parse_quarantine", result
                )
                with self.connection(write=True) as conn:
                    return self.jobs.finish(conn, job_id, outcome)
            return self._commit(
                file_id,
                profile,
                result,
                saved=saved,
                reprocess=reprocess,
                job_id=job_id,
            )

    def approve_file(self, file_id, profile):
        return self.jobs.run(file_id, profile)

    def _commit(
        self, file_id, profile, result, saved=None, reprocess=False, job_id=None
    ):
        mode = profile.get("ingest_mode")
        if mode not in {"replace_all", "append", "delta"}:
            raise ValueError("explicit_ingest_mode_required")
        source = str(profile.get("source") or "default")
        path = str(self.path(self.file_row(file_id)))
        fp = fingerprint(path, profile)
        with self.connection(write=True) as conn:
            prior = conn.execute(
                "SELECT id,base_shipment_id FROM shipments WHERE file_id=? AND source=? ORDER BY generation DESC LIMIT 1",
                (file_id, source),
            ).fetchone()
            revision_save = saved is None and bool(profile.get("id"))
            if prior and not reprocess and not revision_save:
                outcome = {
                    "file_id": file_id,
                    "status": "replay",
                    "shipment_id": prior[0],
                    "reason": "already_committed",
                }
                if job_id:
                    outcome = self.jobs.finish(conn, job_id, outcome)
                return outcome
            current = conn.execute(
                "SELECT shipment_id FROM current WHERE source=?", (source,)
            ).fetchone()
            base_id = (
                prior["base_shipment_id"]
                if (reprocess or revision_save) and prior
                else (current[0] if current else None)
            )
            old = (
                [
                    json.loads(r[0])
                    for r in conn.execute(
                        "SELECT payload FROM items WHERE shipment_id=? ORDER BY id",
                        (base_id,),
                    )
                ]
                if base_id
                else []
            )
            new = list(result["items"])
            if mode == "append":
                new = old + new
            elif mode == "delta":
                delta = profile.get("delta", {})
                keys, operation = delta.get("key_fields"), delta.get("operation_field")
                if (
                    not isinstance(keys, list)
                    or not keys
                    or not isinstance(operation, str)
                    or not operation
                ):
                    raise ValueError("delta_requires_key_fields_and_operation_field")

                def field(item, key):
                    value = item
                    for component in key.split("."):
                        value = (
                            value.get(component) if isinstance(value, dict) else None
                        )
                    return value

                def identity(item):
                    values = tuple(field(item, key) for key in keys)
                    if any(
                        v is None or v == "" or isinstance(v, (dict, list))
                        for v in values
                    ):
                        raise ValueError("delta_invalid_key")
                    return values

                by_key = {}
                for item in old:
                    key = identity(item)
                    if key in by_key:
                        raise ValueError("delta_ambiguous_existing_key")
                    by_key[key] = item
                seen = set()
                for item in new:
                    key = identity(item)
                    if key in seen:
                        raise ValueError("delta_duplicate_patch_key")
                    seen.add(key)
                    op = field(item, operation)
                    if op == "upsert":
                        by_key[key] = item
                    elif op == "delete":
                        if key not in by_key:
                            raise ValueError("delta_delete_missing_key")
                        del by_key[key]
                    elif op != "no_change":
                        raise ValueError("delta_unknown_operation")
                new = list(by_key.values())
            if not new:
                raise ValueError("empty_current_forbidden")
            if saved:
                pid, revision = saved["id"], saved["revision"]
            else:
                pid = profile.get("id") or uuid.uuid4().hex
                owner = conn.execute(
                    "SELECT source FROM profiles WHERE id=? LIMIT 1", (pid,)
                ).fetchone()
                if owner and owner[0] != source:
                    raise ValueError("profile_source_immutable")
                revision = conn.execute(
                    "SELECT coalesce(max(revision),0)+1 FROM profiles WHERE id=?",
                    (pid,),
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO profiles VALUES(?,?,?,?,?,?,?)",
                    (
                        pid,
                        revision,
                        source,
                        profile.get("name") or "Профиль",
                        encode(profile),
                        fp,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            generation = conn.execute(
                "SELECT coalesce(max(generation),0)+1 FROM shipments WHERE source=?",
                (source,),
            ).fetchone()[0]
            sid = uuid.uuid4().hex
            counts = dict(
                result["counts"], items=len(new), imported_items=len(result["items"])
            )
            conn.execute(
                "INSERT INTO shipments VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    sid,
                    file_id,
                    pid,
                    revision,
                    source,
                    generation,
                    "accepted",
                    encode(counts),
                    datetime.now(timezone.utc).isoformat(),
                    base_id,
                ),
            )
            for item in new:
                item = dict(item)
                item.setdefault("source_file_id", file_id)
                item.setdefault("profile_rev", revision)
                conn.execute(
                    "INSERT INTO items(shipment_id,article,name,payload) VALUES(?,?,?,?)",
                    (sid, item.get("article"), item.get("name"), encode(item)),
                )
            for kind in ("quarantine", "dropped"):
                conn.executemany(
                    "INSERT INTO dispositions(file_id,shipment_id,kind,payload) VALUES(?,?,?,?)",
                    ((file_id, sid, kind, encode(row)) for row in result.get(kind, [])),
                )
            if not reprocess:
                conn.execute(
                    "INSERT INTO current VALUES(?,?,?) ON CONFLICT(source) DO UPDATE SET shipment_id=excluded.shipment_id,activated_at=excluded.activated_at",
                    (source, sid, datetime.now(timezone.utc).isoformat()),
                )
            conn.execute(
                "UPDATE files SET status='imported',reason=NULL,source=? WHERE id=?",
                (source, file_id),
            )
            self.audit(
                conn,
                "shipment.committed",
                sid,
                {
                    "file_id": file_id,
                    "profile_id": pid,
                    "profile_rev": revision,
                    "mode": mode,
                    "items": len(new),
                },
            )
            outcome = {
                "file_id": file_id,
                "status": "accepted",
                "shipment_id": sid,
                "profile_id": pid,
                "profile_revision": revision,
                "generation": generation,
                "source": source,
                "counts": counts,
            }
            if job_id:
                outcome = self.jobs.finish(conn, job_id, outcome)
            return outcome

    def reprocess_file(self, file_id, profile_id):
        with self._lock:
            saved = self.get_profile(profile_id)
            if not saved:
                raise ValueError("profile_not_found")
            path = str(self.path(self.file_row(file_id)))
            if fingerprint(path, saved["body"]) != saved["fingerprint"]:
                raise ValueError("profile_fingerprint_miss")
            return self.jobs.run(file_id, saved["body"], saved=saved, reprocess=True)

    def activate_shipment(self, shipment_id, reason):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("activation_reason_required")
        with self.connection(write=True) as conn:
            ship = conn.execute(
                "SELECT * FROM shipments WHERE id=?", (shipment_id,)
            ).fetchone()
            if ship is None or ship["status"] != "accepted":
                raise ValueError("shipment_not_activatable")
            conn.execute(
                "INSERT INTO current VALUES(?,?,?) ON CONFLICT(source) DO UPDATE SET shipment_id=excluded.shipment_id,activated_at=excluded.activated_at",
                (ship["source"], shipment_id, datetime.now(timezone.utc).isoformat()),
            )
            self.audit(
                conn,
                "current.rollback",
                shipment_id,
                {"reason": reason, "source": ship["source"]},
            )
            return {
                "shipment_id": shipment_id,
                "source": ship["source"],
                "status": "accepted",
            }

    def get_shipment(self, shipment_id, offset=0, limit=100):
        with self.connection() as conn:
            ship = conn.execute(
                "SELECT * FROM shipments WHERE id=?", (shipment_id,)
            ).fetchone()
            if ship is None:
                raise ValueError("shipment_not_found")
            ship = dict(ship)
            ship["counts"] = json.loads(ship["counts"])
            items = [
                dict(json.loads(r["payload"]), shipment_id=shipment_id)
                for r in conn.execute(
                    "SELECT payload FROM items WHERE shipment_id=? ORDER BY id LIMIT ? OFFSET ?",
                    (shipment_id, limit, offset),
                )
            ]
            issues = {}
            for kind in ("quarantine", "dropped"):
                issues[kind] = [
                    json.loads(r[0])
                    for r in conn.execute(
                        "SELECT payload FROM dispositions WHERE shipment_id=? AND kind=? ORDER BY id LIMIT ? OFFSET ?",
                        (shipment_id, kind, limit, offset),
                    )
                ]
                issues["total_" + kind] = conn.execute(
                    "SELECT count(*) FROM dispositions WHERE shipment_id=? AND kind=?",
                    (shipment_id, kind),
                ).fetchone()[0]
            return {
                "shipment": ship,
                "items": items,
                **issues,
                "total_items": ship["counts"]["items"],
            }

    def get_catalog(self, source=None, q=None, offset=0, limit=100):
        params = []
        where = []
        if source:
            where.append("c.source=?")
            params.append(source)
        if q:
            where.append("(i.article LIKE ? OR i.name LIKE ?)")
            params.extend(["%" + q + "%"] * 2)
        clause = " WHERE " + " AND ".join(where) if where else ""
        sql = " FROM items i JOIN current c ON c.shipment_id=i.shipment_id" + clause
        with self.connection() as conn:
            total = conn.execute("SELECT count(*)" + sql, params).fetchone()[0]
            rows = conn.execute(
                "SELECT i.payload,i.shipment_id,c.source"
                + sql
                + " ORDER BY i.id LIMIT ? OFFSET ?",
                [*params, limit, offset],
            )
            return {
                "items": [
                    dict(json.loads(r[0]), shipment_id=r[1], source=r[2]) for r in rows
                ],
                "total": total,
            }

    def list_profiles(self, source=None, history=False):
        with self.connection() as conn:
            sql = (
                "SELECT p.* FROM profiles p WHERE 1=1"
                if history
                else "SELECT p.* FROM profiles p WHERE revision=(SELECT max(revision) FROM profiles WHERE id=p.id)"
            )
            params = []
            if source:
                sql += " AND source=?"
                params.append(source)
            rows = conn.execute(sql + " ORDER BY created_at DESC", params)
            return [dict(r, body=json.loads(r["body"])) for r in rows]

    def get_profile(self, profile_id, revision=None):
        with self.connection() as conn:
            sql = "SELECT * FROM profiles WHERE id=?"
            params = [profile_id]
            if revision is not None:
                sql += " AND revision=?"
                params.append(revision)
            row = conn.execute(
                sql + " ORDER BY revision DESC LIMIT 1", params
            ).fetchone()
            return dict(row, body=json.loads(row["body"])) if row else None

    def list_shipments(self, source=None, limit=100):
        with self.connection() as conn:
            sql = "SELECT * FROM shipments" + (" WHERE source=?" if source else "")
            rows = conn.execute(
                sql + " ORDER BY created_at DESC LIMIT ?",
                [source, limit] if source else [limit],
            )
            return [dict(r, counts=json.loads(r["counts"])) for r in rows]

    def get_audit(self, limit=50):
        with self.connection() as conn:
            return [
                dict(r, details=json.loads(r["details"]))
                for r in conn.execute(
                    "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)
                )
            ]

    def get_state(self):
        with self.connection() as conn:
            files = [
                dict(r)
                for r in conn.execute(
                    "SELECT id,content_hash AS hash,original_name,size,source,status,reason,uploaded_at FROM files ORDER BY uploaded_at DESC LIMIT 100"
                )
            ]
            sources = [
                dict(r)
                for r in conn.execute(
                    "SELECT s.source AS name,c.shipment_id AS current_shipment_id,(SELECT count(*) FROM items WHERE shipment_id=c.shipment_id) AS item_count FROM (SELECT source FROM files UNION SELECT source FROM profiles) s LEFT JOIN current c ON c.source=s.source"
                )
            ]
        return {
            "files": files,
            "profiles": self.list_profiles(history=True),
            "shipments": self.list_shipments(),
            "sources": sources,
            "settings": {
                "max_upload_mb": 50,
                "storage": "sqlite_wal",
                "loopback_only": True,
                "quarantine_threshold_default": 0.15,
            },
            "capabilities": {
                "formats": ["xlsx", "xls", "csv"],
                "adapters": {
                    "xlsx": {"supported": True},
                    "xls": {"supported": True, "note": "xlrd; без LibreOffice"},
                    "csv": {"supported": True},
                    "zip": {"supported": True},
                    "mail": {
                        "supported": False,
                        "reason": "Адаптер почты не установлен",
                    },
                    "llm": {
                        "supported": False,
                        "reason": "Выключен, импорт не зависит от модели",
                    },
                    "postgres": {
                        "supported": False,
                        "reason": "Локальный backend SQLite",
                    },
                },
                "ingest_modes": ["replace_all", "append", "delta"],
                "policies": {
                    "P1": {
                        "supported": True,
                        "config_key": "policies.hidden_rows",
                        "description": "include / skip / quarantine",
                    },
                    "P2": {
                        "supported": True,
                        "config_key": "policies.negative_price",
                        "description": "accept / quarantine",
                    },
                    "P3": {
                        "supported": True,
                        "config_key": "policies.multiple_prices",
                        "description": "items / extra",
                    },
                    "P4": {
                        "supported": True,
                        "config_key": "tables",
                        "description": "Несколько областей и вторая таблица на листе — явный выбор; неизвестные — мастер",
                    },
                    "P5": {
                        "supported": True,
                        "config_key": "policies.empty_price",
                        "description": "accept / quarantine",
                    },
                    "P6": {
                        "supported": True,
                        "config_key": "policies.hidden_cost",
                        "description": "drop / quarantine",
                    },
                    "P7": {
                        "supported": True,
                        "config_key": "ingest_mode",
                        "description": "replace_all / append / delta; выбор обязателен",
                    },
                    "P8": {
                        "supported": True,
                        "config_key": "tables.columns.currency",
                        "description": "Валюта каждой цены в колонках",
                    },
                    "P9": {
                        "supported": True,
                        "config_key": "tables.sheet",
                        "description": "Листы выбираются явно",
                    },
                    "P10": {
                        "supported": True,
                        "config_key": "tables.orientation",
                        "description": "rows / vertical / crosstab",
                    },
                    "P11": {
                        "supported": True,
                        "config_key": "engine.zero_items_quarantine",
                        "description": "Ноль позиций — карантин файла; активный каталог никогда не пустеет (порог строк — мера G7)",
                    },
                },
            },
        }

    def get_health(self):
        with self.connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ok"}

    def get_metrics(self):
        with self.connection() as conn:
            return "".join(
                f"# TYPE aggregator_{name}_total gauge\naggregator_{name}_total {conn.execute('SELECT count(*) FROM ' + table).fetchone()[0]}\n"
                for name, table in (
                    ("files", "files"),
                    ("shipments", "shipments"),
                    ("items", "items"),
                    ("receipts", "receipts"),
                )
            )

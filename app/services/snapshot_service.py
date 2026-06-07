"""
Snapshot Service — full disaster-recovery backup/restore.

A snapshot is a `.zip` containing a `pg_dump` of the whole database plus a mirror
of every MinIO object. Unlike the logical bundle (backup_service.py), a snapshot
restores the system *exactly* — same schema, same rows, same files.

Layout:
    manifest.json   { format, arkon_version, created_at, bucket }
    db.dump         pg_dump custom format (-Fc)
    minio/<object_name>...

Requires `pg_dump` / `pg_restore` on PATH (installed via the Dockerfile).
"""

from __future__ import annotations

import asyncio
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.config import settings
from app.services.storage_service import storage_service

SNAPSHOT_FORMAT = "arkon-snapshot"
SNAPSHOT_VERSION = 1


def _libpq_url() -> str:
    """Convert the SQLAlchemy async URL into a libpq URI pg_dump understands."""
    return settings.database_url.replace("+asyncpg", "").replace("postgresql+psycopg2", "postgresql")


async def _run(*args: str, timeout: int = 1800) -> None:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"Command timed out after {timeout}s: {args[0]}")
    if proc.returncode != 0:
        msg = (err or b"").decode(errors="replace")[-2000:]
        raise RuntimeError(f"{args[0]} failed (exit {proc.returncode}): {msg}")


async def create_snapshot(out_path: str, work_dump_path: str, arkon_version: str = "0.1.0") -> dict[str, Any]:
    """Create a full snapshot zip at out_path. work_dump_path is a scratch file."""
    # 1. pg_dump → custom format file
    await _run("pg_dump", "-Fc", "-d", _libpq_url(), "-f", work_dump_path)

    # 2. zip db.dump + all MinIO objects
    objects = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(work_dump_path, "db.dump")
        try:
            for obj in storage_service.list_objects("", recursive=True):
                if not obj.object_name:
                    continue
                blob = storage_service.download_file(obj.object_name)
                zf.writestr(f"minio/{obj.object_name}", blob)
                objects += 1
        except Exception as e:
            logger.warning(f"snapshot: MinIO mirror incomplete: {e}")

        manifest = {
            "format": SNAPSHOT_FORMAT,
            "snapshot_version": SNAPSHOT_VERSION,
            "arkon_version": arkon_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "bucket": settings.minio_bucket,
            "minio_objects": objects,
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    logger.info(f"snapshot: created {out_path} ({objects} MinIO objects)")
    return manifest


def read_manifest(zip_path: str) -> dict[str, Any]:
    with zipfile.ZipFile(zip_path, "r") as zf:
        try:
            raw = zf.read("manifest.json")
        except KeyError:
            raise ValueError("Not a valid Arkon snapshot: manifest.json missing")
    manifest = json.loads(raw)
    if manifest.get("format") != SNAPSHOT_FORMAT:
        raise ValueError("Not a valid Arkon snapshot (bad format marker)")
    return manifest


async def restore_snapshot(zip_path: str, work_dump_path: str) -> dict[str, Any]:
    """Restore a full snapshot: pg_restore (clean) + re-upload all MinIO objects.

    DESTRUCTIVE — drops and recreates objects in the target database.
    """
    manifest = read_manifest(zip_path)

    with zipfile.ZipFile(zip_path, "r") as zf:
        # 1. extract db.dump
        with open(work_dump_path, "wb") as fh:
            fh.write(zf.read("db.dump"))

        # 2. pg_restore with clean (drop existing objects first)
        await _run(
            "pg_restore", "--clean", "--if-exists", "--no-owner", "--no-acl",
            "-d", _libpq_url(), work_dump_path,
        )

        # 3. re-upload MinIO objects
        try:
            await storage_service.ensure_bucket()
        except Exception:
            pass
        uploaded = 0
        for name in zf.namelist():
            if not name.startswith("minio/") or name.endswith("/"):
                continue
            key = name[len("minio/"):]
            if not key:
                continue
            try:
                storage_service.upload_file(key, zf.read(name))
                uploaded += 1
            except Exception as e:
                logger.warning(f"snapshot restore: could not upload {key}: {e}")

    logger.info(f"snapshot: restored {zip_path} ({uploaded} MinIO objects)")
    return {"restored": True, "minio_uploaded": uploaded, "manifest": manifest}

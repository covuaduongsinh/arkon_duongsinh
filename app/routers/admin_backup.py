"""
Admin backup router — export/import logical bundles and full snapshots.

All endpoints require the `org:backup:manage` permission (admins always have it).

  GET  /api/admin/backup/export            -> download a .arkon.zip bundle
  POST /api/admin/backup/import            -> analyze (dry_run) or apply a bundle
  GET  /api/admin/backup/snapshot          -> download a full pg_dump+MinIO snapshot
  POST /api/admin/backup/snapshot/restore  -> restore a full snapshot (destructive)
"""

import os
import tempfile
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.database import get_db
from app.database.models import Employee
from app.services import backup_service, snapshot_service
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission

router = APIRouter(prefix="/admin/backup")

_VALID_SECTIONS = set(backup_service.SECTIONS)


def _parse_sections(raw: str | None) -> set[str]:
    if not raw:
        return set(_VALID_SECTIONS)
    parts = {s.strip() for s in raw.split(",") if s.strip()}
    bad = parts - _VALID_SECTIONS
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown sections: {', '.join(sorted(bad))}")
    return parts


def _tmp(suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="arkon_backup_")
    os.close(fd)
    return path


def _cleanup(*paths: str) -> None:
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Logical bundle: export
# ---------------------------------------------------------------------------

@router.get("/export")
async def export_bundle(
    sections: str | None = None,
    include_files: bool = True,
    include_secrets: bool = False,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("org:backup:manage"),
):
    """Build and stream a portable .arkon.zip bundle."""
    selected = _parse_sections(sections)
    out_path = _tmp(".arkon.zip")
    try:
        await backup_service.export_bundle(
            db, out_path,
            sections=selected,
            include_files=include_files,
            include_secrets=include_secrets,
        )
    except Exception as e:
        _cleanup(out_path)
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")

    await log_audit(
        db, user, "export", "backup", "bundle",
        reason=f"sections={','.join(sorted(selected))} files={include_files} secrets={include_secrets}",
    )
    await db.commit()

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"arkon_backup_{ts}.arkon.zip"
    return FileResponse(
        out_path,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(_cleanup, out_path),
    )


# ---------------------------------------------------------------------------
# Logical bundle: analyze (dry-run) / import
# ---------------------------------------------------------------------------

@router.post("/import")
async def import_bundle(
    file: UploadFile = File(...),
    mode: str = Form("merge"),
    sections: str | None = Form(None),
    dry_run: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("org:backup:manage"),
):
    """Analyze (dry_run=true) or apply (dry_run=false) an uploaded bundle."""
    if mode not in ("merge", "replace"):
        raise HTTPException(status_code=400, detail="mode must be 'merge' or 'replace'")
    selected = _parse_sections(sections)

    in_path = _tmp(".arkon.zip")
    try:
        with open(in_path, "wb") as fh:
            while chunk := await file.read(1024 * 1024):
                fh.write(chunk)

        try:
            backup_service.read_manifest(in_path)  # validates format early
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        if dry_run:
            report = await backup_service.analyze_bundle(db, in_path, selected)
        else:
            report = await backup_service.import_bundle(db, in_path, selected, mode)
            await log_audit(
                db, user, "import", "backup", "bundle",
                reason=f"mode={mode} sections={','.join(sorted(selected))}",
            )
            await db.commit()
        return report
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")
    finally:
        _cleanup(in_path)


# ---------------------------------------------------------------------------
# Full snapshot: export / restore
# ---------------------------------------------------------------------------

@router.get("/snapshot")
async def export_snapshot(
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("org:backup:manage"),
):
    """Build and stream a full pg_dump + MinIO snapshot (disaster recovery)."""
    out_path = _tmp(".snapshot.zip")
    dump_path = _tmp(".dump")
    try:
        await snapshot_service.create_snapshot(out_path, dump_path)
    except Exception as e:
        _cleanup(out_path, dump_path)
        raise HTTPException(status_code=500, detail=f"Snapshot failed: {e}")
    finally:
        _cleanup(dump_path)

    await log_audit(db, user, "export", "backup", "snapshot")
    await db.commit()

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return FileResponse(
        out_path,
        media_type="application/zip",
        filename=f"arkon_snapshot_{ts}.zip",
        background=BackgroundTask(_cleanup, out_path),
    )


@router.post("/snapshot/restore")
async def restore_snapshot(
    file: UploadFile = File(...),
    confirm: str = Form(...),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("org:backup:manage"),
):
    """Restore a full snapshot. DESTRUCTIVE — requires confirm == 'RESTORE'."""
    if confirm != "RESTORE":
        raise HTTPException(status_code=400, detail="Type RESTORE to confirm this destructive action")

    # Audit before the restore wipes the table (best-effort).
    await log_audit(db, user, "restore", "backup", "snapshot")
    await db.commit()

    in_path = _tmp(".snapshot.zip")
    dump_path = _tmp(".dump")
    try:
        with open(in_path, "wb") as fh:
            while chunk := await file.read(1024 * 1024):
                fh.write(chunk)
        try:
            snapshot_service.read_manifest(in_path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return await snapshot_service.restore_snapshot(in_path, dump_path)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {e}")
    finally:
        _cleanup(in_path, dump_path)

"""
Backup Service — logical portable bundle export / analyze / import.

A bundle is a `.arkon.zip` containing one JSONL file per table (1 row/line) plus
the original binary objects pulled from MinIO. It is *portable*: it can be
re-imported into the same or a different Arkon instance.

Layout:
    manifest.json
    wiki/    pages.jsonl, branches.jsonl, drafts.jsonl, revisions.jsonl,
             draft_rounds.jsonl, links.jsonl
    sources/ sources.jsonl, source_departments.jsonl, source_images.jsonl,
             chunk_extracts.jsonl, compilation_plans.jsonl
             files/<minio_key>
    skills/  skills.jsonl, skill_departments.jsonl, skill_versions.jsonl,
             skill_contributions.jsonl
             files/<minio_key>
    config/  departments.jsonl, knowledge_types.jsonl, employees.jsonl,
             employee_departments.jsonl, app_config.jsonl

Design notes:
  - Primary keys (UUIDs) are preserved on import so foreign keys between tables
    stay intact. Merge = upsert by PK; a natural-key collision under a *different*
    PK is reported as a conflict and skipped.
  - Embeddings (wiki_page_embeddings_* / source_chunk_embeddings_*) are NOT
    exported — they are regenerable. Run a re-embed after restore.
  - app_config secrets are skipped unless include_secrets=True; when included the
    value is kept in its encrypted-at-rest form (only decryptable with the same
    SECRET_KEY).
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from loguru import logger
from sqlalchemy import delete, inspect as sa_inspect, select
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import DateTime as SA_DateTime

from app.database.models import (
    AppConfig,
    Department,
    Employee,
    EmployeeDepartment,
    KnowledgeType,
    Skill,
    SkillContribution,
    SkillDepartment,
    SkillVersion,
    Source,
    SourceChunkExtract,
    SourceCompilationPlan,
    SourceDepartment,
    SourceImage,
    WikiBranch,
    WikiDraftRound,
    WikiLink,
    WikiPage,
    WikiPageDraft,
    WikiPageRevision,
)
from app.services.config_service import _is_sensitive
from app.services.storage_service import storage_service

BUNDLE_FORMAT = "arkon-bundle"
BUNDLE_VERSION = 1

SECTIONS = ("wiki", "sources", "skills", "config")


@dataclass
class TableSpec:
    """Describes how one ORM table maps into the bundle."""
    section: str
    model: type
    path: str                       # jsonl path inside the zip
    natural_key: tuple[str, ...] = ()  # attrs forming a portable identity (besides PK)


# Order matters: parents first so foreign keys resolve on insert.
# (delete/replace walks this list in reverse.)
TABLE_SPECS: list[TableSpec] = [
    # --- config (parents for almost everything) ---
    TableSpec("config", Department, "config/departments.jsonl", ("name",)),
    TableSpec("config", KnowledgeType, "config/knowledge_types.jsonl", ("slug",)),
    TableSpec("config", Employee, "config/employees.jsonl", ("email",)),
    TableSpec("config", EmployeeDepartment, "config/employee_departments.jsonl"),
    # --- sources ---
    TableSpec("sources", Source, "sources/sources.jsonl"),
    TableSpec("sources", SourceDepartment, "sources/source_departments.jsonl"),
    TableSpec("sources", SourceImage, "sources/source_images.jsonl"),
    TableSpec("sources", SourceChunkExtract, "sources/chunk_extracts.jsonl"),
    TableSpec("sources", SourceCompilationPlan, "sources/compilation_plans.jsonl"),
    # --- wiki ---
    TableSpec("wiki", WikiPage, "wiki/pages.jsonl", ("slug", "scope_type", "scope_id")),
    TableSpec("wiki", WikiBranch, "wiki/branches.jsonl"),
    TableSpec("wiki", WikiPageDraft, "wiki/drafts.jsonl"),
    TableSpec("wiki", WikiPageRevision, "wiki/revisions.jsonl"),
    TableSpec("wiki", WikiDraftRound, "wiki/draft_rounds.jsonl"),
    TableSpec("wiki", WikiLink, "wiki/links.jsonl"),
    # --- skills ---
    TableSpec("skills", Skill, "skills/skills.jsonl"),
    TableSpec("skills", SkillDepartment, "skills/skill_departments.jsonl"),
    TableSpec("skills", SkillVersion, "skills/skill_versions.jsonl"),
    TableSpec("skills", SkillContribution, "skills/skill_contributions.jsonl"),
    # --- config (no FK; place last) ---
    TableSpec("config", AppConfig, "config/app_config.jsonl", ("key",)),
]


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _json_default(o: Any) -> Any:
    if isinstance(o, uuid.UUID):
        return str(o)
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"Not JSON serializable: {type(o)}")


def _column_attr_keys(model: type) -> list[str]:
    return [attr.key for attr in sa_inspect(model).column_attrs]


def _pk_attr_keys(model: type) -> list[str]:
    """Primary-key attribute names in column order."""
    mapper = sa_inspect(model)
    col_to_attr = {attr.columns[0]: attr.key for attr in mapper.column_attrs}
    return [col_to_attr[col] for col in mapper.primary_key]


def _load_converters(model: type) -> dict[str, Callable[[Any], Any]]:
    """Per-attribute string->python converters for import."""
    convs: dict[str, Callable[[Any], Any]] = {}
    for attr in sa_inspect(model).column_attrs:
        col_type = attr.columns[0].type
        convs[attr.key] = _converter_for(col_type)
    return convs


def _converter_for(col_type: Any) -> Callable[[Any], Any]:
    if isinstance(col_type, PG_UUID):
        return lambda v: uuid.UUID(v) if isinstance(v, str) else v
    if isinstance(col_type, SA_DateTime):
        return lambda v: datetime.fromisoformat(v) if isinstance(v, str) else v
    if isinstance(col_type, PG_ARRAY) and isinstance(col_type.item_type, PG_UUID):
        return lambda v: [uuid.UUID(x) if isinstance(x, str) else x for x in v] if v else v
    return lambda v: v


def _row_to_dict(model: type, row: Any) -> dict[str, Any]:
    return {key: getattr(row, key) for key in _column_attr_keys(model)}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

async def export_bundle(
    session: AsyncSession,
    out_path: str,
    *,
    sections: set[str],
    include_files: bool = True,
    include_secrets: bool = False,
    arkon_version: str = "0.1.0",
) -> dict[str, Any]:
    """Build a `.arkon.zip` at out_path. Returns the manifest dict."""
    sections = {s for s in sections if s in SECTIONS}
    counts: dict[str, int] = {}
    checksums: dict[str, str] = {}
    minio_keys: set[str] = set()

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for spec in TABLE_SPECS:
            if spec.section not in sections:
                continue
            rows = (await session.execute(select(spec.model))).scalars().all()

            lines: list[str] = []
            for row in rows:
                data = _row_to_dict(spec.model, row)
                if spec.model is AppConfig and not include_secrets and _is_sensitive(data.get("key", "")):
                    continue  # redact secret config rows
                lines.append(json.dumps(data, default=_json_default, ensure_ascii=False))
                if include_files:
                    _collect_keys_for_row(spec.model, data, minio_keys)

            payload = ("\n".join(lines) + "\n") if lines else ""
            zf.writestr(spec.path, payload)
            counts[spec.path] = len(lines)
            checksums[spec.path] = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        files_written = 0
        if include_files and (sections & {"sources", "skills"}):
            # Expand skill storage prefixes into concrete object keys.
            expanded = _expand_prefixes(minio_keys)
            for key in sorted(expanded):
                section = "skills" if _is_skill_key(key) else "sources"
                if section not in sections:
                    continue
                try:
                    blob = storage_service.download_file(key)
                except Exception as e:  # object missing — skip, don't abort
                    logger.warning(f"backup: could not download {key}: {e}")
                    continue
                zf.writestr(f"{section}/files/{key}", blob)
                files_written += 1

    manifest = {
        "format": BUNDLE_FORMAT,
        "bundle_version": BUNDLE_VERSION,
        "arkon_version": arkon_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sections": sorted(sections),
        "include_files": include_files,
        "include_secrets": include_secrets,
        "counts": counts,
        "files_count": files_written,
        "checksums": checksums,
    }
    # Append manifest last (zip allows out-of-order members).
    with zipfile.ZipFile(out_path, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

    logger.info(f"backup: exported bundle to {out_path} ({sum(counts.values())} rows, {files_written} files)")
    return manifest


def _collect_keys_for_row(model: type, data: dict[str, Any], keys: set[str]) -> None:
    """Gather MinIO object keys / prefixes referenced by a row."""
    if model is Source and data.get("minio_key"):
        keys.add(data["minio_key"])
    elif model is SourceImage and data.get("minio_key"):
        keys.add(data["minio_key"])
    elif model in (Skill, SkillVersion, SkillContribution) and data.get("storage_path"):
        keys.add(data["storage_path"])


def _is_skill_key(key: str) -> bool:
    return key.startswith("skill") or "skill-contributions" in key


def _expand_prefixes(keys: set[str]) -> set[str]:
    """Turn any prefix (skill storage paths) into concrete object names.

    A key that does not look like a single object (ends with '/' or has no file
    extension and lists children) is expanded via MinIO list_objects.
    """
    out: set[str] = set()
    for key in keys:
        listed = False
        if _is_skill_key(key):
            try:
                for obj in storage_service.list_objects(key, recursive=True):
                    if obj.object_name:
                        out.add(obj.object_name)
                        listed = True
            except Exception as e:
                logger.warning(f"backup: could not list prefix {key}: {e}")
        if not listed:
            out.add(key)
    return out


# ---------------------------------------------------------------------------
# Read / parse a bundle
# ---------------------------------------------------------------------------

def read_manifest(zip_path: str) -> dict[str, Any]:
    with zipfile.ZipFile(zip_path, "r") as zf:
        try:
            raw = zf.read("manifest.json")
        except KeyError:
            raise ValueError("Not a valid Arkon bundle: manifest.json missing")
    manifest = json.loads(raw)
    if manifest.get("format") != BUNDLE_FORMAT:
        raise ValueError("Not a valid Arkon bundle (bad format marker)")
    return manifest


def _read_jsonl(zf: zipfile.ZipFile, path: str) -> list[dict[str, Any]]:
    try:
        raw = zf.read(path).decode("utf-8")
    except KeyError:
        return []
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Analyze (dry-run) & Import
# ---------------------------------------------------------------------------

@dataclass
class TableReport:
    add: int = 0
    update: int = 0
    conflict: int = 0
    total: int = 0

    def as_dict(self) -> dict[str, int]:
        return {"add": self.add, "update": self.update, "conflict": self.conflict, "total": self.total}


async def analyze_bundle(
    session: AsyncSession, zip_path: str, sections: set[str]
) -> dict[str, Any]:
    """Dry-run: report add/update/conflict counts per table without writing."""
    return await _process_bundle(session, zip_path, sections, mode="merge", dry_run=True)


async def import_bundle(
    session: AsyncSession, zip_path: str, sections: set[str], mode: str
) -> dict[str, Any]:
    """Apply a bundle. mode = 'merge' (upsert by PK) | 'replace' (wipe section first)."""
    if mode not in ("merge", "replace"):
        raise ValueError("mode must be 'merge' or 'replace'")
    return await _process_bundle(session, zip_path, sections, mode=mode, dry_run=False)


async def _process_bundle(
    session: AsyncSession,
    zip_path: str,
    sections: set[str],
    *,
    mode: str,
    dry_run: bool,
) -> dict[str, Any]:
    manifest = read_manifest(zip_path)
    bundle_sections = set(manifest.get("sections", []))
    sections = {s for s in sections if s in SECTIONS} & bundle_sections

    report: dict[str, Any] = {
        "mode": mode,
        "dry_run": dry_run,
        "bundle": {k: manifest.get(k) for k in ("arkon_version", "created_at", "include_files")},
        "sections": {s: {} for s in sections},
        "files_uploaded": 0,
    }

    with zipfile.ZipFile(zip_path, "r") as zf:
        # Replace: wipe selected sections' tables in reverse FK order first.
        if mode == "replace" and not dry_run:
            for spec in reversed(TABLE_SPECS):
                if spec.section in sections:
                    await session.execute(delete(spec.model))
            await session.flush()

        for spec in TABLE_SPECS:
            if spec.section not in sections:
                continue
            records = _read_jsonl(zf, spec.path)
            tbl_report = await _apply_table(session, spec, records, mode=mode, dry_run=dry_run)
            key = spec.path.split("/")[-1].replace(".jsonl", "")
            report["sections"][spec.section][key] = tbl_report.as_dict()

        # Restore binary objects to MinIO.
        if not dry_run:
            report["files_uploaded"] = _restore_files(zf, sections)

        if not dry_run:
            await session.commit()

    return report


async def _apply_table(
    session: AsyncSession,
    spec: TableSpec,
    records: list[dict[str, Any]],
    *,
    mode: str,
    dry_run: bool,
) -> TableReport:
    model = spec.model
    rep = TableReport(total=len(records))
    if not records:
        return rep

    convs = _load_converters(model)
    pk_attrs = _pk_attr_keys(model)
    valid_attrs = set(convs.keys())

    for rec in records:
        kwargs = {k: convs[k](v) for k, v in rec.items() if k in valid_attrs}
        pk_vals = tuple(kwargs.get(a) for a in pk_attrs)
        pk_lookup = pk_vals[0] if len(pk_vals) == 1 else pk_vals

        existing = await session.get(model, pk_lookup)

        if existing is not None:
            rep.update += 1
            if not dry_run:
                for k, v in kwargs.items():
                    if k not in pk_attrs:
                        setattr(existing, k, v)
            continue

        # No PK match — check for a natural-key collision under a different PK.
        if spec.natural_key and await _natural_conflict(session, spec, kwargs, pk_attrs):
            rep.conflict += 1
            continue

        rep.add += 1
        if not dry_run:
            session.add(model(**kwargs))

    if not dry_run:
        await session.flush()
    return rep


async def _natural_conflict(
    session: AsyncSession,
    spec: TableSpec,
    kwargs: dict[str, Any],
    pk_attrs: list[str],
) -> bool:
    model = spec.model
    stmt = select(model)
    for attr in spec.natural_key:
        stmt = stmt.where(getattr(model, attr) == kwargs.get(attr))
    found = (await session.execute(stmt)).scalars().first()
    if found is None:
        return False
    # Same row by PK is not a conflict (handled above), but be defensive.
    return tuple(getattr(found, a) for a in pk_attrs) != tuple(kwargs.get(a) for a in pk_attrs)


def _restore_files(zf: zipfile.ZipFile, sections: set[str]) -> int:
    """Upload binaries from the bundle back to MinIO under their original keys."""
    uploaded = 0
    for name in zf.namelist():
        section: Optional[str] = None
        for s in ("sources", "skills"):
            if name.startswith(f"{s}/files/"):
                section = s
                key = name[len(f"{s}/files/"):]
                break
        else:
            continue
        if section not in sections or not key:
            continue
        try:
            blob = zf.read(name)
            storage_service.upload_file(key, blob)
            uploaded += 1
        except Exception as e:
            logger.warning(f"restore: could not upload {key}: {e}")
    return uploaded

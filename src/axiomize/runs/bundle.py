"""Portable run bundles (PHASE 9).

A run directory zips into a single file that another machine or agent
can import and inspect - no chat context required.

Security boundary
-----------------
A bundle is untrusted input. Two properties are enforced here rather than
being left to the caller:

1. Only ``.zip`` bundles are accepted. ``shutil.unpack_archive`` dispatches on
   the file suffix, and its tar/tar.gz code path calls ``tarfile.extractall``
   without a member filter, which writes members outside the destination on the
   Python versions this project supports (3.10-3.13). Restricting the accepted
   format to zip removes that path entirely.
2. Every member is resolved and confirmed to stay inside the destination
   before anything is written. ``zipfile`` strips ``..`` from *its* own
   extraction, but the members are inspected here first so a traversal bundle
   is rejected outright instead of being partially written with a rewritten
   name that no longer matches what the archive declared.

Callers that expose bundle import to a network transport should also pass
``run_root`` so the destination is confined beneath a configured root.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

__all__ = ["export_run", "import_run", "inspect_bundle_members"]

# Guard against decompression bombs and absurd member counts in a bundle that a
# remote peer can supply. A run bundle is a handful of small JSON files.
_MAX_BUNDLE_MEMBERS = 512
_MAX_MEMBER_BYTES = 64 * 1024 * 1024
_MAX_TOTAL_BYTES = 128 * 1024 * 1024


def _require_zip_suffix(bundle_path: str | Path) -> Path:
    bundle = Path(bundle_path)
    if bundle.suffix.lower() != ".zip":
        raise ValueError(
            f"bundle path must end in .zip (got {bundle.suffix!r}); "
            "tar-based archives are rejected because their extraction is not "
            "path-confined on supported Python versions"
        )
    return bundle


def _confine_dest(dest_dir: str | Path, run_root: str | Path | None) -> Path:
    dest = Path(dest_dir)
    if run_root is None:
        return dest
    from axiomize.runs.state import resolve_run_directory

    # Reuse the same confinement primitive the REST and MCP transports use, so
    # bundle import and run inspection cannot drift apart.
    return resolve_run_directory(run_root, dest.name if dest.parent == Path(".") else str(dest))


def inspect_bundle_members(bundle: str | Path) -> list[tuple[str, int]]:
    """Return ``(member_name, size)`` for a zip bundle after validating it.

    Raises ``ValueError`` when the bundle is not a zip, is not a regular file,
    exceeds the member/byte ceilings, or contains a member whose resolved path
    would escape the extraction destination.
    """
    path = _require_zip_suffix(bundle)
    if not path.is_file():
        raise ValueError("bundle must be an existing regular file")

    members: list[tuple[str, int]] = []
    total = 0
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > _MAX_BUNDLE_MEMBERS:
            raise ValueError(f"bundle exceeds hard member limit of {_MAX_BUNDLE_MEMBERS}")
        base = Path(path.name).resolve().parent
        anchor = (base / "__axiomize_bundle_dest__").resolve()
        for info in infos:
            name = info.filename
            if name.endswith("/"):
                # Directory entry; nothing is written for it.
                continue
            if info.file_size > _MAX_MEMBER_BYTES:
                raise ValueError(
                    f"bundle member {name!r} exceeds hard size limit of {_MAX_MEMBER_BYTES} bytes"
                )
            total += info.file_size
            if total > _MAX_TOTAL_BYTES:
                raise ValueError(
                    f"bundle exceeds hard uncompressed limit of {_MAX_TOTAL_BYTES} bytes"
                )
            # Reject absolute members and any member that escapes the
            # destination once resolved.
            candidate = Path(name)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError(f"bundle member {name!r} escapes the extraction directory")
            resolved = (anchor / candidate).resolve()
            try:
                resolved.relative_to(anchor)
            except ValueError as exc:
                raise ValueError(
                    f"bundle member {name!r} escapes the extraction directory"
                ) from exc
            members.append((name, info.file_size))
    return members


def export_run(run_dir: str | Path, bundle_path: str | Path) -> Path:
    bundle = _require_zip_suffix(bundle_path)
    base = str(bundle.with_suffix(""))
    shutil.make_archive(base, "zip", root_dir=str(Path(run_dir).resolve()))
    return bundle


def import_run(
    bundle_path: str | Path,
    dest_dir: str | Path,
    *,
    run_root: str | Path | None = None,
) -> Path:
    """Extract a validated zip bundle into ``dest_dir``.

    The bundle is fully inspected before a single byte is written, so a
    rejected bundle leaves no partial output behind.
    """
    bundle = _require_zip_suffix(bundle_path)
    dest = _confine_dest(dest_dir, run_root)
    inspect_bundle_members(bundle)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.unpack_archive(str(bundle), str(dest))
    return dest

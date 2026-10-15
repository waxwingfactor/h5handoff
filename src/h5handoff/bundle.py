"""Transactional directory bundles and independent recipient verification.

The receipt is an unsigned inventory, not an authenticity proof. Native HDF5
metadata is read only by scan(); payloads are streamed as opaque bytes here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from . import __version__
from .scan import scan

MAX_MANIFEST_BYTES = 16 * 1024 * 1024
_CHUNK = 1024 * 1024


def _redirect(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


class PackError(ValueError):
    """A safe, complete bundle could not be produced."""


def _relative(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError("Expected a nonempty relative path of at most 4096 characters")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or PureWindowsPath(value).drive
        or "\\" in value
        or any(c in value for c in "\x00\r\n")
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise ValueError(f"Unsafe relative path: {value!r}")
    return value


def _regular(base: Path, relative: str) -> Path:
    path = base / _relative(relative)
    if _redirect(base) or not base.is_dir():
        raise ValueError(f"Expected a real directory: {base.name!r}")
    cursor = base
    for part in PurePosixPath(relative).parts:
        cursor = cursor / part
        if _redirect(cursor):
            raise ValueError(f"Symlink is unsupported: {relative!r}")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"Expected a regular file: {relative!r}")
    return path


def _stamp(info: os.stat_result) -> tuple:
    # Windows path stat and fd fstat can give ctime different meanings. Compare
    # ctime only between two calls of the same kind; keep identity/size/mtime
    # checks across path and handle. CPython issue: python/cpython#157671.
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _full_stamp(info: os.stat_result) -> tuple:
    return (*_stamp(info), info.st_ctime_ns)


def _hash(path: Path) -> tuple[str, int]:
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"Expected a regular file: {path.name!r}")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        opened = os.fstat(source.fileno())
        if _stamp(opened) != _stamp(before):
            raise ValueError(f"File changed before hashing: {path.name!r}")
        while block := source.read(_CHUNK):
            digest.update(block)
            size += len(block)
        after = os.fstat(source.fileno())
    final_path = path.stat()
    if (
        _full_stamp(opened) != _full_stamp(after)
        or _full_stamp(before) != _full_stamp(final_path)
        or _stamp(after) != _stamp(final_path)
    ):
        raise ValueError(f"File changed during hashing: {path.name!r}")
    return digest.hexdigest(), size


def _copy(source: Path, target: Path) -> dict:
    before = source.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise PackError(f"Expected a regular source file: {source.name!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as original, target.open("xb") as copied:
        opened = os.fstat(original.fileno())
        if _stamp(opened) != _stamp(before):
            raise PackError(f"Source changed before copying: {source.name!r}")
        while block := original.read(_CHUNK):
            copied.write(block)
            digest.update(block)
            size += len(block)
        copied.flush()
        os.fsync(copied.fileno())
        after = os.fstat(original.fileno())
    final_path = source.stat()
    if (
        _full_stamp(opened) != _full_stamp(after)
        or _full_stamp(before) != _full_stamp(final_path)
        or _stamp(after) != _stamp(final_path)
    ):
        raise PackError(f"Source changed during copying: {source.name!r}")
    expected = digest.hexdigest(), size
    if _hash(source) != expected or _hash(target) != expected:
        raise PackError(f"Copy verification failed: {source.name!r}")
    return {"size": size, "sha256": digest.hexdigest()}


def _json_text(value: dict) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True) + "\n"


def _closure(report: dict) -> dict:
    return {
        key: report[key]
        for key in (
            "entry",
            "resolution_profile",
            "raw_base",
            "files",
            "directories",
            "dependencies",
        )
    } | {
        "filters": [
            {key: item[key] for key in ("file", "object", "id")} for item in report["filters"]
        ]
    }


def pack(entry, root, destination, *, max_files=1000, max_objects=100000) -> dict:
    """Copy the supported closure to a new directory; refuse partial results.

    Input and destination parent must be quiescent. This is not an operating
    system snapshot or a defense against hostile concurrent filesystem edits.
    """
    root = Path(root).absolute()
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise PackError("Output already exists; choose a new directory")
    if destination.resolve().is_relative_to(root.resolve()):
        raise PackError("Output must be outside the input root")
    if not destination.parent.is_dir():
        raise PackError("Output parent directory does not exist")
    report = scan(entry, root, max_files=max_files, max_objects=max_objects)
    if not report["ok"]:
        codes = sorted({item["code"] for item in report["issues"] if item["severity"] == "error"})
        raise PackError("Dependency audit failed: " + ", ".join(codes))
    if any(_redirect(part) for part in (destination.parent, *destination.parent.parents)):
        raise PackError("Output parent must not contain symlinks")
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.h5handoff-", dir=destination.parent)
    )
    try:
        payload = staging / "payload"
        payload.mkdir()
        for relative in report["directories"]:
            (payload / _relative(relative)).mkdir(parents=True, exist_ok=True)
        files = []
        # Avoid collisions on case-insensitive destination filesystems.
        folded = set()
        for item in report["files"]:
            relative = _relative(item["path"])
            if relative.casefold() in folded:
                raise PackError("File names collide on a case-insensitive filesystem")
            folded.add(relative.casefold())
            source = _regular(root, relative)
            files.append({"path": relative, **_copy(source, payload / relative)})
        copied_audit = scan(report["entry"], payload, max_files=max_files, max_objects=max_objects)
        if not copied_audit["ok"] or _closure(copied_audit) != _closure(report):
            raise PackError("Copied dependency closure differs from source audit")
        manifest = {
            "schema_version": 1,
            "tool_version": __version__,
            "entry": report["entry"],
            "resolution_profile": "literal-v1",
            "files": files,
            "audit": copied_audit,
        }
        encoded = _json_text(manifest)
        if len(encoded.encode("utf-8")) > MAX_MANIFEST_BYTES:
            raise PackError("Receipt exceeds 16 MiB; reduce the handoff scope")
        (staging / "handoff.json").write_text(encoded, encoding="utf-8")
        (staging / "README.txt").write_text(
            "h5handoff recipient instructions\n\n"
            "1. Run: h5handoff verify PATH_TO_THIS_BUNDLE\n"
            "2. Change working directory to this bundle's payload directory.\n"
            "3. Open the root-relative entry recorded in handoff.json with your HDF5 application.\n\n"
            "External raw-file paths use payload as the working directory. Unset custom\n"
            "HDF5_EXT_PREFIX, HDF5_VDS_PREFIX and HDF5_EXTFILE_PREFIX overrides.\n"
            "Data has NOT been decoded or scientifically validated. Filter IDs are in\n"
            "handoff.json; your application may need compression plugins. Files remain\n"
            "byte-identical. The receipt is unsigned and does not prove authenticity.\n",
            encoding="utf-8",
        )
        verified = verify(staging, max_files=max_files, max_objects=max_objects)
        if not verified["ok"]:
            raise PackError("Staged bundle verification failed: " + repr(verified["issues"]))
        if destination.exists() or destination.is_symlink():
            raise PackError("Output appeared during packing; refusing to replace it")
        staging.rename(destination)
        return {
            "ok": True,
            "entry": report["entry"],
            "files": files,
            "issues": report["issues"],
            "filters": report["filters"],
            "data_read": False,
        }
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _load_manifest(bundle: Path, max_files: int) -> dict:
    path = _regular(bundle, "handoff.json")
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("Receipt exceeds 16 MiB")
    with path.open("rb") as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("Receipt exceeds 16 MiB")

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate receipt key: {key!r}")
            result[key] = value
        return result

    manifest = json.loads(raw, object_pairs_hook=unique_keys)
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int:
        raise ValueError("Invalid receipt object/schema version")
    if manifest["schema_version"] != 1 or manifest.get("resolution_profile") != "literal-v1":
        raise ValueError("Unsupported receipt version or resolution profile")
    _relative(manifest.get("entry"))
    records = manifest.get("files")
    if not isinstance(records, list) or not 1 <= len(records) <= max_files:
        raise ValueError("Invalid file inventory or file limit exceeded")
    paths = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {"path", "size", "sha256"}:
            raise ValueError("Invalid file record")
        relative = _relative(record["path"])
        if relative.casefold() in paths:
            raise ValueError("Duplicate or case-colliding file record")
        paths.add(relative.casefold())
        if type(record["size"]) is not int or record["size"] < 0:
            raise ValueError("Invalid file size")
        if not isinstance(record["sha256"], str) or not re.fullmatch(
            r"[a-f0-9]{64}", record["sha256"]
        ):
            raise ValueError("Invalid SHA-256 digest")
    if manifest["entry"] not in {item["path"] for item in records}:
        raise ValueError("Entry is absent from inventory")
    audit = manifest.get("audit")
    if not isinstance(audit, dict):
        raise ValueError("Missing audit receipt")
    if (
        type(audit.get("schema_version")) is not int
        or audit["schema_version"] != 1
        or audit.get("ok") is not True
        or audit.get("data_read") is not False
        or audit.get("resolution_profile") != "literal-v1"
        or audit.get("raw_base") != "."
        or audit.get("entry") != manifest["entry"]
    ):
        raise ValueError("Invalid audit receipt header")
    for key in ("files", "dependencies", "filters", "issues"):
        if not isinstance(audit.get(key), list) or not all(
            isinstance(item, dict) for item in audit[key]
        ):
            raise ValueError(f"Invalid audit {key} records")
    if not isinstance(audit.get("directories"), list):
        raise ValueError("Invalid audit directory records")
    for relative in audit["directories"]:
        _relative(relative)
    for item in audit["filters"]:
        if (
            type(item.get("id")) is not int
            or not isinstance(item.get("file"), str)
            or not isinstance(item.get("object"), str)
            or not isinstance(item.get("name"), str)
        ):
            raise ValueError("Invalid filter record")
    return manifest


def verify(bundle, *, max_files=1000, max_objects=100000) -> dict:
    """Verify bytes and re-audit the supported dependency closure, without decoding."""
    issues = []
    result = {"schema_version": 1, "ok": False, "data_read": False, "issues": issues}
    if max_files < 1 or max_objects < 1:
        raise ValueError("Limits must be positive")
    bundle = Path(bundle).absolute()
    try:
        manifest = _load_manifest(bundle, max_files)
        payload = bundle / "payload"
        if _redirect(payload) or not payload.is_dir():
            raise ValueError("Missing payload directory or symlink payload")
        actual = set()
        directories = set()
        pending = [payload]
        # Iterate incrementally, reject redirects and propagate access failures.
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as children:
                for child in children:
                    path = Path(child.path)
                    if _redirect(path):
                        raise ValueError("Payload contains a symlink or reparse point")
                    relative = path.relative_to(payload).as_posix()
                    _relative(relative)
                    if child.is_dir(follow_symlinks=False):
                        directories.add(relative)
                        if len(directories) > max_objects:
                            raise ValueError("Payload directory limit exceeded")
                        pending.append(path)
                    else:
                        _regular(payload, relative)
                        actual.add(relative)
                        if len(actual) > max_files:
                            raise ValueError("Payload file limit exceeded")
        expected = {item["path"] for item in manifest["files"]}
        if actual != expected:
            raise ValueError("Payload inventory differs from receipt (missing or extra files)")
        for record in manifest["files"]:
            path = _regular(payload, record["path"])
            if path.stat().st_size != record["size"]:
                issues.append(
                    {
                        "code": "size_mismatch",
                        "file": record["path"],
                        "severity": "error",
                        "message": "File size differs from receipt",
                    }
                )
            elif _hash(path) != (record["sha256"], record["size"]):
                issues.append(
                    {
                        "code": "hash_mismatch",
                        "file": record["path"],
                        "severity": "error",
                        "message": "SHA-256 differs from receipt",
                    }
                )
        if issues:
            return result
        report = scan(manifest["entry"], payload, max_files=max_files, max_objects=max_objects)
        result["audit"] = report
        result["entry"] = manifest["entry"]
        result["files_verified"] = len(expected)
        issues.extend(report["issues"])
        if {item["path"] for item in report["files"]} != expected:
            raise ValueError("Receipt does not describe exactly the entry's dependency closure")
        if directories != set(report["directories"]):
            raise ValueError("Payload directory inventory differs from dependency closure")
        if _closure(report) != _closure(manifest["audit"]):
            raise ValueError("Fresh dependency closure differs from receipt audit")
        result["ok"] = not any(item["severity"] == "error" for item in issues)
        return result
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
        issues.append({"code": "invalid_bundle", "severity": "error", "message": str(error)})
        return result

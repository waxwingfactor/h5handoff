"""Conservative metadata-only closure for the literal-v1 handoff profile.

The profile is deliberately stricter than HDF5's runtime search rules. Files
are never rewritten, external/soft links are resolved by this module, and no
HDF5 dataset payload is read. Native HDF5 remains trusted-file software.
"""

from __future__ import annotations

import os
import posixpath
import re
import stat
from collections import deque
from pathlib import Path, PureWindowsPath
from typing import Any

import h5py

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_MAX_LINK_HOPS = 256
_MAX_COMPONENTS = 4096


def _parts(path: str) -> list[str]:
    # HDF5 supports '.' but '..' is an ordinary object name, not a parent.
    return [part for part in path.split("/") if part and part != "."]


def _is_link(metadata: os.stat_result) -> bool:
    # Junctions and other Windows reparse points can redirect filesystem access
    # without being reported as ordinary symbolic links.
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _link_names(group: h5py.Group):
    """Yield one name per native iteration call without caching all names."""
    index = 0
    while index < len(group):
        name, index = group.id.links.iterate(
            lambda name: name, idx=index, idx_type=h5py.h5.INDEX_NAME, order=h5py.h5.ITER_INC
        )
        if name is None:
            return
        yield name.decode("utf-8", "surrogateescape")


class _Scanner:
    def __init__(self, entry: Path | str, root: Path | str, max_files: int, max_objects: int):
        for name, value in (("max_files", max_files), ("max_objects", max_objects)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        alias = Path(os.path.abspath(root))
        if _is_link(alias.lstat()):
            raise ValueError("Root must not be a symlink")
        self.root = alias.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("Root must be a directory")
        entry_path = Path(entry)
        if entry_path.is_absolute():
            absolute = entry_path
            try:
                entry_path = absolute.relative_to(alias)
            except ValueError:
                try:
                    entry_path = absolute.relative_to(self.root)
                except ValueError:
                    raise ValueError("Entry must be inside root") from None
        self.entry_literal = entry_path.as_posix()
        entry_name = posixpath.normpath(self.entry_literal)
        if entry_name in (".", "..") or entry_name.startswith("../"):
            raise ValueError("Entry must name a file inside root")
        self.entry = entry_name
        self.max_files = max_files
        self.max_objects = max_objects
        self.files: dict[str, dict[str, Any]] = {}
        self.candidates: set[str] = set()
        self.hdf5_requested: set[str] = set()
        self.pending_files: deque[str] = deque()
        self.pending_checks: deque[tuple[str, str, str, str, bool]] = deque()
        self.dependencies: list[dict[str, Any]] = []
        self.filters: list[dict[str, Any]] = []
        self.issues: list[dict[str, Any]] = []
        self.issue_keys: set[tuple[str, str, str, str]] = set()
        self.objects: set[tuple[str, int]] = set()
        self.directories: set[str] = set()
        self.edges = 0
        self.object_limit_hit = False
        self.edge_limit_hit = False
        self.directory_limit_hit = False
        self.unreadable: set[str] = set()

    def issue(self, code: str, file: str, obj: str, message: str, severity: str = "error") -> None:
        key = (code, file, obj, message)
        if key not in self.issue_keys:
            self.issue_keys.add(key)
            self.issues.append(
                {
                    "code": code,
                    "file": file,
                    "object": obj,
                    "message": message,
                    "severity": severity,
                }
            )

    def literal(self, stored: str, base: str, source: str, obj: str) -> str | None:
        """Validate a stored *filename* before touching its filesystem path."""
        try:
            stored.encode("utf-8")
        except (AttributeError, UnicodeError):
            self.issue("unsafe_path", source, obj, "Dependency filename is not valid UTF-8")
            return None
        if (
            not stored
            or "\x00" in stored
            or stored.startswith("/")
            or PureWindowsPath(stored).drive
            or "\\" in stored
            or _SCHEME.match(stored)
            or "$" in stored
            or "~" in stored
        ):
            self.issue(
                "unsafe_path",
                source,
                obj,
                "Dependency filename is not a supported literal relative path",
            )
            return None
        relative = posixpath.normpath(posixpath.join(base, stored))
        if relative == ".." or relative.startswith("../"):
            self.issue("outside_root", source, obj, "Dependency path leaves the selected root")
            return None
        # Check the literal ancestry before discarding dot components. For
        # example, alias/../data.h5 is unsafe when alias is a symlink, and
        # missing/../data.h5 is not a usable native path either.
        current = self.root / base
        tokens = stored.split("/")
        if len(tokens) > _MAX_COMPONENTS:
            self.issue("traversal_limit", source, obj, "Filename component ceiling reached")
            return None
        for index, component in enumerate(tokens):
            if not component or component == ".":
                continue
            if component == "..":
                if current == self.root:
                    self.issue(
                        "outside_root",
                        source,
                        obj,
                        "Dependency path temporarily leaves the selected root",
                    )
                    return None
                current = current.parent
                continue
            current = current / component
            try:
                metadata = current.lstat()
                if _is_link(metadata):
                    self.issue(
                        "symlink",
                        source,
                        obj,
                        f"Dependency literal path contains a symlink: {stored}",
                    )
                    return None
                if stat.S_ISDIR(metadata.st_mode) and not self.add_directory(
                    current.relative_to(self.root).as_posix(), source, obj
                ):
                    return None
                if index < len(tokens) - 1 and not stat.S_ISDIR(metadata.st_mode):
                    self.issue(
                        "not_regular_file",
                        source,
                        obj,
                        f"Dependency ancestry contains a non-directory: {stored}",
                    )
                    return None
            except FileNotFoundError:
                self.issue("missing_file", source, obj, f"Missing dependency file: {relative}")
                return None
            except (OSError, ValueError):
                self.issue("file_access", source, obj, f"Cannot inspect file path: {relative}")
                return None
        return relative

    def regular(self, relative: str, source: str, obj: str) -> os.stat_result | None:
        """lstat every component under root; never follow a dependency symlink."""
        current = self.root
        try:
            root_metadata = self.root.lstat()
            if _is_link(root_metadata) or not stat.S_ISDIR(root_metadata.st_mode):
                self.issue("symlink", source, obj, "Root changed or became a symlink")
                return None
            for component in relative.split("/"):
                current = current / component
                metadata = current.lstat()
                if _is_link(metadata):
                    self.issue("symlink", source, obj, f"Path contains a symlink: {relative}")
                    return None
                if stat.S_ISDIR(metadata.st_mode) and not self.add_directory(
                    current.relative_to(self.root).as_posix(), source, obj
                ):
                    return None
            if not stat.S_ISREG(metadata.st_mode):
                self.issue("not_regular_file", source, obj, f"Not a regular file: {relative}")
                return None
            return metadata
        except FileNotFoundError:
            self.issue("missing_file", source, obj, f"Missing dependency file: {relative}")
        except (OSError, ValueError):
            self.issue("file_access", source, obj, f"Cannot inspect file path: {relative}")
        return None

    def add_directory(self, relative: str, source: str, obj: str) -> bool:
        if relative == "." or relative in self.directories:
            return True
        if len(self.directories) >= self.max_objects:
            self.issue(
                "directory_limit",
                source,
                obj,
                f"Directory ceiling ({self.max_objects}) reached; closure is incomplete",
            )
            self.directory_limit_hit = True
            return False
        self.directories.add(relative)
        return True

    def edge_allowed(self, relative: str, path: str) -> bool:
        if self.edges >= self.max_objects:
            self.issue(
                "edge_limit",
                relative,
                path,
                f"Link/dependency edge ceiling ({self.max_objects}) reached; closure is incomplete",
            )
            self.edge_limit_hit = True
            return False
        self.edges += 1
        return True

    def limit_hit(self) -> bool:
        return self.object_limit_hit or self.edge_limit_hit or self.directory_limit_hit

    def add_file(self, relative: str, kind: str, source: str, obj: str) -> bool:
        if relative not in self.candidates:
            if len(self.candidates) >= self.max_files:
                self.issue(
                    "file_limit",
                    source,
                    obj,
                    f"File ceiling ({self.max_files}) reached; closure is incomplete",
                )
                return False
            self.candidates.add(relative)
        metadata = self.regular(relative, source, obj)
        if metadata is None:
            return False
        existing = self.files.get(relative)
        if existing is None:
            self.files[relative] = {"path": relative, "kind": kind, "size": metadata.st_size}
        elif kind == "hdf5":
            existing["kind"] = "hdf5"
        if kind == "hdf5" and relative not in self.hdf5_requested:
            self.hdf5_requested.add(relative)
            self.pending_files.append(relative)
        return True

    def record(
        self,
        source: str,
        obj: str,
        kind: str,
        stored: str,
        target_obj: str = "",
        base: str | None = None,
    ) -> str | None:
        if kind == "soft_link":
            target = source
        elif kind == "vds" and stored == ".":
            target = source
        elif kind == "vds" and "%" in stored:
            target = None
            self.issue(
                "unsupported_vds_pattern",
                source,
                obj,
                "VDS percent-formatted source names are outside literal-v1",
            )
        else:
            target = self.literal(
                stored, base if base is not None else posixpath.dirname(source), source, obj
            )
        self.dependencies.append(
            {
                "source": source,
                "object": obj,
                "kind": kind,
                "stored_file": stored,
                "target_object": target_obj,
                "target": target,
            }
        )
        return target

    def object_allowed(self, relative: str, obj: Any, path: str) -> bool:
        identity = (relative, h5py.h5o.get_info(obj.id).addr)
        if identity in self.objects:
            return False
        if len(self.objects) >= self.max_objects:
            self.issue(
                "object_limit",
                relative,
                path,
                f"Object ceiling ({self.max_objects}) reached; closure is incomplete",
            )
            self.object_limit_hit = True
            return False
        self.objects.add(identity)
        return True

    def inspect_dataset(self, relative: str, path: str, dataset: h5py.Dataset) -> None:
        creation = dataset.id.get_create_plist()
        try:
            for index in range(creation.get_nfilters()):
                number, _flags, _values, name = creation.get_filter(index)
                if isinstance(name, bytes):
                    name = name.decode("utf-8", "replace")
                self.filters.append({"file": relative, "object": path, "id": number, "name": name})
            if dataset.is_virtual:
                # virtual_sources() builds every mapping; read one metadata
                # entry at a time so the explicit edge ceiling applies first.
                for index in range(creation.get_virtual_count()):
                    if not self.edge_allowed(relative, path):
                        return
                    filename = creation.get_virtual_filename(index)
                    name = creation.get_virtual_dsetname(index)
                    if isinstance(filename, bytes):
                        filename = filename.decode("utf-8")
                    if isinstance(name, bytes):
                        name = name.decode("utf-8")
                    if "%" in name:
                        self.record(relative, path, "vds", filename, name)
                        self.issue(
                            "unsupported_vds_pattern",
                            relative,
                            path,
                            "VDS percent-formatted dataset names are outside literal-v1",
                        )
                        continue
                    target = self.record(relative, path, "vds", filename, name)
                    if target is not None and self.add_file(target, "hdf5", relative, path):
                        self.pending_checks.append((relative, path, target, name, True))
            preceding_size = 0
            for index in range(creation.get_external_count()):
                if not self.edge_allowed(relative, path):
                    return
                filename, offset, size = creation.get_external(index)
                if isinstance(filename, bytes):
                    try:
                        filename = filename.decode("utf-8")
                    except UnicodeError:
                        self.issue(
                            "unsafe_path",
                            relative,
                            path,
                            "External raw filename is not valid UTF-8",
                        )
                        continue
                target = self.record(relative, path, "external_raw", filename, base="")
                unlimited = size == h5py.h5f.UNLIMITED
                self.dependencies[-1].update(
                    {"offset": offset, "size": "unlimited" if unlimited else size}
                )
                if target is not None and self.add_file(target, "raw", relative, path):
                    available = self.files[target]["size"]
                    # The unlimited final segment needs only the remaining
                    # current logical byte length, not an infinite reservation.
                    required = max(0, dataset.nbytes - preceding_size) if unlimited else size
                    if offset + required > available:
                        self.issue(
                            "short_raw",
                            relative,
                            path,
                            f"Raw segment extends past current EOF: {target}; HDF5 may zero-fill",
                            "warning",
                        )
                if not unlimited:
                    preceding_size += size
        finally:
            creation.close()

    def inspect_file(self, relative: str) -> None:
        if self.limit_hit() or self.regular(relative, relative, "/") is None:
            return
        try:
            with h5py.File(self.root / relative, "r", driver="sec2") as handle:
                # A frame retains one lazy group iterator, never all child
                # objects or all names. The Python stack handles deep groups.
                stack: list[tuple[str, Any, Any]] = [("/", handle, None)]
                while stack and not self.limit_hit():
                    path, obj, names = stack.pop()
                    if names is None:
                        if not self.object_allowed(relative, obj, path):
                            continue
                        if isinstance(obj, h5py.Dataset):
                            self.inspect_dataset(relative, path, obj)
                            continue
                        if not isinstance(obj, h5py.Group):
                            continue
                        names = iter(_link_names(obj))
                    try:
                        name = next(names)
                    except StopIteration:
                        continue
                    stack.append((path, obj, names))
                    child_path = path.rstrip("/") + "/" + name
                    if not self.edge_allowed(relative, child_path):
                        return
                    try:
                        link = obj.get(name, getlink=True)
                        if isinstance(link, h5py.HardLink):
                            # Single component and known HardLink: no external
                            # or soft link can be followed by this lookup.
                            stack.append((child_path, obj[name], None))
                        elif isinstance(link, h5py.SoftLink):
                            self.record(relative, child_path, "soft_link", "", link.path)
                            self.pending_checks.append(
                                (
                                    relative,
                                    child_path,
                                    relative,
                                    self.soft_path(path, link.path),
                                    False,
                                )
                            )
                        elif isinstance(link, h5py.ExternalLink):
                            target = self.record(
                                relative, child_path, "external_link", link.filename, link.path
                            )
                            if target is not None and self.add_file(
                                target, "hdf5", relative, child_path
                            ):
                                self.pending_checks.append(
                                    (relative, child_path, target, link.path, False)
                                )
                        else:
                            self.issue(
                                "unsupported_link",
                                relative,
                                child_path,
                                "Unrecognized HDF5 link type",
                            )
                    except (OSError, ValueError, TypeError, RuntimeError, KeyError):
                        self.issue(
                            "read_error", relative, child_path, "Cannot inspect link metadata"
                        )
        except (OSError, ValueError, TypeError, RuntimeError, KeyError):
            self.unreadable.add(relative)
            self.issue("unreadable_hdf5", relative, "/", "Cannot inspect HDF5 file metadata")

    @staticmethod
    def soft_path(parent: str, target: str) -> str:
        return target if target.startswith("/") else parent.rstrip("/") + "/" + target

    def resolve(
        self, source: str, origin_obj: str, relative: str, target_path: str, require_dataset: bool
    ) -> None:
        """Resolve components manually, restarting after each symbolic link."""
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for _hop in range(_MAX_LINK_HOPS):
            components = _parts(target_path)
            if len(components) > _MAX_COMPONENTS:
                self.issue(
                    "traversal_limit",
                    source,
                    origin_obj,
                    "Object path component ceiling reached; resolution is incomplete",
                )
                return
            state = (relative, tuple(components))
            if state in seen:
                self.issue(
                    "link_cycle", source, origin_obj, "Symbolic link target contains a cycle"
                )
                return
            seen.add(state)
            if relative in self.unreadable:
                return
            if not self.add_file(relative, "hdf5", source, origin_obj):
                return
            try:
                with h5py.File(self.root / relative, "r", driver="sec2") as handle:
                    current: Any = handle
                    traversed: list[str] = []
                    restart = False
                    for index, component in enumerate(components):
                        if not isinstance(current, h5py.Group):
                            self.issue(
                                "missing_object",
                                source,
                                origin_obj,
                                "Target object path crosses a non-group object",
                            )
                            return
                        link = current.get(component, getlink=True)
                        if link is None:
                            self.issue(
                                "missing_object",
                                source,
                                origin_obj,
                                f"Missing target object in {relative}: {target_path}",
                            )
                            return
                        if isinstance(link, h5py.HardLink):
                            current = current[component]
                            traversed.append(component)
                            continue
                        remainder = components[index + 1 :]
                        if isinstance(link, h5py.SoftLink):
                            parent = "/" + "/".join(traversed)
                            target_path = self.soft_path(parent, link.path)
                        elif isinstance(link, h5py.ExternalLink):
                            new_relative = self.literal(
                                link.filename, posixpath.dirname(relative), source, origin_obj
                            )
                            if new_relative is None:
                                return
                            relative = new_relative
                            target_path = link.path
                        else:
                            self.issue(
                                "unsupported_link",
                                source,
                                origin_obj,
                                "Target path contains an unsupported link type",
                            )
                            return
                        if remainder:
                            target_path = target_path.rstrip("/") + "/" + "/".join(remainder)
                        restart = True
                        break
                    if restart:
                        continue
                    if require_dataset and not isinstance(current, h5py.Dataset):
                        self.issue(
                            "not_dataset",
                            source,
                            origin_obj,
                            f"VDS source object in {relative} is not a dataset",
                        )
                    return
            except (OSError, ValueError, TypeError, RuntimeError, KeyError):
                self.issue(
                    "read_error",
                    source,
                    origin_obj,
                    f"Cannot resolve target metadata in {relative}",
                )
                return
        self.issue(
            "traversal_limit",
            source,
            origin_obj,
            f"Symbolic link hop ceiling ({_MAX_LINK_HOPS}) reached; resolution is incomplete",
        )

    def run(self) -> dict[str, Any]:
        initial = self.literal(self.entry_literal, "", self.entry, "/")
        if initial is not None:
            self.add_file(initial, "hdf5", self.entry, "/")
        while (self.pending_files or self.pending_checks) and not self.limit_hit():
            if self.pending_files:
                self.inspect_file(self.pending_files.popleft())
            else:
                self.resolve(*self.pending_checks.popleft())
        self.dependencies.sort(
            key=lambda x: (
                x["source"],
                x["object"],
                x["kind"],
                x["stored_file"],
                x["target_object"],
                x["target"] or "",
            )
        )
        self.filters.sort(key=lambda x: (x["file"], x["object"], x["id"], x["name"]))
        self.issues.sort(key=lambda x: (x["file"], x["object"], x["code"], x["message"]))
        return {
            "schema_version": 1,
            "entry": self.entry,
            "files": sorted(self.files.values(), key=lambda x: x["path"]),
            "directories": sorted(self.directories),
            "dependencies": self.dependencies,
            "filters": self.filters,
            "issues": self.issues,
            "ok": not any(issue["severity"] == "error" for issue in self.issues),
            "data_read": False,
            "raw_base": ".",
            "resolution_profile": "literal-v1",
        }


def scan(
    entry: Path | str, root: Path | str, *, max_files: int = 1000, max_objects: int = 100000
) -> dict[str, Any]:
    """Audit supported file dependencies without reading dataset payloads.

    Relative entry names are relative to root. Files are inventoried whole,
    including unused objects. External raw filenames are relative to root,
    which must also be the receiving reader's working directory.
    """
    return _Scanner(entry, root, max_files, max_objects).run()

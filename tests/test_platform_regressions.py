"""Cross-platform race checks use compatible timestamp meanings.

CPython Windows can expose birth time through path stat().st_ctime_ns and
change time through fstat().st_ctime_ns for the same stable file:
https://github.com/python/cpython/issues/157671

These deterministic simulations run on every CI platform. They exercise real
byte hashing/copying while changing only the observed timestamp metadata.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from h5handoff.bundle import PackError, _copy, _hash


class StatView:
    """Preserve real file identity and fields, overriding selected observations."""

    def __init__(self, original, **overrides):
        self.original = original
        self.overrides = overrides

    def __getattr__(self, name):
        return self.overrides.get(name, getattr(self.original, name))


def test_hash_accepts_stable_path_and_fd_ctime_difference(tmp_path, monkeypatch):
    source = tmp_path / "stable.bin"
    content = b"completed acquisition bytes\0" * 31
    source.write_bytes(content)
    original_fstat = os.fstat

    def windows_fstat(fd):
        original = original_fstat(fd)
        return StatView(original, st_ctime_ns=original.st_ctime_ns + 1_000_000)

    monkeypatch.setattr(os, "fstat", windows_fstat)
    assert _hash(source) == (hashlib.sha256(content).hexdigest(), len(content))


def test_copy_accepts_stable_path_and_fd_ctime_difference(tmp_path, monkeypatch):
    source = tmp_path / "stable.bin"
    target = tmp_path / "copied.bin"
    content = b"byte-preserving transfer\xff" * 101
    source.write_bytes(content)
    original_fstat = os.fstat

    def windows_fstat(fd):
        original = original_fstat(fd)
        return StatView(original, st_ctime_ns=original.st_ctime_ns + 1_000_000)

    monkeypatch.setattr(os, "fstat", windows_fstat)
    result = _copy(source, target)
    assert result == {"sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}
    assert target.read_bytes() == content
    assert source.read_bytes() == content


def test_hash_refuses_change_in_fd_ctime_during_read(tmp_path, monkeypatch):
    source = tmp_path / "changing.bin"
    source.write_bytes(b"same size, same mtime, changed file metadata")
    original_fstat = os.fstat
    observations = 0

    def changing_fstat(fd):
        nonlocal observations
        observations += 1
        original = original_fstat(fd)
        return StatView(original, st_ctime_ns=original.st_ctime_ns + observations)

    monkeypatch.setattr(os, "fstat", changing_fstat)
    with pytest.raises(ValueError, match="during hashing"):
        _hash(source)


def test_copy_refuses_change_in_fd_ctime_during_read(tmp_path, monkeypatch):
    source = tmp_path / "changing.bin"
    source.write_bytes(b"same size, same mtime, changed file metadata")
    original_fstat = os.fstat
    observations = 0

    def changing_fstat(fd):
        nonlocal observations
        observations += 1
        original = original_fstat(fd)
        return StatView(original, st_ctime_ns=original.st_ctime_ns + observations)

    monkeypatch.setattr(os, "fstat", changing_fstat)
    with pytest.raises(PackError, match="during copying"):
        _copy(source, tmp_path / "copy.bin")


def test_hash_retains_same_method_path_ctime_guard(tmp_path, monkeypatch):
    source = tmp_path / "changing.bin"
    source.write_bytes(b"same bytes, observed path metadata changed")
    original_stat = Path.stat
    observations = 0

    def changing_stat(path, *args, **kwargs):
        nonlocal observations
        original = original_stat(path, *args, **kwargs)
        if path == source:
            observations += 1
            return StatView(original, st_ctime_ns=original.st_ctime_ns + observations)
        return original

    monkeypatch.setattr(Path, "stat", changing_stat)
    with pytest.raises(ValueError, match="during hashing"):
        _hash(source)


@pytest.mark.parametrize("field", ["st_dev", "st_ino", "st_size", "st_mtime_ns"])
def test_hash_still_refuses_other_path_fd_identity_mismatches(tmp_path, monkeypatch, field):
    source = tmp_path / "stable.bin"
    source.write_bytes(b"real content")
    original_fstat = os.fstat

    def mismatching_fstat(fd):
        original = original_fstat(fd)
        return StatView(original, **{field: getattr(original, field) + 1})

    monkeypatch.setattr(os, "fstat", mismatching_fstat)
    with pytest.raises(ValueError, match="before hashing"):
        _hash(source)

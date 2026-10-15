"""Scanner-specific metadata tests; acceptance tests independently cover bundles."""

import json

import h5py
import numpy as np
import pytest

from h5handoff.scan import scan


def codes(report):
    return {issue["code"] for issue in report["issues"]}


def test_mixed_whole_file_closure_and_filters(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (tmp_path / "pixels.raw").write_bytes(np.array([3, 4], dtype="i4").tobytes())
    with h5py.File(run / "source.h5", "w") as f:
        f.create_dataset("signal", data=[1, 2], compression="gzip")
        f.create_dataset("raw", (2,), dtype="i4", external=[("pixels.raw", 0, 8)])
        f["self"] = f["/"]
    layout = h5py.VirtualLayout((2,), dtype="i8")
    layout[:] = h5py.VirtualSource("source.h5", "/signal", shape=(2,))
    with h5py.File(run / "master.h5", "w") as f:
        f["source"] = h5py.ExternalLink("source.h5", "/")
        f.create_virtual_dataset("combined", layout)
        f["alias"] = h5py.SoftLink("/combined")
    result = scan("run/master.h5", tmp_path)
    assert result["ok"], result["issues"]
    assert {x["path"] for x in result["files"]} == {"run/master.h5", "run/source.h5", "pixels.raw"}
    assert {x["kind"] for x in result["dependencies"]} == {
        "external_link",
        "vds",
        "external_raw",
        "soft_link",
    }
    assert result["filters"][0]["id"] == 1
    assert result["data_read"] is False
    assert str(tmp_path) not in json.dumps(result)
    assert result == scan(tmp_path / "run/master.h5", tmp_path)


def test_resolves_external_target_with_soft_intermediate(tmp_path):
    with h5py.File(tmp_path / "source.h5", "w") as f:
        f["real/data"] = [1]
        f["redirect"] = h5py.SoftLink("/real")
    with h5py.File(tmp_path / "master.h5", "w") as f:
        f["x"] = h5py.ExternalLink("source.h5", "/redirect/data")
    assert scan("master.h5", tmp_path)["ok"]


def test_same_file_vds_and_hard_cycle(tmp_path):
    layout = h5py.VirtualLayout((1,), dtype="i8")
    layout[:] = h5py.VirtualSource(".", "/x", shape=(1,))
    with h5py.File(tmp_path / "master.h5", "w") as f:
        f["x"] = [9]
        f.create_virtual_dataset("v", layout)
        f["group/back"] = f["/"]
    result = scan("master.h5", tmp_path)
    assert result["ok"], result["issues"]
    assert len(result["files"]) == 1


def test_soft_cycle_and_missing_target_fail(tmp_path):
    with h5py.File(tmp_path / "m.h5", "w") as f:
        f["a"] = h5py.SoftLink("/b")
        f["b"] = h5py.SoftLink("/a")
        f["missing"] = h5py.ExternalLink("absent.h5", "/x")
    result = scan("m.h5", tmp_path)
    assert not result["ok"]
    assert {"missing_file", "link_cycle"} <= codes(result)


def test_parent_object_name_is_not_normalized(tmp_path):
    with h5py.File(tmp_path / "m.h5", "w") as f:
        f["data"] = [1]
        f.create_group("group")
        f["group/x"] = h5py.SoftLink("../data")
    result = scan("m.h5", tmp_path)
    assert not result["ok"]
    assert "missing_object" in codes(result)


def test_short_raw_is_warning(tmp_path):
    (tmp_path / "raw.bin").write_bytes(b"\x01")
    with h5py.File(tmp_path / "m.h5", "w") as f:
        f.create_dataset("x", (2,), dtype="i4", external=[("raw.bin", 0, 8)])
    result = scan("m.h5", tmp_path)
    assert result["ok"]
    assert codes(result) == {"short_raw"}
    assert result["issues"][0]["severity"] == "warning"


@pytest.mark.parametrize(
    "stored",
    [
        "/etc/passwd",
        "../outside.h5",
        r"C:\secret.h5",
        r"dir\file.h5",
        "https://host/f.h5",
        "$HOME/f.h5",
    ],
)
def test_unsafe_filenames_fail_without_following(tmp_path, stored):
    with h5py.File(tmp_path / "m.h5", "w") as f:
        f["x"] = h5py.ExternalLink(stored, "/x")
    result = scan("m.h5", tmp_path)
    assert not result["ok"]
    assert len(result["files"]) == 1


def test_cancelled_symlink_and_missing_ancestor_are_rejected(tmp_path):
    with h5py.File(tmp_path / "source.h5", "w") as f:
        f["x"] = [1]
    (tmp_path / "alias").symlink_to(tmp_path, target_is_directory=True)
    for ancestor, expected in [("alias", "symlink"), ("absent", "missing_file")]:
        with h5py.File(tmp_path / "m.h5", "w") as f:
            f["x"] = h5py.ExternalLink(f"{ancestor}/../source.h5", "/x")
        result = scan("m.h5", tmp_path)
        assert not result["ok"]
        assert expected in codes(result)
        assert len(result["files"]) == 1
    entry_result = scan("alias/../source.h5", tmp_path)
    assert not entry_result["ok"]
    assert "symlink" in codes(entry_result)


def test_vds_percent_and_source_group_block(tmp_path):
    with h5py.File(tmp_path / "source.h5", "w") as f:
        f.create_group("group")
    layout = h5py.VirtualLayout((1,), dtype="i8")
    layout[:] = h5py.VirtualSource("source.h5", "/group", shape=(1,))
    with h5py.File(tmp_path / "m.h5", "w") as f:
        f.create_virtual_dataset("v", layout)
    assert "not_dataset" in codes(scan("m.h5", tmp_path))
    layout = h5py.VirtualLayout((1,), dtype="i8")
    layout[:] = h5py.VirtualSource("source%%.h5", "/x", shape=(1,))
    with h5py.File(tmp_path / "pattern.h5", "w") as f:
        f.create_virtual_dataset("v", layout)
    assert "unsupported_vds_pattern" in codes(scan("pattern.h5", tmp_path))


def test_global_limits(tmp_path):
    with h5py.File(tmp_path / "source.h5", "w") as f:
        f["x"] = [1]
    with h5py.File(tmp_path / "m.h5", "w") as f:
        f["x"] = h5py.ExternalLink("source.h5", "/x")
        f["y"] = [2]
    assert "file_limit" in codes(scan("m.h5", tmp_path, max_files=1))
    assert {"object_limit", "edge_limit"} & codes(scan("m.h5", tmp_path, max_objects=1))


def test_deep_hard_groups_iterative(tmp_path):
    with h5py.File(tmp_path / "m.h5", "w") as f:
        current = f
        for _ in range(1050):
            current = current.create_group("a")
    result = scan("m.h5", tmp_path)
    assert result["ok"], result["issues"]


def test_soft_edges_capped_even_with_one_hard_object(tmp_path):
    with h5py.File(tmp_path / "m.h5", "w") as f:
        for index in range(30):
            f[f"alias{index:03}"] = h5py.SoftLink("/")
    result = scan("m.h5", tmp_path, max_objects=5)
    assert not result["ok"]
    assert "edge_limit" in codes(result)
    assert len(result["dependencies"]) == 5


def test_lazy_vds_mappings_are_capped(tmp_path, monkeypatch):
    with h5py.File(tmp_path / "source.h5", "w") as f:
        f["x"] = [1]
    layout = h5py.VirtualLayout((30,), dtype="i8")
    for index in range(30):
        layout[index : index + 1] = h5py.VirtualSource("source.h5", "/x", shape=(1,))
    with h5py.File(tmp_path / "m.h5", "w") as f:
        f.create_virtual_dataset("v", layout)

    def forbidden(*args, **kwargs):
        raise AssertionError("high-level unbounded mappings API used")

    monkeypatch.setattr(h5py.Dataset, "virtual_sources", forbidden)
    result = scan("m.h5", tmp_path, max_objects=5)
    assert not result["ok"]
    assert "edge_limit" in codes(result)
    assert len(result["dependencies"]) == 4  # one hard link + four mappings


def test_cancelled_directory_skeleton_and_directory_ceiling(tmp_path):
    (tmp_path / "empty").mkdir()
    with h5py.File(tmp_path / "source.h5", "w") as f:
        f["x"] = [1]
    with h5py.File(tmp_path / "m.h5", "w") as f:
        f["x"] = h5py.ExternalLink("empty/../source.h5", "/x")
    result = scan("m.h5", tmp_path)
    assert result["ok"], result["issues"]
    assert result["directories"] == ["empty"]
    (tmp_path / "another").mkdir()
    with h5py.File(tmp_path / "m.h5", "w") as f:
        f["x"] = h5py.ExternalLink("empty/../another/../source.h5", "/x")
    result = scan("m.h5", tmp_path, max_objects=1)
    assert not result["ok"]
    assert "directory_limit" in codes(result)


def test_external_raw_segment_metadata_and_short_unlimited(tmp_path):
    (tmp_path / "data.raw").write_bytes(b"x")
    with h5py.File(tmp_path / "m.h5", "w") as f:
        f.create_dataset("x", (2,), dtype="i4", external=[("data.raw", 2, h5py.h5f.UNLIMITED)])
    result = scan("m.h5", tmp_path)
    assert result["ok"]
    raw = result["dependencies"][0]
    assert raw["offset"] == 2
    assert raw["size"] == "unlimited"
    assert "short_raw" in codes(result)

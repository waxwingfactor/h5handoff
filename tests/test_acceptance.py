"""Independent acceptance checks of the documented public handoff workflow.

Fixtures are constructed with h5py, and relocation is checked by actual HDF5
reads after removing the entire original tree.  Assertions target observable
behavior rather than scanner implementation details.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest

from h5handoff.bundle import pack, verify
from h5handoff.scan import scan

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/create_fixture.py"
_spec = importlib.util.spec_from_file_location("handoff_acceptance_fixture", EXAMPLE)
_example = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_example)


@pytest.fixture
def mixed(tmp_path):
    root = tmp_path / "acquisition"
    _example.create_fixture(root)
    return root


def assert_blocked(report):
    assert report["ok"] is False
    assert any(issue.get("severity", "error") == "error" for issue in report["issues"])


def create_plain(path, name="data"):
    with h5py.File(path, "w") as handle:
        handle.create_dataset(name, data=np.arange(4, dtype="i4"))


def manifest(bundle):
    return json.loads((bundle / "handoff.json").read_text(encoding="utf-8"))


def rewrite_manifest(bundle, data):
    (bundle / "handoff.json").write_text(json.dumps(data), encoding="utf-8")


def cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "h5handoff", *map(str, args)],
        text=True, capture_output=True, cwd=cwd, timeout=30,
    )


def test_mixed_fixture_inventories_the_full_metadata_closure(mixed):
    report = scan("run/master.h5", mixed)
    assert report["ok"], report["issues"]
    assert report["data_read"] is False
    assert report["raw_base"] == "."
    assert report["resolution_profile"] == "literal-v1"
    assert {item["path"] for item in report["files"]} == {
        "run/master.h5", "run/metadata/tree.h5", "data/frames.h5", "raw/detector.bin"
    }
    assert {item["kind"] for item in report["dependencies"]} >= {
        "external_link", "vds", "external_raw", "soft_link"
    }
    assert any(item["id"] == 1 for item in report["filters"])
    assert str(mixed) not in json.dumps(report)
    assert report == scan("run/master.h5", mixed)


def test_audit_does_not_access_any_dataset_payload(mixed, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("metadata audit accessed a dataset payload")

    monkeypatch.setattr(h5py.Dataset, "__getitem__", forbidden)
    assert scan("run/master.h5", mixed)["ok"]


def test_audit_records_an_optional_unknown_filter_without_loading_it(tmp_path):
    with h5py.File(tmp_path / "master.h5", "w") as handle:
        handle.create_dataset(
            "data", shape=(8,), dtype="i4", chunks=(4,),
            compression=32008, allow_unknown_filter=True,
        )
    report = scan("master.h5", tmp_path)
    assert report["ok"], report["issues"]
    assert report["data_read"] is False
    assert any(item["id"] == 32008 for item in report["filters"])


def test_pack_survives_complete_removal_and_reads_real_values(mixed, tmp_path, monkeypatch):
    before = {
        path.relative_to(mixed).as_posix(): path.read_bytes()
        for path in mixed.rglob("*") if path.is_file()
    }
    bundle = tmp_path / "handoff"
    pack("run/master.h5", mixed, bundle)
    receipt = manifest(bundle)
    for item in receipt["files"]:
        assert (bundle / "payload" / item["path"]).read_bytes() == before[item["path"]]
        assert item["sha256"] == hashlib.sha256(before[item["path"]]).hexdigest()
    shutil.rmtree(mixed)
    assert verify(bundle)["ok"]
    monkeypatch.chdir(bundle / "payload")
    with h5py.File("run/master.h5", "r") as handle:
        np.testing.assert_array_equal(handle["entry/images"][:], np.arange(12).reshape(3, 4))
        np.testing.assert_array_equal(handle["entry/virtual"][:], np.arange(12).reshape(3, 4))
        np.testing.assert_array_equal(handle["entry/raw"][:], np.arange(100, 106))
        np.testing.assert_array_equal(handle["entry/alias"][:], np.arange(12).reshape(3, 4))


def test_external_raw_is_root_relative_even_for_a_nested_owner(tmp_path):
    root = tmp_path / "root"
    (root / "nested").mkdir(parents=True)
    (root / "samples.bin").write_bytes(np.array([7], dtype="i4").tobytes())
    with h5py.File(root / "nested/master.h5", "w") as handle:
        handle.create_dataset("raw", (1,), dtype="i4", external=[("samples.bin", 0, 4)])
    report = scan("nested/master.h5", root)
    assert report["ok"], report["issues"]
    assert any(item.get("target") == "samples.bin" for item in report["dependencies"])


def test_short_raw_is_a_warning_not_a_claim_of_corruption(tmp_path):
    (tmp_path / "raw.bin").write_bytes(b"\0\0\0\0")
    with h5py.File(tmp_path / "master.h5", "w") as handle:
        handle.create_dataset("raw", (8,), dtype="i4", external=[("raw.bin", 0, 32)])
    report = scan("master.h5", tmp_path)
    assert report["ok"], report["issues"]
    assert any(item["severity"] == "warning" for item in report["issues"])


def test_missing_vds_source_blocks_even_when_native_hdf5_returns_fill(tmp_path):
    layout = h5py.VirtualLayout((3,), dtype="i4")
    layout[:] = h5py.VirtualSource("missing.h5", "/data", shape=(3,))
    with h5py.File(tmp_path / "master.h5", "w") as handle:
        handle.create_virtual_dataset("virtual", layout, fillvalue=-7)
    with h5py.File(tmp_path / "master.h5", "r") as handle:
        np.testing.assert_array_equal(handle["virtual"][:], [-7, -7, -7])
    assert_blocked(scan("master.h5", tmp_path))


def test_vds_source_must_refer_to_a_dataset(tmp_path):
    with h5py.File(tmp_path / "source.h5", "w") as handle:
        handle.create_group("group")
    layout = h5py.VirtualLayout((1,), dtype="i4")
    layout[:] = h5py.VirtualSource("source.h5", "/group", shape=(1,))
    with h5py.File(tmp_path / "master.h5", "w") as handle:
        handle.create_virtual_dataset("virtual", layout)
    assert_blocked(scan("master.h5", tmp_path))


def test_same_file_virtual_dataset_is_supported(tmp_path):
    layout = h5py.VirtualLayout((4,), dtype="i4")
    layout[:] = h5py.VirtualSource(".", "/data", shape=(4,))
    with h5py.File(tmp_path / "master.h5", "w") as handle:
        handle.create_dataset("data", data=np.arange(4))
        handle.create_virtual_dataset("virtual", layout)
    report = scan("master.h5", tmp_path)
    assert report["ok"], report["issues"]
    assert [item["path"] for item in report["files"]] == ["master.h5"]


def test_unused_objects_in_a_reached_file_are_included(tmp_path):
    with h5py.File(tmp_path / "master.h5", "w") as handle:
        handle["chosen"] = h5py.ExternalLink("child.h5", "/chosen")
    with h5py.File(tmp_path / "child.h5", "w") as handle:
        handle.create_group("chosen")
        handle["unused_broken"] = h5py.ExternalLink("missing.h5", "/data")
    assert_blocked(scan("master.h5", tmp_path))


def test_missing_external_object_blocks(tmp_path):
    create_plain(tmp_path / "source.h5")
    with h5py.File(tmp_path / "master.h5", "w") as handle:
        handle["link"] = h5py.ExternalLink("source.h5", "/absent")
    assert_blocked(scan("master.h5", tmp_path))


def test_hard_group_cycles_terminate_without_false_dependency_errors(tmp_path):
    with h5py.File(tmp_path / "master.h5", "w") as handle:
        group = handle.create_group("g")
        group["self"] = group
        group["root"] = handle["/"]
        group.create_dataset("data", data=[1])
    assert scan("master.h5", tmp_path)["ok"]


def test_soft_link_cycle_is_an_error(tmp_path):
    with h5py.File(tmp_path / "master.h5", "w") as handle:
        handle["a"] = h5py.SoftLink("/b")
        handle["b"] = h5py.SoftLink("/a")
    assert_blocked(scan("master.h5", tmp_path))


def test_external_link_cycle_without_an_object_is_an_error(tmp_path):
    with h5py.File(tmp_path / "a.h5", "w") as handle:
        handle["loop"] = h5py.ExternalLink("b.h5", "/loop")
    with h5py.File(tmp_path / "b.h5", "w") as handle:
        handle["loop"] = h5py.ExternalLink("a.h5", "/loop")
    assert_blocked(scan("a.h5", tmp_path))


def test_global_file_and_object_limits_make_audit_incomplete(mixed):
    assert_blocked(scan("run/master.h5", mixed, max_files=1))
    assert_blocked(scan("run/master.h5", mixed, max_objects=1))


def test_many_symbolic_links_are_bounded_even_with_one_hard_object(tmp_path):
    with h5py.File(tmp_path / "master.h5", "w") as handle:
        for index in range(20):
            handle[f"alias_{index:02d}"] = h5py.SoftLink("/")
    assert_blocked(scan("master.h5", tmp_path, max_objects=8))


def test_deep_groups_are_handled_without_python_recursion_failure(tmp_path):
    with h5py.File(tmp_path / "master.h5", "w") as handle:
        group = handle
        for _ in range(1100):
            group = group.create_group("g")
    report = scan("master.h5", tmp_path, max_objects=1500)
    assert report["ok"], report["issues"]


@pytest.mark.parametrize("stored", ["../outside.h5", "C:/data.h5", "https://example.com/x.h5", "folder\\x.h5", "$HOME/x.h5"])
def test_unsafe_stored_paths_fail_closed(tmp_path, stored):
    root = tmp_path / "root"
    root.mkdir()
    create_plain(tmp_path / "outside.h5")
    with h5py.File(root / "master.h5", "w") as handle:
        handle["link"] = h5py.ExternalLink(stored, "/data")
    report = scan("master.h5", root)
    assert_blocked(report)
    assert all(item["path"] != "../outside.h5" for item in report["files"])


def test_absolute_dependency_is_rejected_even_when_inside_root(tmp_path):
    create_plain(tmp_path / "source.h5")
    with h5py.File(tmp_path / "master.h5", "w") as handle:
        handle["link"] = h5py.ExternalLink(str(tmp_path / "source.h5"), "/data")
    assert_blocked(scan("master.h5", tmp_path))


def test_parent_components_are_supported_when_still_inside_root(tmp_path):
    (tmp_path / "nested").mkdir()
    create_plain(tmp_path / "source.h5")
    with h5py.File(tmp_path / "nested/master.h5", "w") as handle:
        handle["link"] = h5py.ExternalLink("../source.h5", "/data")
    assert scan("nested/master.h5", tmp_path)["ok"]


def test_symlink_in_dependency_ancestry_is_rejected(tmp_path):
    (tmp_path / "actual").mkdir()
    create_plain(tmp_path / "actual/source.h5")
    (tmp_path / "alias").symlink_to(tmp_path / "actual", target_is_directory=True)
    with h5py.File(tmp_path / "master.h5", "w") as handle:
        handle["link"] = h5py.ExternalLink("alias/source.h5", "/data")
    assert_blocked(scan("master.h5", tmp_path))


def test_symlink_entry_is_rejected(tmp_path):
    create_plain(tmp_path / "actual.h5")
    (tmp_path / "entry.h5").symlink_to("actual.h5")
    assert_blocked(scan("entry.h5", tmp_path))


def test_parent_component_does_not_hide_a_symlink(tmp_path):
    (tmp_path / "actual").mkdir()
    (tmp_path / "alias").symlink_to("actual", target_is_directory=True)
    create_plain(tmp_path / "source.h5")
    with h5py.File(tmp_path / "master.h5", "w") as handle:
        handle["link"] = h5py.ExternalLink("alias/../source.h5", "/data")
    assert_blocked(scan("master.h5", tmp_path))


def test_parent_component_does_not_hide_a_missing_directory(tmp_path):
    create_plain(tmp_path / "source.h5")
    with h5py.File(tmp_path / "master.h5", "w") as handle:
        handle["link"] = h5py.ExternalLink("missing/../source.h5", "/data")
    assert_blocked(scan("master.h5", tmp_path))


def test_pack_preserves_required_empty_directory_for_literal_parent_path(tmp_path):
    root = tmp_path / "root"
    (root / "empty").mkdir(parents=True)
    create_plain(root / "source.h5")
    with h5py.File(root / "master.h5", "w") as handle:
        handle["data"] = h5py.ExternalLink("empty/../source.h5", "/data")
    bundle = tmp_path / "handoff"
    pack("master.h5", root, bundle)
    shutil.rmtree(root)
    assert verify(bundle)["ok"]
    assert (bundle / "payload/empty").is_dir()
    with h5py.File(bundle / "payload/master.h5", "r") as handle:
        np.testing.assert_array_equal(handle["data"][:], np.arange(4))


def test_pattern_virtual_sources_are_not_silently_treated_as_literal(tmp_path):
    source = h5py.VirtualSource("part_%b.h5", "/data", shape=(1,), maxshape=(None,))
    layout = h5py.VirtualLayout((1,), dtype="i4", maxshape=(None,))
    layout[0:h5py.h5s.UNLIMITED] = source
    with h5py.File(tmp_path / "master.h5", "w") as handle:
        handle.create_virtual_dataset("virtual", layout)
    assert_blocked(scan("master.h5", tmp_path))


def test_pack_failure_leaves_no_published_or_staged_directory(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with h5py.File(root / "master.h5", "w") as handle:
        handle["missing"] = h5py.ExternalLink("missing.h5", "/data")
    before = set(tmp_path.iterdir())
    with pytest.raises((ValueError, OSError)):
        pack("master.h5", root, tmp_path / "handoff")
    assert set(tmp_path.iterdir()) == before


def test_pack_rejects_output_inside_source_root(mixed):
    with pytest.raises((ValueError, OSError)):
        pack("run/master.h5", mixed, mixed / "handoff")
    assert not (mixed / "handoff").exists()


def test_pack_does_not_overwrite_existing_destination(mixed, tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "sentinel").write_text("preserve", encoding="utf-8")
    with pytest.raises((ValueError, OSError)):
        pack("run/master.h5", mixed, destination)
    assert (destination / "sentinel").read_text(encoding="utf-8") == "preserve"


@pytest.mark.parametrize("mutation", ["modify", "delete", "extra", "omit", "escape", "entry", "symlink"])
def test_verify_rejects_changed_or_inconsistent_handoffs(mixed, tmp_path, mutation):
    bundle = tmp_path / "handoff"
    pack("run/master.h5", mixed, bundle)
    receipt = manifest(bundle)
    target = bundle / "payload/raw/detector.bin"
    if mutation == "modify":
        target.write_bytes(b"X" + target.read_bytes()[1:])
    elif mutation == "delete":
        target.unlink()
    elif mutation == "extra":
        (bundle / "payload/unlisted.txt").write_text("extra", encoding="utf-8")
    elif mutation == "omit":
        receipt["files"] = [item for item in receipt["files"] if item["path"] != "raw/detector.bin"]
        rewrite_manifest(bundle, receipt)
    elif mutation == "escape":
        receipt["files"][0]["path"] = "../outside.bin"
        rewrite_manifest(bundle, receipt)
    elif mutation == "entry":
        receipt["entry"] = "data/frames.h5"
        rewrite_manifest(bundle, receipt)
    elif mutation == "symlink":
        target.unlink()
        target.symlink_to(mixed / "raw/detector.bin")
    assert_blocked(verify(bundle))


def test_verify_enforces_its_own_file_limit(mixed, tmp_path):
    bundle = tmp_path / "handoff"
    pack("run/master.h5", mixed, bundle)
    assert_blocked(verify(bundle, max_files=1))


def test_cli_json_is_machine_readable_and_findings_are_nonzero(mixed, tmp_path):
    success = cli("audit", "run/master.h5", "--root", mixed, "--json", "-")
    assert success.returncode == 0, success.stderr
    assert json.loads(success.stdout)["data_read"] is False
    (mixed / "data/frames.h5").unlink()
    failure = cli("audit", "run/master.h5", "--root", mixed, "--json", "-")
    assert failure.returncode == 1, (failure.stdout, failure.stderr)
    assert_blocked(json.loads(failure.stdout))


def test_cli_existing_json_report_is_not_overwritten(mixed, tmp_path):
    report = tmp_path / "report.json"
    report.write_text("preserve", encoding="utf-8")
    result = cli("audit", "run/master.h5", "--root", mixed, "--json", report)
    assert result.returncode != 0
    assert report.read_text(encoding="utf-8") == "preserve"


def test_cli_pack_verify_and_demo_are_complete_workflows(tmp_path):
    root = tmp_path / "demo"
    result = cli("demo", root)
    assert result.returncode == 0, (result.stdout, result.stderr)
    entries = list(root.rglob("*.h5"))
    assert entries
    # The documented demo entry is run/master.h5, matching the public fixture.
    bundle = tmp_path / "handoff"
    packed = cli("pack", "run/master.h5", "--root", root, "--output", bundle, "--json", "-")
    assert packed.returncode == 0, (packed.stdout, packed.stderr)
    assert json.loads(packed.stdout)["ok"]
    shutil.rmtree(root)
    verified = cli("verify", bundle, "--json", "-")
    assert verified.returncode == 0, (verified.stdout, verified.stderr)
    assert json.loads(verified.stdout)["ok"]
    assert cli("demo", root).returncode == 0
    assert cli("demo", root).returncode != 0

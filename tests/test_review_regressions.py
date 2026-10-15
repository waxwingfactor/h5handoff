"""Review B regressions, targeting completed command and verification behavior."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import h5py
import pytest

from h5handoff.bundle import pack, verify
from h5handoff.demo import create_demo


@pytest.fixture
def collection(tmp_path):
    root = tmp_path / "source"
    create_demo(root)
    return root


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "h5handoff", *map(str, args)],
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize("relative", ["report.json", "payload/report.json"])
def test_pack_refuses_a_report_inside_its_bundle_before_publishing(collection, tmp_path, relative):
    destination = tmp_path / "handoff"
    result = run_cli(
        "pack", "run/master.h5", "--root", collection,
        "--output", destination, "--json", destination / relative,
    )
    assert result.returncode != 0
    assert not destination.exists()
    assert not list(tmp_path.glob(".handoff.h5handoff-*"))


def test_pack_report_parent_components_cannot_hide_a_bundle_collision(collection, tmp_path):
    destination = tmp_path / "handoff"
    (tmp_path / "existing").mkdir()
    report = tmp_path / "existing" / ".." / "handoff" / "payload" / "report.json"
    result = run_cli(
        "pack", "run/master.h5", "--root", collection,
        "--output", destination, "--json", report,
    )
    assert result.returncode != 0
    assert not destination.exists()


@pytest.mark.parametrize("relative", ["report.json", "payload/report.json"])
def test_verify_cannot_add_a_report_to_the_bundle_it_just_checked(collection, tmp_path, relative):
    destination = tmp_path / "handoff"
    pack("run/master.h5", collection, destination)
    result = run_cli("verify", destination, "--json", destination / relative)
    assert result.returncode != 0
    assert not (destination / relative).exists()
    assert verify(destination)["ok"]


def test_verify_report_alias_cannot_bypass_bundle_output_protection(collection, tmp_path):
    destination = tmp_path / "handoff"
    pack("run/master.h5", collection, destination)
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(destination, target_is_directory=True)
    except OSError:
        pytest.skip("This account cannot create directory symlinks")
    result = run_cli("verify", destination, "--json", alias / "payload" / "report.json")
    assert result.returncode != 0
    assert not (destination / "payload/report.json").exists()
    assert verify(destination)["ok"]


def test_report_path_resolution_failure_is_a_clean_io_error(collection, tmp_path):
    loop = tmp_path / "loop"
    try:
        loop.symlink_to("loop", target_is_directory=True)
    except OSError:
        pytest.skip("This account cannot create directory symlinks")
    destination = tmp_path / "handoff"
    result = run_cli(
        "pack", "run/master.h5", "--root", collection,
        "--output", destination, "--json", loop / "report.json",
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert not destination.exists()


def test_missing_report_parent_prevents_bundle_publication(collection, tmp_path):
    destination = tmp_path / "handoff"
    result = run_cli(
        "pack", "run/master.h5", "--root", collection,
        "--output", destination, "--json", tmp_path / "missing" / "report.json",
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert not destination.exists()
    assert not (tmp_path / "missing").exists()


def test_verify_fails_when_any_payload_directory_cannot_be_enumerated(
    collection, tmp_path, monkeypatch,
):
    destination = tmp_path / "handoff"
    pack("run/master.h5", collection, destination)
    opaque = destination / "payload" / "opaque"
    opaque.mkdir()
    (opaque / "unlisted.txt").write_text("not in the receipt", encoding="utf-8")
    original_scandir = os.scandir

    def denied(path):
        if Path(path) == opaque:
            raise PermissionError("review fixture: cannot enumerate opaque directory")
        return original_scandir(path)

    monkeypatch.setattr(os, "scandir", denied)
    result = verify(destination)
    assert not result["ok"]
    assert any(issue["severity"] == "error" for issue in result["issues"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("filters", None),
        ("filters", {}),
        ("filters", 17),
        ("filters", "not a filter inventory"),
        ("files", None),
        ("dependencies", None),
        ("resolution_profile", "unsupported"),
    ],
)
def test_malformed_nested_receipt_fails_as_structured_output(
    collection, tmp_path, field, value,
):
    destination = tmp_path / "handoff"
    pack("run/master.h5", collection, destination)
    receipt_path = destination / "handoff.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["audit"][field] = value
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    result = run_cli("verify", destination, "--json", "-")
    assert result.returncode != 0
    report = json.loads(result.stdout)
    assert not report["ok"]
    assert any(issue["severity"] == "error" for issue in report["issues"])
    assert "Traceback" not in result.stderr


def test_empty_filter_object_cannot_masquerade_as_an_empty_inventory(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    with h5py.File(source / "master.h5", "w") as handle:
        handle.create_dataset("data", data=[1, 2, 3])
    destination = tmp_path / "handoff"
    pack("master.h5", source, destination)
    receipt_path = destination / "handoff.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["audit"]["filters"] == []
    receipt["audit"]["filters"] = {}
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    result = verify(destination)
    assert not result["ok"]
    assert any(issue["severity"] == "error" for issue in result["issues"])

"""Command-line interface. JSON stdout contains exactly one result object."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .bundle import PackError, pack, verify
from .demo import create_demo
from .scan import scan


def _positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _parser():
    parser = argparse.ArgumentParser(
        prog="h5handoff",
        description="Preserve and verify the file dependencies of completed local HDF5 data.",
        epilog="Entry paths are relative to --root. No dataset payloads are decoded.",
    )
    parser.add_argument("--version", action="version", version=f"h5handoff {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("audit", "Inventory and check a bounded dependency closure"),
        ("pack", "Copy a complete closure into a new verified directory bundle"),
        ("verify", "Hash recipient files and independently re-audit their closure"),
    ):
        command_parser = subparsers.add_parser(command, help=help_text)
        if command == "verify":
            command_parser.add_argument("bundle", type=Path)
        else:
            command_parser.add_argument(
                "entry", help="HDF5 entry, relative to --root or absolute inside it"
            )
            command_parser.add_argument(
                "--root", type=Path, required=True, help="Input and raw-file working-directory root"
            )
        if command == "pack":
            command_parser.add_argument(
                "--output", type=Path, required=True, help="New directory outside --root"
            )
        command_parser.add_argument("--max-files", type=_positive, default=1000)
        command_parser.add_argument("--max-objects", type=_positive, default=100000)
        command_parser.add_argument(
            "--json", metavar="PATH|-", help="Write JSON to a new file or stdout (-)"
        )
    demo = subparsers.add_parser("demo", help="Create a small mixed-dependency synthetic dataset")
    demo.add_argument("output", type=Path, help="New directory")
    return parser


def _safe(value):
    return json.dumps(str(value), ensure_ascii=False)[1:-1]


def _human(result, command):
    state = "PASS" if result["ok"] else "FAIL"
    print(f"{state}: {command}")
    if "entry" in result:
        print(f"Entry: {_safe(result['entry'])}")
    if "files" in result:
        print(f"Files: {len(result['files'])}")
    if "files_verified" in result:
        print(f"Files verified: {result['files_verified']}")
    for issue in result.get("issues", []):
        location = issue.get("file", "") + issue.get("object", "")
        print(
            f"{_safe(issue.get('severity', 'error'))}: {_safe(issue['code'])} "
            f"{_safe(location)}: {_safe(issue['message'])}"
        )
    audit = result.get("audit", result)
    filters = audit.get("filters", [])
    custom = sorted({item["id"] for item in filters if item["id"] > 6})
    if custom:
        print(f"Filter plugins may be required by your reader (IDs: {custom}).")
    if command == "demo":
        print(f"Next: h5handoff audit run/master.h5 --root {_safe(result['root'])}")
    else:
        print(
            "Dataset payloads were not decoded. External raw files use the payload/root working directory."
        )


def main(argv=None):
    args = _parser().parse_args(argv)
    json_target = getattr(args, "json", None)
    # Refuse report overwrite before doing any other work, including packing.
    if json_target and json_target != "-":
        report_path = Path(json_target)
        if report_path.exists() or report_path.is_symlink():
            print("h5handoff: JSON output already exists; choose a new file", file=sys.stderr)
            return 2
        if args.command in ("pack", "verify"):
            protected = args.output if args.command == "pack" else args.bundle
            try:
                collision = report_path.resolve().is_relative_to(protected.resolve())
            except (OSError, RuntimeError) as error:
                print(f"h5handoff: cannot resolve report path: {_safe(error)}", file=sys.stderr)
                return 2
            if collision:
                print("h5handoff: JSON output must be outside the bundle", file=sys.stderr)
                return 2
    try:
        options = (
            {"max_files": args.max_files, "max_objects": args.max_objects}
            if args.command != "demo"
            else {}
        )
        if args.command == "audit":
            result = scan(args.entry, args.root, **options)
        elif args.command == "pack":
            result = pack(args.entry, args.root, args.output, **options)
        elif args.command == "verify":
            result = verify(args.bundle, **options)
        else:
            result = create_demo(args.output)
        code = 0 if result["ok"] else 1
    except PackError as error:
        result = {
            "ok": False,
            "data_read": False,
            "issues": [{"code": "pack_refused", "severity": "error", "message": str(error)}],
        }
        code = 1
    except (OSError, ValueError, RuntimeError) as error:
        result = {
            "ok": False,
            "data_read": False,
            "issues": [{"code": "operation_failed", "severity": "error", "message": str(error)}],
        }
        code = 2
    if json_target:
        encoded = json.dumps(result, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
        if json_target == "-":
            sys.stdout.write(encoded)
        else:
            try:
                with Path(json_target).open("x", encoding="utf-8") as output:
                    output.write(encoded)
            except OSError as error:
                print(f"h5handoff: cannot write report: {_safe(error)}", file=sys.stderr)
                return 2
            _human(result, args.command)
    else:
        _human(result, args.command)
    return code

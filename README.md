# h5handoff

**Move a completed HDF5 dataset without leaving its files behind.**

A detector's master file may reference other HDF5 files, virtual dataset sources, and separate raw files. `h5handoff` inventories that dependency closure, copies it into a directory bundle without rewriting any input, then checks the copied closure and every file's SHA-256. The recipient can repeat verification after transfer.

For beamline researchers and data managers handing completed local datasets to colleagues or taking them home. MIT licensed. Python 3.10+. No server, account or network access during use.

## Install

Download the wheel from the [latest public release](https://github.com/waxwingfactor/h5handoff/releases/latest), then install it in a virtual environment:

```sh
python -m venv .venv
# macOS/Linux:
. .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install ./h5handoff-1.0.0-py3-none-any.whl
h5handoff --version
```

The wheel is pure Python; its `h5py` dependency normally supplies platform wheels with HDF5 and NumPy. Platforms without those wheels need a working HDF5/h5py installation. A source distribution is supplied too. This project is distributed through GitHub Releases; it is not currently published on PyPI.

## Try the complete workflow

The installed demo generates a tiny synthetic master, a virtual dataset, a compressed source, and separate raw storage. All paths below are relative to the current directory; the output directories must not exist.

```sh
h5handoff demo example-data
h5handoff audit run/master.h5 --root example-data
h5handoff pack run/master.h5 --root example-data --output example-transfer
h5handoff verify example-transfer
```

Transfer the **whole `example-transfer` directory** with your normal file-transfer tool, or archive that directory with ZIP/tar. Verify again on the recipient's machine. `h5handoff` does not extract archives or upload data.

To confirm the data reads independently, rename `example-data` so the original files cannot supply dependencies. Change into `example-transfer/payload`, then run:

```python
import h5py
with h5py.File("run/master.h5", "r") as f:
    print(f["frames"][:])    # [[0, 1, 2], [3, 4, 5]]
    print(f["virtual"][:])   # same array through a VDS
    print(f["samples"][:])   # [0, 1, 2, 3] from external raw storage
```

Changing into `payload` matters: by default, HDF5 resolves relative **external raw storage** paths from the reader's working directory. Unset custom `HDF5_EXT_PREFIX`, `HDF5_VDS_PREFIX`, and `HDF5_EXTFILE_PREFIX` overrides when reading this profile. See [resolution rules and limits](docs/scope.md).

## Use it on your dataset

```sh
h5handoff audit experiment/master.h5 --root /data/completed-run --json audit.json
h5handoff pack experiment/master.h5 --root /data/completed-run --output /data/run-transfer
h5handoff verify /data/run-transfer --json verification.json
```

`ENTRY` is relative to `--root`, or an absolute path inside it. Choose a root that contains the master and every dependency. For external raw storage, that root also declares the reading working directory. The output must be a new directory outside the input root, with an existing parent.

Audit errors block packing. Fix the source dataset using its producing application, choose the correct root, or use a different tool if it needs unsupported resolution behavior. `h5handoff` never guesses replacement paths or rewrites links.

Each command supports `--max-files` (default 1,000) and `--max-objects` (default 100,000). Reaching a limit produces an incomplete-audit error. Use `--json -` for machine-readable stdout. A JSON report file must be new; existing reports are never overwritten. Exit codes: **0** success, **1** audit/integrity findings or packing refused, **2** invocation/I/O failure.

## What is verified

- Local external links and soft-link targets, including intermediate links and cycles.
- Literal virtual dataset source files and source datasets, including nested source files.
- External raw-file storage under the declared working-directory root; offsets and short-storage warnings are reported.
- Whole reached HDF5 files, conservatively including objects the master may never read.
- SHA-256 and size of every file, exact dependency inventory, and fresh metadata closure after copy and after transfer.

A bundle contains `payload/` with the preserved relative layout, `handoff.json` with the unsigned receipt and metadata audit, and `README.txt` with recipient instructions. Failed packing cleans up its private staging directory. The copy streams file bytes and uses bounded memory; it does not materialize virtual datasets.

**Verification does not decode dataset values.** It does not prove scientific correctness, acquisition completeness, VDS selection coverage, or data readability in every application. Filter IDs are inventoried; compression plugins may still be required. A short external raw segment is a warning because HDF5 can legitimately supply zero-filled bytes beyond EOF. The receipt proves consistency with itself, not authenticity against an attacker who can replace it.

## Supported boundary

Completed, quiescent local datasets using ordinary single-file HDF5 containers and literal relative paths. Absolute/foreign paths, symlinks, paths outside root, filename patterns, environment-based path expansion, remote storage, family/multi drivers and live acquisition are refused or unsupported. No path rewriting, flattening, scientific validation, or hostile-file sandbox is provided. Use a maintained HDF5 library and trusted inputs.

Read the [exact supported scope](docs/scope.md), [architecture](docs/architecture.md), [security model](SECURITY.md), and [research and alternatives](docs/research.md). The research documents real transfer hazards and existing solutions, including `hdf5-vds-check`, `h5ls`, `h5dump` and `h5repack`; it does not claim universal uniqueness or verified customer demand.

## Development and evidence

See [contributing](CONTRIBUTING.md), [positioning and constructed scenarios](docs/positioning.md), [review record](docs/reviews.md), and [release validation](docs/release-validation.md), and a [real public EIGER check](docs/real-data-check.md). Tests generate synthetic files and independently read relocated data after removing the originals. CI covers Python 3.10, 3.12 and 3.14 on Linux, macOS and Windows, including a clean wheel installation.

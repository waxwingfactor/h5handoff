"""Create a small, genuinely multi-file HDF5 handoff example.

Run ``python examples/create_fixture.py NEW_DIRECTORY``.  The destination must
not exist.  No acquisition data, network service, or optional HDF5 filter is
needed.  Read the resulting ``run/master.h5`` with the fixture root as CWD,
because HDF5's external raw storage uses that explicit resolution profile.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np


def create_fixture(destination: str | Path) -> Path:
    """Create external-link, VDS, and raw-storage dependencies; return entry."""
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=False)
    for folder in ("run/metadata", "data", "raw"):
        (root / folder).mkdir(parents=True, exist_ok=True)

    frames = np.arange(12, dtype=np.int32).reshape(3, 4)
    with h5py.File(root / "data/frames.h5", "w") as source:
        source.create_dataset("frames", data=frames, compression="gzip")
        source.attrs["purpose"] = "Synthetic fixture; no real acquisition data"

    raw = np.arange(100, 106, dtype="<i4")
    (root / "raw/detector.bin").write_bytes(raw.tobytes())

    with h5py.File(root / "run/metadata/tree.h5", "w") as tree:
        entry = tree.create_group("entry")
        entry["images"] = h5py.ExternalLink("../../data/frames.h5", "/frames")
        virtual = h5py.VirtualLayout(shape=frames.shape, dtype=frames.dtype)
        virtual[:] = h5py.VirtualSource(
            "../../data/frames.h5", "/frames", shape=frames.shape
        )
        entry.create_virtual_dataset("virtual", virtual, fillvalue=-999)
        entry.create_dataset(
            "raw", shape=raw.shape, dtype=raw.dtype,
            external=[("raw/detector.bin", 0, raw.nbytes)],
        )
        entry["alias"] = h5py.SoftLink("/entry/images")

    master = root / "run/master.h5"
    with h5py.File(master, "w") as handle:
        handle["entry"] = h5py.ExternalLink("metadata/tree.h5", "/entry")
        handle.attrs["reading_profile"] = "cd to fixture root before reading"
    return master


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    entry = create_fixture(args.destination)
    print(f"Created {entry}")
    print(f"Audit: h5handoff audit run/master.h5 --root {args.destination}")


if __name__ == "__main__":
    main()

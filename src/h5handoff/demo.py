"""Small synthetic dataset for an installed, offline end-to-end trial."""

from pathlib import Path


def create_demo(destination) -> dict:
    import h5py
    import numpy as np

    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Demo output already exists; choose a new directory")
    destination.mkdir()
    try:
        run = destination / "run"
        run.mkdir()
        np.arange(4, dtype="<i4").tofile(destination / "samples.raw")
        with h5py.File(run / "frames.h5", "w") as handle:
            handle.create_dataset("frames", data=np.arange(6).reshape(2, 3), compression="gzip")
        with h5py.File(run / "raw.h5", "w") as handle:
            handle.create_dataset("samples", (4,), dtype="<i4", external=[("samples.raw", 0, 16)])
        with h5py.File(run / "master.h5", "w", libver="latest") as handle:
            handle["frames"] = h5py.ExternalLink("frames.h5", "/frames")
            handle["samples"] = h5py.ExternalLink("raw.h5", "/samples")
            layout = h5py.VirtualLayout(shape=(2, 3), dtype="i8")
            layout[:] = h5py.VirtualSource("frames.h5", "frames", shape=(2, 3))
            handle.create_virtual_dataset("virtual", layout, fillvalue=-1)
        return {"ok": True, "entry": "run/master.h5", "root": str(destination), "data_read": False}
    except Exception:
        import shutil

        shutil.rmtree(destination)
        raise

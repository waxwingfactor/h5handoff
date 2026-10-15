# Distribution validation

The release process requires a wheel and source distribution, metadata checks, clean installation and an actual relocated-data read after removing originals. The public release artifacts will be downloaded and tested separately from the development checkout. This record will be completed with artifact hashes, environment and results after publication; no public-artifact verification has occurred yet.

Local preflight on 2026-10-15: Python 3.12.13, h5py 3.16.0, HDF5 2.0.0, macOS arm64. Both wheel and sdist built; `twine check` passed. Independent acceptance tests read real external-link, VDS and raw values from a copied bundle after deleting the source tree. The required GitHub CI matrix will verify Python 3.10/3.12/3.14 on Linux/macOS/Windows before merge.

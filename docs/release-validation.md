# Public release validation: v1.0.0

Completed **2026-10-15**, after publication. The [public release](https://github.com/waxwingfactor/h5handoff/releases/tag/v1.0.0) is non-draft and non-prerelease. Anonymous requests to the repository and release pages returned HTTP 200. The annotated tag resolves to source commit `be7d85c1c0a5b4bc6deeee7b48075c11a20523cc`.

## Required CI and review gate

The [implementation PR](https://github.com/waxwingfactor/h5handoff/pull/3) was independently reviewed by separate AI subagents, with findings and fixes recorded honestly in [the review record](reviews.md). Its final [required CI run](https://github.com/waxwingfactor/h5handoff/actions/runs/38783351745) passed all nine operating-system/Python combinations and the aggregate `quality` gate before self-merge. The [merged-main run](https://github.com/waxwingfactor/h5handoff/actions/runs/38783688417) also passed.

Each combination—Linux, macOS and Windows with Python 3.10, 3.12 and 3.14—ran the 90-test suite, Ruff, wheel/sdist builds, distribution metadata checks, and an isolated wheel-install/demo/pack/verify smoke test. Main protection requires PRs, resolved conversations, required `quality` CI, linear history, and includes administrators. Separate agent reviews are not human approvals or separate GitHub identities.

## Actual public artifacts

The lead built distributions from the exact tagged source. A separate acceptance agent then downloaded the **public GitHub assets**, their published SHA256SUMS, and the public tag reference. It did not test a local development `dist/` directory. Both hashes also matched values supplied separately by the release builder.

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `h5handoff-1.0.0-py3-none-any.whl` | 19,982 | `e1d5fe3fe846d3a372fc69478d8d6153ee8b88778279eba42ab2e1f2017f1479` |
| `h5handoff-1.0.0.tar.gz` | 49,319 | `aaf4a0bcaf30b0505f2e1ebcec186f7193c1cb767f6d309d9a55c1eea9ac3227` |

The [machine-readable receipt](validation/v1.0.0.json) records download URLs, runtime versions, command exit codes, expected arrays, isolation checks and limits. User-specific absolute path prefixes were removed from the published receipt; module locations remain relative to its independent validation directory.

## Independent installation and behavior checks

Executed on macOS 26.5 arm64, Python 3.12.13, h5py 3.16.0, HDF5 2.0.0 and NumPy 2.5.4. The wheel and source archive were installed into **distinct new virtual environments**, with separate working directories and no PYTHONPATH/PYTHONHOME. Imported package locations were confirmed to be inside each environment's `site-packages`.

The installed wheel completed `--version`, `demo`, `audit`, `pack`, and `verify`. The original demo directory was then deleted. Verification of the recipient bundle passed for all four files, and an independent native h5py reader returned the exact expected external-link and VDS arrays `[[0,1,2],[3,4,5]]` and raw array `[0,1,2,3]`. Modifying one payload byte without changing file size then produced `hash_mismatch` and exit status 1.

The downloaded source archive built and installed successfully. Its included tests ran against the installed package:

```text
........................................................................ [ 80%]
..................                                                       [100%]
90 passed in 3.28s
```

## Real-data and claim boundaries

A separate [public Diamond Light Source EIGER smoke check](real-data-check.md) matched source-record sizes/checksums for 18,866,925 bytes of downloaded data, and verified both NeXus and master entry bundles after hiding the originals. It inventoried filter 32008 without decoding detector images. The installed-demo check above additionally read known synthetic data after deleting originals.

These checks establish supported metadata closure, byte preservation, installation and transfer-integrity behavior. They do not establish scientific correctness, acquisition completeness, universal EIGER support, VDS selection coverage, or availability of compression plugins in a recipient's analysis program. Raw storage requires the documented payload working directory. The receipt and release checksums are unsigned; matching them establishes consistency, not publisher authenticity against replacement of both files and checksums. No customer interview or adoption claim is made.

The archive's versioned documentation predates its own public-download test. This live repository record was completed after publication; the release artifacts and tag were not replaced to insert self-referential verification claims.

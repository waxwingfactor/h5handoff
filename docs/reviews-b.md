# Independent review B

Review date: **2026-10-15**. Reviewer: a separate AI subagent in the commission, not a human customer or a separate GitHub approval. This reviewer also authored the research/positioning documents and therefore does not claim independence for their original authorship. The code and acceptance-test review was separate from implementation.

Files reviewed: `src/h5handoff/scan.py`, `bundle.py`, `cli.py`, `demo.py`, packaging/CI configuration, README, scope, architecture, security, research and positioning documents. No product code was changed by this reviewer.

## Findings communicated before merge

### B1 — Report output can invalidate a successful bundle

**Must fix.** `cli.py:main`, report-file creation after `pack` or `verify`.

Reproduction: run `pack ... --output B --json B/payload/report.json`. Packing returns exit 0 and prints `PASS: pack`, but its subsequent report write adds an unlisted file inside the payload. Immediate `verify(B)` then fails exact-inventory validation. The analogous `verify B --json B/payload/new.json` mutates a successful verification result into an invalid bundle.

The JSON path must be checked against the protected payload before performing work, including canonical aliases. A report outside the payload is sufficient. An existing report remains protected by exclusive creation.

### B2 — Unreadable directories can bypass exact inventory verification

**Must fix.** `bundle.py:verify`, `os.walk` without `onerror`.

Reproduction on macOS as the normal account: create a valid demo bundle, add `payload/opaque/unlisted.txt`, and remove all permissions from `opaque`. Verification returns `ok: true` because `os.walk` silently skips the unreadable directory. Permissions were restored after the probe.

Exact inventory requires failing on directory-enumeration errors. Set an error callback that raises, and test the failure behavior independently of platform-specific permission handling.

### B3 — Dynamic plugin disabling is claimed more strongly than implemented

**Must fix the claim or implementation.** `scan.py:_Scanner.run`; SECURITY and scope documentation.

The original code conditionally calls `h5py.h5pl.set_loading_state` only if exposed. In the actual tested supported environment, h5py **3.16.0** with HDF5 **2.0.0**, that module has no `set_loading_state` or `get_loading_state`; the branch therefore does nothing. Unconditional statements that dynamic HDF5 plugin loading is disabled are unsupported. Metadata inspection makes no deliberate decoder calls, which is a different, supportable statement. Trusted native inputs remain an explicit boundary.

### B4 — Raw segment visibility was overstated

**Documentation/capability mismatch.** `scan.py:inspect_dataset` and `record`; README's verification list.

The scanner obtains external raw offsets and segment sizes and uses them for short-file warnings, but the initial dependency records omit both values. A one-segment fixture produced only source/object/kind/stored-file/target fields. README said offsets were reported. Either retain those metadata fields in the report or narrow the statement to what users can inspect.

### B5 — Report-path resolution can escape CLI error handling

**Must fix clean failure behavior.** `cli.py:main`, canonical-path preflight added while addressing B1.

A report path beneath a self-referential directory symlink raises from `Path.resolve()` before the operation's exception handler. The command prints a Python traceback and exits 1 instead of the documented clean invocation/I/O failure status 2. Catch resolution errors as part of preflight and refuse without publishing a bundle.

## Additional observations

- The verifier rejects duplicate JSON keys, extra/missing files, path traversal and symlinks, rehashes files, and compares a new closure with the receipt. These are meaningful checks beyond trusting the sender's file list.
- The receipt remains unsigned; documentation correctly distinguishes consistency from authenticity and excludes hostile native files and concurrent filesystem attackers.
- Malformed nested audit fields generally produce a structured `invalid_bundle` result. An empty object in place of an empty filter list can normalize to the same closure and pass; this does not bypass the fresh scan or hashes, but stricter nested schema typing would improve the receipt contract.
- Source byte preservation, root-relative raw storage, VDS missing-source fill behavior and conservative whole-file traversal are clearly documented. Ordinary copying is acknowledged as sufficient for simple known layouts, and existing VDS-only checking is credited honestly.
- A lexical directory such as `foo/../source.h5` can require a preserved empty directory for native lookup. The current copied-tree audit safely refuses a bundle if it drops necessary path ancestry. This was separately reported by review C; it needs either directory-skeleton support or an explicit supported-scope limit, rather than an assertion that all root-bounded relative paths pack.
- Review C separately raised unbounded group-link enumeration. Any added link/mapping budget should be checked before materializing complete key or VDS-mapping lists; the file/object count alone does not bound graph edges.

## Checks performed

- Ran the full local test suite: **58 passed** at the review checkpoint.
- Constructed and ran the B1 pack/report collision, observing exit 0 followed by immediate verification failure.
- Constructed and ran the B2 unreadable-extra-directory probe, observing a false successful inventory check.
- Inspected actual installed HDF5/h5py versions and plugin-module capabilities for B3.
- Constructed an external raw-storage fixture and examined the reported dependency metadata for B4.
- Mutated nested filter-audit receipt structures and confirmed malformed noniterable values return structured failures.

## Resolution and final retest

All five findings were addressed before this review's final recommendation:

- **B1 resolved:** report destinations inside a pack output or verified bundle are refused before work. Reviewer regressions cover top-level and payload locations, parent-component aliases, and a symlink alias. Rejection leaves the input bundle valid and does not publish a new output.
- **B2 resolved:** verification uses incremental directory enumeration that propagates access failures. The regression injects a denied directory enumeration. The original real `chmod(000)` probe was also repeated: verification now returns `ok: false` with `invalid_bundle` and permission-denied context.
- **B3 resolved:** the unsupported conditional control was removed. Security and scope documentation now accurately state that the scanner does not request decoding or filter-plugin loading and that runtime behavior is not sandboxed.
- **B4 resolved:** raw dependency records include `offset` and `size`. A fresh raw fixture reports `offset: 0` and `size: 4`.
- **B5 resolved:** report-path resolution failures are caught and return the documented status 2 without a traceback or published bundle. A self-referential symlink regression passes.

The additional receipt-contract observation was addressed with typed audit headers, arrays and filter records. The reviewer added a no-filter source fixture, changed its empty filter array to an empty object, and confirmed rejection. Warning-only fresh audits now preserve their warnings in the top-level verification report without converting a warning into an error.

The directory-ancestry observation was addressed by inventorying and reproducing required directory skeletons. A new `foo/../source.h5` fixture successfully packs and verifies with empty `foo` retained. Review C's graph-budget concern was addressed with incremental link enumeration and per-mapping VDS metadata access rather than materializing all names or mappings first.

First local checkpoint: **80 tests passed**, including **16 reviewer-owned regression cases**; `ruff check .` passed. That checkpoint used Python 3.12.13, h5py 3.16.0 and HDF5 2.0.0 on macOS. It did not establish the other Python/platform matrix results.

### Reopened after Python 3.14 CI feedback

Actual Linux Python 3.14 CI caught a gap in the initial B5 resolution: non-strict `Path.resolve()` no longer raises on a symlink loop, so report writing could fail only after publishing a valid bundle. This differs from the Python 3.12 behavior verified above. The [official pathlib documentation](https://docs.python.org/3.14/library/pathlib.html#pathlib.Path.resolve) documents the change beginning in Python 3.13.

The revised preflight strictly resolves the report's existing parent, requires that it is a directory, and then checks the canonical report destination against the protected bundle. The reviewer independently checked the source change, added a missing-parent/no-publication regression, and reran the original symlink-loop test. A manual regular-file-parent check also returns status 2 without traceback or bundle publication.

Final checks against commit `12c9de65884d612834e549c134303a2ce0fabd1f`: **90 tests passed on Python 3.12.13 and 90 passed on Python 3.14.4**, both on macOS with h5py 3.16.0/HDF5 2.0.0. The **17 reviewer-owned regression cases** also passed separately on Python 3.14.4, and `ruff check .` passed. The reviewer inspected the same commit's file-stat portability change: it retains identity, size and mtime comparisons across path/descriptor observations, and compares ctime between observations made through the same method. The additional deterministic platform tests pass in these full runs.

These SHA-256 fingerprints identify the critical code contents at this final checkpoint. Other operating-system CI results and published-artifact installation remain separate release gates, not results claimed by this reviewer:

| File | SHA-256 |
| --- | --- |
| `src/h5handoff/scan.py` | `543db5f213b5c713a79b46941ddee406948776385cdfd1c57bc2b758eede5909` |
| `src/h5handoff/bundle.py` | `e065db668d730b1030526d6446933826104150af96bde2e8d0d2526ba2d8f6ac` |
| `src/h5handoff/cli.py` | `e6a21b8a18e369c91f84ad21f3eeaa772953180c5a97fac544307ec5e309ad80` |
| `src/h5handoff/demo.py` | `470423b305da510319c48ed64fad52cab698e3012d16c4f1025e372a0b53fe9d` |
| `tests/test_review_regressions.py` | `84c0822fe6df5f9281581182bdde4b274276c4fd11b71dc92f3dd371a44ed9a4` |

**Recommendation:** merge these reviewed contents after required CI and distribution checks pass. No unresolved must-fix issue remains in this review. The stated trusted-input, quiescent-filesystem, literal-path, raw-working-directory and metadata-only limitations remain material to use.

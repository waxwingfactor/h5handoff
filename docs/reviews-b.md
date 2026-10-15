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

This record describes the initial findings. Resolution and retest evidence must be appended before treating the review as passed.

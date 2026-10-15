# Architecture

The product is a local command-line tool and importable Python package. Its complete supported workflow is inventory → copy → recipient verification. It has no web UI, daemon, credentials, upload service or application-specific schema requirement.

## Components

- `scan.py`: bounded metadata graph traversal; explicit path and object resolution; whole-file dependency closure; typed issue codes and filter metadata. It never reads dataset values.
- `bundle.py`: streamed opaque-byte copy and SHA-256; before/after file identity/size/time checks; staged receipt; independent copied-tree audit; strict recipient verification.
- `cli.py`: argument validation, safe text rendering, non-overwriting JSON reports, stable exit codes.
- `demo.py`: a tiny synthetic mixed-dependency example available after installation.

The scanner opens each ordinary local HDF5 file read-only with the `sec2` driver, inspects links without HDF5's transparent external traversal, and bounds graph exploration. File paths are root-relative POSIX strings in reports; original absolute input-root paths are omitted. Stored dependency strings remain visible so users can repair a refused source deliberately.

The input graph contains files and HDF5 objects. Hard-linked object identities prevent infinite group traversal. Symbolic target resolution tracks the chain separately so legitimate file-graph cycles do not masquerade as unresolved symbolic loops. Every discovered file is scanned in full; raw files are opaque leaves. Errors are collected into a deterministic report rather than discarded as missing data.

`pack` first audits the input. It creates a private sibling staging directory, preserves the root-relative layout below `payload`, copies bytes with bounded buffers, verifies source and copied hashes, and scans the copied tree. It writes the unsigned receipt and instructions, calls recipient verification against staging, and then renames staging into the new destination. Existing outputs are refused. A normally handled failure removes staging and never publishes a successful-looking partial bundle.

`verify` treats the receipt as untrusted structure: size ceiling, duplicate JSON-key detection, schema/profile check, validated relative paths, unique file records, symlink/regular-file checks and exact payload inventory. It hashes every listed file and re-runs dependency discovery from the recorded entry. A receipt cannot silently include arbitrary unrelated files as part of the closure. The receipt is not a signature; self-consistency does not establish authenticity.

## Invariants and acceptance

1. Source HDF5 bytes and metadata never change.
2. Any incomplete metadata traversal is an error.
3. No unsupported source path is intentionally opened.
4. A published bundle's file inventory equals its supported conservative closure.
5. Copy and recipient verification check full-file bytes; neither claims payload decoding.
6. Source relocation/removal cannot influence the copied-tree audit under the literal profile.
7. Raw-storage users receive the working-directory contract in the CLI, README and bundle.

Tests exercise real HDF5 external links, nested VDS, raw segments, filter metadata, link cycles, path boundaries, mutation/manifest failures and actual reading after relocation. Independent agent acceptance tests complement implementation tests. CI builds both distributions and installs the wheel into an isolated environment across the supported OS/Python matrix.

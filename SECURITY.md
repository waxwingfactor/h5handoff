# Security and trust boundaries

h5handoff is for completed, trusted local HDF5 datasets. HDF5 and h5py parse native binary metadata; this tool is not a sandbox for malicious HDF5 files. Run untrusted files in a separate restricted environment with a maintained HDF5 library.

The scanner inspects metadata without decoding dataset values. It resolves supported links explicitly, bounds traversal, rejects symlinks and paths outside the selected root, and does not request dataset decoding or filter-plugin loading. Native HDF5 plugin/connector behavior still depends on the installed runtime and process configuration; this is not a plugin sandbox. It does not intentionally access remote storage. Bundles retain original bytes and may contain sensitive data, metadata and stored path strings; review before publishing.

Inputs and output parent directories must remain quiescent. File metadata and streamed hashes detect many accidental concurrent changes, but they are not an atomic filesystem snapshot and cannot defend against an adversary changing paths concurrently.

The receipt contains SHA-256 hashes for transfer-integrity checking. It is unsigned: an attacker who can replace both the receipt and files can create a consistent replacement. Authenticate your transport or obtain a trusted digest separately.

Report vulnerabilities privately using GitHub's private vulnerability reporting if enabled, or contact the repository owner through an existing trusted channel. Do not post confidential datasets in a public issue.

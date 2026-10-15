# Supported scope and resolution profile

`literal-v1` deliberately defines a narrower, deterministic transfer contract than all of HDF5's resolution options. A successful audit means the metadata-level closure is complete under this profile; it is not a scientific-content or decoder certification.

| Mechanism | Resolution | Check |
| --- | --- | --- |
| External link | Stored filename relative to the containing HDF5 file | File plus target object; recursively scan whole reached file |
| Soft link | Relative to its containing group, or absolute within the same HDF5 namespace | Resolve each path component without automatic external traversal |
| VDS source | Literal filename relative to containing file; `.` means same file | Source object must resolve to a dataset; recursively scan reached file |
| External raw storage | Stored filename relative to the selected root | File, offset/segment metadata; warn on bytes beyond EOF |

Parent directory references may resolve within root. They may never escape it. Any symlink in a checked input path under root, including root itself, is refused. Soft-link cycles without a concrete target fail; legitimate hard-link cycles terminate through object identity tracking. The scanner follows metadata links explicitly and does not ask HDF5 to resolve arbitrary external links.

Absolute filenames, Windows drive/UNC paths, backslashes, URI-like paths, environment expansion and `%` filename patterns are outside this profile. The scanner never searches basename fallbacks, current-directory fallbacks for external links/VDS, prefix environment variables, custom drivers or remote locations. A source that works only because of those features needs a producer-side repair or a different transfer workflow. No source path rewriting is performed.

For raw storage the input root declares the reading working directory, which may differ from the containing HDF5 file's directory. The recipient must change into `bundle/payload` before opening the recorded entry. This preserves default HDF5 raw-file semantics. Prefix environment overrides must be unset. `HDF5_EXTFILE_PREFIX='${ORIGIN}'` expresses a different file-relative contract and is not interpreted by this tool.

The closure is intentionally conservative: reaching one dataset in another HDF5 file scans that entire file's hard-linked object graph. An unrelated dangling link there can block packing. This avoids delivering a partially usable dependency file. Native open failures and traversal limits produce errors rather than an optimistic partial inventory.

Raw external segment extents beyond EOF are not necessarily corrupt: HDF5 may return zero-filled bytes. Such segments are inventoried with a warning; the product cannot infer intended signal content. VDS dataspace mappings may also intentionally leave unmapped or unallocated regions. No selection-overlap, bounds/coverage, scientific correctness, payload checksum decoding or acquisition-completion claim is made.

File names and stored relative layout are preserved. Transfer to an operating system that cannot represent those names is outside the guarantee. Case-colliding file inventories are refused by packing. The transfer directory can be compressed externally, but archive extraction is outside this product.

Limits bound discovered files, metadata objects, link/mapping edges and required directories (each of the latter three uses the max-objects ceiling), not total file bytes, native parser allocations, all CPU time, or hostile native input. Bundling copies and hashes files several times to detect accidental changes and bad copies. Plan disk space for the full closure plus the originals. Inputs and destination parent must be quiescent: the checks are not an atomic snapshot and are not race-proof against a hostile filesystem writer. Interrupted processes may leave a hidden staging directory; a normally handled failure removes it. Inspect such an orphan before deleting it.

Filters are recorded by numeric ID and stored name; no dataset payloads are decoded and no third-party plugins are bundled. `verify` can succeed while a particular reader lacks a decoder. The scanner does not request dataset decoding or filter-plugin loading and does not change the embedding process's plugin settings. Native library behavior depends on the installed HDF5 runtime and process configuration. This is not a plugin sandbox.

`handoff.json` schema version 1 is an unsigned transfer receipt. Verification checks its paths, file records, sizes and hashes and compares a fresh closure with its recorded closure. Someone able to change files and receipt can manufacture a consistent replacement. Authenticate transport or compare a digest received through a trusted channel.

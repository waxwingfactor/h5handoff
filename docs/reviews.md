# Development and independent review record

Date: 2026-10-15. This product was implemented by an AI lead with separate AI subagents for research, scanner implementation, acceptance testing and adversarial review. These are independent reasoning/testing passes within one commission, not human reviews, customer interviews or separate GitHub identities. Main requires a pull request, resolved conversations and passing `quality` CI; GitHub approval count is zero because the authorized maintainer cannot approve its own PR as another person.

## Review C: acceptance and architecture

The independent acceptance tester owns `tests/test_acceptance.py` and `examples/create_fixture.py`, not product code. The tester generated HDF5 data directly and verified real nested external-link, VDS and raw-file reads after deleting the original tree. Tests cover missing source/fill-value masking, cycles, conservative whole-file closure, global limits, source paths and redirects, manifests, copy refusal and CLI workflows.

Findings before merge: lexical normalization hid canceled symlink/missing-directory ancestors; a hard-object ceiling did not bound symbolic-link edges; and canceled directory paths needed a preserved directory skeleton. Those were addressed with literal ancestry checks, incremental bounded link/VDS traversal, required directory inventories and relocation regressions. Windows reparse ancestry checks were added as a further boundary improvement. The reviewer reported no remaining blocking findings for trusted, quiescent `literal-v1` data after retesting.

## Review B: adversarial code and documentation

The code reviewer authored research/positioning documentation, but did not implement product code. The reviewer found report paths that invalidated successful bundles, silently skipped unreadable directories, unsupported plugin-disable claims, omitted raw-segment report fields, and an uncaught report-path preflight exception. The [detailed record](reviews-b.md) distinguishes findings, fixes and retests.

Fixes include canonical report-output exclusions, incremental directory enumeration with propagated errors, accurate native-runtime/plugin limits, reported raw offsets/segment sizes, and clean preflight failures. The reviewer added focused independent regressions in `tests/test_review_regressions.py`.

## Review A: implementation plus separate bundle review

The scanner author owns `scan.py` and scanner fixtures. Their scanner tests are implementation tests, not independent acceptance. In a separate review of the lead-authored bundle/CLI/demo code, the scanner author independently tested clean JSON packing, valid verification, malformed schema and size values, duplicate file records, malformed nested audit fields and extra payload files. All invalid cases were refused. They approved the parent-authored modules with no blocking findings. Optional report-directory preflight was left as a usability improvement; verification warnings are now surfaced in human output.

## Evidence boundary

The test counts and CI results in the PR/release record apply to the exact tested revision. No external adoption, production datasets or scientific decoding certification is claimed. The published acceptance fixtures are synthetic. Native HDF5 is a trusted-file parser, and payloads may require reader-specific compression plugins.

## Final local gate

The reviewed implementation passed **90 tests** and Ruff on macOS arm64. That includes 44 independently authored acceptance cases and 17 independent reviewer regressions plus 9 platform regressions. Final review B records B1–B5 resolved and source fingerprints; review C and the separate parent-module review A reported no remaining blockers. CI and public-artifact verification are separate gates recorded in [release validation](release-validation.md).

## Cross-platform CI findings before merge

The first CI run exposed two platform differences absent from the local3.12 pass. Python3.13+ non-strict path resolution suppresses symlink-loop exceptions, so CLI report preflight now resolves an existing parent strictly. On Windows, path-based stat and handle-based fstat can assign ctime different meanings; cross-method checks now compare file identity, size and mtime, while ctime remains checked between calls of the same kind. Full-file hash checks are retained. The independent acceptance reviewer approved the timestamp patch and added nine deterministic tests for differing-but-stable timestamps, actual metadata changes and identity mismatches. The official behavior is documented in [Python pathlib](https://docs.python.org/3.14/library/pathlib.html#pathlib.Path.resolve) and [CPython issue157671](https://github.com/python/cpython/issues/157671). Actual rerun CI is the platform gate.

## Real public EIGER smoke check

A separate agent tested the public Diamond Light Source Therm_6_1 collection, matching the source record's sizes/checksums and running both NeXus and master entry workflows after hiding the originals. Both passed byte/closure verification and inventoried bitshuffle filter32008. [The record](real-data-check.md) bounds this metadata/transfer test and explicitly excludes detector-image decoding. The final Windows CI rerun also exposed a test-only separator assumption; the independently authored byte-comparison fixture now uses the receipt's specified POSIX path form. No product behavior was relaxed.

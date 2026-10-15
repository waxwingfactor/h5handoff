# Development and independent review record

Date: 2026-10-15. This product was implemented by an AI lead with separate AI subagents for research, scanner implementation, acceptance testing and adversarial review. These are independent reasoning/testing passes within one commission, not human reviews, customer interviews or separate GitHub identities. Main requires a pull request, resolved conversations and passing `quality` CI; GitHub approval count is zero because the authorized maintainer cannot approve its own PR as another person.

## Review C: acceptance and architecture

The independent acceptance tester owns `tests/test_acceptance.py` and `examples/create_fixture.py`, not product code. The tester generated HDF5 data directly and verified real nested external-link, VDS and raw-file reads after deleting the original tree. Tests cover missing source/fill-value masking, cycles, conservative whole-file closure, global limits, source paths and redirects, manifests, copy refusal and CLI workflows.

Findings before merge: lexical normalization hid canceled symlink/missing-directory ancestors; a hard-object ceiling did not bound symbolic-link edges; and canceled directory paths needed a preserved directory skeleton. Those were addressed with literal ancestry checks, incremental bounded link/VDS traversal, required directory inventories and relocation regressions. Windows reparse ancestry checks were added as a further boundary improvement. The reviewer reported no remaining blocking findings for trusted, quiescent `literal-v1` data after retesting.

## Review B: adversarial code and documentation

The code reviewer authored research/positioning documentation, but did not implement product code. The reviewer found report paths that invalidated successful bundles, silently skipped unreadable directories, unsupported plugin-disable claims, omitted raw-segment report fields, and an uncaught report-path preflight exception. The [detailed record](reviews-b.md) distinguishes findings, fixes and retests.

Fixes include canonical report-output exclusions, incremental directory enumeration with propagated errors, accurate native-runtime/plugin limits, reported raw offsets/segment sizes, and clean preflight failures. The reviewer added focused independent regressions in `tests/test_review_regressions.py`.

## Review A: implementation plus separate bundle review

The scanner author owns `scan.py` and scanner fixtures. Their scanner tests are implementation tests, not independent acceptance. A separate review of the lead-authored bundle/CLI code is being completed before merge; its outcome will be recorded here and in the PR.

## Evidence boundary

The test counts and CI results in the PR/release record apply to the exact tested revision. No external adoption, production datasets or scientific decoding certification is claimed. The published acceptance fixtures are synthetic. Native HDF5 is a trusted-file parser, and payloads may require reader-specific compression plugins.

# Positioning and supported usage scenarios

Prepared **2026-10-15**. These are design hypotheses and constructed scenarios, not accounts of customer interviews or adoption. See [the evidence and alternative analysis](research.md).

## Applying Crossing the Chasm selectively

Geoffrey Moore's [own description of Crossing the Chasm](https://geoffreyamoore.com/book/crossing-the-chasm/) emphasizes proof in a specific customer's use case, a focused segment, a compelling reason to act, and a complete solution. His [positioning guidance](https://geoffreyamoore.com/positioning/) connects a small beachhead with whole-product support and clear comparisons. The [book site's executive summary](https://crossingthechasmbymoore.com/book/) likewise describes choosing an urgent segment-specific problem and delivering its whole solution.

We apply those ideas to scope and usability. We do not assert that this small open-source project is a disruptive innovation, has entered a market chasm, has reference customers, or needs a particular revenue or distribution strategy.

## Beachhead and reason to use it

**Target user:** a beamline researcher or data custodian handing one completed local HDF5 master collection to a collaborator or another storage location. They are comfortable using a terminal and want to preserve the acquired files.

**Trigger:** the collection is complete and ready to transfer. The apparent master can refer to other HDF5 files, virtual sources, or external raw storage. The sender needs a defensible file list; the recipient needs to know whether the same supported collection arrived.

**Compelling reason:** discover an incomplete or unsupported handoff while the original data are still available. Missing VDS sources can yield fill values, so opening the master successfully is weak evidence. The product provides a supported dependency closure and a checkable receipt without rewriting the scientific files.

This reason is weaker for a small, self-contained directory whose contents the sender already knows. Ordinary directory copying remains a good answer there.

## Clear alternatives

**Market alternative:** select files manually using facility naming conventions, `h5ls`/`h5dump`, and scripts; copy them with ordinary transfer tools; investigate missing dependencies when the recipient opens the data. This is often adequate, especially for simple EIGER layouts. h5handoff supplies the dependency decision and receipt for the bounded cases where that manual assembly is uncertain.

**Product alternative:** `h5repack --merge` when the objective is to incorporate externally linked data into a rewritten HDF5 file. h5handoff instead preserves the original files and layout. For the narrower task of checking VDS source access, the existing hdf5-vds-check is a direct alternative and should be considered.

## Two-sentence positioning statement

For beamline researchers and data custodians dissatisfied with manually assembling the files behind a completed local HDF5 master dataset, **h5handoff is an open-source handoff CLI that discovers its supported file dependencies and creates a byte-preserving, verifiable bundle**. Unlike merging the collection with h5repack, h5handoff retains the original files and relative layout and provides explicit refusal diagnostics, per-file hashes, recipient verification, examples, and instructions for the required raw-storage working directory.

This follows the requested target/dissatisfaction/category/capability/alternative/whole-product structure. It is our wording, not a quotation attributed to Moore.

## Constructed scenarios

### 1. A collaborator receives one completed collection

A researcher has finished acquisition. The chosen master and its relative dependencies are all under a declared project root. They inspect the audit, create a bundle, and transfer that directory using their existing file-transfer method. The recipient verifies its hashes and dependency closure before running their usual analysis software.

Success means the bundle contains the required supported files with the same bytes, and its checks pass after relocation. It does not mean the recipient has installed a detector compression plugin or validated the experiment.

### 2. A transfer would omit a dependency

A master contains a VDS mapping or ExternalLink whose named file is absent. The sender sees the specific referencing file, HDF5 object, and stored target in the audit. Packing refuses to produce a successful handoff. The sender restores the file from the acquisition location, then audits again.

Success means an incomplete supported closure cannot be mistaken for a completed bundle. The tool does not fill gaps, alter references, or infer which unrelated replacement file was intended.

### 3. A recipient detects changed or missing bytes

A recipient copies the bundle to a local disk. A file was truncated or subsequently edited. Verification fails against the manifest and identifies the changed file. The parties retransfer from a trusted source and verify again.

Success means detecting change relative to the receipt. The manifest is not a digital signature; replacing both a file and its manifest is outside that integrity promise.

### 4. A collection uses an unsupported path policy

A completed collection refers to an absolute acquisition-server path, a source outside the selected root, a symlink, or a generated VDS filename pattern. The audit reports the unsupported dependency and packing stops. The custodian uses their facility's supported export or merging procedure, or reorganizes a derived copy with appropriate domain tools, before choosing a new handoff.

Success means a clear refusal without modifying the original dataset. The product's supported scope does not expand merely because a particular HDF5 reader can resolve a reference through environment settings.

## The whole product for this scope

| User need | Required product element |
| --- | --- |
| Know which files are involved | Recursive supported dependency audit, paths and origins in a machine-readable report. |
| Understand an incomplete or unsupported collection | Specific diagnostics and documented refusal rules. |
| Preserve acquired files | A bundle that copies whole dependency files and retains bytes and relative layout. |
| Check the recipient's copy | A manifest with file sizes and hashes, plus a verification command that checks supported closure again. |
| Use it without reverse engineering | Installation instructions, a generated example, command help, raw-storage working-directory guidance, and realistic limitations. |
| Decide whether a different tool fits better | Explicit comparisons with directory transfer, VDS-only checks, and h5repack merging. |

Dependencies outside HDF5's supported reference mechanisms, acquisition still in progress, arbitrary external prefixes, remote storage, content decoding, compression-plugin installation, scientific correctness, and universal reader compatibility are outside this whole-product promise. A complete product can have a small explicit scope.

## Validation before broader claims

The release must demonstrate a clean installation, examples run from a relocated copy, detection of omitted or changed files, bounded refusal behavior, and independently reviewed acceptance tests. Those checks establish software behavior. Future real-user observation would be needed to establish the proposed beachhead's demand or time savings.

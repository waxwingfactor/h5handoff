# Evidence and competitive research

Research date: **2026-10-15**. This is a bounded product-selection record, not a claim that no similar software exists. Sources below are primary project documentation, source repositories, facility instructions, and first-person problem reports. We did not conduct interviews or measure adoption, willingness to install, or the frequency of failed transfers.

## Selected problem

A completed beamline data collection can appear to be one HDF5 master file while its data live in other files. Before sending one collection to a collaborator, its custodian needs to identify the required files, catch unsupported or missing dependencies, copy the supported collection without rewriting it, and let the recipient check what arrived.

The narrow initial audience is a researcher or data manager transferring a **completed local beamline master dataset**. The proposed workflow handles dependency metadata and file integrity. It does not certify scientific results, detector metadata correctness, decoded images, or compatibility with every analysis program.

### Documented facts

| Primary source | Relevant evidence | Boundary of the evidence |
| --- | --- | --- |
| [SPring-8 EIGER data and processing instructions](https://github.com/keitaroyam/yamtbx/blob/master/doc/eiger-en.md) | EIGER collections have master and data files; the master uses HDF5 ExternalLinks. The instructions also explain that nonstandard compression requires a plugin. | Establishes a real multi-file acquisition workflow and a separate decoding dependency; it does not establish demand for h5handoff. |
| [Diamond Eiger2 detector manual](https://www.diamond.ac.uk/Instruments/Mx/I04/I04-Manual/Eiger2-Detectors.html) | Documents a facility-specific collection containing NeXus, master, frame, and metadata files, and instructions for processing at home. | This is one facility's workflow, not a universal EIGER layout. |
| [XDS Eiger troubleshooting](https://wiki.uni-konstanz.de/xds/index.php/Eiger) | Warns that moving or renaming data files can break the master's references. | Keeping the known files together already works for simple collections. |
| [HDF Group VDS introduction](https://support.hdfgroup.org/documentation/hdf5/latest/_v_d_s_t_n.html) | A virtual dataset can refer to other source files; unavailable source regions can return fill values. | Reading a VDS successfully is insufficient proof that its sources arrived. |
| [VDS relocation problem report](https://forum.hdfgroup.org/t/updating-source-location-of-virtual-dataset/11912) | A user describes source-location changes breaking a VDS and asks about remapping or materializing it. | One first-person report; not a prevalence estimate. |
| [Dedalus changes from version 2](https://dedalus-project.readthedocs.io/en/latest/pages/changes_from_v2.html) | Explains that virtual analysis files hold references and relocation requires copying the process files too. | Corroborates the issue outside beamlines; broader simulation support is not the initial positioning. |
| [HDF5 dataset access properties](https://support.hdfgroup.org/documentation/hdf5/latest/group___d_a_p_l.html) | External raw-storage paths use the reader's working directory by default; a runtime prefix can change this, and an environment prefix overrides the property list. | File layout alone cannot guarantee arbitrary-working-directory access. |

The inferred opportunity is that a small CLI can combine these concerns into a reviewable handoff. That inference remains unvalidated with users. No customer quotes, testimonials, or deployment claims are implied by the constructed scenarios in [positioning.md](positioning.md).

## Three independent neglect checks

1. **Problem and adjacent-project discovery.** One agent searched data-validation and scientific-transfer workflows, then checked HDF5 native tools, hdfmap, and hdf5-vds-check. This rejected a VDS-only detector as an original product idea.
2. **Adversarial alternative search.** A second agent independently searched combinations including `HDF5 bundle external links tool`, `HDF5 dependencies copy VDS tool`, `HDF5 external links relocation tool`, and `HDF5 dependency closure`. It checked facility instructions, copying/materialization alternatives, and the external-raw working-directory behavior.
3. **Independent broad search and synthesis.** The lead agent searched web and GitHub alternatives separately and compared the proposed complete handoff with native inspection, merging, and ordinary file transfer. The result was restricted to explicit local paths and a recipient verification workflow.

These are separate research passes by AI agents in this commission, not three independent customer studies. Search results can miss tools. Feature claims below concern the linked documentation and source reviewed on the research date; an undocumented capability is described as unestablished, rather than impossible.

## Native tools and alternatives

| Alternative | What it already does well | Comparison with the selected workflow |
| --- | --- | --- |
| [h5ls](https://support.hdfgroup.org/documentation/hdf5/latest/_h5_t_o_o_l__l_s__u_g.html) | Recurses while avoiding cycles. `--follow-symlinks --no-dangling-links` treats unresolved soft/external links as errors. | Appropriate for link checks. Its documented commands do not assemble a byte-preserving dependency bundle with per-file hashes and recipient verification. A claim that native tools cannot find dangling links would be false. |
| [h5dump and VDS tooling](https://support.hdfgroup.org/documentation/hdf5/latest/_v_d_s_t_n.html) | Displays the HDF5 structure and virtual mappings. | Useful inspection primitives. A user still has to interpret paths and implement collection, copying, and verification. |
| [European XFEL hdf5-vds-check](https://github.com/European-XFEL/hdf5-vds-check) | Dedicated installable CLI for inaccessible VDS sources, with a nonzero failure status. | Directly solves VDS source-access checking. The reviewed project does not offer a preserved-file handoff covering external links and raw storage. h5handoff must earn its place through the complete transfer workflow, not a new VDS check. |
| [h5repack](https://portal.hdfgroup.org/documentation/hdf5/latest/_h5_t_o_o_l__r_p__u_g.html) | `--merge` follows external links recursively and incorporates their data; layout and filters can also be changed. | Prefer it when a rewritten, merged HDF5 file is the desired result. h5handoff retains the original files, bytes, and relative layout instead. |
| [hdfmap](https://github.com/DiamondLightSource/hdfmap) | Provides HDF5/NeXus access and metadata utilities, including `hdf_linked_files` for filenames stored in ExternalLinks. | An external-link inventory already exists. The reviewed interface does not establish recursive closure across all three supported mechanisms, a file bundle, and a recipient verification command. |
| [PyNWB export](https://pynwb.readthedocs.io/en/stable/tutorials/advanced_io/plot_linking_data.html) | Offers an NWB-specific export that resolves external links into one file for sharing. | A good existing solution for users wanting that NWB transformation. It changes the storage representation and is not the selected byte-preserving beamline workflow. |
| Ordinary directory copy, archive, or `rsync` | Efficiently transfers a directory or known file list, with mature transfer and integrity options. | Prefer this when the complete file list is already known and contained in one small directory. h5handoff adds value when one entry file's declared dependencies must be selected and checked before copying; it does not replace a network-transfer service. |

The bounded gap found was **dependency discovery plus safe collection plus post-transfer verification of unchanged files**, for an explicitly supported local profile. We did not find a mature set of products documenting that entire workflow. Metadata inventory alone, a checksum manifest alone, and a missing-VDS detector alone would each be weak differentiation.

## Scope consequences

- The input is a completed, trusted, local single-file HDF5 entry file under a user-declared root. Dependencies are recursively collected as whole files; unrelated content inside a required dependency file is consequently included.
- The supported dependency mechanisms are ExternalLinks, literal VDS source filenames, and external raw-storage filenames. This is not discovery of arbitrary filenames stored in attributes, strings, analysis configuration, or custom application conventions.
- ExternalLinks and VDS references follow the documented supported relative-file contract. Relative raw-storage names are interpreted from the declared root, which becomes the bundle payload working directory. The recipient must use that working directory for raw data, unless their reader deliberately supplies a compatible prefix.
- Environment-prefix searches are not used to find hidden dependencies. Absolute paths, foreign path forms, unsupported filename patterns, paths escaping the root, and symlinks prevent packing. Refusal is safer than silently shipping an incomplete collection or rewriting its references.
- A bundle preserves HDF5 and raw-file bytes and contains a manifest. Verification checks file integrity and repeats supported dependency checks. Hashes detect change relative to the manifest; they do not authenticate the sender or prove that the source collection was scientifically correct.
- Full-file hashing and copying require disk space and I/O proportional to the closure. Acquisition must be finished. Compression plugins, reader configuration, analysis code, and scientific validation remain separate responsibilities.

The [external-raw path discussion](https://forum.hdfgroup.org/t/external-datasets-relative-to-current-directory-or-hdf5-file-as-documented/9742) was particularly important: older documentation had described a different default. The current authoritative access-property documentation, rather than that obsolete assumption, determines this project's contract.

## Rejected and deferred candidates

| Candidate | Reason it was not selected | Evidence checked |
| --- | --- | --- |
| BagIt validation or bulk packaging | Mature implementations already create and validate bags. A nicer error report alone was insufficient grounds for a new whole product. | [Library of Congress bagit-python](https://github.com/LibraryOfCongress/bagit-python), [AMIA grabbags](https://github.com/amiaopensource/grabbags), [bagging](https://github.com/jscancella/bagging). |
| QGIS project handoff | Existing consolidation plugins already copy rasters, export vectors, create a project, and offer ZIP packaging. We did not establish a sufficiently distinct unsolved workflow. | [QConsolidate3 plugin listing](https://plugins.qgis.org/plugins/qconsolidate3/). |
| OME-TIFF portability or validation | Established microscopy readers and conversion tools already handle substantial format metadata and multi-file behavior. The initial search did not establish a sharply bounded gap deserving a competing product. | [OME source examples and Bio-Formats guidance](https://github.com/ome/ome-model-documentation/blob/main/ome-tiff/code.rst), [tifffile change history](https://github.com/cgohlke/tifffile/blob/master/CHANGES.rst). |
| VDS-only missing-source checker | An exact, maintained alternative exists. | [hdf5-vds-check](https://github.com/European-XFEL/hdf5-vds-check). |
| Generic tabular/schema preflight | Existing tooling supports a much larger mature validation workflow. | [Frictionless Python](https://github.com/frictionlessdata/frictionless-py). |
| Calendar recurrence-aware diff | An existing project explicitly offers parsing, validation, diffing, and recurrence expansion. | [ics-suite](https://github.com/asouqi/ics-suite). |
| JATS article package completeness | Existing publisher and indexing pipelines already check missing referenced assets; a generic package checker was not clearly neglected. | [Taylor & Francis JATS validator](https://jats.taylorandfrancis.com/tfjats/validation/), [SciELO markup reports](https://docs.scielo.org/projects/scielo-pc-programs/en/latest/markup_reports.html). |
| KiCad project and 3D-model handoff | An upstream request alone would have overstated neglect: independent plugins already collect and rewrite model references. | [Archive3DModels](https://github.com/MitjaNemec/Archive3DModels), [kicad-archive-project](https://github.com/esynr3z/kicad-archive-project). |
| SWMM model input handoff | Missing inputs are documented, but PCSWMM already has project packaging that collects auxiliary files. Open-source availability alone did not justify calling the workflow unsolved. | [Missing input files report](https://www.openswmm.org/Topic/19194/missing-input-files), [PCSWMM's official update history](https://www.pcswmm.com/Downloads/PCSWMM). |

## What would change this decision

An existing tool providing the same bounded discover/pack/verify workflow would narrow or remove the differentiation claim. Evidence that facility users consistently prefer copying the whole visit directory would weaken the beachhead. Real user feedback may favor another supported path policy or a smaller scope; until then, this release offers a concrete inspectable workflow without claiming established demand.

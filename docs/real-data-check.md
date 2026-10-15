# Real EIGER metadata handoff check

Run date: 2026-10-15. This was an independent real-data smoke check, not a customer deployment or scientific validation. No product files were edited.

## Source and download limits

Source: Graeme Winter, Diamond Light Source, **Small example Eiger 2X 16M data set from Diamond Light Source I04**, DOI [10.5281/zenodo.3385862](https://doi.org/10.5281/zenodo.3385862). [Source record](https://zenodo.org/records/3385862); [machine-readable metadata](https://zenodo.org/api/records/3385862). The record declares CC-BY-4.0 and describes the collection as routine-test thaumatin-crystal data intended to help software testing.

Only the following four files were downloaded. Their combined size was **18,866,925 bytes**, below the 25 MB download ceiling. Each curl download had an exact declared-size cap. No Therm_6_2 files were downloaded. The scientific files and their test bundles were not redistributed with this software.

| File | Bytes | Zenodo MD5 | Local verification |
|---|---:|---|---|
| Therm_6_1.nxs | 55,664 | 86efc18b9f9cb49bb04a858ace419282 | exact size and MD5 match |
| Therm_6_1_master.h5 | 49,528 | 5de71f036460cdbaea715517d5c04698 | exact size and MD5 match |
| Therm_6_1_meta.h5 | 104,740 | f4b94077926dabcfb4088e60c0ea0bdf | exact size and MD5 match |
| Therm_6_1_000001.h5 | 18,656,993 | a490695717f3bcf9a6d8666553bfebf1 | exact size and MD5 match |

MD5 was checked against the source record to confirm download identity; h5handoff itself uses SHA-256 receipts. This manually downloaded dataset is not a network dependency of the automated tests.

## Actual dependency structure and results

Release-candidate source was imported using its Python 3.12.13 environment, with h5py 3.16.0, HDF5 2.0.0 and NumPy 2.5.4, on macOS Apple Silicon.

Two entry workflows were tested independently:

1. `Therm_6_1.nxs`: audit succeeded without issues. Its VDS at `/entry/data/data` uses same-file source `.` targeting `/entry/data/data_000001`; that object is an external link into `Therm_6_1_000001.h5:/data`. The discovered file closure contains exactly the NeXus entry file and the 18.7 MB detector file.
2. `Therm_6_1_master.h5`: audit succeeded without issues. Its `/entry/data/data_000001` external link targets the same detector file. The discovered closure contains exactly the master and detector files.

Both workflows successfully completed `pack`, the packer's internal staged verification, and an explicit subsequent `verify`. The input directory was then renamed to `real-eiger-originals-hidden`, ensuring the original source path did not exist. Both copied bundles passed explicit verification again. The original input directory was restored in a `finally` block.

The extra metadata file is not a declared dependency reachable from either tested entry under literal-v1, so the tool correctly omitted it. Likewise the alternate master/NeXus entry is not silently added merely because it occupies the same directory.

## Filter metadata and hashes

Both audits inventoried filter **32008**, with stored name identifying [bitshuffle](https://github.com/kiyo-masui/bitshuffle), on detector dataset `/data`. No filter plugin was installed for this experiment, and no dataset values were requested or decoded. Files were streamed as opaque bytes for checksum and bundle verification.

| File in a tested closure | SHA-256 from successful bundle |
|---|---|
| Therm_6_1.nxs | 10829f7dfb35e44480cf57f5922c5222f784493e8ebf2d9720185018c357a6d7 |
| Therm_6_1_master.h5 | fc5d9d12ccaff0801fa8cdc20793b3bdee5e5aa4973be8c61240eae56158c104 |
| Therm_6_1_000001.h5 | e4fea221e51412591cd2df5b098d8480d65b94f0982b176d3f28bc78df59d59e |

The tested software was the reviewed release-candidate source; published-artifact installation is a separate gate in [release validation](release-validation.md).

## Practical limits

This check establishes that two small real detector entry layouts work through metadata closure, byte-preserving packing, relocation away from the original path, and receipt verification. The NeXus workflow exercises a real same-file VDS source resolving through an external-link object. It does not establish detector-image readability without filter 32008, scientific correctness, acquisition completeness, VDS coverage, raw-external-storage behavior (covered by synthetic tests), support for every EIGER layout, or performance on large acquisition runs. No images were decoded or visually assessed. The unsigned receipt still establishes consistency rather than authenticity.

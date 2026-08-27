# Changelog

## v1.9.2 — 2026-08-27

- Fixed false AAC-profile failures on very high bitrate x265 CRF 8 outputs.
- Increased FFprobe's validation probe budget so it can reach the first AAC packet when a large initial HEVC access unit exceeds the default 5 MiB limit.
- Kept all existing AAC-LC semantic, packet timing and packet payload checks unchanged; this does not relax output validation.

## v1.9.1 — 2026-08-27

- Fixed a crash when a dragged folder or malformed MP4 produced unavailable numeric inspection fields.
- Added first-level MP4 expansion when a folder is dragged or selected; generated archive outputs and non-MP4 items are ignored.
- Limited input inspection to two concurrent workers so large folder drops cannot launch an unbounded number of FFmpeg processes.
- Added safe unknown-value rendering throughout the file summary and detail views.

## v1.9 — 2026-08-26

- Replaced the single-reference byte fingerprint with a bounded semantic allowlist covering the 86 inspected Vivo X200 Ultra files: 1080p30 SDR, 4K60 SDR and 4K60 HLG/Dolby Vision 8.4.
- Added adaptive Main/Main10, 8/10-bit, BT.709/BT.2020 HLG, 30/60 fps and conditional Dolby Vision conversion paths.
- Accepted verified 0°, 90°, 180° and 270° display matrices, missing GPS, multiple HEVC levels, MP4 fast-start layouts and Vivo UUID field variants.
- Added a metadata safety ledger. Independent unknown UUID/`udta`/movie metadata is preserved opaquely and verified byte-for-byte; unprovable structures remain rejected.
- Replaced whole-file media handling with streaming NAL, AAC, EIS, `mdat`, hash and output operations for multi-gigabyte inputs.
- Expanded independent output verification with adaptive video semantics, complete-NAL temporal scan, conditional Dolby Vision checks, native-domain PSNR/SSIM sampling, provenance re-hashing and filesystem timestamp checks.
- Added negative validation tests that deliberately corrupt UUID, display matrix, AAC, EIS and temporal-id data and require the validator to reject every copy.
- Updated the GUI with archive classification, rotation, missing-field handling and a visible metadata preservation ledger.

## v1.8 — 2026-08-21

- Added a native AppKit drag-and-drop GUI with multi-file queueing and detailed input information.
- Added a strict reference-profile gate for the validated Vivo X200 Ultra MP4 structure.
- Added x265 CRF 8 archival mode and experimental VideoToolbox Q65 mode.
- Preserved original AAC and EIS packets, Dolby Vision RPU/`dvvC`, display matrix, PTS, GPS, timestamps and Vivo metadata.
- Added per-file post-conversion verification before an output receives its final filename.
- Added source SHA-256 and conversion provenance to every output.
- Added dependency preflight and `install_dependencies.command`.
- Fixed lost display rotation, lost Dolby Vision container signalling, changed track language codes and a video media-duration mismatch.
- Added reproducible source build and public dependency/licensing documentation.

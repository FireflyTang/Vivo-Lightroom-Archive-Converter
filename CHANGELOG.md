# Changelog

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

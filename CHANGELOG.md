# Changelog

All notable project changes should be recorded here.

## 2026-05-20

### Fixed

- Restored the replay rendering CLI by updating `tools/replay.py` to use the current visualization pipeline.
- Made `tools/viz.py` fail clearly when a replay contains no usable frames.

### Added

- Added `--show-orbits` support to the current HTML/SVG replay renderer.
- Added replay player-name labels via `--names`, so colour-coded players can be mapped to strategy names.
- Added visualization smoke tests for orbit guides, the replay CLI, and empty replay failures.

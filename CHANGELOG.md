# Changelog

All notable project changes should be recorded here.

## 2026-05-26

### Added

- Added `tools/search_params.py` for YAML-based parameter search over strategy presets.
- Added `search_spaces/ow_proto_core.yaml` as a starter search space for `preset:ow_proto`.
- Added `search_spaces/peaking_core.yaml` as a starter search space for `preset:peaking`.
- Added smoke tests and a `make test-search` shortcut for the parameter-search workflow.

## 2026-05-20

### Fixed

- Restored the replay rendering CLI by updating `tools/replay.py` to use the current visualization pipeline.
- Made `tools/viz.py` fail clearly when a replay contains no usable frames.

### Added

- Added `--show-orbits` support to the current HTML/SVG replay renderer.
- Added replay player-name labels via `--names`, so colour-coded players can be mapped to strategy names.
- Added visualization smoke tests for orbit guides, the replay CLI, and empty replay failures.

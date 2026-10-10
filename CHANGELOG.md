# Changelog

## 0.2.0 (unreleased, tag is the maintainer's step)

### Package
- JSON schemas ship as package data (`spritemotion.schemas`) with `version()`, `path()` and `load_file()`. The package
  has no required dependencies; numpy and Pillow are the `imaging` extra (#23).
- Fit rules live in the package: `spritemotion.fit_rules` (Python) and `spritemotion/web/fit-rules.mjs` (JavaScript),
  one source each, with a parity test. `tools/fit-lab/fit_rules.py` is a shim that also works inside Blender (#28).

### Transfer artifact
- New schema `spritemotion.transfer-artifact` v1 and a stdlib-only reader, `spritemotion.transfer` (#24). It rejects
  absolute and `..` paths, missing files, sha256 mismatches and a wrong mirror map; it resolves mirrored facings 5-7 and
  gives `centre = (128 - left, 192 - bottom)`. A synthetic fixture is committed under `tests/fixtures/transfer/`.
- `tools/transfer-export/run.py` turns a finished `tools/uo-content` job into a transfer artifact and fails unless the
  reader accepts the result (#25).

### Fit Lab
- The poke metric models the 1 cm holdout margin, the push-out upper bound and the occlusion modes; push-out is decided
  from the mapping part's `studio_part`, as the renderer does (#21, SM-16a).
- Portability fixes for issues #5-#12: Blender discovery, fonts and paths no longer assume one machine (#18).

### Canonical body
- Vendors Levy's UO_Model3D at upstream e9544f6 (was 3eaae69): 54-bone symmetric rig (no twist, toe, skirt or cloak
  chains), action 17 arm fix, narrower shoulders. `blender_build.py` checks the bones it needs by name instead of a bone
  count. Mappings use `foot.L/R` where they used `toe.L/R` (#27). Client data is not vendored.

### Launchers
- Every `.bat` has a one-sentence description, calls `_shared/common.bat` and has a `.sh` twin; new `dev/` launchers
  for the gates (#26).

### Upgrading from 0.1.0
- A saved fit or mapping that targets `toe.*`, `upper_arm_twist.*` or `forearm_twist.*` must point at `foot.*` and the
  main arm bones. Rebuild items on the new body.
- Schemas moved from the repo-root `schemas/` to `common/schemas/`; load them with `spritemotion.schemas`.

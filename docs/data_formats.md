# Data formats

Every JSON data contract SpriteMotion reads or writes has a schema in `common/schemas/` (shipped as package data,
`spritemotion.schemas`). This page is the index: one row per schema file, with its document id, version, who owns
the format and what reads it. Extend the schema and this page before emitting a new field.

`tests/unit/test_data_formats.py` fails if a schema file has no row here, a row names a missing file, or a version
here differs from the schema's `schema_version`.

Format documents with prose: [annotation-format.md](annotation-format.md) (dataset, skeleton, annotations, game),
[transfer-artifact.md](transfer-artifact.md) (the export another tool imports). Service endpoints that carry
these documents are in [fit-lab-service.md](fit-lab-service.md).

"Version" is the schema's `schema_version` constant. Schemas marked `none` are local state files that have no
`schema` or `schema_version` field; they are checked by the schema alone, and a change to them is a change to the
file listed as owner.

## Schemas

| Schema file | Document id | Version | Owner | Reader |
|---|---|---|---|---|
| `asset-pack.schema.json` | `spritemotion.asset-pack` | 1 | `games/<game>/asset-packs/`, [asset-packs.md](asset-packs.md) | `tools/uo-content/pack_fit.py`, `common/pipeline/status.py` |
| `equipment-slots.schema.json` | `spritemotion.equipment-slots` | 1 | `games/<game>/equipment/layers.json` | `common/pipeline/status.py` |
| `fit-adjustments.schema.json` | none | none | `tools/fit-lab/adjustments.py` (`lab-adjustments.json` and its backups) | Fit Lab server, `tools/uo-content/fit_runtime.py`, `rebuild.py` |
| `fit-build.schema.json` | none | none | `tools/uo-content/pipeline.py` (fit-aware build settings) | `tools/uo-content/rebuild.py`, `tools/uo-content/blender_build.py` |
| `fit-head-ab.schema.json` | none | none | `tools/fit-lab/web/lab.js` (head A/B report) | Fit Lab web UI |
| `fit-lab-build.schema.json` | none | none | `tools/fit-lab/builds.py` (`/api/build`) | Fit Lab server, `tools/fit-lab/web/render-panel.js` |
| `fit-lab-service.schema.json` | `spritemotion.fit-lab-service` | 1 | `tools/fit-lab/service.py`, [fit-lab-service.md](fit-lab-service.md) | `tools/workbench/run.py` |
| `fit-lab-view.schema.json` | `spritemotion.fit-lab-view` | 1 | `tools/fit-lab/web/outfit.mjs` (browser localStorage) | `tools/fit-lab/web/outfit.mjs` |
| `fit-reference.schema.json` | none | none | `tools/fit-lab/reference.py` (`reference.json`) | `tools/fit-lab/web/lab.js` |
| `game.schema.json` | `spritemotion.game` | 1 | `games/<game>/game.json` | `common/pipeline/games.py`, `common/pipeline/status.py` |
| `pose-annotations.schema.json` | `spritemotion.pose-annotations` | 1 | `common/poses/annotations.py` | same module, `tools/silhouette-fit/run.py` |
| `skeleton.schema.json` | `spritemotion.skeleton` | 1 | `games/<game>/` skeleton files | `common/poses/skeleton.py` (`Skeleton.load`) |
| `sprite-sequence.schema.json` | `spritemotion.dataset` | 1 | game adapters (`games/<game>/extraction/`) | `common/sprites/dataset.py` |
| `starter-catalog.schema.json` | `spritemotion.starter-catalog` | 1 | `examples/cc0-starter/catalog.json` | `tools/uo-content/starters.py`, `tools/starter-assets/run.py` |
| `transfer-artifact.schema.json` | `spritemotion.transfer-artifact` | 1 | `tools/transfer-export/run.py`, [transfer-artifact.md](transfer-artifact.md) | `spritemotion.transfer` (`common/transfer.py`) |

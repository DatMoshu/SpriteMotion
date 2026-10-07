# Transfer artifact

A transfer artifact is a finished SpriteMotion export in a form another tool can import without knowing
SpriteMotion's folder layout. It is one directory: a manifest, `transfer.json`, and the PNG files it lists.
The contract comes from the "Transfer artifact" and "Pixel contract" paragraphs of
[guo-integration-plan.md](guo-integration-plan.md). This page covers the format and the reader.

The schema is [`common/schemas/transfer-artifact.schema.json`](../common/schemas/transfer-artifact.schema.json)
(kind `spritemotion.transfer-artifact`, `schema_version` 1). **Status: draft for GUO review.** The exporter that
writes it from a `tools/uo-content` build job is described under [Making one](#making-one).

## What is in the manifest

| Section | Holds | Required |
|---|---|---|
| `identity` | project id, item id, logical equipment slot; optionally source job, source revision, body profile | project, item, slot |
| `reproducibility` | model and renderer fingerprints, input hashes, a fit snapshot file (path + sha256) and its hash, tool versions | all optional |
| `animation` | `mirror_map`, `coverage` (`preview`, `current-action` or `full`), optional Blender `sampling`, and `actions` | map, coverage, actions |
| `pixels` | canvas, anchor, alpha convention, quantization policy | all |
| `frames` | one entry per stored frame | at least one |
| `equipment` | layer, item art file, declared male/female paperdoll support, tiledata, notes | all optional |
| `acceptance` | manual review status, validation report file, known failures, client/shard compatibility | manual review |
| `provenance` | `source` and `rendered`, each with its own redistribution class, licence and attribution | both sides |

Optional means optional: nothing is filled in to look complete. An absent `paperdoll` entry means the export
declares nothing about it.

### Pixels

- Canvas is 256 x 256 and the anchor is (128, 192). The schema and the reader accept no other values.
- A frame's `crop` is `left, top, right, bottom` on the canvas (left and top inclusive, right and bottom exclusive).
  Its PNG holds only the cropped pixels, so the PNG size must equal `(right - left, bottom - top)`.
- The centre is `(128 - left, 192 - bottom)`. Either value can be negative. A frame may state it as `centre`; the
  reader checks the stated value against the crop.
- An empty frame has `"empty": true` and no `png`, `sha256`, `crop` or `centre`. It still counts as a frame.
- `alpha` says how the PNG alpha is meant to be read; `quantization` says whether a palette was applied
  (`none`, or `per-animation-group` with a `palette_size`).
- An animation group is one (action, stored direction). `per-animation-group` means one palette of at most 256 colours
  per (action, stored direction), which is what anim.mul stores per entry, so GUO encodes without requantizing.
- GUO stores 15-bit colour with 1-bit transparency, so `alpha: binary` imports losslessly; straight and premultiplied
  alpha are thresholded.

### Directions and mirroring

Only directions 0-4 are stored. Directions 5, 6 and 7 are the horizontal mirror of 3, 2 and 1. The manifest
spells this out as `mirror_map` and the reader accepts exactly `{"5": 3, "6": 2, "7": 1}`. The map says nothing
about which compass facing a number means; it is the UO stored-direction convention, not the legacy outfit atlas's.

A mirrored frame is the stored frame flipped about the anchor column (x = 128), so its crop becomes
`(256 - right, top, 256 - left, bottom)` and its centre x becomes `right - 128`. `ResolvedFrame.crop` and
`.centre` return those values.

### Equipment tiledata

`equipment.tiledata` holds exactly GUO's `tiledata-item` keys: `flags`, `weight`, `layer`, `count`, `hue`, `light`,
`height`, `name`, and nothing else (no `anim`: GUO assigns it). The numbers are non-negative integers, `layer` is 1-25
and `name` is a string. `flags` is an integer bit field, not a list of names: it is what the tiledata file stores, so
no name table has to be kept in step. If `equipment.layer` and `equipment.tiledata.layer` are both present they must
be equal; the reader raises `TransferError` when they differ.

### Timing

`sampling` records which Blender timeline frames were rendered (first frame and step). `playback.frame_delay_ms`
on an action is how fast to play it. They are separate on purpose. `frame_delay_ms` is metadata only: the UO client
fixes the timing.

## Making one

A finished `tools/uo-content` job (status `complete`) becomes a transfer artifact with:

```powershell
python tools/transfer-export/run.py --job <job-dir> --out <new-dir>
```

It needs Pillow (`pip install "spritemotion[imaging]"`); the reader does not. The job folder is only read. `--out`
must be a new or empty folder outside the job; the exporter refuses anything else, and a failed export removes the
folder it created.

For every stored frame in `render/clothing` it crops the PNG to its alpha bounding box on the 256 x 256 canvas and
writes `frames/aNN-dD-fI.png`; a fully transparent frame becomes an `empty` frame with no file. It then writes
`transfer.json` and finishes by calling `spritemotion.transfer.read` on the result: if that fails, the export failed.

What the manifest takes from the job, and what it leaves out:

| Manifest field | From | Notes |
|---|---|---|
| `identity` | `job.json` | item id and slot from `fit_item` (else `name` and `part`), `source_job` is the job folder name, `project_id` is `--project-id` (default `spritemotion`). No `body_profile`: the job does not record one |
| `reproducibility` | `job.json` | `backend_sha256` as `model_fingerprint`, `render_fingerprint`, `asset_sha256` and `source_fingerprints` as `input_hashes` (file names only, no paths). The frozen `fit_adjustments` are written to `fit-adjustments.json` as `fit` and `fit_hash`; absent when the job has none. No `tool_versions` |
| `animation` | `render/clothing/meta.json`, `job.json` | actions, stored directions and frame counts from the rendered blocks; `coverage` is the job's `mode` (`preview` or `full`; a `full` job missing a stored direction is refused); `sampling` is the UO rule, scene frame 1 + 3i. No `playback`: the job records no timing |
| `pixels` | the exported PNGs | `alpha` is `binary` only if every exported alpha is 0 or 255, otherwise `straight`; `quantization` is `none` |
| `equipment` | `job.json` | only a note naming the uo-content part. No `layer` or `tiledata`: the job records neither |
| `acceptance` | `validation.json` | `manual_review` is `none`; the report is copied in as `validation.json`; `known_failures` lists clipped and empty frames the report names |
| `provenance` | `job.json` | source (input file names, input kind) and rendered output (the job, its creation method) are separate. The job records no licence, so both redistribution classes are `unknown` unless you pass `--source-redistribution`, `--rendered-redistribution`, `--source-license` or `--rendered-license` |

Not done by the exporter: palette quantization, VD decoding, and anything GUO-side.

Job renders can include client-derived art, so an export of one is as private as the job. Do not commit or share it.

## Reading it

`spritemotion.transfer` uses the standard library only (no numpy or Pillow), so it works from a plain
`pip install spritemotion`.

```python
from spritemotion import transfer

artifact = transfer.read("path/to/export")        # raises transfer.TransferError on any problem
artifact.identity["item_id"]
artifact.actions                                   # [0, 4]
frame = artifact.frame(4, 3, 2)                    # action, stored direction, index
frame.path, frame.crop, frame.centre
shown = artifact.resolve(4, 6, 2)                  # any facing 0-7; 6 comes from stored direction 2
shown.mirrored, shown.crop, shown.centre
transfer.centre(frame.crop)                        # (128 - left, 192 - bottom)
```

`read` always checks, whether or not `jsonschema` is installed:

- the manifest kind, version, canvas, anchor and mirror map;
- every path is relative, forward-slash, free of `..` and empty segments, and stays inside the directory;
- every listed file exists and matches its sha256 (frames, and the fit snapshot, item art and validation report
  when present);
- each PNG's size from its header matches its crop;
- every action has a frame for every stored direction it lists and every index below `frame_count`, with no
  duplicates and no stored direction above 4.

When `jsonschema` is present the manifest is also validated against the schema. Each failure is a `TransferError`
whose message names the frame or field.

## GUO importer notes

GUO's first importer refuses `coverage: preview` and needs every stored direction 0-4 for each imported action. The
reader stays permissive and accepts both; the importer enforces its own rules.

## Test fixture

`tests/fixtures/transfer/` is a synthetic artifact: no game data, two actions (0 with 2 frames, 4 with 3 frames),
stored directions 0-4, an asymmetric L-shaped sprite, one empty frame (action 4, direction 2, index 1) and one
negative centre (action 4, direction 4, index 0: centre (-22, -12)). Regenerate it with
`python tools/transfer-fixture/run.py`; the output is byte-identical every run and a test checks that the
committed copy matches.

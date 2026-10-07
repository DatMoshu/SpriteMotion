# Fit Lab editor connection, version 1

GUO and the standalone browser connect to one loopback Fit Lab process. Editors first GET `/api/service` and
require `schema: spritemotion.fit-lab-service`, `schema_version: 1` and the configured `pack`. A mismatch is an
error, not permission to start another server on that port. Service discovery contains no machine paths.

| Route | Contract |
|---|---|
| GET `/api/service` | `common/schemas/fit-lab-service.schema.json`; capability and pack negotiation |
| GET `/data/manifest.json` | Available item IDs, slots, actions, GLB paths and camera |
| GET `/api/mapping` | Local pack defaults; never publish this response |
| GET `/api/state` | Adjustment document, opaque revision and saved backups |
| POST `/api/adjustments` | `{adjustments, base_revision}`; 409 preserves a concurrent editor's changes |
| GET `/api/backups/<id>` | A prior document; restoring it is another revision-checked save |
| GET, POST `/api/build` | Build state / `common/schemas/fit-lab-build.schema.json` request |
| GET `/api/renders?item=<id>` | Completed jobs, newest first, with action coverage |
| GET `/builds/<job>/review/manifest.json` | Final sprite sequences, frame counts, playback FPS and anchor |

Start with `python tools/fit-lab/run.py serve --pack <pack> --port <port> --no-browser`. The configured checkout
and Python executable belong in the consuming editor's local settings. Pack exports must already exist. Closing
an editor view detaches from the process; it must not kill shared builds or start duplicate workers after reload.

Native controls and embedded web controls use these same saved documents. GUI undo is distinct from undoing a
published game asset. Preserve unknown adjustment fields, stable item IDs, and all unrelated scoped corrections.
Do not treat a live 3D preview as a final sprite export. Native consumers must preserve nearest-neighbour pixels,
alpha, anchors, action/direction identities and the explicit mirror mapping in the review artifact.

Version 1 does not provide a GUO staging importer, cross-process worker locking, or a native 3D viewport contract.
These remain integration work; service discovery alone does not mean an editor integration is complete.

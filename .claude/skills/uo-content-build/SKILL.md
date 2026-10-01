---
name: uo-content-build
description: Turn a UO item prompt, picture or 3D model into a fitted Blender item, animated sprite frames and VD/client import packages using SpriteMotion's shared v13 model.
---

Use `tools/uo-content/README.md` in the selected SpriteMotion checkout. The canonical model is UO_Model3D v13 from the user's shared main archive; do not substitute SpriteMotion's historical reconstruction or the older v12 mesh. Preserve the source scene and work in a new job.

For a supplied mesh, import through `pipeline.py build --spec <json> --asset <model>`. Prefer packed GLB. Helmets follow head rigidly; weapons use hand.R, shields shield.L. Auto fitting needs review of orientation, grip and silhouette; use Blender rest-pose placement and `fit: preserve` for a precise fit. Never discard animated bone scale or `inherit_scale: NONE` by routing this model through the legacy rotation/translation-only rig exporter.

For a freeform prompt, author geometry in Blender or use available image generation for design artwork, according to the requested result. The studio's text parser only configures templates and must not be described as unrestricted generative AI. For artwork generation, use the imagegen skill when available; retain the prompt, reference and generated file. For a supplied picture, determine whether the user wants surface artwork, a directional redraw, or new geometry. A texture wrapped on a template does not establish the unseen silhouette. Build custom geometry when the requested silhouette requires it; do not silently present a template as a faithful image-to-3D reconstruction.

Create the item asset, then use the deterministic pipeline. Save settings and original design inputs in the job. Preview first, inspect action 0 walk, 4 idle, 9 attack, 22 fall and 25 mounted in all facings. Correct placement or geometry before a full 35-action export. Preserve numeric action IDs, native three-frame timeline spacing, and the renderer's 256×256 canvas / (128,192) anchor. Mirrored facings reflect around x=127.5.

Read `validation.json` and inspect the rendered item over the original body. Full output should contain 175 action/direction blocks, expected frame counts, and pass the independent VD alpha/anchor decode. Resolve clipping; inspect any empty frames in context. Rig projections and generated surfaces are dependent estimates, never approved annotations or independent reconstruction evidence.

Deliver the editable scene, PNG/metadata, review and VD/import package. For game integration, resolve the user's actual client/server, a free animation ID and a separate static graphic ID. Use `equipment.py` to stage verified classic MUL/art/tiledata copies and a cosmetic server class; account for UOP overrides, Body/Equip conversions, paperdoll art and female support. Do not report a live import until files are deployed to the chosen environment and an in-game equip test succeeds. Existing task authorization governs deployment; do not add a second approval ceremony when the destination and action are already authorized.

# Live female pose editor

The active source is now `UO_Female_Fitted.blend`: the user's saved pose edits are baked in, head scale is 1.12, shoulder centers are moved outward 2 cm each, the leg stance is narrowed and knees bend forward with shins back in idle. Thigh/shin lengths remain 46.1/45.3 cm. Albedo and lighting are grayscale. The previous scene and the pre-fit edits snapshot remain available. `scene.json` identifies the source blend so subsequent exports retain these adjustments. The refreshed render review uses the fitted scene too.

Run `launchers/editor/female-live-pose.ps1`, or run `python games/ultima-online/region-masks/pose_editor_server.py` and open `http://127.0.0.1:8768/editor/`. The server binds only to loopback. It uses the existing female locomotion outputs; the paid mesh and textures stay in the ignored workspace.

Drag a wrist square in any of the three panels. The other panels immediately show the same skinned pose. Drag an elbow circle to change the bend while keeping the wrist fixed. Knees and ankles work the same way. The selection menu makes overlapping controls accessible; arrow buttons move the selected control by a sprite pixel and depth buttons move it by 1 cm. Wrist/foot twist buttons rotate by 5 degrees. Fingers keep the supplied closed grip, including the corrected thumbs.

Choose Idle, Walk or Run, a source frame, and one of five stored UO directions. Edits belong to a 3D pose, not to a particular view: inspect another direction to resolve depth ambiguity. The original camera anchor and pixel scale are fixed. Pose controls do not reshape the female's body proportions. Targets beyond a limb's reach are clamped to preserve bone length. Leg edits are not constrained to the floor and there is no self-collision solver.

Each completed gesture auto-saves to `workspace/ultima-online/female-locomotion/editor/edits.json`. Undo, redo and reset frame are available. Download/load edits provide portable JSON snapshots checked against the exact source asset fingerprint. Undo history lasts for the current page session; saved poses survive reloads. This is a single-user local editor; do not edit the same session simultaneously in multiple tabs.

**Export edited Blender scene** writes a separate timestamp-independent job folder under `editor/exports/<job>/`, including the scene, input edits, export log and verification report. The original locomotion blend is preserved. Edits are converted from parent-local skeleton transforms to Blender pose basis keys, with the first frame repeated at the cycle endpoint. Blender interpolates between the source keys. The browser plays the source samples at their clip timing. It uses WebGL lighting for immediate feedback, so its shading differs from the Cycles renders; the exported Blender scene retains the original render setup.

## Rebuild assets

Run Blender on `UO_Female_Idle_Walk_Run.blend` with `--python-exit-code 1 --python tools/blender/export_pose_editor.py`. This exports all 151 bones, rest inverses, ten meshes with original UVs and normals, textures and 21 source poses. Up to eight skin influences are preserved; weights are not reduced to four. Run `tools/blender/verify_pose_editor.py` on the same scene to compare exported skinning against evaluated Blender geometry at every source pose. The initial verification measured a maximum vertex discrepancy of approximately 0.0000011 m.

The renderer uses Three.js 0.180.0 (MIT). Place `build/three.module.js`, `build/three.core.js` and `LICENSE` from that version in `workspace/ultima-online/female-locomotion/editor/vendor/` (license filename `LICENSE.txt`). The current local installation is ready and needs no network access. App source is served directly from `pose_editor.html`, `.css`, and `.js` in `games/ultima-online/region-masks/`.

Export verification checks evaluated joint transforms, including descendants, against the edited poses and verifies cycle closure. It does not certify collision-free poses or foot contact after manual edits.

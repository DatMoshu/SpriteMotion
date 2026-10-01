# Female idle, walk and run from the mask-guided armature

This experiment uses the separately supplied N-hance Stylized Modular Human Female base. The packed base blend and all results live in the ignored `workspace/ultima-online/female-locomotion/` directory. The large paid-art source folder is not copied into the repository.

## Deliverable

`UO_Female_Idle_Walk_Run.blend` contains the original 151-bone rig and three independent Actions:

- `SM_Female_Idle`: holds the single source idle pose for 60 frames.
- `SM_Female_Walk`: 30-frame in-place cycle.
- `SM_Female_Run`: 20-frame in-place cycle, retaining flight phases.

Playback is 30 fps. The default NLA track is a 300-frame review reel: idle (1–60), four walk cycles (61–180), six run cycles (181–300). Press Play in Blender to see the reel. To inspect a single action, mute the NLA review track and select the action in the Action Editor.

All three clips use a UO-style closed grip. Finger joints curl toward the palm in anatomical hand space; the thumb sits outside the fingers and bends down, as requested. The grip is keyed on both hands throughout each clip rather than changing the rest pose. The imported right pinky base is misplaced at the middle finger's second joint; its pose rotation uses a mirrored virtual knuckle pivot to avoid twisting the hand, without changing bind data. A small upper-arm clearance adjustment keeps low fists outside the female thighs.

`SM_Review_Camera` is the lit close-up camera. `SM_UO_Camera` matches the candidate character projection used for reconstruction and has a static body401 idle reference background. That background is an idle reference, not a dynamically switched sprite sequence. The local HTML viewer provides synchronized per-frame/per-view comparisons.

Open `review/index.html` for animated previews, actual retargeted armature overlays and native-camera body401 comparisons. `verification.json` records bind/mesh/weight preservation, loop closure, bone-length checks, floor clearance across every integer animation frame and packed textures.

For interactive posing with immediate 3D feedback and Blender export, see [Live pose editor](live-pose-editor.md). Run `launchers/editor/female-live-pose.ps1` to open it.

## Motion source and limitations

The motion source is the new Astra region-mask armature pass for male body400, actions 4, 0 and 2. Five stored directions jointly estimate each 3D joint; mirrored views are excluded as redundant evidence. A robust weighted least-squares lift and mild cyclic smoothing reduce disagreement between the source views. This reconstructs plausible depth, not verified original 3D motion.

Retargeting follows joint-to-joint vectors rather than FBX bone tails: the imported Unreal-style bone axes do not reliably align with the next anatomical joint. The original female bind pose, mesh vertices and weights remain unchanged. Two-bone leg IK adapts the motion to her limb lengths; a forward knee bend constraint avoids inward knees from changing stance proportions. Thigh accessories follow the thighs while keeping their original bind matrices. Walk/idle are grounded, run keeps flight, and integer-frame interpolation penetrations are corrected if needed.

Timing is authored, not recovered game playback metadata. Idle is a hold, not an invented breathing animation. The female proportions are retained; this is a transfer of body400 motion, not a fitted reconstruction of body401. The body401 silhouette scores are comparison diagnostics only. This is an in-place animation pass; it does not solve locomotion root travel or gameplay foot locking.

## Reproduce

1. Place the packed source blend at `workspace/ultima-online/female-locomotion/source/UOCharacter2_Female_Base.blend`.
2. With Python, NumPy and Pillow, run `games/ultima-online/region-masks/prepare_female_motion.py`. It uses the three new armature JSON files and extracts the body401 reference sprites from `SPRITEMOTION_UO_SOURCE` (or the existing default client path).
3. Run Blender with `--factory-startup`, the source blend, and `--python tools/blender/female_locomotion.py`. Optional arguments after `--`: `--pilot` renders one frame per action; `--no-render` skips images.
4. Run Blender with `--factory-startup --python tools/blender/verify_female_locomotion.py`. It opens the base and result, verifies preservation and animation, corrects small interpolation floor penetrations, saves the result, and exports the actual rig projections.
5. Run `games/ultima-online/region-masks/review_female_motion.py` to build the local review page, GIFs and comparison sheets.

The original source blend, male scenes and Unity project are not edited by this workflow.

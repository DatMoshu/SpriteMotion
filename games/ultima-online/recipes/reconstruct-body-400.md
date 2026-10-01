# Recipe: reconstructing a body-400 action

This recipe applies the general [reconstruction workflow](../../../docs/reconstruction-workflow.md)
to UO. Example: `action-022` (`death_forward`), the one action with approved
poses.

## Inputs

- The extracted dataset: `workspace/ultima-online/body-400` (see [README](../README.md)).
- A rigged humanoid in `workspace/ultima-online/model.blend`. Set
  `SPRITEMOTION_BLEND`.
- A matching rig mapping. Set `SPRITEMOTION_MAPPING`:
  - A generated **Rigify** rig in FK mode: `skeletons/rig-mappings/rigify.json` (A → L)
  - A **Mixamo** skeleton (`mixamorig:*`): `skeletons/rig-mappings/mixamo.json` (A → Right)
  - Anything else: copy one of these and rename the bones.

The rig's rest pose should face −Y (Blender front). If it faces elsewhere,
pass `--model-forward x,y` to `fit`, `apply_solution.py` and
`render_views.py`.

## Steps

```bat
launchers\pipeline\3-fit.bat action-022            :: approved targets only (the six SE poses)
launchers\pipeline\4-key-in-blender.bat action-022 :: keys action fit_action-022, reports reprojection error
launchers\pipeline\5-render-views.bat action-022   :: the 5 stored directions; N/NE/E are compared as flips of W/SW/S
launchers\pipeline\6-compare.bat action-022        :: IoU + contact sheet
```

What to expect with only the SE approvals: SE will match well, and the other
directions may get *worse* ([findings §3](../research/findings.md#3-one-approved-view-does-not-fix-a-3d-pose)).
That tells you to approve a second direction, not that the fit failed.

For a scene that already animates the action (e.g. the pass-2 scene), start
the fit action from that clip so the channels the fit leaves alone (IK/FK
switches, helper bones, morph properties) keep their values:

```sh
blender -b --factory-startup model.blend --python tools/blender/apply_solution.py -- \
    --solution workspace/fits/action-022.json --action fit_action-022 \
    --copy-from UO_400_022_Die_Hard_Back_01 --armature target_character --mapping <mapping> --swap-sides \
    --dataset <dataset> --frame-start 1 --frame-step 4 --save model.blend
```

Checked on the pass-2 scene (2026-09-25): the six SE approvals fit with a mean
of 0.95 px (A → R), the keyed pose reprojects at 0.8–1.2 px on SE, and SE
silhouette overlap is 68%. The other directions are 22–44%, as expected with
one approved view.

## Limb sides for action 22

The approved SE poses were originally fitted with A → right. With the Rigify
mapping (A → L), compare the two assignments:

```sh
python -m spritemotion fit <dataset> --sequence action-022 --rig workspace/fits/rig.json \
    --mapping games/ultima-online/skeletons/rig-mappings/rigify.json --out workspace/fits/a22.json
python -m spritemotion fit <dataset> --sequence action-022 --rig workspace/fits/rig.json \
    --mapping games/ultima-online/skeletons/rig-mappings/rigify.json --swap-sides --out workspace/fits/a22-swapped.json
```

Keep whichever has the lower per-joint errors in its `report`. Pass the same
`--swap-sides` to `apply_solution.py`.

## Trying the candidate camera

```sh
python -m spritemotion fit ... --camera games/ultima-online/profiles/cameras/character-depth-0447.json --out workspace/fits/a22-0447.json
```

Give the same `--camera` to `apply_solution.py` and `render_views.py`, then
compare. Record results, including the ones that got worse, in
[research/findings.md](../research/findings.md).

## Other actions

Other actions have no approved poses yet, so `3-fit.bat action-000` will
find no targets. Either review some poses first
([review-annotations](review-annotations.md)), or seed from the rig
projections to try the pipeline:

```sh
python -m spritemotion fit <dataset> --sequence action-000 ... --targets all --allow-dependent-targets
```

A fit to rig projections only reproduces the rig that made them. It is
useful as a smoke test, and useless as validation.

## Layering equipment and clothing

The client draws equipment as separate animated layers, anchored exactly
like the body. So an item modelled on the reconstructed character and
rendered with the same camera, canvas (256×256, anchor 128,192), directions
and timeline lines up with the body sprite. Render each layer on its own
(`render_views.py --keep-render-settings` with only that object visible).
Converting renders into game files is outside SpriteMotion's scope. Use your
usual UO tooling for that.

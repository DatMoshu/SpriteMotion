# SpriteMotion Sheet Reference (Blender add-on)

`spritemotion_sheet_reference.py` (v0.6.0, Blender 4.2 to 5.x) shows UO
animation frames on a camera-aligned plane in the viewport, next to your
model, so you can pose or check against the sprite. It also renders a rigged
model into UO mobile frames through the SpriteMotion UO camera (see
[UO Frame Render](#uo-frame-render)). Open it from
**View3D › Sidebar › SpriteMotion**.

It does not include or download any art. It reads sprite sheets that **you
export** with UOFiddler's animation export as packed output: an
`anim_<body>_<action>.png` sheet plus a `.json` next to it. Set **Sheets**
to that folder. **Props art** is optional and holds your own exported ground
and prop tiles.

Features:

- action, UO direction (mapped to stored row and mirror, as in the client),
  and frame, with a timeline-follow mode (`Hold` = scene frames per sprite
  frame, default 4)
- opacity, colour, outline and edge views; the plane can be drawn in front
  of or behind the model
- an optional model turn per direction
- a see-through bone overlay
- sprite-bone and rig-error overlays

## Viewport controls

The buttons, sliders, compass and status text are drawn in screen space.
By default they are **docked** in a corner of the 3D viewport, so they stay
put when the camera moves. Settings are in the **Frame view** box:

| Setting | What it does |
|---|---|
| Controls: **Docked** / **Follow plane** | Docked keeps them in a corner. Follow plane puts them next to the sheet plane, as 0.4 did, but still keeps them inside the viewport. |
| **Corner** | Top left, top right, bottom left (default) or bottom right |
| **Margin** | Gap to the viewport edge in pixels, before UI scaling |
| **Controls size** | 0.5 to 2 × on top of Blender's Resolution Scale |
| Reset (↺) | Clears grip drags and docks the controls again |

The small square grips move the controls block and the compass. Whatever you
do, the controls stay inside the visible part of the viewport: the toolbar,
N-panel and header are subtracted when region overlap is on. In a small
viewport the button rows wrap and shrink. If there is still no room, the
status text, then the compass, then the sliders are hidden.

## Install

- **One step:** run `launchers\dev\install-blender-addon.bat`. It installs
  and enables the add-on in `SPRITEMOTION_BLENDER` and disables the old one.
- **By hand:** **Edit › Preferences › Add-ons › Install from Disk…** and
  choose `spritemotion_sheet_reference.py`.

You can also run it with `blender --python`.

### Upgrading from UO Sheet Reference (0.4.x)

The add-on was renamed. Its operators are now `spritemotion.*`, and its
settings live on `Object.spritemotion_sheet`.

1. In **Preferences › Add-ons**, disable **UO Sheet Reference**. Both
   add-ons draw a HUD, so do not run them together.
2. Optionally click **Remove** on the old add-on, or delete
   `uo_sheet_reference.py` from your Blender user `scripts/addons` folder.
3. Old `.blend` files keep their settings. Open the **SpriteMotion** tab and
   click **Import old UO Sheet settings**. The old data is left in place.

Data markers inside scenes (`uo_sheet_mat`, `uo_*` action properties, the
`UO_*` action names) are unchanged.

## Blender versions

The add-on is tested headless on 4.2 LTS and 5.2 LTS: register and
unregister, settings, the HUD layout, materials and action F-curves. Blender
5 has slotted actions, where `Action.fcurves` is gone, and it uses EEVEE Next
material settings. The add-on handles both versions.

## UO Frame Render

The **UO Frame Render** panel renders a rigged model as UO mobile frames. It
replaces the old *UO Isometric Renderer* (`uo_isometric_renderer.py` 1.2),
which used a 26.57° dimetric camera, an arbitrary zoom, all eight directions
and no ground anchor.

- **Camera:** a SpriteMotion affine camera, `canvas = anchor + M @ world`,
  with world units in tiles (x east, y north, z up). It is converted exactly
  as in `common/rendering/ortho.py`. The presets are *Ground grid*
  ([ground-grid.json](../profiles/cameras/ground-grid.json), ClassicUO's own
  tile maths, 45° with a √2 vertical stretch) and *Character depth 0.447*
  ([character-depth-0447.json](../profiles/cameras/character-depth-0447.json),
  the unvalidated candidate from [findings.md](../research/findings.md)).
  You can also pick any camera JSON. **Set up UO camera** creates
  `SpriteMotion UO Camera`, makes it the scene camera and sets the canvas
  (default 256×256) and pixel aspect. It stores the matrix's row norms on the
  camera, and the sheet overlay sizes its planes from them, so the overlay
  and the renders always use the same camera.
- **Directions:** only the 5 stored rows are rendered: 0 SE (1,−1), 1 S
  (0,−1), 2 SW (−1,−1), 3 W (−1,0), 4 NW (−1,1). The client mirrors N, NE
  and E. The **Model** object is turned about z to face each row, using its
  **Forward** axis (−Y for glTF, Mixamo and Rigify). Its origin must be at
  the world origin, which is the tile centre and lands on the anchor
  (default 128,192). Scale the model so that 1 Blender unit is 1 tile. A
  classic human is about 61 px tall.
- **Actions:** the UO people actions 0–34, with body 400's frame counts. The
  Blender action for each is found by name (`UO_<body>_<aaa>_<name>`,
  `UO_<name>`, `<name>`, `fit_action-<aaa>`), or comes from an **Action map**
  JSON `{actions: [{action, clip, frames, loop, pick}]}`. With a map, only the
  actions it lists are rendered. There are two **Sampling** modes. *Clip span*
  samples loops over [start, end) and one-shots over [start, end], and takes
  1-frame actions at *Pick*. *Keyed* samples frame f at start + f × Step, as
  SpriteMotion fits are keyed.
- **Output:** `canvas/aAA_dD_fFF.png` (full canvas, RGBA) and `render.json`
  (camera, anchor, clips and sample times). With **Crop + uopack JSON**, it
  also writes `body_NNNN/aAA_dD_fFF.png`, cropped with alpha cut at 128, and
  `body_NNNN/aAA_dD.json`, which holds `{kind: anim, body, action,
  direction, frames: [{png, center_x, center_y, width, height}]}`. The centres
  follow ClassicUO: `center_x = anchor_x − left` and
  `center_y = (anchor_y − top) − height`.
- **Look:** *Scene* uses your engine, lights and materials. *Silhouette* uses
  flat Workbench with hard edges. **Only the model** hides the stage, the
  grid and the sheet planes while rendering. Render settings, the model's
  turn and its action are restored afterwards.

Headless:

```bat
blender -b scene.blend --python games\ultima-online\blender\spritemotion_sheet_reference.py -- --render-uo-frames --model Pivot --out <out-dir> --actions 0-34 [--camera GROUND_GRID|DEPTH_0447|cam.json] [--rows 0,1,2,3,4] [--body 400] [--action-map map.json] [--forward NEG_Y] [--sampling SPAN|KEYED --step 4] [--look SCENE|SILHOUETTE] [--no-crop]
```

The test is `tests/render_frames_test.py` (run with
`blender -b --factory-startup --python ...`). It passes on 4.2 LTS and
5.2 LTS. With both cameras, a marker lands within 0.6 px of its projected
position in every row, and the uopack centres reproduce it.

## Relation to SpriteMotion

The sheet overlay predates the SpriteMotion toolkit and does not read a
dataset. Its scales come from the scene camera: a camera made by **Set up UO
camera** carries its matrix's row norms. A pre-0.6 stage camera falls back to
the ground-grid scales, 31.113 px per unit horizontally and 44 px per
camera-vertical unit.

For reconstruction (fitting, and pixel-for-pixel silhouette comparison
against a dataset), use the dataset-driven scripts in
[`tools/blender/`](../../../tools/blender/README.md).

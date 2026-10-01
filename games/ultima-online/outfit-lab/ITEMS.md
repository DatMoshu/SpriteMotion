# Reskinning items and weapons for body 400

This guide covers changing the look of an item worn or held by the human male body (body 400), then
exporting the result as a UOFiddler `.vd` animation and a paperdoll gump. It was worked out on a
sword, a staff, a hooded robe, a kite shield and a cloak. Section 10 lists what has **not** been
checked.

Work on a **copy** of your client. The tools only read it, but importing into UOFiddler writes to
it. Keep results in `workspace/ultima-online/<your-job>/`, which git ignores.

```powershell
$env:SPRITEMOTION_UO_SOURCE = '<your UO client folder>'
$py = '.venvs\spritemotion\Scripts\python.exe'
$w  = 'workspace\ultima-online\my-job'
```

| Script | Job |
|---|---|
| `build.py` | A/B atlases for a set of items from one design sheet; `--config` picks the items |
| `build_item.py` | one item, any ItemID, from a single picture |
| `merge_items.py` | merge a second item into an already built one (a hood onto a cloak) |
| `atlas_to_vd.py` | pack an item's "new" row into a `.vd` |
| `make_gump.py`, `make_gump_cloak.py` | paperdoll gumps |
| `verify.py` | check a build against the decoder |
| `../region-masks/uo.py` | the animation reader (`UOReader`) |
| `../../../tools/vd/` | `mul2vd.py`, `vdtool.py` |

Body 400 region masks must already exist (see `../region-masks/README.md`).

## 1. Find the item's animation

ItemID → animation id comes from `tiledata.mul`: `UOReader(client).item(graphic)` returns `animId`,
`layer` and `label`. `Equipconv.def` (lines `400 <id> <conv> <gump> <hue>`) and `Bodyconv.def` can
redirect it. `uo.py` follows `Bodyconv.def` into `anim2`–`anim5.mul`. Bodies remapped by `Body.def`
and `.uop`-only animations are not readable.

Check that the animation reads before you design anything:
`reader.sequence(animId, action, direction)` returns the frames (try 0 walk, 4 idle, 9 attack).

Examples measured on one shard's client. Check yours, because shards and client versions differ:

| ItemID | Item | Anim |
|---|---|---|
| `0xF5E` | broadsword | 618 |
| `0xDF0` | black staff | 617 |
| `0x2684` | hooded shroud | 970 |
| `0x13FD` | heavy crossbow | 616 |
| `0x1414` | plate gloves | 530 |
| `0xE75` | backpack | 422 (in `anim3.mul` on that shard) |

## 2. Choose a method

| Item type | Method | Script |
|---|---|---|
| Clothing, armour, robes: the shape stays, the material changes | texture transfer, `fit_texture` | `build_item.py` (one item) or `build.py` |
| Flat item: shield, banner | whole picture laid on the item, `fit_planar` | `build_item.py --planar` |
| Slender hand-held weapon: sword, staff, spear (long straight axis) | axis fit, `fit_lightsaber` | `build.py --config` with `axisFit` |
| Helmet with different views | one picture per direction (`fit_helmet`) | see `build_spartan.py` |
| Shorter or ragged hanging item (cloak) | shape step, `shorten_frayed` | `build_item.py --cut/--fray` |

Crossbows and bows have irregular shapes. The axis fit is untested on them.

## 3. Prepare the pictures

- PNG with a transparent background (RGBA). If a picture has a white background, cut it away with a
  flood fill from the edges. `.webp` files often already have alpha; check `Image.mode` first.
- Treat `alpha >= 128` as "pixel present". Faint alpha noise around a drawing breaks `getbbox()`, so
  crop on `alpha >= 64`. Without that, a staff cut from a sheet cell comes out square and fits as a blob.
- Weapons for `axisFit`: a **horizontal** picture, grip or butt on the **left**, tip on the right. A
  vertical picture (taller than wide) is rotated so its top points right.
- Clothing: one front view, flat lighting, no shadows. The folds come from the original animation.
- Design sheet for `build.py`: a grid of 4 columns × 3 rows of equal cells, each item centred in its
  cell with a margin. An empty cell stops the build with `Empty design`.
- `.vd` has one 256-colour palette (15-bit) per action and direction, and on/off alpha. Expect no
  soft edges, glows or gradients.

## 4. Configuration (`--config`)

```json
{
  "title": "Black Staff",
  "items": [["staff", "0xDF0"]],
  "cells": {"staff": 1},
  "props": [],
  "hide": {"staff": [5]},
  "drawOrder": ["staff"],
  "defaultOff": [],
  "exclusive": [],
  "axisFit": ["staff"],
  "axisImages": {"staff": "workspace/ultima-online/my-job/staff.png"},
  "axisThickness": {"staff": 17},
  "axisContinuity": ["staff"],
  "axisTorsoRule": true,
  "displayNames": {"staff": "Black staff (617)"}
}
```

| Key | Meaning |
|---|---|
| `items` | `[key, ItemID]` pairs; replaces the built-in ten items |
| `cells` | design-sheet cell index (0–11) per key |
| `props` | items drawn as static art overlays rather than animations |
| `hide` | body region ids cut out of the new material per key (1 = face, 5 = hands) |
| `drawOrder` | viewer paint order |
| `defaultOff` | items switched off when the viewer opens |
| `exclusive` | items that cannot be shown together (sword or crossbow) |
| `title`, `displayNames` | viewer labels |
| `axisFit` | keys that use the axis fit instead of texture transfer |
| `axisImages` | own picture per key instead of a sheet cell |
| `axisThickness` | constant thickness in px (preferred) |
| `axisRatio` | thickness as a fraction of the projected length (old behaviour) |
| `axisContinuity` | keys whose butt end is tracked from frame to frame |
| `axisTorsoRule` | the working end is the one farther from the torso (default `true`) |

A fuller example: [examples/hunter.json](examples/hunter.json). The file is read as `utf-8-sig`, so
a BOM is fine. PowerShell 5.1's `Set-Content -Encoding utf8` writes one. To write without a BOM:
`[IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding($false)))`.

## 5. Build and check

Start with a few actions (0 walk, 4 idle, 9 slash 1h, 13 slash 2h, 16 spell), then build all 35.

```powershell
& $py games\ultima-online\outfit-lab\build.py --out "$w\lab" --design sheet.png --lightsaber sword.png --config my.json --actions 0 4 9 13
& $py games\ultima-online\outfit-lab\verify.py "$w\lab"
& $py -m http.server 8780 --bind 127.0.0.1 --directory "$w\lab"      # then http://127.0.0.1:8780
```

`--design` and `--lightsaber` must point to existing files even when the config does not use them.
`verify.py` must report `"errors": []` and `missingSequences: 0`. It exits with 1 when an item's
pixels did not change at all. After rebuilding, reload the viewer with Ctrl+F5 or `?v=N`.

One item without a sheet:

```powershell
# clothing from one picture; --hide-labels 1 5 leaves face and hands visible (otherwise a hood covers the head)
& $py games\ultima-online\outfit-lab\build_item.py --graphic 0x2684 --design robe.png --out "$w\lab" --key robe --title "My robe"
# flat item: the whole picture follows the shield's axis and width; brown (inside/edge) pixels get plain wood
& $py games\ultima-online\outfit-lab\build_item.py --graphic 0x1B74 --design shield.png --out "$w\lab" --key shield --planar
# shorter, ragged cloak; shape only, the colours stay
& $py games\ultima-online\outfit-lab\build_item.py --graphic 0x1515 --out "$w\lab" --key cloak --cut 0.25 --fray 0.07
# hood merged onto that cloak in one animation (on top by default, --under reverses it)
& $py games\ultima-online\outfit-lab\merge_items.py --base-lab "$w\lab" --base-key cloak --graphic 0xA706 --out "$w\lab-hood" --key cloak_hood --smooth 3
```

## 6. Tuning weapons

1. **Use a constant thickness in pixels** (`axisThickness`), not a fraction of length. The on-screen
   length changes with perspective, so a fraction makes a side view too thick and a foreshortened
   view too thin. The original staff is about 3 px thick.
2. The thickness applies to the whole picture height, orb or crystal included. Measure an idle frame
   with the weapon upright: the median row width and the bbox width, against the original. One pixel
   of shaft is a few units of `axisThickness`.
3. **Which end is which.** For a weapon held mid-shaft the hand cannot tell the ends apart, so the
   orb jumps between frames. `axisContinuity` takes the lower end on screen as the butt in the first
   frame and follows it afterwards. `axisTorsoRule` treats the end farther from the torso as the
   working end. Check the sheets of every action for the orb on the wrong end, especially attacks and
   deaths (actions 7, 10, 14, 18, 22).
4. **Clip to the body** (`atlas_to_vd.py --body anim_0400.vd`). Original item frames have the parts
   behind the body cut out. The new weapon is kept only off the body, or within 2 px of the original
   shape, so it does not "walk onto" the character.
5. A 1 px dark outline (`--outline 1`) suits a sword: it thickens a thin blade by 2 px in UO style.
   Skip it for a picture that already has a dark outline.

## 7. Export to `.vd`

```powershell
& $py tools\vd\mul2vd.py "$env:SPRITEMOTION_UO_SOURCE\anim.idx" "$env:SPRITEMOTION_UO_SOURCE\anim.mul" "$w\vd" 617   # the original
& $py tools\vd\mul2vd.py "$env:SPRITEMOTION_UO_SOURCE\anim.idx" "$env:SPRITEMOTION_UO_SOURCE\anim.mul" "$w\vd" 400   # the body, for clipping
& $py games\ultima-online\outfit-lab\atlas_to_vd.py "$w\lab" staff "$w\vd\anim_0617.vd" "$w\vd\staff.vd" --body "$w\vd\anim_0400.vd"
& $py tools\vd\vdtool.py info "$w\vd\staff.vd"
```

The key (`staff`) is the item key from the config or `--key`. Self-test of the converter: with
`--original` it packs the untouched row, and `vdtool verify original.vd result.vd` must print
`IDENTICAL BYTE FOR BYTE` or `IMAGE IDENTICAL`.

Atlas views 3..7 are `.vd` directions 0..4. The atlas anchor (128,192) is the `.vd` frame anchor.
`mul2vd.py` reads only `anim.mul`. Export animations that live in `anim2`–`anim5.mul` from UOFiddler
(Animation Edit → Export to VD). `atlas_to_vd.py` needs the original `.vd` only for its frame counts.

Import: UOFiddler → Animations → Animation Edit → file and ID → Import from VD → Save, on the client
copy. The type must match the target: human clothing and weapons are type 2, 35 actions.

## 8. Paperdoll gump

- Gump ids: male = anim + 50000, female = male + 10000. Check `Equipconv.def` for a literal gump
  that overrides this.
- The original gump comes from `Gumpidx.mul`/`Gumpart.mul` (RLE, RGB555, 0 = transparent), and so do
  the body gumps 12 (male) and 13 (female). Clients often lack the female gump of an item; in
  UOFiddler that needs Insert rather than Replace.
- `make_gump.py` extracts the original, fits the picture to its axis, clips it to body gumps 12 and
  13, and writes male and female PNGs plus `comparison.png`:

  ```powershell
  # staff (anim 617): horizontal picture, orb on the right
  & $py games\ultima-online\outfit-lab\make_gump.py --anim 617 --image staff.png --thickness 26 --out "$w\gump"
  # sword (anim 618): hilt in the hand, fingers in front of the grip
  & $py games\ultima-online\outfit-lab\make_gump.py --anim 618 --image sword.png --ratio 0.15 --shift 3,-9 --front-below 106 --outline --out "$w\gump"
  # shortened, ragged cloak with a hood
  & $py games\ultima-online\outfit-lab\make_gump_cloak.py --cloak-gump 50468 --hood-gump 50400 --out "$w\gump" --tooth 9 --fray 0.06
  ```

  Options: `--thickness` (px) or `--ratio`, `--butt bottom|top|left|right` (which end of the original
  gump is the grip), `--shift dx,dy`, `--front-below Y` (the row from which the hand covers the item),
  `--outline`, `--gump-id`. Alpha is on/off. A staff is about 26 px thick on a gump; a sword fits with
  `--ratio 0.15`.
- Clipping works as for the animation: a pixel shows when it is off the body or within 2 px of the
  original. For a gripped weapon, switch that allowance off below the guard so the fingers stay in
  front of the grip. Choose shifts on a magnified crop of the hand, with a few variants side by side.

## 9. Checklist before handing over

- [ ] `verify.py`: `errors: []`, `missingSequences: 0`, all actions.
- [ ] Sheets of all 35 actions in 3 directions reviewed (grip and orb on the right ends, nothing on the body).
- [ ] `vdtool info` shows type 2, 35 actions × 5 directions, frame counts equal to the original.
- [ ] A backup of the previous `.vd` and config.
- [ ] The result shown in the HTML viewer and the thickness and orientation agreed.

## 10. Not verified

- Import into UOFiddler and the look in the actual client. Results were judged on composites with
  body frames and gumps only, on chosen frames, not all of them.
- Body 401 and other bodies (no region masks). Torso and leg items beyond a robe.
- Item icons (ground art) and server-side entries (`ItemData.csv`, `bodyTable.cfg`, scripts).
- `.uop`-only animations, `Body.def` remaps, mounted-only and gargoyle bodies.
- Crossbows, shields and bows on the axis path. The shield's front/back choice is a colour heuristic
  (brown = inside or edge, grey = steel). It leaves specks on very narrow views or can take a
  glancing steel face for the back. Narrow views cannot show an emblem anyway.
- The torso rule was tuned on a handful of frames. Frames where the weapon points down (spells,
  deaths) may still put the orb on the wrong end.
- Merged items (hood + cloak) share one layer. The client's draw order between their real layers was
  not tested. Gump placement is chosen by eye; there is no automatic hand detection.

## 11. Known pitfalls

- An empty sheet or cell gives `Empty design` (`build.py`; `axisImages` are not affected).
- Sheet cells often carry faint alpha noise: crop on `alpha >= 64`.
- `verify.py` exits with 1 when an item's pixels did not change; that is a check, not a crash.
- On NumPy 2, `ndarray.ptp()` is gone; use `np.ptp(array)`.
- After changing `build.py`, `viewer.js`, `verify.py` or `uo.py`, packages handed out earlier are out of date.

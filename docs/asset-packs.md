# Asset packs

The content studio (`tools/uo-content`) can fit parts of third-party 3D asset packs (modular outfits, helmets,
weapons) onto the UO body and export them as UO equipment. Each pack is described by one **asset-pack mapping**, a
JSON document (`schema: spritemotion.asset-pack`, `schemas/asset-pack.schema.json`). A mapping holds two tables:

1. **Bones → target rig.** How the pack's skeleton is fitted onto the canonical UO rig (`uo-model3d-v13`).
2. **Parts → equipment slots.** Which of the game's equipment layers each part type becomes.

The game's slots are a separate document (`schema: spritemotion.equipment-slots`). For UO it is
[`games/ultima-online/equipment/layers.json`](../games/ultima-online/equipment/layers.json): the client's Layer
enum, with whether each layer animates, the rig bones it is fitted to and the body regions it covers.

Packs are handled one at a time, 1:1: one mapping per pack, written for that pack's skeleton and part naming. Nothing
in the studio is specific to a pack. `tools/uo-content/pack_fit.py` reads the mapping, and a job selects it with
`pack_mapping` in its settings.

## Licensing: where mappings live

Most commercial packs forbid redistributing their meshes, textures and data. The mapping itself is only bone names,
part codes and our own decisions, but keep a commercial pack's mapping, its batch scripts and every output **outside
this repository**, in a local sidecar folder. The pack's files are located through the environment variable named in
`source.env`; they are never copied. `examples/asset-pack/example-modular.json` is a fictional mapping that shows the
format and is validated by the tests. A mapping placed in `games/<game>/asset-packs/` is validated with the
repository data; only put one there if its pack's licence allows it.

## Bones

`bones` lists **every** bone of the pack's skeleton:

| Field | Meaning |
|---|---|
| `role` | `root`, `deform`, `twist`, `finger`, `attach` (socket bones like a head or back attachment), `face`, `dynamic`, `ik`, `prop` (weapon sockets) |
| `target` | Target-rig bone that receives this bone's vertex weights |
| `end` | Present on **aligned** bones: the source bone at the far end of the chain (`null`: use `fit.missing_end_offset`) |
| `keep_orientation` | Aligned bone that is only moved, not rotated or scaled (spine, head: FBX bone roll is unrelated to anatomy) |
| `follows` | For a non-aligned bone: the aligned ancestor it moves with |
| `proposed_target` | A better target the rig offers that the fitter does not use yet (twist bones, fingers, the shield bone) |

The fit, per source mesh: every aligned bone's chain (head → `end` head) is rotated onto its target bone and scaled to
its length, clamped to `fit.scale_clamp`. Every vertex is moved by the weighted blend of its bones' transforms, and
its weights are folded into the target bones. A bone that is not aligned (twist, finger, socket, a part's own cloth or
hair bones) uses its nearest aligned ancestor (`fit.unmapped: nearest_mapped_ancestor`).

`dynamic_chains` lists cloth and hair bones that ship inside part files rather than the base skeleton (matched by name
prefix), with the socket they hang from and, where the rig has one, a better target such as the rig's cloak or skirt
chains. `attach_points` lists the pack's sockets and the layers they serve.

## Parts

One entry per part **type** (a helmet type, a left-hand type, and so on):

| Field | Meaning |
|---|---|
| `status` | `uo`: becomes an item on `uo_layer`. `merge`: folded into another part's item (lower arms into the Arms item). `extra`: no fitting layer; `candidate_slot` says what a new slot would be. `body`: part of the base body. `skip`: never used. |
| `uo_layer` | Layer id from the game's slots document, or `null` |
| `alternatives` | Other layers that fit some pieces of this type, chosen per asset |
| `pair` | The mirrored part. Left and right pieces become one item, because one UO layer is one item. |
| `studio_part` | Fit template in the studio (`helm`, `chest`, `arms`, `gloves`, `legs`, `boots`, `robe`, `cloak`, `skirt`, `weapon`, `shield`, `bow`, `quiver`) |
| `bind` | `skinned` (deforms with its bones) or `rigid` (moves with one bone; metal must not stretch) |
| `offset` | Rest-pose offset in metres, applied before binding (for example helmet crown clearance) |
| `rotate`, `scale` | Rest-pose rotation (degrees, XYZ about the item centre) and uniform scale |
| `hide_body` | `{enabled, outward, inward}`: CC4-style hiding of body faces under the part (metres along each face normal, rest pose), so the body cannot poke through or hold out holes in the sprite |
| `weighted_bones` | Bones the pack's parts of this type are weighted to (sampled) |

`uncovered_layers` lists the game's animated layers that the pack has no source for.

Tune `offset`, `rotate`, `scale`, `bind` and `hide_body` per slot in the [fit lab](../tools/fit-lab/README.md).

## Adding a pack

1. Dump the pack's skeleton and the bones each part type is weighted to (a Blender script importing the base model and
   a few part files per type).
2. Write the mapping: align the main chains (pelvis, spine, neck, head, clavicles, arms, hands, legs, feet, toes),
   then let everything else follow. Map each part type to a layer, mark pairs, and choose rigid binding for hard pieces.
3. Validate it: `python -c "from spritemotion.schemas import validate, read_json; print(validate(read_json('<file>'), 'spritemotion.asset-pack', required=True))"`
   (an empty list means valid).
4. Build a preview job with `source_files`, `palette` (if the pack uses a palette texture) and `pack_mapping` in its
   settings, and review the fit on the contact sheet before running full builds.

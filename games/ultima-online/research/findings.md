# Findings so far (body 400)

These findings come from the 2026-09 reconstruction experiments. A draft
rigged model was fitted to all 35 body-400 actions in Blender and rendered
back through the camera. The models, scenes and renders were local and are
not part of this repository. The numbers below are there so the next person
knows where things stood. They measure the listed experiments, not the
quality of any model shipped here, because none is.

All overlap figures are **silhouette IoU**: alpha intersection over union at
the native 256×256 size, with the source anchored by its original centre
offsets. They measure shape agreement, not anatomy, timing or correctness,
and they are **not** percentages of completion.

## 1. The ground-grid camera is probably not the character camera

The ground-grid projection (see [uo-conventions.md](uo-conventions.md))
reproduces the tile grid exactly. Character art may have been drawn or
rendered differently.

- **Landmark evidence.** Approximate manual head and pelvis positions from
  three different actions each implied a depth projection of about
  **0.44–0.46** of the ground-grid depth term. The residuals were 0.6–2.3 px,
  against an estimated 1–3 px of uncertainty in the observations.
- **Candidate.** Depth factor 1/√5 ≈ 0.447 (the ground rows scaled from 22 to
  9.834), with the horizontal scale, body-height term and anchor unchanged.
  This is `profiles/cameras/character-depth-0447.json`. It is one projection
  consistent with the evidence, not recovered production metadata.
- **Re-fit comparison.** All 210 poses were fitted again under the candidate
  and rendered in all five stored directions, 1,050 frames in total. Mean
  overlap rose from **61.0% to 65.7%**, and **27 of 35** action means
  improved:

  | action | ground grid | candidate |
  |---|---:|---:|
  | death_back | 43.8% | 62.0% |
  | death_forward | 40.1% | 51.2% |
  | combatadvance | 55.5% | 66.1% |
  | run | 64.2% | 68.6% |
  | walk | ≈ flat | ≈ flat |
  | idle | 68.3% | 66.2% |

- **Not validated:** anatomy, temporal continuity, ground contacts, the
  mirrored views, clothing behaviour.
- **Consequence for tools:** under the candidate, the ground diamond no
  longer matches the game grid. Anything that places reference planes or
  converts offsets at 45° has to take the camera as data, not only swap the
  camera rotation. SpriteMotion does this: the camera is a matrix in the
  dataset, and `--camera` overrides it everywhere.

**Next step:** fit shared body proportions and the camera jointly, using
approved annotations of the head, pelvis, knees, ankles and wrists across
several actions and at least two directions per frame.

## 2. Limb identity is inconsistent across the legacy data

The humanoid-20 skeleton names limb chains **A** and **B** because a sprite
often does not show which side a limb is on. In the migrated data these
labels do not agree:

- The six approved SE `death_forward` poses were fitted with **A → right**,
  which is what `rig-mappings/mixamo.json` records.
- The rig-projection estimates of every other action were generated with
  **A → left**, which is what `rig-mappings/rigify.json` records.
- The manual action-22 A/B labels are **provisional per view**. The person
  who placed them was not asked to confirm anatomical sides for occluded limbs.

Each annotation file records its convention in `limb_identity`. Until a
reviewer settles it, fit action 22 with the Mixamo-style assignment, or pass
`--swap-sides`, and compare the per-joint errors of the two assignments.
Mirrored views keep the chain labels of their source view.

## 3. One approved view does not fix a 3D pose

Fitting the six SE approvals of `death_forward` raised SE overlap from
**42.9% to 72.9%** (landmark error under 0.83 px). The same 3D action,
rotated into the other directions, got **worse** in five of the seven:

| N | NE | E | SE | S | SW | W | NW |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 38.9 → 24.6 | 36.7 → 26.9 | 40.7 → 44.8 | 42.9 → 72.9 | 40.4 → 45.5 | 37.0 → 27.4 | 39.3 → 24.4 | 40.6 → 26.5 |

Depth is unconstrained by a single view, which is why
[reconstruct-body-400](../recipes/reconstruct-body-400.md) asks for approved
poses in two or more directions per frame.

## 4. Draft animation quality

- With the ground-grid camera, the draft actions scored a mean overlap of
  about **56–69%** per action across all eight directions. The falls were
  lowest, at about 40–44%.
- A later anatomy-first pass (head and foot constraints, no floor
  penetration) moved the overall mean from 55.9% to 58.3%. That pass put
  anatomy ahead of silhouette matching.
- In several combat actions, the draft had **150–178° local rotation jumps**
  in the arm and forearm between frames. These are real rotations, not
  quaternion sign flips. Frame-by-frame silhouette fitting can land on the
  wrong side of an ambiguous limb, so fits need temporal terms
  (`temporal_weight`) and stable elbow and hand targets before clothing
  simulation can work.
- Hands, foot sliding, falls and mounted poses (horse and saddle alignment)
  all needed more work.

## Open questions

1. What projection was the character art made with? Test it with
   multi-view approved landmarks, not silhouettes.
2. Which anatomical side is limb A in each stored view of each action? This
   is a review task.
3. Are body proportions constant across actions? Some fits wanted different
   limb lengths per action.
4. What is the frame timing? It is not in the MUL files. The scenes used 4
   Blender frames per source frame.

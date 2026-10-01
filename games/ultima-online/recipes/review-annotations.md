# Recipe: reviewing body-400 annotations

The fastest way to improve a UO reconstruction is to add approved,
independent poses. This recipe is the review loop.

## Set up

```bat
set SPRITEMOTION_UO_SOURCE=<your UO folder>
launchers\pipeline\1-extract-uo.bat
launchers\editor\sprite-pose-editor.bat
```

## Choose what to review

Priority order:

1. **A second direction of `action-022` frames 0–5.** SE is already
   approved, so S or E makes the depth of those poses solvable.
2. **Key poses of the actions people use most:** idle (`action-004`), walk
   (`action-000`), run (`action-002`), and one-handed and two-handed attacks
   (`action-009`, `action-013`). Review SE and S first, then a profile (W or
   E).
3. **Contact frames:** feet planted in walk and run, and weapon extension in
   attacks.

Every pose outside action 22 starts as a *rig projection*. The inspector
shows "not independent evidence" for these. They are close, but they are
the draft model's opinion, not the sprite's.

## For each pose

1. Turn on **Original ghost** so you can see the starting estimate.
2. Drag each joint onto the sprite. Place joints at the centre of the joint,
   not on its outline:
   - head centre (not the top of the head)
   - wrist at the crease
   - hand at the fist or palm centre
   - toe at the tip of the foot
3. If a limb is hidden, place your best estimate and say so in the notes,
   for example "arm B elbow occluded by torso".
4. Decide limb identity for this view. Is chain A the anatomical right or
   left? Write it in the notes if you are not sure. See
   [research/findings.md §2](../research/findings.md#2-limb-identity-is-inconsistent-across-the-legacy-data).
5. Tick **Pose approved** only after every joint is checked.

**Link mirrored view** moves the mirrored partner too (for example S and E).
Mirrored views are pixel-exact flips in UO, so this is safe. Chain names are
kept across the flip.

## Share

```bat
.venvs\spritemotion\Scripts\python -m spritemotion promote workspace\ultima-online\body-400 ^
    --bundle games\ultima-online\annotations\body-400 --sequences action-004
.venvs\spritemotion\Scripts\python -m spritemotion validate
```

Open a pull request that lists the sequences, directions and frames you
approved. Do not attach screenshots of game art to the repository. See
[CONTRIBUTING.md](../../../CONTRIBUTING.md).

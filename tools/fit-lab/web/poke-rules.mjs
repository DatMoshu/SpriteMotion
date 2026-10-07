// The rule the Measure poke count follows, kept pure so Node can test it. It mirrors the final renderer:
//  - tools/uo-content/occlusion.py (BodyHoldout / blocked_pixels): the body cuts an item pixel only where it is
//    more than `margin` in front of the item; in clothing mode with hide-body on, a same-region contact gets
//    max(margin, hide.inward).
//  - the installed canonical renderer, render_uo_layer.py: HOLDOUT_MARGIN = 0.01 m and BODY_GAP = 0.006 m (push-out),
//    which tools/uo-content/blender_build.py sets to 0 for rigid items and for helm, weapon, shield, bow and quiver.
export const HOLDOUT_MARGIN = 0.01;
export const PUSH_OUT_GAP = 0.006;
const NO_PUSH_OUT = new Set(['helm', 'weapon', 'shield', 'bow', 'quiver']);

// studioPart is the mapping part's `studio_part`, the value builds.py hands the renderer as spec.part (not the pack
// part code or the layer name). A part without one is treated as pushed.
export function pokeRule(fit, studioPart) {
  const mode = fit.occlusion || 'clothing';
  if (mode === 'none') return { measure: false, mode, allowance: 0, faces: 'none' };   // renderer skips the holdout
  const tolerance = mode === 'clothing' && fit.hide?.enabled ? (fit.hide.inward ?? 0.01) : 0;
  const pushed = fit.bind !== 'rigid' && !NO_PUSH_OUT.has(studioPart);
  return { measure: true, mode,
    allowance: Math.max(HOLDOUT_MARGIN, tolerance) + (pushed ? PUSH_OUT_GAP : 0),
    // clothing: limb/head faces under the item (the torso never holds out); body: the whole body, hide-body ignored
    faces: mode === 'body' ? 'all' : 'under' };
}

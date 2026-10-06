import test from 'node:test';
import assert from 'node:assert/strict';
import { pokeRule, HOLDOUT_MARGIN, PUSH_OUT_GAP } from './poke-rules.mjs';

const fit = (o = {}) => ({ occlusion: 'clothing', bind: 'skinned', hide: { enabled: true, outward: .02, inward: .01 }, ...o });
const info = (o = {}) => ({ slot: 'chest', part: 'chest', ...o });

test('clothing: 1 cm margin plus 6 mm push-out for a skinned garment', () => {
  const r = pokeRule(fit(), info());
  assert.equal(r.measure, true); assert.equal(r.faces, 'under');
  assert.ok(Math.abs(r.allowance - (HOLDOUT_MARGIN + PUSH_OUT_GAP)) < 1e-12);
});
test('hide-body inward larger than the margin is the contact allowance; off falls back to the margin', () => {
  assert.ok(Math.abs(pokeRule(fit({ hide: { enabled: true, inward: .03 } }), info()).allowance - .036) < 1e-12);
  assert.ok(Math.abs(pokeRule(fit({ hide: { enabled: false, inward: .03 } }), info()).allowance - .016) < 1e-12);
});
test('rigid items and helm/weapon/shield/bow/quiver get no push-out', () => {
  assert.equal(pokeRule(fit({ bind: 'rigid' }), info()).allowance, HOLDOUT_MARGIN);
  for (const part of ['helm', 'weapon', 'shield', 'bow', 'quiver'])
    assert.equal(pokeRule(fit(), info({ part, slot: part })).allowance, HOLDOUT_MARGIN);
});
test('body mode uses the whole body and ignores the hide-body tolerance', () => {
  const r = pokeRule(fit({ occlusion: 'body' }), info());
  assert.equal(r.faces, 'all'); assert.ok(Math.abs(r.allowance - .016) < 1e-12);
});
test('none mode measures nothing, like the renderer', () => {
  assert.equal(pokeRule(fit({ occlusion: 'none' }), info()).measure, false);
});

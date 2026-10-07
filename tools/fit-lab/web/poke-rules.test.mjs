import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { pokeRule, HOLDOUT_MARGIN, PUSH_OUT_GAP } from './poke-rules.mjs';

const fit = (o = {}) => ({ occlusion: 'clothing', bind: 'skinned', hide: { enabled: true, outward: .02, inward: .01 }, ...o });
const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-12, `${a} != ${b}`);

test('clothing: 1 cm margin plus 6 mm push-out for a skinned garment', () => {
  const r = pokeRule(fit(), 'chest');
  assert.equal(r.measure, true); assert.equal(r.faces, 'under');
  near(r.allowance, HOLDOUT_MARGIN + PUSH_OUT_GAP);
});
test('a part with no studio_part is treated as pushed', () => {
  near(pokeRule(fit(), undefined).allowance, HOLDOUT_MARGIN + PUSH_OUT_GAP);
});
test('hide-body inward larger than the margin is the contact allowance; off falls back to the margin', () => {
  near(pokeRule(fit({ hide: { enabled: true, inward: .03 } }), 'chest').allowance, .036);
  near(pokeRule(fit({ hide: { enabled: false, inward: .03 } }), 'chest').allowance, .016);
});
test('rigid items get no push-out whatever the studio part', () => {
  assert.equal(pokeRule(fit({ bind: 'rigid' }), 'chest').allowance, HOLDOUT_MARGIN);
});
test('helm, weapon, shield, bow and quiver studio parts get no push-out', () => {
  for (const part of ['helm', 'weapon', 'shield', 'bow', 'quiver'])
    assert.equal(pokeRule(fit(), part).allowance, HOLDOUT_MARGIN);
});
test('pack part codes and layer names do not decide the push-out', () => {
  for (const code of ['hood', 'weapon-sword', 'shield-round', 'backpack', 'OneHanded', 'Helm'])
    near(pokeRule(fit(), code).allowance, HOLDOUT_MARGIN + PUSH_OUT_GAP);
});
test('body mode uses the whole body and ignores the hide-body tolerance', () => {
  const r = pokeRule(fit({ occlusion: 'body' }), 'chest');
  assert.equal(r.faces, 'all'); near(r.allowance, .016);
});
test('none mode measures nothing, like the renderer', () => {
  assert.equal(pokeRule(fit({ occlusion: 'none' }), 'chest').measure, false);
});
test('cc0 starter mapping: every part gets the allowance the renderer implies', () => {
  const mapping = JSON.parse(readFileSync(new URL('../../../examples/cc0-starter/outfit-mapping.json', import.meta.url)));
  const plain = ['hood', 'hair', 'beard', 'weapon-sword', 'shield-round', 'backpack'];
  const pushedCodes = ['shirt', 'pants', 'cloak'];
  for (const p of mapping.parts) {
    const rigid = p.bind === 'rigid', free = ['helm', 'weapon', 'shield', 'bow', 'quiver'].includes(p.studio_part);
    const r = pokeRule(fit({ bind: p.bind }), p.studio_part);
    near(r.allowance, rigid || free ? .01 : .016);
    if (plain.includes(p.code)) near(r.allowance, .01);
    if (pushedCodes.includes(p.code)) near(r.allowance, .016);
  }
  assert.ok(plain.concat(pushedCodes).every(c => mapping.parts.some(p => p.code === c)));
});

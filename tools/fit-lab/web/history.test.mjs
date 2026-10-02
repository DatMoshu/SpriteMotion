import test from 'node:test';
import assert from 'node:assert/strict';
import { EditHistory, same } from './history.mjs';

const value = n => ({ parts: { TEST: { scale: n } }, items: {} });
test('multi-step undo/redo, branch replacement, recovery and immutable snapshots', () => {
  const history = new EditHistory(value(1));
  const input = value(2); history.commit(input, 'Scale'); input.parts.TEST.scale = 99;
  history.commit(value(3), 'Scale'); history.commit(value(4), 'Scale');
  assert.deepEqual(history.go(1), value(2));
  assert.deepEqual(history.go(3), value(4));
  history.go(1);
  const recovered = new EditHistory(value(0), JSON.parse(JSON.stringify(history.serialize())));
  assert.equal(recovered.canRedo, true);
  assert.deepEqual(recovered.value, value(2));
  recovered.commit(value(8), 'New branch');
  assert.equal(recovered.canRedo, false);
  assert.equal(recovered.entries.length, 3);
  assert.equal(recovered.commit(value(8), 'No change'), false);
});
test('100 undo steps remain bounded and object key ordering is irrelevant', () => {
  const history = new EditHistory(value(1));
  for (let i = 2; i <= 150; i++) history.commit(value(i), 'Scale');
  assert.equal(history.entries.length, 101);
  assert.deepEqual(history.go(0), value(50));
  assert.equal(history.canUndo, false);
  assert.ok(same({ parts: {}, items: {} }, { items: {}, parts: {} }));
});

// Pure edit history; saved snapshots never share references with live fit controls.
export const clone = value => JSON.parse(JSON.stringify(value));
export function same(a, b) {
  const ordered = v => Array.isArray(v) ? v.map(ordered) : v && typeof v === 'object'
    ? Object.fromEntries(Object.keys(v).sort().map(k => [k, ordered(v[k])])) : v;
  return JSON.stringify(ordered(a)) === JSON.stringify(ordered(b));
}

export class EditHistory {
  constructor(value, saved) {
    this.entries = [{ label: 'Opened adjustments', value: clone(value) }];
    this.index = 0;
    if (saved && Array.isArray(saved.entries) && saved.entries.length > 0 && saved.entries.length <= 101
        && Number.isInteger(saved.index) && saved.index >= 0 && saved.index < saved.entries.length
        && saved.entries.every(e => typeof e.label === 'string' && e.value?.parts && e.value?.items)) {
      this.entries = clone(saved.entries); this.index = saved.index;
    }
  }
  get value() { return clone(this.entries[this.index].value); }
  get canUndo() { return this.index > 0; }
  get canRedo() { return this.index < this.entries.length - 1; }
  commit(value, label) {
    if (same(this.value, value)) return false;
    this.entries.splice(this.index + 1);
    this.entries.push({ label, value: clone(value) });
    if (this.entries.length > 101) this.entries.shift();
    this.index = this.entries.length - 1;
    return true;
  }
  go(index) { this.index = Math.max(0, Math.min(this.entries.length - 1, index)); return this.value; }
  serialize() { return { entries: this.entries, index: this.index }; }
}

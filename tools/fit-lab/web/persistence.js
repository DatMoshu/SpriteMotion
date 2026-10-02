import { EditHistory, clone, same } from './history.mjs';

// Keep local recovery synchronous, and disk requests serial. Never let an older response erase a newer edit.
export class FitPersistence {
  constructor(key, initial, onRestore) {
    this.key = key; this.revision = initial.revision; this.disk = initial.adjustments;
    this.history = new EditHistory(initial.adjustments); this.value = clone(initial.adjustments);
    this.onRestore = onRestore; this.localOK = true; this.conflict = false; this.saving = false;
    this.status = document.getElementById('saveStatus');
    try {
      const cached = JSON.parse(localStorage.getItem(key) || 'null');
      if (cached?.history && cached?.value?.parts && cached?.value?.items) {
        this.history = new EditHistory(cached.value, cached.history); this.value = cached.value;
        this.history.commit(this.value, 'Recovered unfinished edit');
        this.conflict = cached.revision !== this.revision && !same(this.value, this.disk);
      }
    } catch { this.localOK = false; }
    this.renderBackups(initial.backups); this.renderHistory();
    this.message(this.conflict ? 'Disk changed since this browser session. Choose a version below.'
      : same(this.value, this.disk) ? 'Saved to disk' : 'Recovered edits — autosave pending');
    document.getElementById('recovery').hidden = !this.conflict;
    document.getElementById('useDisk').onclick = () => this.resolve(false);
    document.getElementById('useLocal').onclick = () => this.resolve(true);
    document.getElementById('restoreBackup').onclick = () => this.restoreBackup();
    this.cache();
    if (!this.conflict && !same(this.value, this.disk)) this.schedule();
  }
  message(text) { this.status.textContent = text + (this.localOK ? '' : ' · Browser recovery unavailable'); }
  cache() {
    try { localStorage.setItem(this.key, JSON.stringify({ revision: this.revision, value: this.value, history: this.history.serialize() })); }
    catch { this.localOK = false; }
  }
  edit(value) {
    this.value = clone(value); this.cache(); this.schedule();
  }
  commit(value, label) {
    this.history.commit(value, label); this.value = clone(value); this.renderHistory(); this.cache(); this.schedule();
  }
  jump(index) {
    if (this.suspended) return;
    // A shortcut during a drag should still retain the in-progress adjustment for redo.
    this.history.commit(this.value, 'Fit adjustment');
    this.value = this.history.go(index); this.onRestore(clone(this.value));
    this.renderHistory(); this.cache(); this.schedule();
  }
  undo() {
    if (this.suspended) return;
    this.history.commit(this.value, 'Fit adjustment'); this.jump(this.history.index - 1);
  }
  redo() { this.jump(this.history.index + 1); }
  renderHistory() {
    const list = document.getElementById('history'); list.replaceChildren();
    this.history.entries.forEach((entry, index) => {
      const button = document.createElement('button');
      button.textContent = `${index}. ${entry.label}`; button.classList.toggle('current', index === this.history.index);
      button.setAttribute('aria-current', index === this.history.index ? 'step' : 'false');
      button.onclick = () => this.jump(index); list.appendChild(button);
    });
    document.getElementById('undo').disabled = !this.history.canUndo;
    document.getElementById('redo').disabled = !this.history.canRedo;
    document.getElementById('historyCount').textContent = `${this.history.index} / ${this.history.entries.length - 1}`;
  }
  renderBackups(backups) {
    const select = document.getElementById('backups'); select.replaceChildren();
    for (const [i, backup] of backups.entries()) {
      const option = document.createElement('option'); option.value = backup.id;
      option.textContent = `${i + 1}. Before ${new Date(backup.saved_at).toLocaleString()}`; select.appendChild(option);
    }
    if (!backups.length) { const option = document.createElement('option'); option.textContent = 'No previous saves yet'; select.appendChild(option); }
    document.getElementById('restoreBackup').disabled = !backups.length;
  }
  schedule() {
    clearTimeout(this.timer);
    if (this.conflict) return;
    this.message(same(this.value, this.disk) ? 'Saved to disk' : this.localOK
      ? 'Unsaved changes · recovery cached locally' : 'Unsaved changes · keep this tab open');
    if (!same(this.value, this.disk)) this.timer = setTimeout(() => this.save(), 800);
  }
  async save() {
    clearTimeout(this.timer);
    if (this.saving || this.conflict) return;
    if (same(this.value, this.disk)) { this.message('Saved to disk'); return; }
    this.saving = true; const sent = clone(this.value);
    this.message('Saving…');
    let failed = false;
    try {
      const response = await fetch('api/adjustments', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ adjustments: sent, base_revision: this.revision }) });
      const result = await response.json();
      if (response.status === 409) { this.conflict = true; document.getElementById('recovery').hidden = false; }
      if (!response.ok) throw new Error(result.error || `Save failed (${response.status})`);
      this.revision = result.revision; this.disk = sent; this.renderBackups(result.backups); this.cache();
      this.message('Saved to disk · ' + new Date().toLocaleTimeString());
    } catch (error) {
      failed = true; this.message(`${error.message} · Edits retained in this tab`);
    } finally {
      this.saving = false;
      if (!this.conflict && !same(this.value, this.disk)) {
        if (failed) this.timer = setTimeout(() => this.save(), 5000);
        else this.schedule();
      }
    }
  }
  async resolve(keepLocal) {
    if (this.suspended || this.saving) return;
    try {
      const response = await fetch('api/state'); if (!response.ok) throw new Error('Cannot read disk version.');
      const latest = await response.json(); this.revision = latest.revision; this.disk = latest.adjustments;
      this.conflict = false; document.getElementById('recovery').hidden = true; this.renderBackups(latest.backups);
      if (!keepLocal) { this.commit(this.disk, 'Use disk version'); this.onRestore(clone(this.value)); }
      this.cache(); this.schedule();
    } catch (error) { this.message(error.message); }
  }
  async restoreBackup() {
    if (this.suspended) return;
    try {
      const id = document.getElementById('backups').value;
      const response = await fetch('api/backups/' + encodeURIComponent(id));
      if (!response.ok) throw new Error('Backup is no longer available. Save or reload to refresh the list.');
      const value = await response.json(); this.commit(value, 'Restore backup'); this.onRestore(clone(value));
    } catch (error) { this.message(error.message); }
  }
}

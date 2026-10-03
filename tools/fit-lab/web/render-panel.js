// Blender render pane: the selected item's real renderer output beside the live 3D view, frame-locked to it, as a
// single frame or as the action's sprite sheet. Renders run as lab builds in the background (POST /api/build).
// Review strips (pipeline.finish): 256 px per frame, row 0 = original UO body, row 1 = the rendered item layer.
import { resolveFit, storedDirection } from './fit-rules.mjs';

const $ = id => document.getElementById(id);
const CELL = 256;
const pad = n => String(n).padStart(2, '0');

export class RenderPanel {
  // hooks: pose() -> {info, action:{id,frames}, frame, dir}; part(info); adjustments(); setPose(dir, frame);
  // ready() -> true when every edit is saved to disk; save() -> Promise; edited() -> ms timestamp of the last fit edit.
  constructor(hooks) {
    this.hooks = hooks; this.mode = 'frame'; this.renders = []; this.strips = new Map(); this.jobs = new Map();
    this.item = null; this.status = { state: 'idle' }; this.autoKey = null; this.drawn = '';
    this.canvas = $('renderFrame'); this.ctx = this.canvas.getContext('2d');
    for (const button of document.querySelectorAll('#renderModes button')) button.onclick = () => this.setMode(button.dataset.mode);
    $('renderBase').onchange = () => { this.drawn = ''; this.sync(); };
    $('renderNow').onclick = $('renderGo').onclick = () => this.build('build', 'action');
    $('buildItem').onclick = () => this.build('build', $('buildCoverage').value);
    $('rebuildItem').onclick = () => this.build('rebuild', $('buildCoverage').value);
    $('renderSheetDownload').onclick = () => this.downloadSheet();
    try { $('renderAuto').checked = localStorage.getItem('fit-lab:auto-render') === '1'; } catch {}
    $('renderAuto').onchange = e => { try { localStorage.setItem('fit-lab:auto-render', e.target.checked ? '1' : '0'); } catch {} this.sync(); };
    new ResizeObserver(() => { this.drawn = ''; this.sync(); }).observe($('renderStage'));
    this.poll();
  }

  setMode(mode) {
    this.mode = mode;
    for (const button of document.querySelectorAll('#renderModes button')) button.setAttribute('aria-pressed', button.dataset.mode === mode);
    this.drawn = ''; this.sync();
  }

  // ---------- data ----------
  async refresh() {
    const id = this.item;
    const response = await fetch('api/renders?item=' + encodeURIComponent(id));
    const { renders } = await response.json();
    if (id === this.item) { this.renders = renders; this.drawn = ''; this.sync(); }
  }
  job(id) {
    if (!this.jobs.has(id)) this.jobs.set(id, fetch(`builds/${id}/job.json`).then(r => r.ok ? r.json() : null).catch(() => null));
    return this.jobs.get(id);
  }
  strip(job, action) {
    const key = job + '/' + action;
    if (!this.strips.has(key)) this.strips.set(key, Promise.all([0, 1, 2, 3, 4].map(d => {
      const image = new Image(); image.src = `builds/${job}/review/a${pad(action)}-d${d}.png`;
      return image.decode().then(() => image, () => null);
    })).then(images => ({ images, box: bounds(images) })));
    return this.strips.get(key);
  }
  // The newest render that includes this action; older jobs keep other animations visible.
  renderFor(action) { return this.renders.find(r => r.actions.includes(action)); }
  stale(spec, pose) {
    if (!spec) return false;
    const now = this.hooks.adjustments(), part = this.hooks.part(pose.info);
    for (let d = 0; d < 5; d++)
      if (JSON.stringify(resolveFit(spec.fit_adjustments || { parts: {}, items: {} }, part, pose.info, pose.action.id, d)) !==
          JSON.stringify(resolveFit(now, part, pose.info, pose.action.id, d))) return true;
    return false;
  }

  // ---------- drawing ----------
  async sync() {
    const pose = this.hooks.pose(); if (!pose.info) return;
    if (pose.info.id !== this.item) {
      this.item = pose.info.id; this.renders = []; this.drawn = '';
      this.refresh().catch(error => this.chip('failed', error.message));
    }
    const render = this.renderFor(pose.action.id), mine = this.status.state === 'building' && this.status.item === this.item;
    const empty = $('renderEmpty');
    $('renderPackage').hidden = $('renderSheetDownload').hidden = !render;
    if (render) $('renderPackage').href = `builds/${render.job}/import-package.zip`;
    if (!render) {
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height); $('renderSheet').replaceChildren(); this.drawn = '';
      empty.hidden = mine;
      $('renderEmptyText').textContent = this.renders.length ?
        `Animation ${pose.action.id} isn't in this item's renders yet.` : 'This item has no Blender render yet.';
      if (!mine) this.chip('none', 'Not rendered');
      this.auto(pose, null, true); return;
    }
    empty.hidden = true;
    const [strip, spec] = await Promise.all([this.strip(render.job, pose.action.id), this.job(render.job)]);
    if (this.hooks.pose().info.id !== pose.info.id) return;
    const stale = this.stale(spec, pose);
    if (!mine) this.chip(stale ? 'stale' : 'fresh', stale ? 'Fit changed since this render' : 'Matches the saved fit');
    this.auto(pose, render, stale);
    $('renderMeta').textContent = `${pose.info.family || pose.info.id} · job ${render.job} · finished ${new Date(render.finished * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    this.mode === 'frame' ? this.drawFrame(strip, pose) : this.drawSheet(strip, pose, render.job);
  }
  layers(image, frame, ctx, x, y, box, scale) {
    const sw = box.x1 - box.x0, sh = box.y1 - box.y0;
    if ($('renderBase').checked) ctx.drawImage(image, frame * CELL + box.x0, box.y0, sw, sh, x, y, sw * scale, sh * scale);
    ctx.drawImage(image, frame * CELL + box.x0, CELL + box.y0, sw, sh, x, y, sw * scale, sh * scale);
  }
  drawFrame(strip, pose) {
    const stored = storedDirection(pose.dir), image = strip.images[stored], key = `f${pose.dir}/${pose.frame}/${image?.src}`;
    $('renderStage').classList.remove('sheet');
    const box = $('renderStage').getBoundingClientRect(), dpr = devicePixelRatio || 1;
    const w = Math.max(1, Math.round(box.width * dpr)), h = Math.max(1, Math.round(box.height * dpr));
    if (this.canvas.width !== w || this.canvas.height !== h) { this.canvas.width = w; this.canvas.height = h; this.drawn = ''; }
    if (key === this.drawn) return; this.drawn = key;
    const ctx = this.ctx; ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, w, h); ctx.imageSmoothingEnabled = false;
    $('renderSheet').replaceChildren();
    if (!image) { $('renderMeta').textContent = `Direction ${stored} is missing from this render.`; return; }
    const c = strip.box, sw = c.x1 - c.x0, sh = c.y1 - c.y0;
    const scale = Math.max(1, Math.floor(Math.min((w - 24 * dpr) / sw, (h - 24 * dpr) / sh)));
    const x = Math.round((w - sw * scale) / 2), y = Math.round((h - sh * scale) / 2);
    if (pose.dir > 4) { ctx.translate(w, 0); ctx.scale(-1, 1); }   // the client mirrors 5-7 from 3-1
    this.layers(image, Math.min(pose.frame, image.width / CELL - 1), ctx, x, y, c, scale);
    $('renderPose').textContent = `${scale}× · direction ${pose.dir}${pose.dir > 4 ? ` (mirrors ${stored})` : ''} · frame ${pose.frame + 1}`;
  }
  drawSheet(strip, pose, job) {
    $('renderStage').classList.add('sheet');
    const key = `s${job}/${pose.action.id}/${$('renderBase').checked}`, wrap = $('renderSheet');
    if (key !== this.drawn) {
      this.drawn = key; this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height); wrap.replaceChildren();
      const c = strip.box, sw = c.x1 - c.x0, sh = c.y1 - c.y0;
      const space = wrap.getBoundingClientRect();
      const scale = Math.max(1, Math.min(3, Math.floor((space.width - 40) / (pose.action.frames * (sw + 2)))));
      strip.images.forEach((image, d) => {
        const row = document.createElement('div'); row.className = 'sheet-row';
        const label = document.createElement('span'); label.textContent = d; label.title = `Stored direction ${d}`; row.append(label);
        for (let f = 0; f < (image ? image.width / CELL : 0); f++) {
          const cell = document.createElement('canvas'); cell.width = sw * scale; cell.height = sh * scale;
          cell.dataset.dir = d; cell.dataset.frame = f; cell.title = `Direction ${d}, frame ${f + 1}`;
          const ctx = cell.getContext('2d'); ctx.imageSmoothingEnabled = false; this.layers(image, f, ctx, 0, 0, c, scale);
          cell.onclick = () => this.hooks.setPose(d, f);
          row.append(cell);
        }
        wrap.append(row);
      });
    }
    const stored = storedDirection(pose.dir);
    for (const cell of wrap.querySelectorAll('canvas'))
      cell.classList.toggle('on', +cell.dataset.dir === stored && +cell.dataset.frame === pose.frame);
    $('renderPose').textContent = `${pose.action.frames} frames × 5 stored directions · 5–7 mirror 3–1 in the client`;
  }
  async downloadSheet() {
    const pose = this.hooks.pose(), render = this.renderFor(pose.action.id); if (!render) return;
    const strip = await this.strip(render.job, pose.action.id), c = strip.box, sw = c.x1 - c.x0, sh = c.y1 - c.y0;
    const sheet = document.createElement('canvas'); sheet.width = sw * pose.action.frames; sheet.height = sh * 5;
    const ctx = sheet.getContext('2d');
    strip.images.forEach((image, d) => { if (image) for (let f = 0; f < image.width / CELL; f++) this.layers(image, f, ctx, f * sw, d * sh, c, 1); });
    const link = document.createElement('a'); link.download = `${pose.info.id}-a${pad(pose.action.id)}-sheet.png`;
    link.href = sheet.toDataURL('image/png'); link.click();
  }

  // ---------- builds ----------
  chip(kind, text) { const chip = $('renderChip'); chip.dataset.kind = kind; chip.textContent = text; }
  async build(mode, coverage) {
    const pose = this.hooks.pose();
    try {
      await this.hooks.save();
      if (!this.hooks.ready()) throw new Error('Wait for Saved to disk before rendering.');
      const response = await fetch('api/build', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item: pose.info.id, mode, coverage, action: pose.action.id }) });
      const result = await response.json(); if (!response.ok) throw new Error(result.error);
      this.status = result; this.show(); clearTimeout(this.timer); this.timer = setTimeout(() => this.poll(), 1500);
    } catch (error) { $('buildStatus').textContent = error.message; this.chip('failed', error.message); }
  }
  // Auto-render: once the fit has been saved and left alone for 3 s, render the current animation if it is stale
  // or missing. One attempt per fit+pose, so a failing build is not retried in a loop.
  auto(pose, render, stale) {
    if (!$('renderAuto').checked || !stale || this.status.state === 'building') return;
    if (!this.hooks.ready() || performance.now() - this.hooks.edited() < 3000) return;
    const key = JSON.stringify([pose.info.id, pose.action.id, this.hooks.adjustments()]);
    if (key === this.autoKey) return;
    this.autoKey = key; this.build('build', 'action');
  }
  async poll() {
    clearTimeout(this.timer);
    try {
      const previous = this.status.state;
      this.status = await (await fetch('api/build')).json();
      this.show();
      if (previous === 'building' && this.status.state !== 'building' && this.status.item === this.item) await this.refresh();
    } catch (error) { $('buildStatus').textContent = error.message; }
    // Idle polling keeps auto-render responsive and notices builds started from another tab.
    this.timer = setTimeout(() => this.poll(), this.status.state === 'building' ? 1500 : 4000);
    if (this.status.state !== 'building') this.sync();
  }
  show() {
    const s = this.status, building = s.state === 'building', mine = building && s.item === this.item;
    $('buildItem').disabled = $('rebuildItem').disabled = $('renderGo').disabled = $('renderNow').disabled = building;
    $('renderProgress').hidden = !mine;
    const p = s.progress, elapsed = building ? Date.now() / 1000 - s.started : 0;
    if (building) {
      const share = p ? p.done / p.total : 0;
      $('renderBar').style.width = (p ? Math.max(2, share * 100) : 2) + '%';
      $('renderProgress').classList.toggle('waiting', !p?.done);
      const left = p?.done ? Math.max(0, elapsed / p.done * (p.total - p.done)) : null;
      const text = p ? `${p.done} of ${p.total} frames` + (left === null ? ' · starting Blender' : ` · about ${minutes(left)} left`) : `${minutes(elapsed)} so far`;
      if (mine) this.chip('busy', 'Rendering · ' + text);
      $('buildStatus').textContent = `Rendering ${s.item} · ${text}`;
    } else if (s.state === 'failed') {
      $('buildStatus').textContent = s.error;
      if (s.item === this.item) this.chip('failed', 'Render failed: ' + s.error);
    } else if (s.state === 'complete') {
      $('buildStatus').textContent = `${s.item}: ${s.unchanged ? 'no changed blocks' : 'rendered and validated'} · job ${s.job}`;
    }
    $('buildReview').hidden = !s.review; if (s.review) $('buildReview').href = s.review;
  }
}

function minutes(seconds) { return seconds < 90 ? `${Math.max(1, Math.round(seconds))} s` : `${Math.round(seconds / 60)} min`; }

// Union of visible pixels across every frame and direction, symmetric about the mirror axis so 5-7 line up.
function bounds(images) {
  let x0 = CELL, y0 = CELL, x1 = 0, y1 = 0;
  const scratch = document.createElement('canvas'), ctx = scratch.getContext('2d', { willReadFrequently: true });
  for (const image of images) {
    if (!image) continue;
    scratch.width = image.width; scratch.height = image.height; ctx.drawImage(image, 0, 0);
    const data = ctx.getImageData(0, 0, image.width, image.height).data;
    for (let y = 0; y < image.height; y++) for (let x = 0; x < image.width; x++) {
      if (!data[(y * image.width + x) * 4 + 3]) continue;
      const cx = x % CELL, cy = y % CELL;
      if (cx < x0) x0 = cx; if (cx > x1) x1 = cx; if (cy < y0) y0 = cy; if (cy > y1) y1 = cy;
    }
  }
  if (x1 < x0) return { x0: 0, y0: 0, x1: CELL, y1: CELL };
  x0 = Math.max(0, Math.min(x0, CELL - 1 - x1) - 4); x1 = CELL - x0;
  return { x0, y0: Math.max(0, y0 - 4), x1, y1: Math.min(CELL, y1 + 5) };
}

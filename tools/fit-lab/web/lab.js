// Fit lab: asset-pack items on the animated UO body (UO_Model3D v13), slot-level fit adjustments, CC4-style body
// face hiding under clothes, and a poke-through measure that mimics the renderer's body holdout.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { computeBoundsTree } from 'three-mesh-bvh';
import { FitPersistence } from './persistence.js';
import { same } from './history.mjs';
import { resolveFit, storedDirection } from './fit-rules.mjs';
import { pokeRule } from './poke-rules.mjs';
import { RenderPanel } from './render-panel.js';
import { dominantJoint } from './rigid-binding.mjs';
THREE.BufferGeometry.prototype.computeBoundsTree = computeBoundsTree;

const $ = id => document.getElementById(id);
const OCCLUDERS = new Set(['head', 'upper_arm', 'forearm', 'hand', 'thigh', 'shin', 'foot']);   // render_uo_layer.py
const W = 136, H = 120;
const clean = n => n.replace(/[\[\].:\/]/g, '');          // GLTFLoader's node-name sanitising
const html = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
// Blender (Z up) -> glTF (Y up): (x, y, z) -> (x, z, -y)
const C = new THREE.Matrix4().set(1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1);
const Cinv = C.clone().invert();

const state = { manifest: null, mapping: null, adjust: { parts: {}, items: {} }, slot: null, selected: null,
  shown: new Set(), action: 0, frame: 0, dir: 3, playing: false, baseline: {}, results: {} };
const items = new Map();                                   // id -> loaded item
const hiddenCache = new Map();
const loader = new GLTFLoader();
let persistence, renderPanel, measuring = false, slotRequest = 0, lastEdit = 0;
const preview = { frame: 0, dir: 3, playing: true, cycling: true, dirty: true, lastFrame: 0, lastDir: 0 };

// ---------- scene ----------
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(devicePixelRatio);
$('view').appendChild(renderer.domElement);
const scene = new THREE.Scene(); scene.background = new THREE.Color(0x0b0e11);
scene.add(new THREE.HemisphereLight(0xffffff, 0x334455, 1.6));
const sun = new THREE.DirectionalLight(0xffffff, 1.6); scene.add(sun);
const charRoot = new THREE.Group(); scene.add(charRoot);
const view = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 100);
const uoCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 100);
const controls = new OrbitControls(view, renderer.domElement);
const target = new THREE.WebGLRenderTarget(W, H);
target.texture.colorSpace = THREE.SRGBColorSpace; // readback pixels should match the visible viewport's brightness
const pixels = new Uint8Array(W * H * 4);
const flat = c => new THREE.MeshBasicMaterial({ color: c, side: THREE.DoubleSide });
const RED = flat(0xff0000), GREEN = flat(0x00ff00);
const DEPTH = new THREE.MeshBasicMaterial({colorWrite:false, depthWrite:true, side:THREE.DoubleSide});
const pushBack = metres => shader => {     // move the body `metres` away from the UO camera, as the renderer's margin does
  shader.vertexShader = shader.vertexShader.replace('#include <project_vertex>',
    '#include <project_vertex>\ngl_Position.z += ' + (2 * metres / (uoCam.far - uoCam.near)).toFixed(8) + ' * gl_Position.w;');
};
DEPTH.onBeforeCompile = pushBack(.01);
const pokeMaterials = new Map();           // allowance in metres -> red body material shifted back by it
function pokeMaterial(allowance) {
  const key = allowance.toFixed(4);
  if (!pokeMaterials.has(key)) { const m = flat(0xff0000); m.onBeforeCompile = pushBack(allowance); pokeMaterials.set(key, m); }
  return pokeMaterials.get(key);
}
let poseAction = null, poseDirection = null, currentPoseFrame = 0, referenceCanvas;
let body, bodyMesh, mixer, clips = {}, bodyBase, bodyTris, occluderTri, hiddenOverlay, bodyMeasure;
let reference, referenceImage, stabilizeHead = false, headBone;
const headPoses = new Map();

function setupCameras() {
  const cam = state.manifest.camera;
  const M = C.clone().multiply(new THREE.Matrix4().set(...cam.matrix_world.flat()));
  for (const c of [view, uoCam]) {
    M.decompose(c.position, c.quaternion, new THREE.Vector3());
    const hw = cam.ortho_scale / 2, hh = hw * H / W;
    Object.assign(c, { left: -hw, right: hw, top: hh, bottom: -hh }); c.updateProjectionMatrix();
  }
  sun.position.copy(uoCam.position);
  resetView();
}
function resetView() {
  view.position.copy(uoCam.position); view.quaternion.copy(uoCam.quaternion); view.zoom = 1.1;
  const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(view.quaternion);
  const p = new THREE.Vector3(0, 0.9, 0);
  controls.target.copy(view.position).addScaledVector(fwd, p.clone().sub(view.position).dot(fwd));
  resize(); controls.update();
}
function resize() {
  const r = $('view').getBoundingClientRect(); renderer.setSize(r.width, r.height);
  const hh = uoCam.top, hw = hh * r.width / r.height;
  Object.assign(view, { left: -hw, right: hw, top: hh, bottom: -hh }); view.updateProjectionMatrix();
}
addEventListener('resize', resize);

// ---------- loading ----------
async function getJSON(url) { const r = await fetch(url); if (!r.ok) throw new Error(url + ' ' + r.status); return r.json(); }

async function loadBody() {
  const g = await loader.loadAsync('data/body.glb');
  body = g.scene; charRoot.add(body); body.updateMatrixWorld(true);
  body.traverse(o => { if (o.isSkinnedMesh) bodyMesh = o; });
  bodyMesh.material = new THREE.MeshStandardMaterial({ color: 0x9c8f86, roughness: 0.8 });
  mixer = new THREE.AnimationMixer(body);
  for (const c of g.animations) clips[c.name] = c;
  headBone = bodyMesh.skeleton.bones.find(b => b.name.toLowerCase() === 'head');
  for (const clip of g.animations) {
    mixer.stopAllAction();
    const action = mixer.clipAction(clip); action.play(); action.paused = true;
    action.time = Math.min(...clip.tracks.map(t => t.times[0])); mixer.update(0);
    if (headBone) headPoses.set(clip.name, {position: headBone.position.clone(), quaternion: headBone.quaternion.clone()});
  }
  mixer.stopAllAction();
  // bind-pose positions in the glTF scene space, and triangles with their dominant bone
  const geo = bodyMesh.geometry, pos = geo.attributes.position;
  bodyBase = []; const v = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) bodyBase.push(v.fromBufferAttribute(pos, i).applyMatrix4(bodyMesh.bindMatrix).clone());
  bodyTris = Array.from(geo.index.array);
  const si = geo.attributes.skinIndex, sw = geo.attributes.skinWeight, bones = bodyMesh.skeleton.bones;
  occluderTri = [];
  for (let t = 0; t < bodyTris.length / 3; t++) {
    const w = {};
    for (let k = 0; k < 3; k++) { const vi = bodyTris[3 * t + k]; for (let j = 0; j < 4; j++) { const b = si.getComponent(vi, j); w[b] = (w[b] || 0) + sw.getComponent(vi, j); } }
    const best = +Object.keys(w).reduce((a, b) => w[a] >= w[b] ? a : b);
    occluderTri.push(OCCLUDERS.has(bones[best].name.replace(/[LR]$/, '')));
  }
  hiddenOverlay = new THREE.SkinnedMesh(geo.clone(), flat(0xff2050)); hiddenOverlay.geometry.setIndex([]);
  bodyMeasure = new THREE.SkinnedMesh(geo.clone(), RED);
  for (const m of [hiddenOverlay, bodyMeasure]) { bodyMesh.parent.add(m); m.position.copy(bodyMesh.position); m.quaternion.copy(bodyMesh.quaternion); m.bind(bodyMesh.skeleton, bodyMesh.bindMatrix); }
  bodyMeasure.visible = false;
}

async function loadItem(info) {
  if (items.has(info.id)) return items.get(info.id);
  const g = await loader.loadAsync('data/' + info.file); g.scene.updateMatrixWorld(true);
  const index = Object.fromEntries(bodyMesh.skeleton.bones.map((b, i) => [b.name, i]));
  const parts = [];
  g.scene.traverse(o => {
    if (!o.isMesh) return;
    const geo = o.geometry.clone(), bind = o.isSkinnedMesh ? o.bindMatrix : o.matrixWorld;
    const base = [], normals = [], v = new THREE.Vector3(), nm = new THREE.Matrix3().getNormalMatrix(bind);
    for (let i = 0; i < geo.attributes.position.count; i++) {
      base.push(v.fromBufferAttribute(geo.attributes.position, i).applyMatrix4(bind).clone());
      if (geo.attributes.normal) normals.push(v.fromBufferAttribute(geo.attributes.normal, i).applyMatrix3(nm).normalize().clone());
    }
    if (o.isSkinnedMesh) {                       // remap joints to the body skeleton by name
      const si = geo.attributes.skinIndex;
      for (let i = 0; i < si.count; i++) for (let j = 0; j < 4; j++) si.setComponent(i, j, index[o.skeleton.bones[si.getComponent(i, j)].name] ?? 0);
    }
    // Blender rigid binding chooses an anchor separately for each source mesh.
    // A paired item must not attach its right piece to the left piece's bone.
    const anchor = o.isSkinnedMesh ? dominantJoint(geo.attributes.skinIndex, geo.attributes.skinWeight) : undefined;
    const sideWeights = base.map((_, i) => {
      const weights = [0,0]; let total = 0;
      if (o.isSkinnedMesh) for (let j=0;j<4;j++) {
        const weight=geo.attributes.skinWeight.getComponent(i,j);
        const name=bodyMesh.skeleton.bones[geo.attributes.skinIndex.getComponent(i,j)]?.name || '';
        total+=weight;
        if (name.endsWith('L')) weights[0]+=weight;
        if (name.endsWith('R')) weights[1]+=weight;
      }
      return weights.map(w => total ? w/total : 0);
    });
    parts.push({ geo, base, normals, sideWeights, material: o.material,
      bone: bodyMesh.skeleton.bones[anchor ?? index[clean(info.dominant_bone)]] });
  });
  const center = new THREE.Box3().setFromPoints(parts.flatMap(p => p.base)).getCenter(new THREE.Vector3());
  const item = { info, parts, center, skinned: [], rigid: [] };
  for (const p of parts) {
    const s = new THREE.SkinnedMesh(p.geo, p.material); bodyMesh.parent.add(s);
    s.position.copy(bodyMesh.position); s.quaternion.copy(bodyMesh.quaternion); s.bind(bodyMesh.skeleton, bodyMesh.bindMatrix);
    s.frustumCulled = false; item.skinned.push(s);
    const r = new THREE.Mesh(p.geo.clone(), p.material); r.matrixAutoUpdate = false; r.frustumCulled = false; body.add(r); item.rigid.push(r);
  }
  items.set(info.id, item); applyFit(item); setVisible(item, false);
  return item;
}

// ---------- fit ----------
function partOf(info) { return (state.mapping?.parts || []).find(p => p.code === info.part) || {}; }
function fitFor(info) {
  const fit = resolveFit(state.adjust, partOf(info), info, poseAction, poseDirection);
  return {...fit, hide:fit.hide_body, itemOffset:[0,0,0]};
}
function baseFor(info) {
  const m = partOf(info), a = state.adjust.parts[info.part] || {};
  return {offset:a.offset ?? m.offset ?? [0,0,0], rotate:a.rotate ?? m.rotate ?? [0,0,0], scale:a.scale ?? m.scale ?? 1,
    depth_scale:a.depth_scale ?? m.depth_scale ?? 1,
    bind:a.bind ?? m.bind ?? 'skinned', hide:a.hide_body ?? m.hide_body ?? {enabled:true,outward:.02,inward:.01},
    itemOffset:state.adjust.items[info.id]?.offset ?? [0,0,0]};
}
function fitMatrix(item) {
  const f = fitFor(item.info), o = f.offset.map((x, i) => x + f.itemOffset[i]);
  const off = new THREE.Vector3(o[0], o[1], o[2]).applyMatrix4(C);
  const R = new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(...f.rotate.map(THREE.MathUtils.degToRad), 'ZYX'));
  const Rg = C.clone().multiply(R).multiply(Cinv);
  return new THREE.Matrix4().makeTranslation(item.center.x + off.x, item.center.y + off.y, item.center.z + off.z)
    .multiply(Rg).multiply(C.clone().multiply(new THREE.Matrix4().makeScale(f.scale, f.scale*f.depth_scale, f.scale)).multiply(Cinv))
    .multiply(new THREE.Matrix4().makeTranslation(-item.center.x, -item.center.y, -item.center.z));
}
function applyFit(item) {
  const M = fitMatrix(item), N = new THREE.Matrix3().getNormalMatrix(M), toBody = bodyMesh.bindMatrix.clone().invert();
  const sides = fitFor(item.info).sides;
  const offsets = ['left','right'].map(side => new THREE.Vector3(...(sides[side] || [0,0,0])).applyMatrix4(C));
  item.world = [];
  item.parts.forEach((p, k) => {
    const pos = p.geo.attributes.position, nrm = p.geo.attributes.normal, w = [];
    for (let i = 0; i < pos.count; i++) {
      const v = p.base[i].clone().applyMatrix4(M);
      offsets.forEach((offset, side) => v.addScaledVector(offset, p.sideWeights[i][side]));
      w.push(v);
      const l = v.clone().applyMatrix4(toBody); pos.setXYZ(i, l.x, l.y, l.z);
      if (nrm && p.normals[i]) { const n = p.normals[i].clone().applyMatrix3(N).normalize(); nrm.setXYZ(i, n.x, n.y, n.z); }
    }
    pos.needsUpdate = true; if (nrm) nrm.needsUpdate = true; p.geo.computeBoundingSphere();
    const rg = item.rigid[k].geometry, rp = rg.attributes.position;
    w.forEach((v, i) => rp.setXYZ(i, v.x, v.y, v.z)); rp.needsUpdate = true; rg.computeBoundingSphere();
    item.world.push(w);
  });
  item.bvh = null;
}
function setVisible(item, on) {
  const rigid = fitFor(item.info).bind === 'rigid';
  item.skinned.forEach(m => m.visible = on && !rigid); item.rigid.forEach(m => m.visible = on && rigid);
}

// ---------- CC4-style hide-under-clothes ----------
const COVER = { enabled: true, outward: 0.05, inward: 0.03 };   // 'under the item' for the poke measure
function hiddenFor(item) { const h = fitFor(item.info).hide; return h.enabled ? facesNear(item, h) : new Set(); }
function coveredFor(item) { return facesNear(item, COVER); }
function facesNear(item, h) {
  const key = item.info.id + JSON.stringify(h) + JSON.stringify(fitFor(item.info));
  if (hiddenCache.has(key)) return hiddenCache.get(key);
  if (!item.bvh) {
    const all = item.world.flat(), geo = new THREE.BufferGeometry().setFromPoints(all), idx = [];
    let base = 0;
    item.parts.forEach((p, k) => { const ix = p.geo.index ? p.geo.index.array : [...Array(p.base.length).keys()]; for (const i of ix) idx.push(i + base); base += p.base.length; });
    geo.setIndex(idx); geo.computeBoundsTree(); item.bvh = geo.boundsTree;
  }
  const hidden = new Set(), ray = new THREE.Ray(), a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), n = new THREE.Vector3();
  for (let t = 0; t < bodyTris.length / 3; t++) {
    a.copy(bodyBase[bodyTris[3 * t]]); b.copy(bodyBase[bodyTris[3 * t + 1]]); c.copy(bodyBase[bodyTris[3 * t + 2]]);
    n.subVectors(b, a).cross(c.clone().sub(a)).normalize();
    const centre = a.add(b).add(c).multiplyScalar(1 / 3);
    ray.origin.copy(centre).addScaledVector(n, -h.inward); ray.direction.copy(n);
    const hit = item.bvh.raycastFirst(ray, THREE.DoubleSide);
    if (hit && hit.distance <= h.inward + h.outward) hidden.add(t);
  }
  hiddenCache.set(key, hidden);
  return hidden;
}
function bodyIndex(hidden, under) {         // under: only limb/head faces lying under the item (poke candidates)
  const idx = [];
  for (let t = 0; t < bodyTris.length / 3; t++) if (!hidden.has(t) && (!under || (occluderTri[t] && under.has(t)))) idx.push(bodyTris[3 * t], bodyTris[3 * t + 1], bodyTris[3 * t + 2]);
  return idx;
}
function updateBody() {
  const hidden = new Set();
  for (const id of state.shown) { const it = items.get(id); if (it) for (const t of hiddenFor(it)) hidden.add(t); }
  bodyMesh.geometry.setIndex(bodyIndex(hidden, null));
  const over = []; for (const t of hidden) over.push(bodyTris[3 * t], bodyTris[3 * t + 1], bodyTris[3 * t + 2]);
  hiddenOverlay.geometry.setIndex(over); hiddenOverlay.visible = $('showHidden').checked;
  $('status').textContent = `${hidden.size} body faces hidden`;
}

// ---------- pose ----------
function setPose(actionIdx, frame, dir) {
  const act = state.manifest.actions[actionIdx], clip = clips[act.name];
  poseAction = act.id; poseDirection = dir; currentPoseFrame = frame;
  let refit = false;
  for (const item of items.values()) {
    const signature = JSON.stringify(fitFor(item.info));
    if (item.poseFit !== signature) { item.poseFit = signature; applyFit(item); refit = true; }
  }
  if (refit) { hiddenCache.clear(); updateBody(); }
  mixer.stopAllAction();
  if (clip) {
    const a = mixer.clipAction(clip); a.play(); a.paused = true;
    const t0 = Math.min(...clip.tracks.map(t => t.times[0]));
    a.time = Math.min(clip.duration, t0 + frame * state.manifest.frame_step / state.manifest.fps); mixer.update(0);
  }
  if (stabilizeHead && headBone && headPoses.has(act.name)) {
    const pose = headPoses.get(act.name);
    headBone.position.copy(pose.position); headBone.quaternion.copy(pose.quaternion);
  }
  const stored = dir <= 4 ? dir : 8 - dir;
  charRoot.rotation.y = -stored * Math.PI / 4;
  charRoot.updateMatrixWorld(true);
  const inv = body.matrixWorld.clone().invert();
  for (const it of items.values()) {               // rigid items: bone location + rotation, no animated scale
    it.parts.forEach((part, k) => {
      if (!part.bone) return;
      const rest = bodyMesh.skeleton.boneInverses[bodyMesh.skeleton.bones.indexOf(part.bone)].clone().invert();
      const now = inv.clone().multiply(part.bone.matrixWorld);
      it.rigid[k].matrix.copy(noScale(now).multiply(noScale(rest).invert()));
    });
  }
  scene.updateMatrixWorld(true);
  return dir > 4;
}
function noScale(m) { const p = new THREE.Vector3(), q = new THREE.Quaternion(), s = new THREE.Vector3(); m.decompose(p, q, s); return new THREE.Matrix4().compose(p, q, new THREE.Vector3(1, 1, 1)); }

// ---------- offscreen UO-camera renders ----------
function renderTarget() { renderer.setRenderTarget(target); renderer.clear(); renderer.render(scene, uoCam); renderer.readRenderTargetPixels(target, 0, 0, W, H, pixels); renderer.setRenderTarget(null); return pixels; }
function soloRender(item, mode) {        // mode: 'mask' | 'poke' | 'look'
  const background = scene.background;
  if (mode === 'look') scene.background = null;
  const bodyIndexBefore = bodyMesh.geometry.index;
  const keep = []; scene.traverse(o => { if (o.isMesh) { keep.push([o, o.visible, o.material]); o.visible = false; } });
  const rigid = fitFor(item.info).bind === 'rigid', meshes = rigid ? item.rigid : item.skinned;
  meshes.forEach(m => { m.visible = true; if (mode !== 'look') m.material = GREEN; });
  if (mode === 'poke') {                 // the renderer's holdout rule for this item, see poke-rules.mjs
    const rule = pokeRule(fitFor(item.info), partOf(item.info).studio_part);
    bodyMeasure.geometry.setIndex(rule.measure ? (rule.faces === 'all' ? bodyIndex(new Set(), null) : bodyIndex(hiddenFor(item), coveredFor(item))) : []);
    bodyMeasure.material = pokeMaterial(rule.allowance); bodyMeasure.visible = rule.measure;
  }
  if (mode === 'look' && $('previewBase').value === 'model') { bodyMesh.geometry.setIndex(bodyIndex(hiddenFor(item), null)); bodyMesh.visible = true; }
  let out = renderTarget().slice();
  if (mode === 'look' && $('previewBase').value !== 'model' && fitFor(item.info).occlusion !== 'none') {
    const free = out;
    const occlusion = fitFor(item.info).occlusion;
    // Use all potential occluders, not just faces near the item at rest.
    const hidden = occlusion === 'body' ? new Set() : hiddenFor(item), maskIndices = [];
    for (let t = 0; t < bodyTris.length / 3; t++) if (!hidden.has(t) &&
      (occlusion === 'body' || occluderTri[t])) maskIndices.push(...bodyTris.slice(t*3,t*3+3));
    bodyMeasure.geometry.setIndex(maskIndices); bodyMeasure.material = DEPTH; bodyMeasure.visible = true; bodyMeasure.renderOrder = -1;
    out = renderTarget().slice();
    const tile = reference?.tiles[`${poseAction},${currentPoseFrame},${storedDirection(poseDirection)}`];
    if (tile && referenceCanvas) {
      const alpha = referenceCanvas.getContext('2d').getImageData(tile[0]*W,tile[1]*H,W,H).data;
      for (let y=0;y<H;y++) for(let x=0;x<W;x++) if (!alpha[((H-1-y)*W+x)*4+3]) {
        const pixel=(y*W+x)*4; out.set(free.subarray(pixel,pixel+4),pixel);
      }
    }
  }
  for (const [o, v, m] of keep) { o.visible = v; o.material = m; }
  meshes.forEach((m, k) => m.material = item.parts[k].material);
  bodyMeasure.visible = false; bodyMeasure.material = RED;
  bodyMesh.geometry.setIndex(bodyIndexBefore);
  scene.background = background;
  return out;
}
function pokeCount(item) {
  const mask = soloRender(item, 'mask'), both = soloRender(item, 'poke'); let n = 0; const where = [];
  for (let i = 0; i < W * H; i++) if (mask[4 * i + 1] > 128 && both[4 * i] > 128 && both[4 * i + 1] < 128) { n++; where.push(i); }
  return { n, where };
}

// ---------- UI ----------
function slider(parent, label, value, min, max, step, unit, onChange) {
  const row = document.createElement('div'); row.className = 'slider';
  row.innerHTML = `<label>${label}</label><input type="range" min="${min}" max="${max}" step="${step}" value="${value}"><span>${(+value).toFixed(step < 1 ? 1 : 0)}${unit}</span>`;
  const input = row.querySelector('input'), out = row.querySelector('span');
  input.setAttribute('aria-label', label);
  input.oninput = () => { out.textContent = (+input.value).toFixed(step < 1 ? 1 : 0) + unit; onChange(+input.value); };
  input.onchange = () => record(label);
  parent.appendChild(row);
}
function part() { return state.adjust.parts[state.selected.part] ??= {}; }
function record(label) { persistence?.commit(state.adjust, `${state.slot}: ${label}`); }
function changed() {
  hiddenCache.clear(); lastEdit = performance.now();
  for (const it of items.values()) applyFit(it);
  for (const it of items.values()) setVisible(it, state.shown.has(it.info.id));
  updateBody(); drawSheet();
  persistence?.edit(state.adjust);
}
function buildPanels() {
  const info = state.selected; if (!info) return;
  const f = baseFor(info), fit = $('fit'), hide = $('hide');
  $('partCode').textContent = `${info.part} · ${partOf(info).name || ''} · layer ${partOf(info).uo_layer ?? '—'}`;
  fit.innerHTML = ''; hide.innerHTML = '';
  ['X', 'Y', 'Z'].forEach((ax, i) => slider(fit, 'Offset ' + ax, f.offset[i] * 100, -10, 10, 0.1, ' cm', v => { const o = [...baseFor(info).offset]; o[i] = v / 100; part().offset = o; changed(); }));
  ['X', 'Y', 'Z'].forEach((ax, i) => slider(fit, 'Rotate ' + ax, f.rotate[i], -30, 30, 1, '°', v => { const r = [...baseFor(info).rotate]; r[i] = v; part().rotate = r; changed(); }));
  slider(fit, 'Scale', f.scale * 100, 80, 125, 1, '%', v => { part().scale = v / 100; changed(); });
  slider(fit, 'Front/back depth', f.depth_scale * 100, 50, 250, 1, '%', v => { part().depth_scale = v / 100; changed(); });
  const bind = document.createElement('label');
  bind.innerHTML = `Binding <select><option value="skinned">skinned (deforms)</option><option value="rigid">rigid (follows one bone)</option></select>`;
  bind.querySelector('select').value = f.bind; bind.querySelector('select').onchange = e => { part().bind = e.target.value; changed(); record('Binding'); };
  fit.appendChild(bind);
  const sub = document.createElement('p'); sub.className = 'hint'; sub.textContent = `This item only (${info.id}):`; fit.appendChild(sub);
  ['X', 'Y', 'Z'].forEach((ax, i) => slider(fit, 'Item ' + ax, f.itemOffset[i] * 100, -5, 5, 0.1, ' cm', v => {
    const o = [...baseFor(info).itemOffset]; o[i] = v / 100; (state.adjust.items[info.id] ??= {}).offset = o; changed(); }));
  const sideHint = document.createElement('p'); sideHint.className='hint';
  sideHint.textContent='Separate sides for this item (character left/right, before animation). Shared fit still applies to both.'; fit.appendChild(sideHint);
  for (const side of ['left','right']) {
    const values=state.adjust.items[info.id]?.sides?.[side] || [0,0,0];
    ['X','Y','Z'].forEach((axis,i) => slider(fit, `${side === 'left' ? 'Left' : 'Right'} ${axis}`, values[i]*100,-15,15,.1,' cm', value => {
      const entry=state.adjust.items[info.id] ??= {}; const sides=entry.sides ??= {};
      const offset=[...(sides[side] || [0,0,0])]; offset[i]=value/100; sides[side]=offset; changed();
    }));
    const reset=document.createElement('button'); reset.textContent=`Reset ${side} offset`;
    reset.onclick=() => { if(state.adjust.items[info.id]?.sides) delete state.adjust.items[info.id].sides[side]; changed(); record(`Reset ${side}`); buildPanels(); }; fit.appendChild(reset);
  }
  const on = document.createElement('label');
  on.innerHTML = `<input type="checkbox" ${f.hide.enabled ? 'checked' : ''}> Hide body under this slot`;
  on.querySelector('input').onchange = e => { part().hide_body = { ...baseFor(info).hide, enabled: e.target.checked }; changed(); record('Hide body'); };
  hide.appendChild(on);
  slider(hide, 'Outward', f.hide.outward * 100, 0, 8, 0.1, ' cm', v => { part().hide_body = { ...baseFor(info).hide, outward: v / 100 }; changed(); });
  slider(hide, 'Inward', f.hide.inward * 100, 0, 5, 0.1, ' cm', v => { part().hide_body = { ...baseFor(info).hide, inward: v / 100 }; changed(); });
  buildScopedPanel();
}
function correctionSelector() {
  const target = $('scopeTarget').value, when = $('scopeWhen').value, selector = {target};
  if (target !== 'pack') selector.key = target === 'item' ? state.selected.id : target === 'slot' ? state.slot : $('scopeGroup').value;
  if (when === 'action' || when === 'pose') selector.action = state.manifest.actions[state.action].id;
  if (when === 'direction' || when === 'pose') selector.direction = storedDirection(state.dir);
  return selector;
}
function selectedCorrection(create=false) {
  const selector = correctionSelector();
  if (selector.target === 'group' && !selector.key) return null;
  let rule = state.adjust.corrections?.find(r => ['target','key','action','direction'].every(k => r[k] === selector[k]));
  if (!rule && create) { rule = {...selector, fit:{}}; (state.adjust.corrections ??= []).push(rule); }
  return rule;
}
function buildScopedPanel() {
  if (!state.selected) return;
  const group = $('scopeGroup').value;
  $('scopeGroup').replaceChildren(...Object.keys(state.adjust.groups || {}).sort().map(name => new Option(name,name)));
  if (state.adjust.groups?.[group]) $('scopeGroup').value = group;
  const selector = correctionSelector(), fit = selectedCorrection()?.fit || {}, box = $('scopeFit');
  const label = `${selector.target}: ${selector.key || 'all items'} · animation ${selector.action ?? 'all'} · direction ${selector.direction ?? 'all'}`;
  $('scopeLabel').textContent = label + ('direction' in selector ? ' (mirrored partner shares this correction)' : '') + ' · deltas from base fit';
  box.replaceChildren(); box.inert = selector.target === 'group' && !selector.key;
  const commit = () => { persistence.commit(state.adjust, label); $('removeCorrection').disabled=!selectedCorrection(); };
  const addSlider = (name,value,min,max,step,unit,update) => {
    slider(box,name,value,min,max,step,unit,v => { const rule=selectedCorrection(true); if(rule) {update(rule.fit,v); changed();} });
    box.lastElementChild.querySelector('input').onchange = commit;
  };
  ['X','Y','Z'].forEach((axis,i) => addSlider('Correction '+axis,(fit.offset?.[i] || 0)*100,-30,30,.1,' cm',(f,v) => {(f.offset ??= [0,0,0])[i]=v/100;}));
  ['X','Y','Z'].forEach((axis,i) => addSlider('Correction rotate '+axis,fit.rotate?.[i] || 0,-90,90,1,'°',(f,v) => {(f.rotate ??= [0,0,0])[i]=v;}));
  addSlider('Correction scale',(fit.scale ?? 1)*100,50,150,1,'%',(f,v) => {f.scale=v/100;});
  addSlider('Correction depth',(fit.depth_scale ?? 1)*100,50,250,1,'%',(f,v) => {f.depth_scale=v/100;});
  const labelEl=document.createElement('label'), select=document.createElement('select'); labelEl.textContent='Body masking ';
  for(const [value,text] of [['','Inherit'],['clothing','Clothing: limbs/head'],['body','Attachment: whole body'],['none','No body masking']]) select.add(new Option(text,value));
  select.value=fit.occlusion || ''; select.onchange=() => {const rule=selectedCorrection(true); if(!rule)return; if(select.value)rule.fit.occlusion=select.value; else delete rule.fit.occlusion; changed();commit();};
  labelEl.append(select);box.append(labelEl);
  $('removeCorrection').disabled=!selectedCorrection();
}
function scopeChanged() {
  if ($('scopeWhen').value !== 'all') {
    state.playing=false; $('play').textContent='Play'; preview.playing=preview.cycling=false;
    $('previewPlay').checked=$('previewCycle').checked=false; preview.frame=state.frame;preview.dir=state.dir;
  }
  buildScopedPanel(); frameUI();
}
async function selectSlot(slot) {
  const request = ++slotRequest;
  const list = state.manifest.items.filter(i => i.slot === slot);
  $('slotInfo').textContent = `${list.length} items · part ${list[0]?.part}`;
  await Promise.all(list.map(loadItem));
  if (request !== slotRequest) return;
  state.slot = slot;
  state.shown = new Set([list[0].id]); state.selected = list[0];
  renderItems(); for (const it of items.values()) setVisible(it, state.shown.has(it.info.id));
  buildPanels(); updateBody(); buildSheet(); drawSheet(); renderMeasureTable(); renderPanel?.sync();
}
function renderItems() {
  const box = $('items'); box.innerHTML = '';
  for (const info of state.manifest.items.filter(i => i.slot === state.slot)) {
    const row = document.createElement('div'); row.className = 'item' + (state.selected?.id === info.id ? ' on' : '');
    row.innerHTML = `<input type="checkbox" title="Show in the 3D view" aria-label="Show ${html(info.id)} in 3D" ${state.shown.has(info.id) ? 'checked' : ''}><div><div class="name">${html(info.family || info.id)}</div><div class="code">${html(info.id)}</div></div>`;
    row.querySelector('input').onclick = e => { e.stopPropagation(); e.target.checked ? state.shown.add(info.id) : state.shown.delete(info.id); changed(); };
    row.onclick = () => selectItem(info);
    box.appendChild(row);
  }
}
function selectItem(info) {
  state.selected = info; renderItems(); buildPanels();
  for (const [id, card] of previewCards) card.canvas.parentElement.classList.toggle('on', id === info.id);
  renderPanel?.sync();
}
function drawSheet() { preview.dirty = true; }
const previewCards = new Map();
function buildSheet() {
  previewCards.clear(); $('sheet').replaceChildren();
  for (const info of state.manifest.items.filter(i => i.slot === state.slot)) {
    const figure = document.createElement('figure'), canvas = document.createElement('canvas'), caption = document.createElement('figcaption');
    canvas.width = W; canvas.height = H; canvas.setAttribute('aria-label', info.id + ' live preview');
    figure.title = info.id; figure.append(canvas, caption); $('sheet').appendChild(figure);
    figure.classList.toggle('on', state.selected?.id === info.id); canvas.onclick = () => selectItem(info);
    caption.textContent = info.family || info.id;
    previewCards.set(info.id, { canvas, caption, info });
  }
}
function renderSheet() {
    const mirror = setPose(state.action, preview.frame, preview.dir);
    const bounds = $('sheet').getBoundingClientRect();
    for (const { info, canvas: cv, caption } of previewCards.values()) {
      const rect = cv.getBoundingClientRect();
      if (rect.right < bounds.left || rect.left > bounds.right) continue;
      const it = items.get(info.id); if (!it) continue;
      const look = soloRender(it, 'look'), { n, where } = $('previewPokes').checked ? pokeCount(it) : {n: null, where: []};
      for (const i of where) look.set([255, 61, 242, 255], 4 * i);
      cv.classList.toggle('mirror', mirror);
      const img = new ImageData(W, H);
      for (let y = 0; y < H; y++) img.data.set(look.subarray((H - 1 - y) * W * 4, (H - y) * W * 4), y * W * 4);
      const ctx = cv.getContext('2d'); ctx.clearRect(0, 0, W, H);
      const tile = reference?.tiles[`${state.manifest.actions[state.action].id},${preview.frame},${preview.dir > 4 ? 8 - preview.dir : preview.dir}`];
      if ($('previewBase').value === 'original' && tile && referenceImage) ctx.drawImage(referenceImage, tile[0] * W, tile[1] * H, W, H, 0, 0, W, H);
      const layer = document.createElement('canvas'); layer.width = W; layer.height = H;
      layer.getContext('2d').putImageData(img, 0, 0); ctx.drawImage(layer, 0, 0);
      caption.textContent = `${info.family || info.id}${n === null ? '' : ` · ${n} poke px`}`;
    }
    $('previewPose').textContent = `Direction ${preview.dir} · frame ${preview.frame + 1}/${state.manifest.actions[state.action].frames}`;
    setPose(state.action, state.frame, state.dir); preview.dirty = false;
}
async function measure() {
  if (measuring) return;
  measuring = true; persistence.suspended = true;
  const panels = ['left', 'right', 'bar', 'previewBar', 'topActions']; panels.forEach(id => $(id).inert = true);
  try {
  const acts = [...document.querySelectorAll('#measureActions input:checked')].map(i => +i.value);
  const list = state.manifest.items.filter(i => i.slot === state.slot).map(i => items.get(i.id));
  const totals = Object.fromEntries(list.map(it => [it.info.id, 0]));
  let done = 0; const jobs = acts.reduce((s, a) => s + state.manifest.actions[a].frames * 5, 0);
  for (const a of acts) for (let f = 0; f < state.manifest.actions[a].frames; f++) for (let d = 0; d < 5; d++) {
    setPose(a, f, d);
    for (const it of list) totals[it.info.id] += pokeCount(it).n;
    if (++done % 10 === 0) { $('status').textContent = `measuring ${done}/${jobs} poses…`; await new Promise(r => setTimeout(r)); }
  }
  for (const id in totals) { state.baseline[id] ??= totals[id]; state.results[id] = totals[id]; }
  $('status').textContent = `measured ${jobs} poses × ${list.length} items`;
  renderMeasureTable(); setPose(state.action, state.frame, state.dir);
  } catch (error) { $('status').textContent = 'Measurement failed: ' + error.message; }
  finally {
    measuring = false; persistence.suspended = false; panels.forEach(id => $(id).inert = false);
    updateBody(); setPose(state.action, state.frame, state.dir); drawSheet();
  }
}
function renderMeasureTable() {
  const rows = state.manifest.items.filter(i => i.slot === state.slot && i.id in state.results);
  let sumB = 0, sumN = 0;
  const body = rows.map(i => { const b = state.baseline[i.id], n = state.results[i.id]; sumB += b; sumN += n;
    return `<tr><td title="${html(i.id)}">${html(i.family || i.id)}</td><td>${b}</td><td>${n}</td><td class="${n < b ? 'better' : n > b ? 'worse' : ''}">${n - b}</td></tr>`; }).join('');
  $('results').innerHTML = rows.length ? `<tr><th>item</th><th>first</th><th>now</th><th>Δ</th></tr>${body}<tr><th>slot</th><th>${sumB}</th><th>${sumN}</th><th class="${sumN < sumB ? 'better' : sumN > sumB ? 'worse' : ''}">${sumN - sumB}</th></tr>` : '';
}
function frameUI() {
  const act = state.manifest.actions[state.action];
  $('frame').max = act.frames - 1; state.frame = Math.min(state.frame, act.frames - 1); $('frame').value = state.frame;
  $('frameLabel').textContent = `${state.frame + 1}/${act.frames}`;
  [...$('dirs').children].forEach((b, d) => b.classList.toggle('on', d === state.dir));
  renderer.domElement.style.transform = state.dir > 4 ? 'scaleX(-1)' : '';
  setPose(state.action, state.frame, state.dir); drawSheet();
  buildScopedPanel(); renderPanel?.sync();
}

async function loadAssets() {
  $('loadAssets').disabled = true;
  try {
    const response = await fetch('api/assets', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({directory: $('assetDirectory').value, slot: state.slot, part: state.selected.part})});
    const result = await response.json(); if (!response.ok) throw new Error(result.error);
    for (const info of result.items) if (!state.manifest.items.some(i => i.id === info.id)) state.manifest.items.push(info);
    await selectSlot(state.slot);
    $('packName').textContent = `${state.manifest.pack} · ${state.manifest.items.length} items · ${state.manifest.model}`;
    $('assetStatus').textContent = `${result.items.length} compatible GLBs loaded. ` + result.skipped.map(i => `${i.file}: ${i.reason}`).join('; ');
    if (!result.items.length && !result.skipped.length) $('assetStatus').textContent = 'No GLBs found. Export fitted models as GLB first.';
  } catch (error) { $('assetStatus').textContent = error.message; }
  finally { $('loadAssets').disabled = false; }
}
let cancelAB = false, reportURL;
function paintComparison(ctx, pixels, action, frame, dir, x, y) {
  const tile = reference?.tiles[`${state.manifest.actions[action].id},${frame},${dir}`];
  if (tile && referenceImage) ctx.drawImage(referenceImage, tile[0] * W, tile[1] * H, W, H, x, y, W, H);
  const image = new ImageData(W, H), layer = document.createElement('canvas'); layer.width = W; layer.height = H;
  for (let line = 0; line < H; line++) image.data.set(pixels.subarray((H - 1 - line) * W * 4, (H - line) * W * 4), line * W * 4);
  layer.getContext('2d').putImageData(image, 0, 0); ctx.drawImage(layer, x, y);
}
async function headAB() {
  if (measuring) return;
  const actions = [...document.querySelectorAll('#measureActions input:checked')].map(i => +i.value);
  if (!actions.length) { $('abStatus').textContent = 'Select at least one action.'; return; }
  measuring = true; cancelAB = false; persistence.suspended = true;
  const previous = stabilizeHead;
  const previousBase = $('previewBase').value; $('previewBase').value = 'none';
  const slotNames = [...new Set(state.manifest.items.map(i => i.slot))].sort();
  const contact = document.createElement('canvas'); contact.width = W * 6; contact.height = slotNames.length * (H + 55);
  const context = contact.getContext('2d'); context.fillStyle = '#14181d'; context.fillRect(0, 0, contact.width, contact.height);
  context.font = '10px sans-serif'; context.fillStyle = '#dfe5ec';
  $('abImages').replaceChildren(contact); $('abImageDownload').hidden = true;
  const panels = ['left', 'bar', 'previewBar', 'topActions']; panels.forEach(id => $(id).inert = true);
  const disabled = [...$('right').querySelectorAll('button,input,select')].map(el => [el, el.disabled]);
  disabled.forEach(([el]) => el.disabled = el.id !== 'cancelAB'); $('cancelAB').hidden = false;
  const report = {created: new Date().toISOString(), complete: false, actions: actions.map(a => state.manifest.actions[a].id),
    adjustments: structuredClone(state.adjust), items: []};
  $('abResults').innerHTML = '<tr><th>Slot / item</th><th>Before</th><th>After</th><th>Δ</th></tr>';
  try {
    for (const slot of slotNames) {
      const list = state.manifest.items.filter(i => i.slot === slot).sort((a, b) => a.id.localeCompare(b.id)).slice(0, 3);
      for (const info of list) {
        if (cancelAB) break;
        const item = await loadItem(info), row = {id: info.id, slot, before: 0, after: 0, poses: 0};
        let largest = -1, pair;
        for (const action of actions) {
          for (let frame = 0; frame < state.manifest.actions[action].frames && !cancelAB; frame++) {
            for (let dir = 0; dir < 5; dir++) {
              stabilizeHead = false; setPose(action, frame, dir); row.before += pokeCount(item).n;
              const beforePixels = soloRender(item, 'look');
              stabilizeHead = true; setPose(action, frame, dir); row.after += pokeCount(item).n;
              const afterPixels = soloRender(item, 'look');
              let changedPixels = 0;
              for (let pixel = 0; pixel < beforePixels.length; pixel += 4) {
                if (beforePixels[pixel + 3] !== afterPixels[pixel + 3] ||
                    ((beforePixels[pixel + 3] || afterPixels[pixel + 3]) &&
                     (beforePixels[pixel] !== afterPixels[pixel] || beforePixels[pixel + 1] !== afterPixels[pixel + 1] || beforePixels[pixel + 2] !== afterPixels[pixel + 2]))) changedPixels++;
              }
              if (changedPixels > largest) { largest = changedPixels; pair = {beforePixels, afterPixels, action, frame, dir}; }
              row.poses++;
            }
            $('abStatus').textContent = `A/B ${slot} · ${info.family || info.id} · action ${state.manifest.actions[action].id}, frame ${frame + 1} · ${report.items.length} items finished`;
            await new Promise(resolve => setTimeout(resolve, 0));
          }
          if (cancelAB) break;
        }
        report.items.push(row);
        if (pair) {
          row.comparison = {action: state.manifest.actions[pair.action].id, frame: pair.frame, direction: pair.dir, changed_pixels: largest};
          const x = list.indexOf(info) * W * 2, y = slotNames.indexOf(slot) * (H + 55);
          context.fillText(`${slot}: ${info.family || info.id}`, x + 2, y + 12, W * 2 - 4);
          context.fillText(`Action ${state.manifest.actions[pair.action].id}, frame ${pair.frame + 1}, dir ${pair.dir} · ${largest} changed px`, x + 2, y + 25, W * 2 - 4);
          context.fillText('Before', x + 2, y + 40); context.fillText('Stabilized', x + W + 2, y + 40);
          paintComparison(context, pair.beforePixels, pair.action, pair.frame, pair.dir, x, y + 45);
          paintComparison(context, pair.afterPixels, pair.action, pair.frame, pair.dir, x + W, y + 45);
        }
        const tr = document.createElement('tr');
        for (const value of [`${slot}: ${info.family || info.id}`, row.before, row.after, row.after - row.before]) {
          const td = document.createElement('td'); td.textContent = value; tr.appendChild(td);
        }
        $('abResults').appendChild(tr);
      }
      if (cancelAB) break;
    }
    report.complete = !cancelAB;
    $('abStatus').textContent = `${cancelAB ? 'Stopped (partial)' : 'Complete'}: ${report.items.length} items. Before = original motion; after = local head stabilized. Counts are preview estimates.`;
  } catch (error) { $('abStatus').textContent = 'A/B failed: ' + error.message; }
  finally {
    if (reportURL) URL.revokeObjectURL(reportURL);
    reportURL = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], {type: 'application/json'}));
    $('abDownload').href = reportURL; $('abDownload').hidden = false;
    // A visible report also lets the result be copied without depending on a browser download.
    $('abJSON').textContent = JSON.stringify(report, null, 2);
    $('abImageDownload').href = contact.toDataURL('image/png'); $('abImageDownload').hidden = false;
    $('previewBase').value = previousBase;
    stabilizeHead = previous; measuring = false; persistence.suspended = false;
    panels.forEach(id => $(id).inert = false); disabled.forEach(([el, value]) => el.disabled = value);
    $('cancelAB').hidden = true; updateBody(); frameUI();
  }
}

function setupTabs() {
  const tabs = [...document.querySelectorAll('#tabs button')];
  const show = name => {
    for (const tab of tabs) tab.setAttribute('aria-selected', tab.dataset.tab === name);
    for (const panel of document.querySelectorAll('#right .tab')) panel.hidden = panel.dataset.tab !== name;
    try { localStorage.setItem('fit-lab:tab', name); } catch {}
  };
  tabs.forEach(tab => tab.onclick = () => show(tab.dataset.tab));
  let saved = 'fit'; try { saved = localStorage.getItem('fit-lab:tab') || 'fit'; } catch {}
  show(tabs.some(t => t.dataset.tab === saved) ? saved : 'fit');
}

async function main() {
  state.manifest = await getJSON('data/manifest.json');
  state.mapping = await getJSON('api/mapping').catch(() => null);
  const saved = await getJSON('api/state');
  persistence = new FitPersistence(`fit-lab:${location.origin}:${state.manifest.pack}`, saved, value => {
    state.adjust = value; buildPanels(); changed();
  });
  state.adjust = persistence.value;
  $('packName').textContent = `${state.manifest.pack} · ${state.manifest.items.length} items · ${state.manifest.model}`;
  setupCameras(); await loadBody();
  try {
    reference = await getJSON('data/reference.json'); referenceImage = new Image();
    referenceImage.src = 'data/' + reference.image; await referenceImage.decode();
    referenceCanvas = document.createElement('canvas'); referenceCanvas.width = referenceImage.width; referenceCanvas.height = referenceImage.height;
    referenceCanvas.getContext('2d', {willReadFrequently:true}).drawImage(referenceImage,0,0);
    $('referenceStatus').textContent = 'Original UO reference loaded · depth masking enabled · final Blender edge correction and push-out may differ.';
  } catch {
    $('previewBase').querySelector('[value=original]').disabled = true;
    $('referenceStatus').textContent = 'Original sprite unavailable. Run the pack export again to extract the canonical reference.';
  }
  const slots = [...new Set(state.manifest.items.map(i => i.slot))];
  $('slot').innerHTML = slots.map(s => `<option>${s}</option>`).join(''); $('slot').onchange = e => selectSlot(e.target.value);
  $('action').innerHTML = state.manifest.actions.map((a, i) => `<option value="${i}">${a.id} ${a.name.replace(/^\d+_/, '')}</option>`).join('');
  $('action').onchange = e => { state.action = +e.target.value; preview.frame = 0; frameUI(); };
  $('dirs').innerHTML = [...Array(8).keys()].map(d => `<button style="--a:${d * 45}deg" class="${d > 4 ? 'mirror' : ''}" title="Direction ${d}${d > 4 ? `: the client mirrors direction ${8 - d}` : ''}">${d}</button>`).join('');
  [...$('dirs').children].forEach((b, d) => b.onclick = () => {
    state.dir = preview.dir = d; preview.cycling = false; $('previewCycle').checked = false; frameUI();
  });
  $('frame').setAttribute('aria-label', 'Main frame');
  $('frame').oninput = e => { state.frame = preview.frame = +e.target.value; frameUI(); };
  $('play').onclick = () => { state.playing = !state.playing; $('play').textContent = state.playing ? 'Pause' : 'Play'; $('play').setAttribute('aria-label', $('play').textContent); };
  setupTabs();
  $('uoView').onclick = resetView; $('showHidden').onchange = updateBody;
  $('measureActions').innerHTML = state.manifest.actions.map((a, i) => `<label><input type="checkbox" value="${i}" ${[0, 2, 4, 9, 16].includes(a.id) ? 'checked' : ''}>${a.id}</label>`).join('');
  $('measure').onclick = measure;
  $('headAB').onclick = headAB;
  $('cancelAB').onclick = () => { cancelAB = true; };
  $('loadAssets').onclick = loadAssets;
  for (const id of ['scopeTarget','scopeWhen','scopeGroup']) $(id).onchange=scopeChanged;
  $('makeGroup').onclick=() => {
    const name=$('groupName').value.trim();
    if (!name || !state.shown.size) { $('scopeLabel').textContent='Enter a name and check at least one item.';return; }
    if (state.adjust.groups?.[name]) { $('scopeLabel').textContent='That group exists; choose a new name.';return; }
    (state.adjust.groups ??= {})[name]=[...state.shown].sort(); persistence.commit(state.adjust,'Create group '+name);
    buildScopedPanel();$('scopeGroup').value=name;$('scopeTarget').value='group';scopeChanged();
  };
  $('removeCorrection').onclick=() => { const rule=selectedCorrection(); if(!rule)return; state.adjust.corrections=state.adjust.corrections.filter(r=>r!==rule);changed();persistence.commit(state.adjust,'Remove scoped correction');buildScopedPanel(); };
  $('previewBase').onchange = drawSheet; $('previewPokes').onchange = drawSheet;
  $('stabilizeHead').onchange = e => { stabilizeHead = e.target.checked; frameUI(); };
  $('save').onclick = () => persistence.save();
  $('reset').onclick = () => { delete state.adjust.parts[state.selected.part]; buildPanels(); changed(); record('Reset slot'); };
  $('undo').onclick = () => persistence.undo(); $('redo').onclick = () => persistence.redo();
  document.addEventListener('keydown', e => {
    if (!(e.ctrlKey || e.metaKey) || e.altKey || measuring) return;
    if (e.target.isContentEditable || e.target.matches('textarea,input:not([type=range]):not([type=checkbox])')) return;
    const key = e.key.toLowerCase();
    if (key === 'z' || key === 'y') { e.preventDefault(); key === 'y' || e.shiftKey ? persistence.redo() : persistence.undo(); }
  });
  $('previewPlay').onchange = e => { preview.playing = e.target.checked; preview.lastFrame = performance.now(); };
  $('previewCycle').onchange = e => { preview.cycling = e.target.checked; preview.lastDir = performance.now(); };
  $('previewSize').onchange = e => { $('sheet').style.setProperty('--preview-scale', e.target.value); drawSheet(); };
  $('sheet').onscroll = drawSheet;
  new ResizeObserver(() => { resize(); drawSheet(); }).observe($('view'));
  renderPanel = new RenderPanel({
    pose: () => ({info: state.selected, action: state.manifest.actions[state.action], frame: state.frame, dir: state.dir}),
    part: partOf, adjustments: () => state.adjust, edited: () => lastEdit, save: () => persistence.save(),
    ready: () => !persistence.conflict && !persistence.saving && same(persistence.disk, state.adjust),
    setPose: (dir, frame) => {
      state.playing = false; $('play').textContent = 'Play'; preview.cycling = false; $('previewCycle').checked = false;
      state.dir = preview.dir = dir; state.frame = preview.frame = frame; frameUI();
    },
  });
  await selectSlot(slots[0]); frameUI();
  ['left', 'right', 'bar', 'previewBar', 'topActions'].forEach(id => $(id).inert = false);
  let last = 0;
  renderer.setAnimationLoop(t => {
    if (measuring || document.hidden) return;
    const count = state.manifest.actions[state.action].frames;
    if (preview.playing && t - preview.lastFrame >= 125) { preview.lastFrame = t; preview.frame = (preview.frame + 1) % count; preview.dirty = true; }
    if (preview.cycling && t - preview.lastDir >= 2000) { preview.lastDir = t; preview.dir = (preview.dir + 1) % 8; preview.dirty = true; }
    if (state.playing && t - last > 125) { last = t; state.frame = (state.frame + 1) % state.manifest.actions[state.action].frames; $('frame').value = state.frame; $('frameLabel').textContent = `${state.frame + 1}/${state.manifest.actions[state.action].frames}`; setPose(state.action, state.frame, state.dir); renderPanel.sync(); }
    if (preview.dirty) renderSheet();
    renderer.render(scene, view);
  });
}
main().catch(e => { $('status').textContent = 'Error: ' + e.message; console.error(e); });

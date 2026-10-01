import * as T from './vendor/three.module.js';
const $=id=>document.getElementById(id), V=(a)=>new T.Vector3(...a), size=576;
async function main(){
const sceneData=await fetch('scene.json').then(r=>r.json());
const raw=await fetch('mesh.bin').then(r=>r.arrayBuffer());
const scene=new T.Scene(), root=new T.Group();scene.add(root);
const bones=sceneData.bones.map(b=>{const o=new T.Bone();o.name=b.name;o.position.fromArray(b.p);o.quaternion.fromArray(b.q);o.scale.fromArray(b.s);return o});
const byName=Object.fromEntries(bones.map(b=>[b.name,b]));
sceneData.bones.forEach((b,i)=>(b.parent<0?root:bones[b.parent]).add(bones[i]));
scene.updateMatrixWorld(true);
const skeleton=new T.Skeleton(bones,sceneData.bones.map(b=>new T.Matrix4().fromArray(b.inverse)));
const textureLoader=new T.TextureLoader();
const materials=await Promise.all(sceneData.materials.map(async m=>{
  const texture=m.texture?await textureLoader.loadAsync(m.texture):null;
  if(texture){texture.colorSpace=T.SRGBColorSpace;texture.anisotropy=4;}
  const material=new T.MeshStandardMaterial({map:texture,color:texture?0xffffff:new T.Color(...m.color.slice(0,3)),roughness:.88,side:T.DoubleSide});
  // Keep every imported influence (several face vertices have five). No truncation.
  material.onBeforeCompile=shader=>{
    shader.vertexShader='attribute vec4 skinIndex2;\nattribute vec4 skinWeight2;\n'+shader.vertexShader;
    shader.vertexShader=shader.vertexShader.replace('#include <skinbase_vertex>',T.ShaderChunk.skinbase_vertex+'\nmat4 extraSkin = skinWeight2.x*getBoneMatrix(skinIndex2.x)+skinWeight2.y*getBoneMatrix(skinIndex2.y)+skinWeight2.z*getBoneMatrix(skinIndex2.z)+skinWeight2.w*getBoneMatrix(skinIndex2.w);');
    shader.vertexShader=shader.vertexShader.replace('#include <skinnormal_vertex>',T.ShaderChunk.skinnormal_vertex.replace('skinMatrix = bindMatrixInverse','skinMatrix += extraSkin;\n skinMatrix = bindMatrixInverse'));
    shader.vertexShader=shader.vertexShader.replace('#include <skinning_vertex>',T.ShaderChunk.skinning_vertex.replace('transformed =','skinned += extraSkin * skinVertex;\n transformed ='));
  };
  return material;
}));
for(const m of sceneData.meshes){
  const geometry=new T.BufferGeometry();
  for(const [name,a] of Object.entries(m.attributes))geometry.setAttribute(name,new T.BufferAttribute(new (a.type==='float32'?Float32Array:Uint16Array)(raw,a.offset,a.length),a.size));
  m.groups.forEach(g=>geometry.addGroup(g.start,g.count,g.material));
  const mesh=new T.SkinnedMesh(geometry,materials);mesh.name=m.name;mesh.frustumCulled=false;
  mesh.bind(skeleton,new T.Matrix4());root.add(mesh);
}
scene.add(new T.HemisphereLight(0xe4e4e4,0x686868,2.1));
for(const [pos,power,color] of [[[3,-4,6],2.4,0xffffff],[[-4,-2,3],1.2,0xffffff],[[1,3,4],1.5,0xffffff]]){
  const light=new T.DirectionalLight(color,power);light.position.fromArray(pos);scene.add(light);
}
const renderer=new T.WebGLRenderer({alpha:true,antialias:true,preserveDrawingBuffer:true});
renderer.setSize(size,size);renderer.setClearColor(0x000000,0);renderer.outputColorSpace=T.SRGBColorSpace;
renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1;
const camera=new T.OrthographicCamera();
let right=new T.Vector3(),up=new T.Vector3(),back=new T.Vector3(),sx=1,sy=1;
function setCamera(){
  const rotation=new T.Matrix4().fromArray(sceneData.directions[$('dir').value]);
  const inv=rotation.clone().invert(),M=sceneData.camera.matrix;
  sx=V(M[0]).length();sy=V(M[1]).length();
  right=V(M[0]).normalize().transformDirection(inv);up=V(M[1]).normalize().negate().transformDirection(inv);back=new T.Vector3().crossVectors(right,up).normalize();
  camera.left=-48/sx;camera.right=48/sx;camera.top=84/sy;camera.bottom=-12/sy;camera.near=.1;camera.far=30;
  camera.position.copy(back).multiplyScalar(10);camera.up.copy(up);camera.lookAt(0,0,0);camera.updateProjectionMatrix();camera.updateMatrixWorld(true);
}
const chains={
  arm_A:{names:['upperarm_l','lowerarm_l','hand_l'],labels:['shoulder','elbow','wrist'],color:'#28d9ff'},
  arm_B:{names:['upperarm_r','lowerarm_r','hand_r'],labels:['shoulder','elbow','wrist'],color:'#ff5edb'},
  leg_A:{names:['thigh_l','calf_l','foot_l'],labels:['hip','knee','ankle'],color:'#78ff6b'},
  leg_B:{names:['thigh_r','calf_r','foot_r'],labels:['hip','knee','ankle'],color:'#ff9a3b'}
};
let edits={},history=[],future=[],playing=false,lastTime=0,drag=null,dirty=false,saveTimer=null,revision=0,saveQueue=Promise.resolve();
let loadingReference=false,reference=null,refTicket=0,changed=true,notice='';
const frame=()=>+$('frame').value,clip=()=>$('clip').value,key=()=>`${clip()}:${frame()}`;
const snapshot=()=>JSON.stringify(edits), world=b=>b.getWorldPosition(new T.Vector3());
function frameEdits(){return edits[key()]||{};}
function applyPose(){
  const pose=sceneData.clips[clip()].frames[frame()],adjust=frameEdits();
  bones.forEach((b,i)=>{b.position.fromArray(pose[i].p);b.quaternion.fromArray(adjust[b.name]||pose[i].q);b.scale.fromArray(pose[i].s)});
  scene.updateMatrixWorld(true);skeleton.update();changed=true;
  $('frameLabel').textContent=`${frame()+1} / ${sceneData.clips[clip()].frames.length}`;
  $('undo').disabled=!history.length;$('redo').disabled=!future.length;
  $('status').textContent=`${clip()} · frame ${frame()+1} · ${Object.keys(edits).length} edited frame${Object.keys(edits).length===1?'':'s'}${notice?' · '+notice:''}`;
}
async function loadReference(){
  const ticket=++refTicket;loadingReference=true;changed=true;
  const im=new Image();im.src=`../references/${clip().toLowerCase()}_d${$('dir').value}_f${String(frame()).padStart(2,'0')}.png`;
  try{await im.decode();if(ticket===refTicket){reference=im;loadingReference=false;changed=true;}}
  catch(e){if(ticket===refTicket){reference=null;loadingReference=false;notice='Reference image unavailable';applyPose();}}
}
function project(p){const n=p.clone().project(camera);return [(n.x+1)*size/2,(1-n.y)*size/2];}
function handles(){const result=[];for(const [id,c] of Object.entries(chains))c.names.forEach((n,i)=>result.push({id:`${id}_${c.labels[i]}`,p:project(world(byName[n])),color:c.color,editable:i>0}));return result;}
function drawJoints(ctx){
  for(const [id,c] of Object.entries(chains)){
    const points=c.names.map(n=>project(world(byName[n])));
    ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.strokeStyle='#10212b';ctx.lineWidth=5;ctx.stroke();ctx.strokeStyle=c.color;ctx.lineWidth=2;ctx.stroke();
  }
  const core=['pelvis','spine_02','neck_01','head'].map(n=>project(world(byName[n])));
  ctx.beginPath();core.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.strokeStyle='#ffe45e';ctx.lineWidth=2;ctx.stroke();
  for(const [x,y] of core){ctx.beginPath();ctx.arc(x,y,3,0,Math.PI*2);ctx.fillStyle='#ffe45e';ctx.fill();}
  for(const h of handles()){
    const [x,y]=h.p,selected=h.id===$('control').value,r=h.editable?6:3;
    if(selected){ctx.beginPath();ctx.arc(x,y,11,0,Math.PI*2);ctx.strokeStyle='#fff';ctx.lineWidth=2;ctx.stroke();}
    ctx.beginPath();if(h.id.endsWith('wrist'))ctx.rect(x-r,y-r,r*2,r*2);else ctx.arc(x,y,r,0,Math.PI*2);
    ctx.fillStyle=h.color;ctx.fill();ctx.strokeStyle='#10212b';ctx.lineWidth=2;ctx.stroke();
  }
}
function render(){
  scene.updateMatrixWorld(true);skeleton.update();renderer.render(scene,camera);
  for(const id of ['source','model','overlay']){
    const c=$(id).getContext('2d');c.globalAlpha=1;c.fillStyle='#263443';c.fillRect(0,0,size,size);c.imageSmoothingEnabled=false;
    if(id!=='model'&&reference&&!loadingReference)c.drawImage(reference,80,108,96,96,0,0,size,size);
    if(id!=='source'){c.globalAlpha=id==='overlay'?+$('opacity').value:1;c.drawImage(renderer.domElement,0,0);c.globalAlpha=1;}
    if($('points').checked)drawJoints(c);
    if(loadingReference&&id!=='model'){c.fillStyle='#afc1d2';c.font='15px system-ui';c.fillText('Loading reference…',18,28);}
  }
  changed=false;
}
function storeBones(names){
  const k=key();edits[k]??={};for(const n of names)edits[k][n]=byName[n].quaternion.toArray();
  changed=true;
}
function aim(name,child,target){
  const bone=byName[name],origin=world(bone),current=world(byName[child]).sub(origin).normalize(),desired=target.clone().sub(origin).normalize();
  if(desired.lengthSq()<1e-10)return;
  const delta=new T.Quaternion().setFromUnitVectors(current,desired),q=bone.getWorldQuaternion(new T.Quaternion());
  const parent=bone.parent.getWorldQuaternion(new T.Quaternion()).invert();
  bone.quaternion.copy(parent.multiply(delta.multiply(q)));scene.updateMatrixWorld(true);
}
function moveControl(id,target){
  const chain=chains[id.slice(0,5)],[a,b,c]=chain.names;
  const origin=world(byName[a]),elbow=world(byName[b]),wrist=world(byName[c]);
  const isPole=id.endsWith('elbow')||id.endsWith('knee');
  const l1=origin.distanceTo(elbow),l2=elbow.distanceTo(wrist);
  const endpoint=isPole?wrist:target,axis=endpoint.clone().sub(origin);
  const distance=T.MathUtils.clamp(axis.length(),Math.abs(l1-l2)+.0001,l1+l2-.0001);axis.normalize();
  if(axis.lengthSq()<.5)axis.set(0,0,-1);
  const pole=(isPole?target:elbow).clone().sub(origin);pole.addScaledVector(axis,-pole.dot(axis));
  if(pole.lengthSq()<1e-8){pole.copy(back);pole.addScaledVector(axis,-pole.dot(axis));}
  if(pole.lengthSq()<1e-8){pole.copy(right);pole.addScaledVector(axis,-pole.dot(axis));}
  pole.normalize();
  const along=(l1*l1-l2*l2+distance*distance)/(2*distance),height=Math.sqrt(Math.max(0,l1*l1-along*along));
  const bend=origin.clone().addScaledVector(axis,along).addScaledVector(pole,height);
  const goal=origin.clone().addScaledVector(axis,distance);
  // Retain wrist/foot world orientation, including the user's closed grip.
  const endRotation=byName[c].getWorldQuaternion(new T.Quaternion());
  aim(a,b,bend);aim(b,c,goal);
  byName[c].quaternion.copy(byName[c].parent.getWorldQuaternion(new T.Quaternion()).invert().multiply(endRotation));
  scene.updateMatrixWorld(true);storeBones([a,b,c]);
  notice=!isPole&&goal.distanceTo(target)>.005?'Target limited by bone length':'';
  if(id.startsWith('leg')){
    for(const name of [`LegPlate_${a.endsWith('_l')?'L':'R'}`,`Hip_${a.endsWith('_l')?'L':'R'}`]){
      const extra=byName[name];if(!extra)continue;
      const thighIndex=bones.indexOf(byName[a]),extraIndex=bones.indexOf(extra);
      const matrix=byName[a].matrixWorld.clone().multiply(new T.Matrix4().fromArray(sceneData.bones[thighIndex].inverse)).multiply(new T.Matrix4().fromArray(sceneData.bones[extraIndex].inverse).invert());
      const local=extra.parent.matrixWorld.clone().invert().multiply(matrix);const p=new T.Vector3(),s=new T.Vector3();local.decompose(p,extra.quaternion,s);
      // Accessory origins are shared with the thigh in this source rig.
      storeBones([name]);
    }
  }
  changed=true;
}
function selectedPosition(){const id=$('control').value,c=chains[id.slice(0,5)];return world(byName[c.names[id.endsWith('elbow')||id.endsWith('knee')?1:2]]);}
function stop(){playing=false;$('play').textContent='Play';}
function begin(){stop();return snapshot();}
function commit(before){if(before===snapshot())return;history.push(before);if(history.length>100)history.shift();future=[];dirty=true;revision++;$('blendLink').hidden=true;$('saveState').textContent='Unsaved edits';clearTimeout(saveTimer);saveTimer=setTimeout(()=>save().catch(showError),600);applyPose();}
function showError(e){$('saveState').textContent='Action failed';$('status').textContent=e.message||String(e);}
function nudge(dx,dy,dz=0){const before=begin();const target=selectedPosition().addScaledVector(right,dx/sx).addScaledVector(up,-dy/sy).addScaledVector(back,dz);moveControl($('control').value,target);commit(before);}
for(const id of ['source','model','overlay']){
  const canvas=$(id);const coords=e=>{const r=canvas.getBoundingClientRect();return [(e.clientX-r.left)*size/r.width,(e.clientY-r.top)*size/r.height]};
  canvas.onpointerdown=e=>{
    if(!$('points').checked||e.button!==0)return;
    const p=coords(e),eligible=handles().filter(h=>h.editable).map(h=>({...h,d:Math.hypot(p[0]-h.p[0],p[1]-h.p[1])})).filter(h=>h.d<20);
    eligible.sort((a,b)=>a.d-b.d);let h=eligible[0];
    const selected=eligible.find(h=>h.id===$('control').value);if(selected&&selected.d<12)h=selected;
    if(!h)return;
    const before=begin();$('control').value=h.id;
    drag={id:h.id,start:p,world:selectedPosition(),before};canvas.setPointerCapture(e.pointerId);changed=true;
  };
  canvas.onpointermove=e=>{if(!drag)return;const p=coords(e),target=drag.world.clone().addScaledVector(right,(p[0]-drag.start[0])/size*96/sx).addScaledVector(up,-(p[1]-drag.start[1])/size*96/sy);moveControl(drag.id,target);};
  canvas.onpointerup=e=>{if(!drag)return;const before=drag.before;drag=null;canvas.releasePointerCapture(e.pointerId);commit(before);};
  canvas.onpointercancel=()=>{if(drag){edits=JSON.parse(drag.before);drag=null;applyPose();}};
}
function payload(){return {version:1,assetId:sceneData.assetId,edits};}
function validate(doc){
  if(doc.version!==1||doc.assetId!==sceneData.assetId||!doc.edits||typeof doc.edits!=='object')throw Error('This edits file belongs to a different model version.');
  const allowed=new Set(Object.values(chains).flatMap(c=>c.names).concat(['LegPlate_L','LegPlate_R','Hip_L','Hip_R']));
  for(const [k,pose] of Object.entries(doc.edits)){
    const [name,f]=k.split(':');if(!sceneData.clips[name]||!/^\d+$/.test(f)||+f>=sceneData.clips[name].frames.length)throw Error('Invalid clip or frame in edits.');
    for(const [bone,q] of Object.entries(pose)){if(!allowed.has(bone)||!Array.isArray(q)||q.length!==4||q.some(v=>!Number.isFinite(v))||Math.abs(Math.hypot(...q)-1)>.001)throw Error('Invalid bone rotation in edits.');}
  }
  return doc.edits;
}
function save(){
  const rev=revision,body=JSON.stringify(payload());
  saveQueue=saveQueue.catch(()=>{}).then(async()=>{
    const response=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body});
    if(!response.ok)throw Error(await response.text());
    if(rev===revision){dirty=false;$('saveState').textContent='Saved locally';}
  });
  return saveQueue;
}
function download(){const url=URL.createObjectURL(new Blob([JSON.stringify(payload(),null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='female-pose-edits.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('clip').onchange=()=>{stop();$('frame').max=sceneData.clips[clip()].frames.length-1;$('frame').value=0;notice='';applyPose();loadReference();};
$('dir').onchange=()=>{setCamera();loadReference();changed=true;};
$('frame').oninput=()=>{stop();notice='';applyPose();loadReference();};
$('points').onchange=$('opacity').oninput=$('control').onchange=()=>changed=true;
$('play').onclick=()=>{playing=!playing;$('play').textContent=playing?'Pause':'Play';lastTime=performance.now();};
$('left').onclick=()=>nudge(-1,0);$('right').onclick=()=>nudge(1,0);$('up').onclick=()=>nudge(0,-1);$('down').onclick=()=>nudge(0,1);$('near').onclick=()=>nudge(0,0,.01);$('far').onclick=()=>nudge(0,0,-.01);
function twist(sign){const before=begin(),id=$('control').value,c=chains[id.slice(0,5)],bone=byName[c.names[2]],axis=world(bone).sub(world(byName[c.names[1]])).normalize();const q=new T.Quaternion().setFromAxisAngle(axis,sign*Math.PI/36).multiply(bone.getWorldQuaternion(new T.Quaternion()));bone.quaternion.copy(bone.parent.getWorldQuaternion(new T.Quaternion()).invert().multiply(q));storeBones([bone.name]);commit(before);}
$('twistMinus').onclick=()=>twist(-1);$('twistPlus').onclick=()=>twist(1);
function undo(redo=false){stop();const from=redo?future:history,to=redo?history:future;if(!from.length)return;to.push(snapshot());edits=JSON.parse(from.pop());revision++;dirty=true;applyPose();save().catch(showError);}
$('undo').onclick=()=>undo();$('redo').onclick=()=>undo(true);
$('reset').onclick=()=>{const before=begin();delete edits[key()];commit(before);};
$('save').onclick=()=>save().catch(showError);$('download').onclick=download;
$('import').onchange=async()=>{try{const file=$('import').files[0];if(!file)return;const doc=JSON.parse(await file.text()),next=validate(doc),before=begin();edits=next;commit(before);}catch(e){showError(e)}finally{$('import').value='';}};
$('bake').onclick=async()=>{
  stop();$('bake').disabled=true;$('blendLink').hidden=true;
  try{
    await save();const r=await fetch('/api/bake',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())});
    if(!r.ok)throw Error(await r.text());const job=await r.json();$('status').textContent='Exporting a separate Blender scene…';
    const poll=async()=>{try{const response=await fetch(`/api/job?id=${encodeURIComponent(job.id)}`);if(!response.ok)throw Error(await response.text());const state=await response.json();if(state.status==='running'){setTimeout(poll,1000);return;}if(state.status!=='done')throw Error(state.error||'Blender export failed');$('blendLink').href=state.url;$('blendLink').hidden=false;$('status').textContent='Edited Blender scene ready. Original scene preserved.';$('bake').disabled=false;}catch(e){$('bake').disabled=false;showError(e)}};setTimeout(poll,1000);
  }catch(e){$('bake').disabled=false;showError(e)}
};
document.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName))return;if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();undo(e.shiftKey);return;}const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];if(delta){e.preventDefault();nudge(delta[0]*(e.shiftKey?.25:1),delta[1]*(e.shiftKey?.25:1));}});
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
try{const response=await fetch('/api/edits');if(response.ok){const doc=await response.json();if(doc)edits=validate(doc);}}catch(e){showError(e)}
setCamera();applyPose();await loadReference();$('saveState').textContent=Object.keys(edits).length?'Saved edits restored':'Ready · no edits';
function animate(time){requestAnimationFrame(animate);if(playing&&time-lastTime>=sceneData.clips[clip()].step/30*1000){lastTime=time;$('frame').value=(frame()+1)%sceneData.clips[clip()].frames.length;applyPose();loadReference();}if(changed)render();}
requestAnimationFrame(animate);
}
main().catch(e=>{$('saveState').textContent='Could not load editor';$('status').textContent=e.message;console.error(e);});

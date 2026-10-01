'use strict';
const M=window.OUTFIT,$=id=>document.getElementById(id), names=['N','NE','E','SE','S','SW','W','NW'];
const state={action:4,facing:3,frame:0,playing:true,loaded:false,version:0,time:0};
const OFF=M.defaultOff||['staff','robe'],EXCL=M.exclusive||['sword','staff'];
const modes=Object.fromEntries(M.items.map(i=>[i.key,'new']));OFF.forEach(k=>{if(k in modes)modes[k]='off'});document.title=M.title+' · Outfit Lab';
const images=new Map();let current=null,last=0,acc=0,follow={x:0,y:0};
for(const a of M.actions){const o=new Option(`${a.index} · ${a.name}`,a.index);$('action').add(o)}
if(!M.actions.some(a=>a.index===state.action))state.action=M.actions[0].index;
$('action').value=state.action;
names.forEach((n,i)=>$('facing').add(new Option(n,i)));$('facing').value=state.facing;
M.items.forEach(item=>{const row=document.createElement('div');row.className='item';const name=document.createElement('span');name.textContent=item.displayName||item.key;const select=document.createElement('select');select.id='item-'+item.key;select.setAttribute('aria-label',item.displayName||item.key);[['off','Off'],['original','UO'],['new','New']].forEach(([v,t])=>select.add(new Option(t,v)));select.value=modes[item.key];select.onchange=()=>{modes[item.key]=select.value;if(EXCL.includes(item.key)&&select.value!=='off'){EXCL.filter(k=>k!==item.key).forEach(other=>{if(other in modes){modes[other]='off';$('item-'+other).value='off'}})}render()};row.append(name,select);$('items').append(row)});
M.items.forEach(item=>{const figure=document.createElement('figure');const img=document.createElement('img');img.src='designs/'+item.key+'.png';img.alt=item.displayName||item.key;const caption=document.createElement('figcaption');caption.textContent=item.displayName||item.key;figure.append(img,caption);$('designs').append(figure)});
M.limitations.forEach(t=>{const li=document.createElement('li');li.textContent=t;$('limits').append(li)});
$('sources').textContent=M.items.map(i=>`${i.key}: ${i.label} · graphic 0x${i.graphic.toString(16)} · animation ${i.animId}`).join('\n');
function view(){const facing=state.facing;const stored=facing<3?[6,5,4][facing]:facing;const a=M.actions.find(a=>a.index===state.action);return {...a.views[stored],stored,mirror:facing<3}}
async function load(){const version=++state.version;state.loaded=false;render();const v=view();let im=images.get(v.atlas);if(!im){im=new Image();im.src=v.atlas;try{await im.decode()}catch(e){$('notice').textContent='Could not load atlas: '+v.atlas;return}images.set(v.atlas,im);while(images.size>3)images.delete(images.keys().next().value)}if(version!==state.version)return;current=im;state.loaded=true;state.frame=Math.min(state.frame,v.count-1);$('frame').max=v.count-1;render()}
function sprite(ctx,row,dx=0,dy=0){const v=view();ctx.save();ctx.translate(320+dx,360+dy);ctx.scale(v.mirror?-3:3,3);ctx.drawImage(current,state.frame*256,row*256,256,256,-128,-192,256,256);ctx.restore()}
function draw(canvas,original){const ctx=canvas.getContext('2d');ctx.imageSmoothingEnabled=false;ctx.fillStyle='#15232c';ctx.fillRect(0,0,640,480);ctx.strokeStyle='#263b43';ctx.lineWidth=1;for(let x=-480;x<900;x+=64){ctx.beginPath();ctx.moveTo(x,480);ctx.lineTo(x+640,160);ctx.stroke();ctx.beginPath();ctx.moveTo(x,160);ctx.lineTo(x+640,480);ctx.stroke()}
 if(!state.loaded){ctx.fillStyle='#bbd8d6';ctx.fillText('Loading original frames…',230,230);return}
 const travel=$('travel').checked?Math.sin(state.time*.65)*85:0;
 ctx.save();ctx.translate(travel,0);ctx.fillStyle='#090f1580';ctx.beginPath();ctx.ellipse(320,362,46,13,0,0,Math.PI*2);ctx.fill();
 const row=k=>{const j=M.items.findIndex(i=>i.key===k);return 2+j*2+((!original&&modes[k]==='new')?1:0)};
 const enabled=k=>k in modes&&modes[k]!=='off';
 // Stored SE/S/SW face the viewer: backpack is occluded by the body and outfit.
 // W/NW (and mirrored N) expose the back: backpack is drawn above torso.
 const backVisible=[0,6,7].includes(state.facing);
 const drawItem=k=>{if(enabled(k))sprite(ctx,row(k))};
 if(!backVisible)drawItem('backpack');
 sprite(ctx,0);
 (M.drawOrder||['pants','shoes','shirt','robe','hair','gloves','sword','staff']).forEach(drawItem);
 if(backVisible)drawItem('backpack');
 if(enabled('familiar')){const dx=$('orbit').checked?follow.x-travel:0;sprite(ctx,row('familiar'),dx,0)}
 if($('masks').checked)sprite(ctx,1);
 ctx.restore();
}
function render(){draw($('original'),true);draw($('custom'),false);$('frame').value=state.frame;const v=view();$('status').textContent=`${names[state.facing]} · frame ${state.frame+1} / ${v.count} · ${v.mirror?'mirrored':'stored'}`;const missing=M.report.missing.filter(m=>m.action===state.action&&m.facing===v.stored&&modes[m.item]!=='off');$('notice').textContent=missing.length?'Unavailable original sequences (hidden): '+missing.map(m=>m.item).join(', '):'Body 400 · native frame registration · experimental outfit layering';}
$('action').onchange=()=>{state.action=+$('action').value;state.frame=0;load()};$('facing').onchange=()=>{state.facing=+$('facing').value;load()};
$('play').onclick=()=>{state.playing=!state.playing;$('play').textContent=state.playing?'Pause':'Play'};
$('step').onclick=()=>{state.playing=false;$('play').textContent='Play';state.frame=(state.frame+1)%view().count;render()};
$('frame').oninput=()=>{state.playing=false;$('play').textContent='Play';state.frame=+$('frame').value;render()};
['masks','orbit','travel'].forEach(id=>$(id).onchange=render);
function preset(robe,bare=false){for(const k in modes){modes[k]=bare?'off':(OFF.includes(k)?'off':'new');if(k==='robe'&&robe)modes[k]='new';$('item-'+k).value=modes[k]}render()}
$('separates').onclick=()=>preset(false);$('robed').onclick=()=>preset(true);$('off').onclick=()=>preset(false,true);
$('capture').onclick=()=>{const c=document.createElement('canvas');c.width=1280;c.height=540;const ctx=c.getContext('2d');ctx.fillStyle='#101a20';ctx.fillRect(0,0,1280,540);ctx.fillStyle='#dbebeb';ctx.font='18px sans-serif';ctx.fillText(`${M.title} | action ${state.action} | ${names[state.facing]} | frame ${state.frame} | A: UO / B: selected`,20,30);ctx.drawImage($('original'),0,60);ctx.drawImage($('custom'),640,60);const a=document.createElement('a');a.download=`outfit-a${state.action}-d${state.facing}-f${state.frame}.png`;a.href=c.toDataURL();a.click();const b=document.createElement('a');b.download=`outfit-a${state.action}-d${state.facing}-f${state.frame}.json`;const u=URL.createObjectURL(new Blob([JSON.stringify({state,modes,maskOverlay:$('masks').checked},null,2)],{type:'application/json'}));b.href=u;b.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
function tick(now){const dt=Math.min((now-last)/1000,.1);last=now;if(state.playing&&state.loaded){state.time+=dt;acc+=dt;const fps=Math.max(1,Math.min(30,+$('fps').value||8));if(acc>=1/fps){state.frame=(state.frame+Math.floor(acc*fps))%view().count;acc%=1/fps}const target=$('travel').checked?Math.sin(state.time*.65)*85:0;follow.x+=(target-follow.x)*Math.min(1,dt*3);render()}requestAnimationFrame(tick)}
load();requestAnimationFrame(tick);

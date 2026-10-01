"""Build local UO equipment A/B atlases from original frames and generated designs."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import sys

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / 'region-masks'))
from uo import UOReader, client_source

ITEMS = [('sword',0xF5E),('staff',0xE89),('robe',0x1F03),
         ('hair',0x203C),('shirt',0x1517),('pants',0x1539),('shoes',0x170F),
         ('gloves',0x13C6),('backpack',0xE75),('familiar',0xE2D)]
FACING = [3,4,5,6,7]
DESIGN_CELLS = dict(zip(['sword','staff','robe','hat','hair','shirt','pants','shoes','gloves','backpack','familiar'],range(11)))

def fit_lightsaber(original, design, labels, width_ratio=.15):
    """Register the generated straight saber to the source weapon axis and grip.

    Hand-mask proximity chooses the hilt end. Native brightness breaks ties or
    handles frames without visible hands. The source's projected length retains
    foreshortening; no blade is invented for an empty equipment frame.
    """
    src=np.array(original)
    ys,xs=np.where(src[:,:,3]>0)
    if len(xs)<2: return Image.new('RGBA',original.size)
    points=np.column_stack([xs,ys]).astype(float); center=points.mean(axis=0)
    _,axes=np.linalg.eigh(np.cov(points.T)); axis=axes[:,-1]
    t=(points-center)@axis; lo,hi=t.min(),t.max()
    ends=[center+axis*lo,center+axis*hi]
    hy,hx=np.where(labels==5)
    if len(hx):
        hands=np.column_stack([hx,hy]);dist=[np.min(np.sum((hands-p)**2,axis=1)) for p in ends]
        reverse=dist[1]<dist[0]
    else:
        light=src[ys,xs,:3].mean(axis=1)
        reverse=np.mean(light[t<np.quantile(t,.3)])>np.mean(light[t>np.quantile(t,.7)]) if hi>lo else False
    start=ends[1] if reverse else ends[0]
    direction=-axis if reverse else axis
    length=max(hi-lo,2); normal=np.array([-direction[1],direction[0]])
    thickness=max(5.,length*width_ratio)
    w,h=design.size
    u=direction*(w-1)/length; v=normal*(h-1)/thickness
    coeff=(u[0],u[1],-u@start,v[0],v[1],h/2-v@start)
    return design.transform(original.size,Image.Transform.AFFINE,coeff,Image.Resampling.BICUBIC)

def canvas(frame):
    im = Image.new('RGBA',(256,256))
    if frame and not frame.get('empty'):
        im.alpha_composite(frame['image'],(128-frame['center'][0],192-frame['image'].height-frame['center'][1]))
    return im

def static_art(root, graphic):
    """Decode classic static art; retain the actual crystal-ball/backpack reference."""
    with (root/'artidx.mul').open('rb') as f:
        f.seek((graphic+0x4000)*12)
        offset,length,_ = struct.unpack('<iii',f.read(12))
    if offset < 0 or length <= 0:
        raise ValueError(f'Missing static art {graphic:#x}')
    with (root/'art.mul').open('rb') as f:
        f.seek(offset); data=f.read(length)
    w,h=struct.unpack_from('<HH',data,4)
    im=np.zeros((h,w,4),np.uint8)
    for y in range(h):
        p=8+2*h+2*struct.unpack_from('<H',data,8+2*y)[0]; x=0
        while True:
            skip,n=struct.unpack_from('<HH',data,p);p+=4
            if skip==n==0: break
            x+=skip
            for i in range(n):
                c=struct.unpack_from('<H',data,p)[0];p+=2
                rgb=[(c>>10)&31,(c>>5)&31,c&31]
                im[y,x+i]=[(v<<3)|(v>>2) for v in rgb]+[255]
            x+=n
    return Image.fromarray(im)

def fit_texture(original, design):
    """Scanline transfer preserves native articulation/alpha, including separated limbs.

    Generated cloth supplies material and embroidery; native luminance supplies folds.
    This is a 2D prototype, not a recovered 3D garment or independent view synthesis.
    """
    src=np.array(original); box=original.getbbox()
    if box is None: return original.copy()
    x0,y0,x1,y1=box
    tex=np.array(design.resize((x1-x0,y1-y0),Image.Resampling.BOX))
    supported=np.flatnonzero(np.any(tex[:,:,3]>32,axis=1))
    if not len(supported): return original.copy()
    # Transparent design borders must not punch holes into a fitted garment.
    for y in range(tex.shape[0]):
        ty=int(supported[np.argmin(abs(supported-y))])
        valid=np.flatnonzero(tex[ty,:,3]>32)
        if len(valid):
            row=tex[ty,valid,:3]
            xs=np.flatnonzero(src[y+y0,x0:x1,3]>0)
            if len(xs):
                samples=np.linspace(0,len(row)-1,len(xs)).astype(int)
                shade=.65+.55*np.mean(src[y+y0,xs+x0,:3],axis=1)/255
                src[y+y0,xs+x0,:3]=np.clip(row[samples]*shade[:,None],0,255)
    return Image.fromarray(src)

def occlude(image, labels, ids):
    arr=np.array(image); arr[np.isin(labels,ids),3]=0
    return Image.fromarray(arr)

def prop(design, labels, kind, frame, facing):
    im=Image.new('RGBA',(256,256))
    ys,xs=np.where(np.isin(labels,[3,10]))
    cx=int(np.median(xs)) if len(xs) else 128
    cy=int(np.median(ys)) if len(ys) else 155
    if kind=='backpack':
        size=(24,48); xy=(cx-12,cy-37)
    else:
        size=(19,25); xy=(cx+28,cy-24+round(3*math.sin(frame*math.pi/4)))
    im.alpha_composite(design.resize(size,Image.Resampling.NEAREST),xy)
    return im

def build(args):
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    (out/'atlases').mkdir(exist_ok=True);(out/'designs').mkdir(exist_ok=True)
    if Path(args.design).resolve() != (out/'design.png').resolve():
        shutil.copyfile(args.design,out/'design.png')
    sheet=Image.open(args.design).convert('RGBA')
    designs={}
    for key,_ in ITEMS:
        i=DESIGN_CELLS[key]
        x=i%4;y=i//4
        tile=sheet.crop((x*sheet.width//4,y*sheet.height//3,(x+1)*sheet.width//4,(y+1)*sheet.height//3))
        box=tile.getbbox()
        if not box: raise ValueError(f'Empty design: {key}')
        designs[key]=tile.crop(box);designs[key].save(out/'designs'/f'{key}.png')
    saber=Image.open(args.lightsaber).convert('RGBA')
    # Ignore nearly invisible halo pixels when deriving the asset registration.
    support=saber.getchannel('A').point(lambda a:255 if a>24 else 0).getbbox()
    if support is None: raise ValueError('Lightsaber design is empty')
    designs['sword']=saber.crop(support)
    designs['sword'].save(out/'designs/sword.png')
    root=Path(args.source);reader=UOReader(root)
    items=[dict(key=k,**reader.item(g)) for k,g in ITEMS]
    items[0]['displayName']='Red lightsaber'
    refs={k:static_art(root,g) for k,g in ITEMS if k in ('backpack','familiar')}
    for k,im in refs.items(): im.save(out/'designs'/f'{k}-original.png')
    actions=json.loads((HERE.parent/'profiles/human-actions.json').read_text())['actions']
    manifest={'title':'Astral Wayfarer','body':400,'canvas':256,'origin':[128,192],
      'items':items,'actions':[],'rows':{'body':0,'mask':1},
      'limitations':['Body 400 only; estimated region labels are not ground-truth depth.',
      'Clothes retain original equipment alpha; generated textures are fitted in 2D. The lightsaber uses the original weapon axis and estimated hand anchor.',
      'Backpack has no usable wearable animation here: static item reference, custom anchored overlay.',
      'Facing layer policies are experimental, not a full ClassicUO equipment renderer.',
      'Playback FPS is adjustable; client movement/combat timing is not simulated.']}
    report={'frames':0,'missing':[],'source':str(root),'hashes':{},'occludedPixels':0}
    for filename in ['anim.idx','tiledata.mul','Equipconv.def']:
        report['hashes'][filename]=hashlib.sha256((root/filename).read_bytes()).hexdigest()
    report['hashes']['design']=hashlib.sha256(Path(args.design).read_bytes()).hexdigest()
    report['hashes']['lightsaber']=hashlib.sha256(Path(args.lightsaber).read_bytes()).hexdigest()
    masks=Path(args.masks)
    try:
      for action in actions:
        if args.actions and action['index'] not in args.actions: continue
        a=action['index'];entry={**action,'views':{}}
        for stored,facing in enumerate(FACING):
          body=reader.sequence(400,a,stored)
          if not body: continue
          n=len(body);atlas=Image.new('RGBA',(256*n,256*(2+2*len(items))))
          seqs={}
          for item in items:
            k=item['key']
            if k in refs: continue
            aid=reader.equip.get((400,item['animId']),(item['animId'],0))[0]
            seqs[k]=reader.sequence(aid,a,stored)
            if len(seqs[k])!=n:
                report['missing'].append({'item':k,'action':a,'facing':facing,'bodyFrames':n,'itemFrames':len(seqs[k])})
          for f,b in enumerate(body):
            base=canvas(b);atlas.paste(base,(256*f,0))
            maskpath=masks/f'a{a:02}_d{facing}_f{f:02}_region_ids.png'
            labels=np.array(Image.open(maskpath))
            vis=np.zeros((256,256,4),np.uint8)
            vis[:,:,:3]=np.stack([(labels*41)%255,(labels*79)%255,(labels*113)%255],axis=-1)
            vis[:,:,3]=(labels>0)*150;atlas.paste(Image.fromarray(vis),(256*f,256))
            for j,item in enumerate(items):
              k=item['key']
              if k in refs:
                original=prop(refs[k],labels,k,f,facing)
                new=prop(designs[k],labels,k,f,facing)
              else:
                original=canvas(seqs[k][f]) if len(seqs[k])==n else Image.new('RGBA',(256,256))
                new=fit_lightsaber(original,designs[k],labels) if k=='sword' else fit_texture(original,designs[k])
              # Preserve exposed hands/face where a new cloth texture overlaps.
              ids={'robe':[1,5],'shirt':[1,5],'pants':[5],'hair':[5],'sword':[5],'staff':[5]}.get(k,[])
              before=np.count_nonzero(np.array(new)[:,:,3]);new=occlude(new,labels,ids)
              report['occludedPixels']+=int(before-np.count_nonzero(np.array(new)[:,:,3]))
              atlas.paste(original,(256*f,256*(2+j*2)))
              atlas.paste(new,(256*f,256*(3+j*2)))
            report['frames']+=1
          name=f'a{a:02}_d{facing}.png';atlas.save(out/'atlases'/name,optimize=True)
          entry['views'][str(facing)]={'count':n,'atlas':'atlases/'+name}
        manifest['actions'].append(entry)
        print(f'Built {a}: {action["name"]}',flush=True)
    finally: reader.close()
    manifest['report']=report
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    (out/'data.js').write_text('window.OUTFIT='+json.dumps(manifest)+';')
    for name in ['index.html','viewer.js','style.css']:
        shutil.copyfile(HERE/name,out/name)
    print(json.dumps({'frames':report['frames'],'missing':len(report['missing']),'out':str(out)}))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',default=os.environ.get('SPRITEMOTION_UO_SOURCE'))
    p.add_argument('--out',default=str(REPO/'workspace/ultima-online/outfit-lab'))
    p.add_argument('--design',default=str(REPO/'workspace/ultima-online/outfit-lab/design.png'))
    p.add_argument('--lightsaber',default=str(REPO/'workspace/ultima-online/outfit-lab/lightsaber.png'))
    p.add_argument('--masks',default=str(REPO/'workspace/ultima-online/region-audit/all-actions-region-pass/frames'))
    p.add_argument('--actions',nargs='+',type=int)
    a=p.parse_args();a.source=client_source(a.source)
    build(a)

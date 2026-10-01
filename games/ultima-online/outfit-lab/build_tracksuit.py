"""A second outfit using native UO motion, region-fitted stripes and energy sword."""
import json
import os
import hashlib
import shutil
from pathlib import Path
import numpy as np
from PIL import Image
from uo import client_source
from build import REPO, HERE, UOReader, canvas, fit_texture, fit_lightsaber, occlude

OUT=REPO/'workspace/ultima-online/tracksuit-lab'
MASKS=REPO/'workspace/ultima-online/region-audit/all-actions-region-pass/frames'
SOURCE=os.environ.get('SPRITEMOTION_UO_SOURCE')

def cloth(original, design, region_alpha):
    """Fit red material to source folds, then fit white stripes to limb scanlines."""
    a=np.array(original);visible=a[:,:,3]>0
    texture=np.array(fit_texture(original,design))
    # Keep the red material consistent when a sleeve moves across the torso.
    light=a[:,:,:3].mean(axis=2)/255
    a[:,:,:3]=np.stack([85+155*light,7+28*light,12+29*light],axis=-1).astype(np.uint8)
    # Use generated red surface detail without allowing chest whites to migrate.
    red=texture[:,:,0]>texture[:,:,1]*1.5
    a[red&visible,:3]=(a[red&visible,:3]*.6+texture[red&visible,:3]*.4).astype(np.uint8)
    for y in range(256):
        xs=np.flatnonzero(region_alpha[y]&visible[y])
        groups=np.split(xs,np.where(np.diff(xs)>1)[0]+1)
        for g in groups:
            if len(g)<3:continue
            # Outer side of each visible limb; compact enough for native pixel scale.
            x=g[1] if np.mean(g)<128 else g[-2]
            a[y,x,:3]=[240,240,231]
    return Image.fromarray(a)

def chain_image(design,labels,facing):
    result=Image.new('RGBA',(256,256))
    if facing in [6,7]:return result
    ys,xs=np.where(labels==3)
    if len(xs)<8:return result
    x0,x1=np.percentile(xs,[10,90]);y0,y1=np.percentile(ys,[5,80])
    width=max(7,min(17,int(x1-x0)));height=max(6,min(11,int((y1-y0)*.6)))
    result.alpha_composite(design.resize((width,height),Image.Resampling.LANCZOS),(int(np.median(xs)-width/2),int(y0+1)))
    # Necklace is a surface detail: only its visible torso pixels survive.
    a=np.array(result);a[labels!=3,3]=0
    return Image.fromarray(a)

def main():
    OUT.mkdir(exist_ok=True,parents=True);(OUT/'atlases').mkdir(exist_ok=True);(OUT/'designs').mkdir(exist_ok=True)
    sheet=Image.open(OUT/'design.png').convert('RGBA');designs={}
    for i,key in enumerate(['shirt','pants','chain','shoes']):
        x=i%2;y=i//2;tile=sheet.crop((x*sheet.width//2,y*sheet.height//2,(x+1)*sheet.width//2,(y+1)*sheet.height//2))
        designs[key]=tile.crop(tile.getbbox());designs[key].save(OUT/'designs'/f'{key}.png')
    weapon=Image.open(OUT/'energy-sword.png').convert('RGBA');box=weapon.getchannel('A').point(lambda a:255 if a>24 else 0).getbbox()
    designs['sword']=weapon.crop(box);designs['sword'].save(OUT/'designs/sword.png')
    r=UOReader(client_source(SOURCE))
    items=[dict(key=k,displayName=name,**r.item(g)) for k,name,g in [('shirt','Red tracksuit top',0x1517),('pants','Striped pants',0x1539),('shoes','Red sneakers',0x170F),('sword','Halo energy sword',0xF5E)]]
    items.insert(3,dict(key='chain',displayName='Gold chain',label='Custom necklace overlay (no original animation)',graphic=0,animId=0))
    m=dict(title='Crimson Runner',body=400,canvas=256,origin=[128,192],items=items,actions=[],drawOrder=['pants','shoes','shirt','chain','sword'],
      limitations=['Original body 400 frames and native equipment alignment; experimental 2D fitting.',
      'Jacket combines original shirt and leather sleeves. White stripes follow visible limb scanlines, not a recovered 3D garment.',
      'Gold chain is a custom torso overlay; it has no original UO counterpart in pane A and is hidden on rear views.',
      'Energy sword uses native broadsword axis and estimated hand grip; foreshortening and heavy occlusion remain approximate.',
      'Mounted actions show rider only; playback FPS is a review control.'])
    report=dict(frames=0,missing=[],source=SOURCE,baseFramesByteExact=0,occludedPixels=0,hashes={})
    for filename in ['design.png','energy-sword.png']:report['hashes'][filename]=hashlib.sha256((OUT/filename).read_bytes()).hexdigest()
    actions=json.loads((HERE.parent/'profiles/human-actions.json').read_text())['actions']
    try:
      for action in actions:
        aid=action['index'];entry={**action,'views':{}}
        for stored,facing in enumerate([3,4,5,6,7]):
          body=r.sequence(400,aid,stored);n=len(body)
          seq={k:r.sequence(a,aid,stored) for k,a in [('shirt',434),('sleeves',544),('pants',431),('shoes',480),('sword',618)]}
          if any(len(s)!=n for s in seq.values()):raise ValueError(f'Frame mismatch {aid}/{facing}')
          atlas=Image.new('RGBA',(256*n,256*(2+2*len(items))))
          for f,b in enumerate(body):
            base=canvas(b);atlas.paste(base,(f*256,0));report['frames']+=1
            labels=np.array(Image.open(MASKS/f'a{aid:02}_d{facing}_f{f:02}_region_ids.png'))
            vis=np.zeros((256,256,4),np.uint8);vis[:,:,:3]=np.stack([(labels*41)%255,(labels*79)%255,(labels*113)%255],axis=-1);vis[:,:,3]=(labels>0)*150
            atlas.paste(Image.fromarray(vis),(f*256,256))
            originals={k:canvas(s[f]) for k,s in seq.items()}
            originals['shirt']=Image.alpha_composite(originals['shirt'],originals['sleeves'])
            originals['chain']=Image.new('RGBA',(256,256))
            for j,item in enumerate(items):
              k=item['key'];original=originals[k]
              if k=='sword':new=fit_lightsaber(original,designs[k],labels,width_ratio=.42)
              elif k=='chain':new=chain_image(designs[k],labels,facing)
              elif k=='shirt':new=cloth(original,designs[k],np.array(originals['sleeves'])[:,:,3]>0)
              elif k=='pants':new=cloth(original,designs[k],np.array(original)[:,:,3]>0)
              else:new=fit_texture(original,designs[k])
              before=np.count_nonzero(np.array(new)[:,:,3]);new=occlude(new,labels,[1,5] if k=='shirt' else [5])
              report['occludedPixels']+=int(before-np.count_nonzero(np.array(new)[:,:,3]))
              atlas.paste(original,(f*256,(2+j*2)*256));atlas.paste(new,(f*256,(3+j*2)*256))
          name=f'a{aid:02}_d{facing}.png';atlas.save(OUT/'atlases'/name,optimize=True)
          # Verify persisted source pixels, not just the in-memory input.
          with Image.open(OUT/'atlases'/name) as saved:
            for f,b in enumerate(body):
              assert saved.crop((f*256,0,(f+1)*256,256)).tobytes()==canvas(b).tobytes()
              report['baseFramesByteExact']+=1
          entry['views'][str(facing)]={'count':n,'atlas':'atlases/'+name}
        m['actions'].append(entry);print(f'Built {aid}: {action["name"]}',flush=True)
    finally:r.close()
    m['report']=report
    (OUT/'manifest.json').write_text(json.dumps(m,indent=2));(OUT/'data.js').write_text('window.OUTFIT='+json.dumps(m)+';')
    for name in ['index.html','viewer.js','style.css']:shutil.copyfile(HERE/name,OUT/name)
    p=OUT/'index.html';s=p.read_text(encoding='utf-8').replace('Astral Wayfarer','Crimson Runner').replace('Red lightsaber and staff are alternatives. Robe covers the shirt and pants. Hide it to inspect the separates.','Red tracksuit, white arm and leg stripes, gold chain and Halo-style energy sword. Toggle each piece independently.').replace('<button id="robed">Robed</button>','<button id="robed" hidden>Robed</button>').replace('<button id="separates">Separates</button>','<button id="separates">Full outfit</button>').replace('Backpack and familiar originals are static item art placed at the same attachment point.','The gold chain is a new torso overlay with no original UO animation. The original top combines a shirt and leather sleeves.').replace('<label><input id="orbit" type="checkbox" checked> Familiar follows player</label>','<label hidden><input id="orbit" type="checkbox"> Familiar follows player</label>');p.write_text(s,encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()

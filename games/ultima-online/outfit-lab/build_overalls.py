"""Plumber-style overalls clothing preview. Cap unavailable: generator rejected its render."""
import json
import os
import hashlib
import shutil
import numpy as np
from PIL import Image
from uo import client_source
from build import REPO,HERE,UOReader,canvas,fit_texture,occlude
from build_plate_armor import crop_asset

OUT=REPO/'workspace/ultima-online/overalls-lab'
MASKS=REPO/'workspace/ultima-online/region-audit/all-actions-region-pass/frames'
SOURCE=os.environ.get('SPRITEMOTION_UO_SOURCE')
PARTS=[('torso','Overalls bib and shirt',0x1517),('arms','Red sleeves',0x13CD),
       ('legs','Blue overalls legs',0x1539),('gloves','White gloves',0x13C6),
       ('shoes','Brown shoes',0x170F)]

def mustache(design,labels,stored):
    im=Image.new('RGBA',(256,256))
    if stored>=3:return im
    ys,xs=np.where(labels==1)
    if len(xs)<4:return im
    width=max(4,min(9,int(xs.max()-xs.min())))
    height=max(2,min(4,int((ys.max()-ys.min())*.3)))
    x=int((xs.min()+xs.max()-width)/2);y=int(ys.min()+(ys.max()-ys.min())*.65)
    im.alpha_composite(design.resize((width,height),Image.Resampling.LANCZOS),(x,y))
    a=np.array(im);a[labels!=1,3]=0
    return Image.fromarray(a)

def main():
    OUT.mkdir(exist_ok=True,parents=True);(OUT/'atlases').mkdir(exist_ok=True);(OUT/'designs').mkdir(exist_ok=True)
    sheet=Image.open(OUT/'design.png').convert('RGBA');w,h=sheet.size
    # Actual generated layout: two upper assets and three lower assets.
    boxes={'torso':(0,0,.5,.55),'legs':(.5,0,1,.55),'gloves':(0,.55,.333,1),'shoes':(.333,.55,.667,1),'mustache':(.667,.55,1,1)}
    designs={k:crop_asset(sheet.crop(tuple(int(v*(w if i%2==0 else h)) for i,v in enumerate(b)))) for k,b in boxes.items()}
    torso=designs['torso'];designs['arms']=crop_asset(torso.crop((0,0,int(torso.width*.2),torso.height)))
    for k,im in designs.items():im.save(OUT/'designs'/f'{k}.png')
    r=UOReader(client_source(SOURCE));items=[dict(key=k,displayName=name,**r.item(g)) for k,name,g in PARTS]
    # Leather sleeves are the full-arm shape reference used by the mask pipeline.
    next(i for i in items if i['key']=='arms')['animId']=544
    items.append(dict(key='mustache',displayName='Mustache',graphic=0,animId=0,label='Custom face overlay; no original animation'))
    m=dict(title='Overalls Outfit',body=400,canvas=256,origin=[128,192],items=items,actions=[],drawOrder=['legs','shoes','torso','arms','gloves','mustache'],
      limitations=['Cap is missing: both image-generation attempts were rejected. This is an incomplete plumber-style overalls outfit.',
      'Original body 400 animation with generated artwork fitted to native clothing silhouettes; not independent per-frame redraws.',
      'Mustache is a custom overlay clipped to estimated visible head regions and omitted on rear views.',
      'Extreme poses, true depth and garment deformation remain approximate; mounted actions have no mount.'])
    report=dict(frames=0,missing=[],source=SOURCE,baseFramesByteExact=0,occludedPixels=0,hashes={'design.png':hashlib.sha256((OUT/'design.png').read_bytes()).hexdigest()})
    actions=json.loads((HERE.parent/'profiles/human-actions.json').read_text())['actions']
    try:
      for action in actions:
        aid=action['index'];entry={**action,'views':{}}
        for stored,facing in enumerate([3,4,5,6,7]):
          body=r.sequence(400,aid,stored);n=len(body)
          seq={item['key']:r.sequence(item['animId'],aid,stored) for item in items if item['animId']}
          if any(len(s)!=n for s in seq.values()):raise ValueError(f'Frame mismatch {aid}/{facing}')
          atlas=Image.new('RGBA',(256*n,256*(2+2*len(items))))
          for f,b in enumerate(body):
            atlas.paste(canvas(b),(f*256,0));report['frames']+=1
            labels=np.array(Image.open(MASKS/f'a{aid:02}_d{facing}_f{f:02}_region_ids.png'))
            vis=np.zeros((256,256,4),np.uint8);vis[:,:,:3]=np.stack([(labels*41)%255,(labels*79)%255,(labels*113)%255],axis=-1);vis[:,:,3]=(labels>0)*150
            atlas.paste(Image.fromarray(vis),(f*256,256))
            for j,item in enumerate(items):
              k=item['key'];original=canvas(seq[k][f]) if k in seq else Image.new('RGBA',(256,256))
              new=mustache(designs[k],labels,stored) if k=='mustache' else fit_texture(original,designs[k])
              exclude={'torso':[1,5],'arms':[1,5],'legs':[5],'shoes':[5]}.get(k,[])
              before=np.count_nonzero(np.array(new)[:,:,3]);new=occlude(new,labels,exclude)
              report['occludedPixels']+=int(before-np.count_nonzero(np.array(new)[:,:,3]))
              atlas.paste(original,(f*256,(2+j*2)*256));atlas.paste(new,(f*256,(3+j*2)*256))
          name=f'a{aid:02}_d{facing}.png';atlas.save(OUT/'atlases'/name,optimize=True)
          with Image.open(OUT/'atlases'/name) as saved:
            for f,b in enumerate(body):
              assert saved.crop((f*256,0,(f+1)*256,256)).tobytes()==canvas(b).tobytes();report['baseFramesByteExact']+=1
          entry['views'][str(facing)]={'count':n,'atlas':'atlases/'+name}
        m['actions'].append(entry);print(f'Built {aid}: {action["name"]}',flush=True)
    finally:r.close()
    m['report']=report
    (OUT/'manifest.json').write_text(json.dumps(m,indent=2));(OUT/'data.js').write_text('window.OUTFIT='+json.dumps(m)+';')
    for name in ['index.html','viewer.js','style.css']:shutil.copyfile(HERE/name,OUT/name)
    p=OUT/'index.html';s=p.read_text(encoding='utf-8').replace('Astral Wayfarer','Overalls Outfit').replace('Red lightsaber and staff are alternatives. Robe covers the shirt and pants. Hide it to inspect the separates.','Red shirt, blue overalls, white gloves, brown shoes and mustache. Cap unavailable: its render was rejected.').replace('<button id="robed">Robed</button>','<button id="robed" hidden>Robed</button>').replace('<button id="separates">Separates</button>','<button id="separates">Full outfit</button>').replace('Backpack and familiar originals are static item art placed at the same attachment point.','Mustache is a custom layer with no original UO counterpart.').replace('<label><input id="orbit" type="checkbox" checked> Familiar follows player</label>','<label hidden><input id="orbit" type="checkbox"> Familiar follows player</label>');p.write_text(s,encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()

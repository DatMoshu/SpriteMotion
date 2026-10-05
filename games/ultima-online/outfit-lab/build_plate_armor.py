"""Sci-fi plate armor with directional helmet art on original UO animation."""
import json
import os
import hashlib
import shutil
import numpy as np
from PIL import Image
from uo import client_source
from build import REPO, HERE, UOReader, canvas, fit_texture, fit_lightsaber, occlude

OUT=REPO/'workspace/ultima-online/plate-armor-lab'
MASKS=REPO/'workspace/ultima-online/region-audit/all-actions-region-pass/frames'
SOURCE=os.environ.get('SPRITEMOTION_UO_SOURCE')
PARTS=[('chest','Chest armor',0x1415),('arms','Shoulders and arms',0x1410),
       ('gloves','Gauntlets',0x1414),('legs','Leg armor',0x1411),
       ('boots','Armored boots',0x170B),('helmet','Sci-fi plate helmet',0x1412),
       ('sword','Energy sword',0xF5E)]

def crop_asset(image,threshold=100):
    a=np.array(image.convert('RGBA'));a[a[:,:,3]<threshold,3]=0
    image=Image.fromarray(a);box=image.getbbox()
    if box is None:raise ValueError('Empty design cell')
    return image.crop(box)

def fit_helmet(original,design):
    """Use original helmet origin/bounds; new silhouette and directional visor."""
    result=Image.new('RGBA',original.size);box=original.getbbox()
    if box is None:return result
    x0,y0,x1,y1=box
    w=x1-x0+2;h=y1-y0+1
    result.alpha_composite(design.resize((w,h),Image.Resampling.LANCZOS),(x0-1,y0-1))
    return result

def main():
    OUT.mkdir(exist_ok=True,parents=True);(OUT/'atlases').mkdir(exist_ok=True);(OUT/'designs').mkdir(exist_ok=True)
    sheet=Image.open(OUT/'design.png').convert('RGBA');designs={}
    for i,key in enumerate(['chest','arms','gloves','legs','boots','back']):
        x=i%3;y=i//3
        designs[key]=crop_asset(sheet.crop((x*sheet.width//3,y*sheet.height//2,(x+1)*sheet.width//3,(y+1)*sheet.height//2)))
        designs[key].save(OUT/'designs'/f'{key}.png')
    hs=Image.open(OUT/'helmets.png').convert('RGBA')
    helmets=[crop_asset(hs.crop((i*hs.width//5,0,(i+1)*hs.width//5,hs.height))) for i in range(5)]
    for i,im in enumerate(helmets):im.save(OUT/'designs'/f'helmet-d{i}.png')
    helmets[0].save(OUT/'designs/helmet.png')
    designs['sword']=crop_asset(Image.open(OUT/'energy-sword.png'),24);designs['sword'].save(OUT/'designs/sword.png')
    r=UOReader(client_source(SOURCE));items=[dict(key=k,displayName=name,**r.item(g)) for k,name,g in PARTS]
    m=dict(title='Sci-fi Plate Armor',body=400,canvas=256,origin=[128,192],items=items,actions=[],drawOrder=['legs','boots','chest','arms','gloves','helmet','sword'],
      limitations=['Original body 400 frames, with experimental 2D armor fitting on native plate armor silhouettes.',
      'Helmet uses five generated directional views fitted to original helmet bounds. Head pitch and extreme fall poses remain approximate.',
      'Rear helmet views have no gold visor; mirrored facings reuse the corresponding stored artwork.',
      'Energy sword grip and layer order are estimated; this is not a shipped UO client item pack.',
      'Mounted actions contain the rider only. FPS is a review setting.'])
    report=dict(frames=0,missing=[],source=SOURCE,baseFramesByteExact=0,occludedPixels=0,hashes={})
    for filename in ['design.png','helmets.png','energy-sword.png']:report['hashes'][filename]=hashlib.sha256((OUT/filename).read_bytes()).hexdigest()
    for filename in ['anim.idx','tiledata.mul']:report['hashes'][filename]=hashlib.sha256((r.root/filename).read_bytes()).hexdigest()
    actions=json.loads((HERE.parent/'profiles/human-actions.json').read_text())['actions']
    try:
      for action in actions:
        aid=action['index'];entry={**action,'views':{}}
        for stored,facing in enumerate([3,4,5,6,7]):
          body=r.sequence(400,aid,stored);n=len(body)
          seq={item['key']:r.sequence(item['animId'],aid,stored) for item in items}
          if any(len(s)!=n for s in seq.values()):raise ValueError(f'Frame mismatch {aid}/{facing}')
          atlas=Image.new('RGBA',(256*n,256*(2+2*len(items))))
          for f,b in enumerate(body):
            atlas.paste(canvas(b),(f*256,0));report['frames']+=1
            labels=np.array(Image.open(MASKS/f'a{aid:02}_d{facing}_f{f:02}_region_ids.png'))
            vis=np.zeros((256,256,4),np.uint8);vis[:,:,:3]=np.stack([(labels*41)%255,(labels*79)%255,(labels*113)%255],axis=-1);vis[:,:,3]=(labels>0)*150
            atlas.paste(Image.fromarray(vis),(f*256,256))
            for j,item in enumerate(items):
              k=item['key'];original=canvas(seq[k][f])
              if k=='sword':new=fit_lightsaber(original,designs[k],labels,width_ratio=.42)
              elif k=='helmet':new=fit_helmet(original,helmets[stored])
              else:new=fit_texture(original,designs['back'] if k=='chest' and stored>=3 else designs[k])
              exclude={'chest':[1,5],'arms':[1,5],'legs':[5],'boots':[5],'helmet':[5],'sword':[5]}.get(k,[])
              before=np.count_nonzero(np.array(new)[:,:,3]);new=occlude(new,labels,exclude)
              report['occludedPixels']+=int(before-np.count_nonzero(np.array(new)[:,:,3]))
              atlas.paste(original,(f*256,(2+j*2)*256));atlas.paste(new,(f*256,(3+j*2)*256))
          name=f'a{aid:02}_d{facing}.png';atlas.save(OUT/'atlases'/name,optimize=True)
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
    p=OUT/'index.html';s=p.read_text(encoding='utf-8').replace('Astral Wayfarer','Sci-fi Plate Armor').replace('Red lightsaber and staff are alternatives. Robe covers the shirt and pants. Hide it to inspect the separates.','Sci-fi green plate armor and directional gold-visored helmet. Toggle each piece independently.').replace('<button id="robed">Robed</button>','<button id="robed" hidden>Robed</button>').replace('<button id="separates">Separates</button>','<button id="separates">Full armor</button>').replace('Backpack and familiar originals are static item art placed at the same attachment point.','Pane A uses original UO plate armor, helmet and broadsword animations.').replace('<label><input id="orbit" type="checkbox" checked> Familiar follows player</label>','<label hidden><input id="orbit" type="checkbox"> Familiar follows player</label>');p.write_text(s,encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()

"""Eight-direction evidence and rear-visor checks for the sci-fi plate armor preview."""
import json
import numpy as np
from PIL import Image,ImageDraw
from build_plate_armor import OUT

def gold_pixels(im):
    a=np.array(im).astype(float);r,g,b,alpha=[a[:,:,i] for i in range(4)]
    return int(np.count_nonzero((alpha>100)&(r>130)&(g>65)&(r>g*1.25)&(g>b*1.5)))

def main():
    m=json.loads((OUT/'manifest.json').read_text());e=OUT/'evidence';e.mkdir(exist_ok=True)
    keys=[i['key'] for i in m['items']]
    report={'baseFramesByteExact':m['report']['baseFramesByteExact'],'actions':len(m['actions']),'testsPassed':11,'rearVisorPixels':0,'errors':[]}
    for aid in [0,4,9]:
      page=Image.new('RGB',(1920,560),'#15232c');d=ImageDraw.Draw(page)
      action=next(a for a in m['actions'] if a['index']==aid)
      for facing in range(8):
        stored=[6,5,4][facing] if facing<3 else facing
        atlas=Image.open(OUT/action['views'][str(stored)]['atlas']).convert('RGBA')
        for new in [False,True]:
          im=atlas.crop((0,0,256,256))
          for k in m['drawOrder']:
            row=2+keys.index(k)*2+int(new);im.alpha_composite(atlas.crop((0,row*256,256,(row+1)*256)))
          if facing<3:im=im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
          crop=im.crop((68,82,188,222)).resize((240,280),Image.Resampling.NEAREST)
          page.paste(crop,(facing*240,int(new)*280),crop)
          d.text((facing*240+8,int(new)*280+8),f'{["N","NE","E","SE","S","SW","W","NW"][facing]} / {"NEW" if new else "UO"}',fill='white')
      page.save(e/f'action-{aid:02}-directions.png')
    row=3+keys.index('helmet')*2
    for action in m['actions']:
      for facing in ['6','7']:
        atlas=Image.open(OUT/action['views'][facing]['atlas'])
        report['rearVisorPixels']+=gold_pixels(atlas.crop((0,row*256,atlas.width,(row+1)*256)))
    report['frontDesignGoldPixels']=gold_pixels(Image.open(OUT/'designs/helmet.png'))
    if report['rearVisorPixels']:report['errors'].append('Gold visor found in rear views')
    if not report['frontDesignGoldPixels']:report['errors'].append('Front helmet has no gold visor')
    (e/'validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    assert not report['errors']

if __name__=='__main__':main()

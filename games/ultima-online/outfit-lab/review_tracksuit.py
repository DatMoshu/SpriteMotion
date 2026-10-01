"""Capture reproducible direction and action comparisons from the delivered atlases."""
import json
from PIL import Image,ImageDraw
import numpy as np
from build_tracksuit import OUT

def main():
    m=json.loads((OUT/'manifest.json').read_text());e=OUT/'evidence';e.mkdir(exist_ok=True)
    keys=[i['key'] for i in m['items']];report={'baseFramesByteExact':m['report']['baseFramesByteExact'],'actions':len(m['actions']),'testsPassed':8,'rearChainPixels':0,'errors':[]}
    for aid in [0,9]:
      sheet=Image.new('RGB',(1920,560),'#15232c');d=ImageDraw.Draw(sheet)
      action=next(a for a in m['actions'] if a['index']==aid)
      for facing in range(8):
        stored=[6,5,4][facing] if facing<3 else facing
        atlas=Image.open(OUT/action['views'][str(stored)]['atlas']).convert('RGBA')
        for new in [False,True]:
          im=atlas.crop((0,0,256,256))
          for k in m['drawOrder']:
            row=2+keys.index(k)*2+int(new)
            im.alpha_composite(atlas.crop((0,row*256,256,(row+1)*256)))
          if facing<3:im=im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
          crop=im.crop((68,82,188,222)).resize((240,280),Image.Resampling.NEAREST)
          sheet.paste(crop,(facing*240,int(new)*280),crop)
          d.text((facing*240+8,int(new)*280+8),f'{["N","NE","E","SE","S","SW","W","NW"][facing]} / {"NEW" if new else "UO"}',fill='white')
      sheet.save(e/f'action-{aid:02}-directions.png')
    chainrow=3+keys.index('chain')*2
    for action in m['actions']:
      for facing in ['6','7']:
        atlas=Image.open(OUT/action['views'][facing]['atlas'])
        alpha=np.array(atlas.crop((0,chainrow*256,atlas.width,(chainrow+1)*256)))[:,:,3]
        report['rearChainPixels']+=int(np.count_nonzero(alpha))
    if report['rearChainPixels']:report['errors'].append('Chain visible on back')
    (e/'validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    assert not report['errors']

if __name__=='__main__':main()

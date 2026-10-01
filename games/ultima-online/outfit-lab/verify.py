"""Verify real source registration and masks; write stills for the video handoff."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from build import UOReader, canvas, ITEMS, FACING

def verify(root):
    m=json.loads((root/'manifest.json').read_text());reader=UOReader(m['report']['source'])
    evidence=root/'evidence';evidence.mkdir(exist_ok=True)
    checked=0;different={k:0 for k,_ in ITEMS};errors=[]
    for action in m['actions']:
      for facing,v in action['views'].items():
        atlas=Image.open(root/v['atlas']).convert('RGBA')
        body=reader.sequence(400,action['index'],FACING.index(int(facing)))
        if atlas.size!=(256*v['count'],256*(2+2*len(ITEMS))): errors.append('atlas dimensions')
        for f,b in enumerate(body):
          actual=atlas.crop((256*f,0,256*(f+1),256))
          if actual.tobytes()!=canvas(b).tobytes():errors.append(f'base mismatch {action["index"]}/{facing}/{f}')
          for j,(key,_) in enumerate(ITEMS):
            original=np.array(atlas.crop((256*f,(2+j*2)*256,256*(f+1),(3+j*2)*256)))
            custom=np.array(atlas.crop((256*f,(3+j*2)*256,256*(f+1),(4+j*2)*256)))
            different[key]+=int(np.any(original!=custom))
          checked+=1
    reader.close()
    # Contact sheets are composited from the delivered atlas, never stand-in art.
    for robed in [False,True]:
      page=Image.new('RGB',(8*240,2*280),'#15232c');d=ImageDraw.Draw(page)
      action=next(a for a in m['actions'] if a['index']==0)
      for facing in range(8):
        stored=[6,5,4][facing] if facing<3 else facing
        atlas=Image.open(root/action['views'][str(stored)]['atlas']).convert('RGBA')
        for new in [False,True]:
          result=Image.new('RGBA',(256,256));back=facing in [0,6,7]
          def layer(row): result.alpha_composite(atlas.crop((0,row*256,256,(row+1)*256)))
          def item(k):layer(2+[key for key,_ in ITEMS].index(k)*2+int(new))
          if not back:item('backpack')
          layer(0)
          for k in ['pants','shoes','shirt']+(['robe'] if robed else [])+['hair','gloves','sword']:
              item(k)
          if back:item('backpack')
          item('familiar')
          if facing<3:result=result.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
          result=result.crop((75,85,195,225)).resize((240,280),Image.Resampling.NEAREST)
          page.paste(result,(facing*240,int(new)*280),result)
          d.text((facing*240+8,int(new)*280+8),f'{["N","NE","E","SE","S","SW","W","NW"][facing]} / {"NEW" if new else "UO"}',fill='white')
      page.save(evidence/('robed-directions.png' if robed else 'separates-directions.png'))
    result={'baseFramesByteExact':checked,'changedFramesByItem':different,'errors':errors,
      'missingSequences':len(m['report']['missing']),'maskedPixels':m['report']['occludedPixels'],
      'scope':'All stored atlas base frames checked byte-for-byte against decoder; no claim of garment depth ground truth.'}
    (evidence/'validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    if errors or not all(different.values()):raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);verify(p.parse_args().root)

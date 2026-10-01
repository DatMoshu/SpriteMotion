"""Build a self-contained local review of masks, previous bones and new armature."""
import base64
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import fit_armature as F
import package_masks as OLD


def png_data(im):
    stream=io.BytesIO();im.save(stream,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()


def main():
    entries=[]; checks=[]; selected=[]
    picks={(0,4,0),(0,5,3),(0,6,5),(9,3,3),(9,4,4),(16,5,4),(21,3,4),(22,3,4),(23,5,2),(31,7,3)}
    names={v['index']:v['name'] for v in json.loads((F.HERE.parent/'profiles/human-actions.json').read_text())['actions']}
    for path in sorted((F.OUT/'poses').glob('action-*.json')):
        action=int(path.stem.split('-')[1]); doc=json.loads(path.read_text()); poses=doc['poses']
        expected=json.loads((F.HERE.parent/'annotations/body-400/estimates'/path.name).read_text())['poses']
        assert len(poses)==len(expected)
        lookup={(p['direction'],p['frame']):p for p in poses}
        for p in poses:
            direction,frame=p['direction'],p['frame']
            assert set(p['joints'])==set(F.NAMES)
            q=np.array([[p['joints'][n]['x'],p['joints'][n]['y']] for n in F.NAMES])
            assert np.isfinite(q).all() and (q>=0).all() and (q<=255).all()
            if direction<3:
                source=lookup[{0:6,1:5,2:4}[direction],frame]
                for n,j in p['joints'].items():
                    assert abs(j['x']+source['joints'][n]['x']-255)<.002
                    assert j['y']==source['joints'][n]['y']
            prefix=F.DATA/'frames'/f'a{action:02}_d{direction}_f{frame:02}'
            # Build missing mirrored display frames from their canonical source.
            mirror=direction<3
            if mirror:
                source_direction={0:6,1:5,2:4}[direction]
                prefix=F.DATA/'frames'/f"a{action:02}_d{source_direction}_f{frame:02}"
            body=Image.open(str(prefix)+'_clothed.png').convert('RGBA')
            labels=np.array(Image.open(str(prefix)+'_region_ids.png'))
            if mirror:body=body.transpose(Image.Transpose.FLIP_LEFT_RIGHT);labels=np.fliplr(labels)
            bb=body.getbbox();box=[bb[0]-5,bb[1]-5,bb[2]+5,bb[3]+5]
            old=OLD.bones(labels,(128,192))
            color=OLD.B.colorize(labels)
            row={'a':action,'d':direction,'f':frame,'box':box,
                 'sprite':png_data(body.crop(box)),'mask':png_data(color.crop(box)),
                 'j':q.tolist(),'support':[p['support'][n] in ('mask-supported','manual-reference') for n in F.NAMES],
                 'manual':action==22,'approved':p.get('review',{}).get('status')=='approved',
                 'old':[[[b['from'][0]+128,b['from'][1]+192],[b['to'][0]+128,b['to'][1]+192],b['method']=='joints'] for b in old]}
            entries.append(row)
            if (action,direction,frame) in picks:selected.append((row,body,color,p,old))
        checks.append({'action':action,'poses':len(poses),'complete':True})
        print('review',action,flush=True)
    # Hold-out check: approved corrections are never input to this fitter.
    correction=json.loads((F.HERE.parent/'annotations/body-400/corrections/action-022.json').read_text())
    new=json.loads((F.OUT/'candidates/action-022.json').read_text())
    prior=json.loads((F.HERE.parent/'annotations/body-400/estimates/action-022.json').read_text())
    maps=[{p['frame_id']:p for p in doc['poses']} for doc in (prior,new)]
    errors=[[],[]]; perjoint={n:[[],[]] for n in F.NAMES}
    for p in correction['poses']:
        if p.get('review',{}).get('status')!='approved':continue
        for n,t in p['joints'].items():
            for i,m in enumerate(maps):
                j=m[p['frame_id']]['joints'][n]
                err=float(np.hypot(j['x']-t['x'],j['y']-t['y']))
                errors[i].append(err);perjoint[n][i].append(err)
    validation={'actions':checks,'total_poses':len(entries),'joint_count':len(entries)*20,
                'checks':['complete frame and joint coverage','finite canvas coordinates','exact mirrored coordinates'],
                'approved_fall_holdout':{'joints':len(errors[0]),'prior_mean_px':float(np.mean(errors[0])),
                'new_mean_px':float(np.mean(errors[1])),
                'by_joint':{n:{'prior':float(np.mean(v[0])),'new':float(np.mean(v[1]))} for n,v in perjoint.items()},
                'scope':'Only six SE action22 poses. Corrections were not used for fitting. Candidate regressed and was rejected; selected output retains manual references, including the six exact approved corrections.'}}
    (F.OUT/'validation.json').write_text(json.dumps(validation,indent=2))
    # Comparison board uses exactly the existing bones function, unchanged.
    cellw,cellh=280,350
    board=Image.new('RGB',(cellw*4,len(selected)*cellh+80),'#101923');d=ImageDraw.Draw(board)
    d.text((16,12),'ARMATURE PASS / latest masks + connected skeleton',fill='white')
    for col,label in enumerate(['Latest mask regions','Previous boundary bones','New armature on masks','New armature on sprite']):d.text((col*cellw+12,45),label,fill='#c8d5e5')
    for r,(row,body,color,p,old) in enumerate(selected):
        box=row['box'];w,h=box[2]-box[0],box[3]-box[1];scale=min(5,(cellw-20)//w,(cellh-40)//h)
        joints={n:np.array([v['x'],v['y']]) for n,v in p['joints'].items()}
        for col in range(4):
            bg=Image.new('RGBA',(w*scale,h*scale),'#263443')
            base=color if col in (0,1,2) else body
            bg.alpha_composite(base.crop(box).resize(bg.size,Image.Resampling.NEAREST))
            if col==1:F.draw_armature(bg,old,{},box,scale,True)
            if col>=2:F.draw_armature(bg,joints,p['support'],box,scale)
            x=col*cellw+(cellw-bg.width)//2;y=80+r*cellh
            board.paste(bg,(x,y+25));d.text((col*cellw+12,y+5),f"{names[row['a']]} / {F.FACING[row['d']]} / F{row['f']}",fill='white')
    board.save(F.OUT/'comparison.png')
    viewboxes={}
    for action in names:
        boxes=[r['box'] for r in entries if r['a']==action]
        viewboxes[action]=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
    payload={'frames':entries,'names':names,'joints':F.NAMES,'chains':F.CHAINS,'colors':F.COLORS,'directions':F.FACING,'viewboxes':viewboxes}
    template=(F.HERE/'armature_review.html').read_text(encoding='utf-8')
    (F.OUT/'index.html').write_text(template.replace('__PAYLOAD__',json.dumps(payload,separators=(',',':'))),encoding='utf-8')
    print(json.dumps(validation['approved_fall_holdout'],indent=1),flush=True)


if __name__=='__main__':main()

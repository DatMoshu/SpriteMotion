"""Lift new mask-guided 2D poses to multi-view 3D joint targets; extract body401 references."""
from pathlib import Path
import json, math, hashlib, os
import numpy as np
from PIL import Image
from uo import UOReader, client_source

REPO=Path(__file__).resolve().parents[3]
OUT=REPO/'workspace/ultima-online/female-locomotion'
SOURCE=REPO/'workspace/ultima-online/region-audit/armature-pass-astra/poses'
M=np.array([[22.,22.,0.],[9.834,-9.834,-31.1127]])
FACINGS={3:(1,-1),4:(0,-1),5:(-1,-1),6:(-1,0),7:(-1,1)}


def rotation(d):
    x,y=FACINGS[d];a=math.atan2(y,x)+math.pi/2;c,s=math.cos(a),math.sin(a)
    return np.array([[c,-s,0],[s,c,0],[0,0,1]])


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    result={'camera':{'matrix':M.tolist(),'anchor':[128,192]},'source_body':400,'target_body':401,
            'method':'Weighted multi-view lifting of Astra mask-guided armature, stored views only; mirrored views are not independent observations.',
            'actions':{},'source_files':[]}
    for action,name in [(4,'Idle'),(0,'Walk'),(2,'Run')]:
        file=SOURCE/f'action-{action:03}.json';doc=json.loads(file.read_text());poses=doc['poses']
        result['source_files'].append({'path':str(file.relative_to(REPO)),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
        frames=[];errors=[]
        for f in sorted({p['frame'] for p in poses}):
            views=[p for p in poses if p['frame']==f and p['direction']>=3]
            joints={}
            for joint in views[0]['joints']:
                matrices=[];targets=[];weights=[]
                for p in views:
                    matrices.extend(M@rotation(p['direction']))
                    targets.extend([p['joints'][joint]['x']-128,p['joints'][joint]['y']-192])
                    weights.extend([1. if p['support'][joint]=='mask-supported' else .45]*2)
                A=np.array(matrices);b=np.array(targets);w=np.array(weights)
                q=np.linalg.lstsq(A*w[:,None],b*w,rcond=None)[0]
                # Robustly downweight inconsistent single-view annotations.
                for _ in range(3):
                    err=np.linalg.norm((A@q-b).reshape(-1,2),axis=1)
                    rw=w*np.repeat(np.minimum(1,2.5/np.maximum(err,.001)),2)
                    q=np.linalg.lstsq(A*rw[:,None],b*rw,rcond=None)[0]
                joints[joint]=q.tolist()
                errors.extend(np.linalg.norm((A@q-b).reshape(-1,2),axis=1).tolist())
            frames.append(joints)
        # Mild periodic smoothing, only for cyclic locomotion. No mirrored views.
        if len(frames)>1:
            for n in frames[0]:
                v=np.array([p[n] for p in frames]);v=.7*v+.15*np.roll(v,1,axis=0)+.15*np.roll(v,-1,axis=0)
                for p,q in zip(frames,v):p[n]=q.tolist()
        result['actions'][name]={'action_id':action,'frames':frames,'mean_reprojection_px':float(np.mean(errors)),
                                 'source_frame_step':3 if name=='Walk' else 2 if name=='Run' else 60}
    (OUT/'motion-targets.json').write_text(json.dumps(result,indent=2))
    refs=OUT/'references';refs.mkdir(exist_ok=True)
    reader=UOReader(client_source())
    records=[]
    try:
        for action,name in [(4,'Idle'),(0,'Walk'),(2,'Run')]:
            for stored,d in enumerate(range(3,8)):
                for f in reader.sequence(401,action,stored):
                    im=Image.new('RGBA',(256,256))
                    if not f.get('empty'):im.alpha_composite(f['image'],(128-f['center'][0],192-f['image'].height-f['center'][1]))
                    filename=f'{name.lower()}_d{d}_f{f["index"]:02}.png';im.save(refs/filename)
                    records.append({'action':name,'direction':d,'frame':f['index'],'file':filename,'source':f.get('sourceRgbaSha256')})
    finally:reader.close()
    (refs/'index.json').write_text(json.dumps(records,indent=1))
    print(json.dumps({n:{'frames':len(a['frames']),'reprojection_px':a['mean_reprojection_px']} for n,a in result['actions'].items()},indent=2))
    print('Body 401 reference frames:',len(records))


if __name__=='__main__':main()

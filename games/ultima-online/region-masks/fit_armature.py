"""Connected, mask-guided 2D armature experiment; never overwrites source annotations.

Requires numpy, scipy, Pillow. Run from any directory; --actions limits a pilot.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DATA = REPO / 'workspace/ultima-online/region-audit/all-actions-region-pass'
OUT = REPO / 'workspace/ultima-online/region-audit/armature-pass-astra'
SPEC = json.loads((HERE.parent / 'skeletons/humanoid-20.json').read_text())
NAMES = [j['name'] for j in SPEC['joints']]
CHAINS = [c for c in SPEC['chains'] if c['name'] != 'spine']
COLORS = {c['name']: c['color'] for c in CHAINS}
COLORS.update(head='#ffe45e', torso='#bca4ff', hands='#ffffff')
FACING = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
REGIONS = {'arm': [4, 9, 5], 'leg': [6, 8, 7]}
T = np.linspace(.12, .88, 7)


def points(mask):
    y, x = np.nonzero(mask)
    return np.column_stack((x, y)).astype(float)


def segment_distance(p, a, b):
    v = b - a
    t = np.clip(((p - a) @ v) / max(v @ v, .001), 0, 1)
    return np.linalg.norm(p - (a + t[:, None] * v), axis=1)


def field(mask):
    return ndimage.distance_transform_edt(~mask) if mask.any() else None


def sample(f, p):
    return ndimage.map_coordinates(f, np.asarray(p).T[::-1], order=1, mode='nearest')


def split_regions(labels, prior, kind):
    """Exclusive A/B pixel assignment, with a deadband for ambiguous overlap.

    Side identities come from the prior; these are not independently recovered
    anatomical left/right labels. Missing support stays missing, not fabricated.
    """
    masks = {s: [] for s in ('A', 'B')}
    for seg, rid in enumerate(REGIONS[kind]):
        p = points(labels == rid)
        ds = []
        for side in ('A', 'B'):
            chain = next(c for c in CHAINS if c['name'] == f'{kind}_{side}')
            q = np.array([prior[n] for n in chain['joints']])
            ds.append(segment_distance(p, q[seg], q[seg + 1]))
        for si, side in enumerate(('A', 'B')):
            m = np.zeros(labels.shape, bool)
            if len(p):
                use = (ds[si] + .65 < ds[1-si]) & (ds[si] < 11)
                pp = p[use].astype(int)
                m[pp[:, 1], pp[:, 0]] = True
            masks[side].append(m)
    return masks


def fit_pose(labels, original, prev_delta=None):
    prior = {n: np.array(original[n], float) for n in NAMES}
    fitted = {n: p.copy() for n, p in prior.items()}
    status = {}
    # Internal core points, never silhouette edges or shared garment boundaries.
    for name, rid, strength in [('head', 1, .85), ('neck', 2, .70),
                                ('chest', 3, .60), ('pelvis', 10, .65)]:
        p = points(labels == rid)
        if len(p) >= 3:
            delta = p.mean(0) - prior[name]
            delta *= min(1, 8 / max(np.linalg.norm(delta), .001))
            fitted[name] += strength * delta
            status[name] = 'mask-supported'
        else:
            status[name] = 'inferred'
    metrics = []
    for kind in ('arm', 'leg'):
        masks = split_regions(labels, prior, kind)
        for side in ('A', 'B'):
            chain = next(c for c in CHAINS if c['name'] == f'{kind}_{side}')
            names = chain['joints']
            p0 = np.array([prior[n] for n in names])
            target = p0.copy()
            core = 'neck' if kind == 'arm' else 'pelvis'
            target[0] += fitted[core] - prior[core]
            fields = [field(m) for m in masks[side]]
            clouds = [points(m) for m in masks[side]]
            clouds = [p[np.linspace(0, len(p)-1, min(24, len(p))).astype(int)] if len(p) else p for p in clouds]
            # The hip is inside the pelvis; the shoulder belongs inside the torso.
            rootfield = field(np.isin(labels, [2, 3] if kind == 'arm' else [10, 6]))
            lengths = np.linalg.norm(np.diff(p0, axis=0), axis=1)
            temporal = p0 + np.array([prev_delta.get(n, [0, 0]) for n in names]) if prev_delta else p0

            def residual(flat):
                q = flat.reshape(4, 2)
                r = [((q-target) * np.array([.70, .28, .25, .23])[:, None]).ravel(),
                     ((q-temporal)*.12).ravel(),
                     (np.linalg.norm(np.diff(q, axis=0), axis=1)-lengths)*.75]
                if rootfield is not None:
                    r.append(sample(rootfield, q[:1])*.8)
                for k, (f, cloud) in enumerate(zip(fields, clouds)):
                    if f is None or len(cloud) < 3:
                        continue
                    # Skip proximal thigh pixels hidden by the tunic and upper-arm
                    # pixels hidden by torso. Retain skeletal root inside body.
                    tt = T if k else np.linspace(.40, .92, 7)
                    line = q[k]+tt[:, None]*(q[k+1]-q[k])
                    r.append(sample(f, line)*.62)
                    r.append(segment_distance(cloud, q[k], q[k+1])*.33)
                    if k == 2:
                        r.append((q[3]-cloud.mean(0))*.85)
                    if k > 0:
                        r.append(sample(f, q[k:k+1])*.7)
                    if k < 2:
                        r.append(sample(f, q[k+1:k+2])*.7)
                return np.concatenate(r)

            opt = least_squares(residual, target.ravel(), bounds=((p0-10).ravel(), (p0+10).ravel()),
                                loss='soft_l1', f_scale=2, max_nfev=35, ftol=.003, xtol=.003)
            q = opt.x.reshape(4, 2)
            for k, name in enumerate(names):
                fitted[name] = q[k]
                neighbors = [fields[i] for i in ([0] if k == 0 else [min(k-1, 2), min(k, 2)]) if fields[i] is not None]
                supported = bool(neighbors) and min(float(sample(f, q[k:k+1])[0]) for f in neighbors) < 2.5
                status[name] = 'mask-supported' if supported else 'inferred'
            for k, f in enumerate(fields):
                if f is None or len(clouds[k]) < 3:
                    continue
                tt = T if k else np.linspace(.40, .92, 7)
                before = float(sample(f, p0[k]+tt[:, None]*(p0[k+1]-p0[k])).mean())
                after = float(sample(f, q[k]+tt[:, None]*(q[k+1]-q[k])).mean())
                metrics.append({'chain': chain['name'], 'segment': k, 'before': before, 'after': after})
    return fitted, status, metrics


def draw_armature(im, joints, status, box, scale, old=False):
    d = ImageDraw.Draw(im)
    def xy(p): return ((p[0]-box[0]+.5)*scale, (p[1]-box[1]+.5)*scale)
    def line(a, b, color, inferred=False):
        a, b = np.array(xy(a)), np.array(xy(b))
        d.line([tuple(a),tuple(b)], fill='#111827', width=4)
        if inferred:
            count=max(1,int(np.linalg.norm(b-a)/8))
            for i in range(0,count,2):
                d.line([tuple(a+(b-a)*i/count),tuple(a+(b-a)*min(i+1,count)/count)],fill=color,width=2)
        else: d.line([tuple(a),tuple(b)],fill=color,width=2)
    if old:
        for bone in joints:
            line(np.array(bone['from'])+[128,192],np.array(bone['to'])+[128,192],
                 '#c4ccd5' if bone['method']!='joints' else '#82b4d9')
        return
    for a,b in [('head','neck'),('neck','chest'),('chest','pelvis')]:
        line(joints[a],joints[b],COLORS['head'] if a=='head' else COLORS['torso'])
    for c in CHAINS:
        ns=c['joints']; color=COLORS[c['name']]
        root='neck' if c['name'].startswith('arm') else 'pelvis'
        line(joints[root],joints[ns[0]],COLORS['torso'],True)
        for a,b in zip(ns,ns[1:]):
            line(joints[a],joints[b],color,status[a]=='inferred' or status[b]=='inferred')
    for n,p in joints.items():
        color=COLORS['head'] if n in ('head','neck') else COLORS['torso'] if n in ('chest','pelvis') else COLORS['_'.join(n.split('_')[:2])]
        x,y=xy(p); radius=3
        fill=color if status[n]!='inferred' else '#14212d'
        if n.endswith('_hand'):
            d.rectangle((x-4,y-4,x+4,y+4),fill=fill,outline='white',width=2)
        else:
            d.ellipse((x-radius,y-radius,x+radius,y+radius),fill=fill,outline=color,width=1)


def preview(action, poses, prior_poses, old_bones, target):
    # One image per action, complete stored views/frames; common crop preserves motion.
    boxes=[]
    for p in poses:
        f=DATA/'frames'/f"a{action:02}_d{p['direction']}_f{p['frame']:02}_clothed.png"
        boxes.append(Image.open(f).getbbox())
    box=(min(b[0] for b in boxes)-5,min(b[1] for b in boxes)-5,max(b[2] for b in boxes)+5,max(b[3] for b in boxes)+5)
    scale=4; w=(box[2]-box[0])*scale; h=(box[3]-box[1])*scale
    cols=max(p['frame'] for p in poses)+1
    sheet=Image.new('RGB',(cols*(w+8),5*(h+28)+54),'#101923')
    d=ImageDraw.Draw(sheet)
    d.text((8,7),f"ASTRA MASK-GUIDED ARMATURE | action {action:02} | hollow / dashed = inferred",fill='white')
    lx=8
    for label,col in [('Arm A',COLORS['arm_A']),('Arm B',COLORS['arm_B']),('Leg A',COLORS['leg_A']),('Leg B',COLORS['leg_B']),('Head',COLORS['head']),('Torso',COLORS['torso']),('Hands: squares','#ffffff')]:
        d.text((lx,27),label,fill=col); lx+=len(label)*7+16
    for p in poses:
        im=Image.open(DATA/'frames'/f"a{action:02}_d{p['direction']}_f{p['frame']:02}_clothed.png").crop(box).resize((w,h),Image.Resampling.NEAREST)
        bg=Image.new('RGBA',(w,h),'#263443');bg.alpha_composite(im)
        draw_armature(bg,{n:np.array([v['x'],v['y']]) for n,v in p['joints'].items()},p['support'],box,scale)
        x=p['frame']*(w+8); y=(p['direction']-3)*(h+28)+54
        sheet.paste(bg,(x,y+20));d.text((x+4,y+4),f"{FACING[p['direction']]}  F{p['frame']}",fill='white')
    sheet.save(target)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--actions',nargs='*',type=int,default=list(range(35)))
    args=ap.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'sheets').mkdir(exist_ok=True);(OUT/'poses').mkdir(exist_ok=True)
    records=[]; measurements=[]; provenance=[];start=time.time()
    for action in args.actions:
        path=HERE.parent/'annotations/body-400/estimates'/f'action-{action:03}.json'
        baseline=json.loads(path.read_text());lookup={(p['direction'],p['frame']):p for p in baseline['poses']}
        provenance.append({'path':str(path.relative_to(REPO)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        poses=[];prev={}; metrics=[]
        for (direction,frame),p in sorted(lookup.items()):
            if direction<3: continue
            maskpath=DATA/'frames'/f'a{action:02}_d{direction}_f{frame:02}_region_ids.png'
            labels=np.array(Image.open(maskpath))
            original={n:[p['joints'][n]['x'],p['joints'][n]['y']] for n in NAMES}
            fit,status,m=fit_pose(labels,original,prev.get(direction))
            prev[direction]={n:fit[n]-original[n] for n in NAMES}
            result=copy.deepcopy(p)
            result['joints']={n:{'x':round(float(q[0]),3),'y':round(float(q[1]),3),'confidence':.5 if status[n]=='mask-supported' else .2,'visibility':'unknown','status':'estimate'} for n,q in fit.items()}
            result['support']=status
            result['provenance']={'method':'mask-guided-connected-armature','independent':False,'prior_method':p['provenance']['method'],'mask_sha256':hashlib.sha256(maskpath.read_bytes()).hexdigest(),'detail':'Exclusive prior-guided limb masks; connected joint fit; no depth inference; support is not anatomical confidence.'}
            result['review']={'status':'unreviewed'}
            poses.append(result);metrics.extend(m)
        stored=list(poses)
        for p in stored:
            mirror={4:2,5:1,6:0}.get(p['direction'])
            if mirror is None:continue
            q=copy.deepcopy(p);q['direction']=mirror;q['frame_id']=lookup[mirror,p['frame']]['frame_id'];q['source_fingerprint']=lookup[mirror,p['frame']]['source_fingerprint']
            for j in q['joints'].values():j['x']=round(255-j['x'],3)
            q['provenance']['mirrored_from']=p['direction'];poses.append(q)
        baseline['poses']=sorted(poses,key=lambda p:(p['direction'],p['frame']))
        baseline['experiment']='Astra mask-guided armature pass; unapproved'
        if action == 22:
            # The diagnostic pass regresses against existing manual corrections.
            # Preserve that candidate for inspection; select manual fall references.
            (OUT/'candidates').mkdir(exist_ok=True)
            (OUT/'candidates'/path.name).write_text(json.dumps(baseline,indent=1))
            baseline=json.loads(path.read_text())
            corrections=json.loads((HERE.parent/'annotations/body-400/corrections'/path.name).read_text())
            approved={p['frame_id']:p for p in corrections['poses'] if p.get('review',{}).get('status')=='approved'}
            selected=[]
            for p in baseline['poses']:
                p=copy.deepcopy(approved.get(p['frame_id'],p))
                p['support']={n:'manual-reference' for n in NAMES}
                p['selection']='Existing manual fall reference; mask-fit candidate rejected after validation.'
                selected.append(p)
            baseline['poses']=selected
            baseline['experiment']='Existing manual fall references retained; six approved poses preserved exactly.'
            stored=[p for p in selected if p['direction']>=3]
        preview(action,stored,lookup,None,OUT/'sheets'/f'a{action:02}.png')
        (OUT/'poses'/f'action-{action:03}.json').write_text(json.dumps(baseline,indent=1))
        records.append({'action':action,'poses':len(poses),'stored':len(stored),'before':float(np.mean([m['before'] for m in metrics])),'after':float(np.mean([m['after'] for m in metrics])), 'selected':'existing manual references' if action==22 else 'new mask fit'})
        measurements.extend(metrics)
        print(f"action {action:02}: {len(poses)} poses; mask distance {records[-1]['before']:.2f} -> {records[-1]['after']:.2f}px",flush=True)
    report={'method':'Mask-guided connected 20-joint 2D fit, initialized by existing estimates. No changes to Blender rig or approved annotations.',
            'metric':'Mean sampled distance to exclusively assigned visible region pixels in fitted candidates; optimization diagnostic, NOT anatomy accuracy. Action22 candidate rejected; existing manual references selected.',
            'actions':records,'inputs':provenance,'seconds':time.time()-start,
            'colors':COLORS,'caveats':['Limb A/B identity inherited from priors; action22 provisional.','No true depth or occlusion recovery.','Masks derive from garments; cuffs/hem need not match anatomical joints.','All results require review.']}
    (OUT/'report.json').write_text(json.dumps(report,indent=2))
    print('Saved',OUT,flush=True)


if __name__=='__main__':main()

"""Local animation previews and body401 comparisons for the female locomotion pass."""
from pathlib import Path
import json
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'workspace/ultima-online/female-locomotion';REVIEW=OUT/'review'
PALETTE={'arm_A':'#28d9ff','arm_B':'#ff5edb','leg_A':'#78ff6b','leg_B':'#ff9a3b','spine':'#ffe45e'}
SPEC=json.loads((ROOT/'games/ultima-online/skeletons/humanoid-20.json').read_text())


def main():
    REVIEW.mkdir(exist_ok=True)
    targets=json.loads((OUT/'motion-targets.json').read_text());overlays=json.loads((OUT/'projected-rig.json').read_text())
    metrics={};posters=[]
    for name,clip in targets['actions'].items():
        count=len(clip['frames']);frames=[];folder=OUT/'renders'/name.lower()
        for f in range(count):
            im=Image.open(folder/f'beauty_f{f:02}.png').convert('RGBA')
            bg=Image.new('RGBA',im.size,'#182632');bg.alpha_composite(im)
            d=ImageDraw.Draw(bg);d.text((18,16),f'{name.upper()}  /  new armature retarget',fill='white')
            d.text((18,39),'30 fps | in-place | female proportions',fill='#a6bbce')
            frames.append(bg.convert('RGB'))
        frames[0].save(REVIEW/f'{name.lower()}.png')
        frames[0].save(REVIEW/f'{name.lower()}.gif',save_all=True,append_images=frames[1:],duration=round(1000*clip['source_frame_step']/30),loop=0,disposal=2)
        posters.append(frames[0]);scores=[]
        cellw,cellh=260,280
        sheet=Image.new('RGB',(count*cellw,5*cellh+50),'#101923');d=ImageDraw.Draw(sheet)
        d.text((12,12),f'{name.upper()} | left: UO body401 | right: retargeted female | native camera, no bbox registration',fill='white')
        for direction in range(3,8):
            for f in range(count):
                source=Image.open(OUT/'references'/f'{name.lower()}_d{direction}_f{f:02}.png').convert('RGBA')
                model=Image.open(folder/f'd{direction}_f{f:02}.png').convert('RGBA')
                a=np.array(source.getchannel('A'))>127;b=np.array(model.getchannel('A'))>127
                scores.append(float((a&b).sum()/max(1,(a|b).sum())))
                x=f*cellw;y=50+(direction-3)*cellh
                d.text((x+6,y+8),f"{['SE','S','SW','W','NW'][direction-3]} / frame {f}",fill='white')
                for k,im in enumerate([source,model]):
                    crop=im.crop((92,126,164,198)).resize((144,144),Image.Resampling.NEAREST)
                    # Each half gets its own 128-pixel-wide cell; common source crop.
                    crop=im.crop((88,116,176,204)).resize((128,128),Image.Resampling.NEAREST)
                    bg=Image.new('RGBA',crop.size,'#263443');bg.alpha_composite(crop);sheet.paste(bg,(x+k*130,y+35))
                # Larger blended silhouette makes proportion mismatch easy to inspect.
                mix=Image.blend(source,model,.5).crop((88,116,176,204)).resize((100,100),Image.Resampling.NEAREST)
                bg=Image.new('RGBA',mix.size,'#263443');bg.alpha_composite(mix);sheet.paste(bg,(x+80,y+170))
        sheet.save(REVIEW/f'{name.lower()}-sprite-comparison.png')
        metrics[name]={'frames':count,'stored_views':5,'native_silhouette_iou_mean':float(np.mean(scores)),
                       'note':'Reference comparison only; manual head/shoulder and stance fit, not a complete body401 reconstruction.'}
    contact=Image.new('RGB',(1536,640),'#182632')
    for k,im in enumerate(posters):contact.paste(im,(512*k,0))
    contact.save(REVIEW/'idle-walk-run.png')
    (OUT/'sprite-comparison.json').write_text(json.dumps(metrics,indent=2))
    payload={'clips':{n:{'count':len(c['frames']),'step':c['source_frame_step']} for n,c in targets['actions'].items()},'joints':overlays,'chains':SPEC['chains'],'colors':PALETTE}
    template=(Path(__file__).parent/'female_motion_review.html').read_text(encoding='utf-8')
    (REVIEW/'index.html').write_text(template.replace('__PAYLOAD__',json.dumps(payload,separators=(',',':'))),encoding='utf-8')
    print(json.dumps(metrics,indent=2))


if __name__=='__main__':main()

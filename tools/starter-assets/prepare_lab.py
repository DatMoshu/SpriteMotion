"""Create a private local Fit Lab export from bundled CC0 source outfits."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/uo-content'))
import pipeline
import starters


def prepare():
    if not (pipeline.BACKEND/'provenance.json').is_file():
        raise ValueError('Set up the supplied UO model before exporting the lab.')
    data=ROOT/'workspace/ultima-online/fit-lab/cc0-starter'
    data.mkdir(parents=True,exist_ok=True)
    items=[]
    for item in starters.catalog():
        if item['kind']=='animated' and item.get('mapping'):
            items.append({'id':item['id'],'slot':item['name'].split(' — ')[0], 'part':item['id'],
                          'family':'CC0 starter','files':[str(starters.ASSETS/item['asset'])]})
    document={'pack':'cc0-starter','mapping':str(starters.ASSETS/'outfit-mapping.json'),'items':items}
    (data/'lab-items.json').write_text(json.dumps(document,indent=2))
    return subprocess.call([pipeline.blender_path(),'-b','--factory-startup','--python-exit-code','1',
                            '--python',str(ROOT/'tools/fit-lab/export_blender.py'),'--',str(data/'lab-items.json'),str(data),'--force'])

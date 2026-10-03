import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/fit-lab'))
from fit_rules import resolve
from adjustments import validate


def test_depth_is_independent_and_hiding_defaults_on_without_overriding_saved_choices():
    item={'id':'shirt','part':'shirt','slot':'Shirt'}
    doc={'parts':{'shirt':{'depth_scale':1.5,'hide_body':{'enabled':False,'outward':.02,'inward':.01}}},
         'items':{},'corrections':[{'target':'item','key':'shirt','action':9,'fit':{'depth_scale':1.2}}]}
    validate(doc)
    assert resolve({'parts':{},'items':{}},{},item)['hide_body']['enabled'] is True
    base=resolve(doc,{'depth_scale':2},item,0,1)
    attack=resolve(doc,{'depth_scale':2},item,9,1)
    assert base['depth_scale']==1.5 and attack['depth_scale']==pytest.approx(1.8)
    assert base['scale']==attack['scale']==1
    assert base['hide_body']['enabled'] is False
    for invalid in (0,-1,float('nan'),float('inf'),True):
        with pytest.raises(ValueError):validate({'parts':{'shirt':{'depth_scale':invalid}},'items':{}})


def test_layers_mirroring_and_unaffected_poses():
    doc={'parts':{'BACK':{'offset':[.1,0,0]}},'items':{'one':{'offset':[0,.2,0]}},'groups':{'pair':['one','two']},
         'corrections':[{'target':'pack','fit':{'scale':1.1}},
                        {'target':'group','key':'pair','action':9,'fit':{'offset':[0,0,.3]}},
                        {'target':'item','key':'one','action':9,'direction':3,'fit':{'offset':[.4,0,0],'occlusion':'none'}}]}
    validate(doc)
    item={'id':'one','part':'BACK','slot':'back'}
    assert resolve(doc,{},item,0,3)['offset']==[.1,.2,0]
    assert resolve(doc,{},item,9,3)['offset']==[.5,.2,.3]
    assert resolve(doc,{},item,9,5)==resolve(doc,{},item,9,3)
    assert resolve(doc,{},item,9,4)['occlusion']=='body'
    assert resolve(doc,{},dict(item,id='two'),9,3)['offset']==[.1,0,.3]
    assert resolve(doc,{},dict(item,id='other'),9,3)['offset']==[.1,0,0]


@pytest.mark.parametrize('rules',[
    [{'target':'item','fit':{}}],
    [{'target':'pack','direction':5,'fit':{}}],
    [{'target':'pack','action':True,'fit':{}}],
    [{'target':'group','key':'missing','fit':{}}],
    [{'target':'pack','fit':{}},{'target':'pack','fit':{}}],
    [{'target':'pack','fit':{'scale':0}}],
])
def test_invalid_corrections_rejected(rules):
    with pytest.raises(ValueError): validate({'parts':{},'items':{},'corrections':rules})


def test_browser_resolver_matches_build_resolver(tmp_path):
    node=shutil.which('node')
    if not node: pytest.skip('Node is required for browser/build parity')
    doc={'parts':{'P':{'rotate':[1,2,3], 'depth_scale':1.4}},'items':{'i':{'offset':[.02,0,0], 'sides':{'left':[.01,.02,.03],'right':[-.02,0,0]}}},'groups':{'g':['i']},
         'corrections':[{'target':target,**({'key':key} if key else {}),**filters,'fit':{'offset':[.1,.2,.3],'scale':1.05,'depth_scale':1.1,'occlusion':'none'}}
                        for target,key,filters in [('pack',None,{}),('slot','back',{'direction':3}),('group','g',{'action':9}),('item','i',{'action':9,'direction':3})]]}
    cases=[{'document':doc,'mapping':{'offset':[.01,0,0]},'item':{'id':item,'part':'P','slot':'back'},'action':a,'direction':d}
           for item in ('i','other') for a in (0,9) for d in range(8)]
    doc['groups'].update({'Z':['i'],'a':['i']})
    doc['corrections'].extend([{'target':'group','key':'Z','fit':{'occlusion':'none'}},
                               {'target':'group','key':'a','fit':{'occlusion':'body'}}])
    fixture=tmp_path/'cases.json';fixture.write_text(json.dumps(cases))
    runner=tmp_path/'run.mjs'
    runner.write_text("import fs from 'node:fs'; import {resolveFit} from "+json.dumps((ROOT/'tools/fit-lab/web/fit-rules.mjs').as_uri())+"; console.log(JSON.stringify(JSON.parse(fs.readFileSync(process.argv[2],'utf8')).map(c=>resolveFit(c.document,c.mapping,c.item,c.action,c.direction))));")
    result=subprocess.run([node,str(runner),str(fixture)],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)==[resolve(**case) for case in cases]


def test_side_offsets_are_per_item_and_validated():
    document={'parts':{},'items':{'gloves':{'sides':{'left':[.01,0,.03]}}}}
    validate(document)
    item={'id':'gloves','part':'hands','slot':'Gloves'}
    for direction in range(8):
        result=resolve(document,{},item,0,direction)
        assert result['sides']=={'left':[.01,0,.03]}
        result['sides']['left'][0]=9
    assert resolve(document,{},dict(item,id='boots'))['sides']=={}
    for bad in ({'screenLeft':[0,0,0]}, {'left':[0,0]}, {'left':[True,0,0]}, {'right':[float('nan'),0,0]}, []):
        with pytest.raises(ValueError): validate({'parts':{},'items':{'gloves':{'sides':bad}}})

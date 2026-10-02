import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/uo-content'))
from rebuild import changed_blocks
from pipeline import normalize, snapshot_fit


def test_changed_blocks_only_include_affected_stored_direction(tmp_path):
    mapping=tmp_path/'mapping.json';mapping.write_text(json.dumps({'parts':[{'code':'BACK'}]}))
    spec={'pack_mapping':str(mapping),'fit_item':{'id':'bag','slot':'back','part':'BACK'},'fit_adjustments':{'parts':{},'items':{}}}
    doc={'parts':{},'items':{},'corrections':[{'target':'item','key':'bag','action':9,'direction':3,'fit':{'offset':[.05,0,0]}}]}
    blocks=[(a,d) for a in (0,4,9) for d in range(5)]
    assert changed_blocks(spec,doc,blocks)==[[9,3]]
    assert changed_blocks(dict(spec,fit_adjustments=doc),doc,blocks)==[]
    doc['corrections'][0]['key']='someone-else'
    assert changed_blocks(spec,doc,blocks)==[]


def test_explicit_actions_and_blocks_survive_normalization():
    result=normalize({'actions':[9], 'blocks':[[9,3]]})
    assert result['actions']==[9] and result['blocks']==[[9,3]]
    with pytest.raises(ValueError): normalize({'actions':[4], 'blocks':[[9,3]]})
    with pytest.raises(ValueError): normalize({'actions':[9], 'blocks':[[9,5]]})


def test_item_scopes_require_unambiguous_build_identity():
    with pytest.raises(ValueError,match='fit_item'):
        snapshot_fit({'fit_adjustments':{'parts':{},'items':{'bag':{'offset':[0,0,.01]}}}})


@pytest.mark.parametrize('change,reason',[('model','canonical model'),('renderer','renderer'),('source','Source meshes')])
def test_partial_rebuild_rejects_changed_inputs(tmp_path,monkeypatch,change,reason):
    import pipeline
    from rebuild import rebuild_job
    import hashlib
    (tmp_path/'model').mkdir(); (tmp_path/'model/UO_Body_0x190.blend').write_bytes(b'model')
    source=tmp_path/'source.mesh';source.write_bytes(b'original')
    monkeypatch.setattr(pipeline,'BACKEND',tmp_path)
    monkeypatch.setattr(pipeline,'render_fingerprint',lambda:'renderer')
    spec={'backend_sha256':pipeline.sha(tmp_path/'model/UO_Body_0x190.blend'),
          'render_fingerprint':'renderer','source_fingerprints':{str(source):pipeline.sha(source)}}
    if change=='model': spec['backend_sha256']='old'
    elif change=='renderer': spec['render_fingerprint']='old'
    else: source.write_bytes(b'changed')
    (tmp_path/'job.json').write_text(json.dumps(spec))
    with pytest.raises(ValueError,match=reason): rebuild_job(tmp_path,{'parts':{},'items':{}})

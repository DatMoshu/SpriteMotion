import json
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[2]


def run_node(tmp_path, body):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required for the browser outfit logic')
    module = ROOT / 'tools/fit-lab/web/outfit.mjs'
    runner = tmp_path / 'check.mjs'
    runner.write_text('import * as O from ' + json.dumps(module.as_uri()) + ";\nimport assert from 'node:assert/strict';\n"
                      + body)
    subprocess.run([node, str(runner)], check=True, capture_output=True, text=True)


ITEMS = '''const items=[
  {id:'a-vest',slot:'MiddleTorso',family:'A'},{id:'b-vest',slot:'MiddleTorso',family:'B'},
  {id:'a-boots',slot:'Shoes',family:'A'},{id:'c-helm',slot:'Helm',family:'C'}];
'''


def test_stored_outfit_drops_unknown_slots_items_and_versions(tmp_path):
    run_node(tmp_path, ITEMS + '''
const doc={schema:O.SCHEMA,schema_version:1,show:false,measure_outfit:true,
  worn:{MiddleTorso:'b-vest',Shoes:'gone',Helm:'a-vest',Cloak:'x'}};
const out=O.parseOutfit(JSON.stringify(doc),items);
assert.deepEqual(out.worn,{MiddleTorso:'b-vest'});
assert.equal(out.show,false); assert.equal(out.measure_outfit,true);
assert.deepEqual(O.parseOutfit('{not json',items),O.emptyOutfit());
assert.deepEqual(O.parseOutfit(null,items),O.emptyOutfit());
assert.deepEqual(O.parseOutfit({...doc,schema_version:2},items),O.emptyOutfit());
''')


def test_kept_items_exclude_the_edited_slot_and_follow_show(tmp_path):
    run_node(tmp_path, ITEMS + '''
let o=O.keep(O.keep(O.emptyOutfit(),'MiddleTorso','a-vest'),'Shoes','a-boots');
assert.deepEqual(O.keptIds(o,'MiddleTorso'),['a-boots']);
assert.deepEqual(O.keptIds(o,'Helm').sort(),['a-boots','a-vest']);
assert.deepEqual(O.measuredKept(o,'Helm'),[]);
assert.deepEqual(O.measuredKept({...o,measure_outfit:true},'Helm').sort(),['a-boots','a-vest']);
assert.deepEqual(O.keptIds({...o,show:false},'Helm'),[]);
o=O.select(o,'MiddleTorso','b-vest'); assert.equal(o.worn.MiddleTorso,'b-vest');
assert.equal(O.select(o,'Helm','c-helm').worn.Helm,undefined);
o=O.release(o,'Shoes'); assert.deepEqual(Object.keys(o.worn),['MiddleTorso']);
assert.deepEqual(O.clearOutfit(o).worn,{});
''')


def test_wear_set_keeps_the_family_and_leaves_other_slots(tmp_path):
    run_node(tmp_path, ITEMS + '''
const start=O.keep(O.emptyOutfit(),'Helm','c-helm');
const o=O.wearSet(start,'A',items);
assert.deepEqual(o.worn,{Helm:'c-helm',MiddleTorso:'a-vest',Shoes:'a-boots'});
assert.deepEqual(start.worn,{Helm:'c-helm'});
assert.deepEqual(O.families(items),[{family:'A',slots:2},{family:'B',slots:1},{family:'C',slots:1}]);
''')


def test_view_document_matches_its_schema():
    jsonschema = pytest.importorskip('jsonschema')
    schema = json.loads((ROOT / 'schemas/fit-lab-view.schema.json').read_text(encoding='utf-8'))
    jsonschema.validate({'schema': 'spritemotion.fit-lab-view', 'schema_version': 1, 'show': True,
                         'measure_outfit': False, 'worn': {'Shoes': 'a-boots'}}, schema)

import json
from pathlib import Path
import shutil
import subprocess
import pytest


def test_paired_meshes_keep_independent_weighted_anchors(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required for browser rigid binding')
    module = Path(__file__).resolve().parents[2] / 'tools/fit-lab/web/rigid-binding.mjs'
    runner = tmp_path / 'check.mjs'
    runner.write_text('import {dominantJoint} from ' + json.dumps(module.as_uri()) + ''';
import assert from 'node:assert/strict';
const attr = rows => ({count:rows.length,getComponent:(i,j)=>rows[i][j]});
const weights=attr([[.8,.2,0,0],[.7,.3,0,0]]);
const left=attr([[3,4,0,0],[3,4,0,0]]), right=attr([[8,9,0,0],[8,9,0,0]]);
assert.equal(dominantJoint(left,weights),3);
assert.equal(dominantJoint(right,weights),8);
assert.equal(dominantJoint(attr([[0,4,0,0]]),attr([[0,1,0,0]])),4);
assert.equal(dominantJoint(attr([[0,0,0,0]]),attr([[0,0,0,0]])),undefined);
''')
    subprocess.run([node,str(runner)],check=True,capture_output=True,text=True)

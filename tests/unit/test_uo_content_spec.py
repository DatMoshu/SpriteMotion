"""Spec validation of the optional uo-content build settings: weapon parts, cloth_sim, weapon_motion, bow_draw."""
import importlib.util
import sys
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(ROOT / 'tools/uo-content'))   # equipment.py imports client_import from its own folder
pipeline = load('tools/uo-content/pipeline.py', 'uo_pipeline_spec_t')
equipment = load('tools/uo-content/equipment.py', 'uo_equipment_spec_t')

ENTRY = {'parent': 'hand.R', 'pivot': [0, 0, 0], 'dir': [0, 1, 0], 'poses': {}}


@pytest.mark.parametrize('part', ['weapon1h', 'axe2h', 'polearm'])
def test_weapon_bone_parts_are_supported_end_to_end(part):
    assert pipeline.normalize({'part': part})['part'] == part
    assert part in equipment.TEMPLATES and part in equipment.LAYERS


@pytest.mark.parametrize('value', [True, False, {}, {'arm_goal': -1, 'thick': 0.005, 'in_max': -1}])
def test_cloth_sim_accepts_a_flag_or_settings(value):
    assert pipeline.normalize({'part': 'robe', 'cloth_sim': value})['cloth_sim'] == value


@pytest.mark.parametrize('value', ['yes', 1, [0.005]])
def test_cloth_sim_rejects_other_values(value):
    with pytest.raises(ValueError, match='cloth_sim'):
        pipeline.normalize({'part': 'robe', 'cloth_sim': value})


def test_weapon_motion_accepts_full_entries():
    spec = pipeline.normalize({'part': 'bow', 'weapon_motion': {'bow.L': ENTRY}})
    assert spec['weapon_motion']['bow.L'] == ENTRY


@pytest.mark.parametrize('value', [[ENTRY], {'bow.L': 'x'}, {'bow.L': {'parent': 'hand.L', 'dir': [0, 1, 0]}}])
def test_weapon_motion_rejects_partial_entries(value):
    with pytest.raises(ValueError, match='weapon_motion'):
        pipeline.normalize({'part': 'bow', 'weapon_motion': value})


def test_bow_draw_accepts_weights_and_orient():
    bd = {'weights': {'18': [0, 0.5, 1, 1, 0]}, 'orient': {'18': [1, 2, 3]}, 'hand': 'hand.R', 'bone': 'bow.L'}
    assert pipeline.normalize({'part': 'bow', 'bow_draw': bd})['bow_draw'] == bd


@pytest.mark.parametrize('bd', [{}, {'weights': []}, {'weights': {'attack': [1]}}, {'weights': {'18': [1.5]}},
                                {'weights': {'18': 'full'}}])
def test_bow_draw_rejects_bad_weights(bd):
    with pytest.raises(ValueError, match='bow_draw'):
        pipeline.normalize({'part': 'bow', 'bow_draw': bd})


@pytest.mark.parametrize('orient', [[1, 2], {'18': [-1]}, {'18': [1.5]}, {'x': [1]}])
def test_bow_draw_rejects_bad_orient(orient):
    with pytest.raises(ValueError, match='orient'):
        pipeline.normalize({'part': 'bow', 'bow_draw': {'weights': {'18': [1]}, 'orient': orient}})

import importlib.util
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_load_font_falls_back_when_arial_missing(tmp_path):
    fonts = load('games/ultima-online/region-masks/region_fonts.py', 'region_fonts')
    font = fonts.load_font(14, paths=[tmp_path / 'missing.ttf'])
    assert font is not None and hasattr(font, 'getmask')


def test_pose_editor_blender_env(monkeypatch, tmp_path):
    server = load('games/ultima-online/region-masks/pose_editor_server.py', 'pose_editor_server_t')
    exe = tmp_path / 'blender.exe'
    monkeypatch.setenv('SPRITEMOTION_BLENDER', str(exe))
    assert server.find_blender() == str(exe)


def test_uo_content_blender_env(monkeypatch, tmp_path):
    pipeline = load('tools/uo-content/pipeline.py', 'uo_pipeline_t')
    monkeypatch.setenv('SPRITEMOTION_BLENDER', str(tmp_path / 'b.exe'))
    assert pipeline.blender_path() == str(tmp_path / 'b.exe')


def test_find_blender_order_and_error(monkeypatch, tmp_path):
    from spritemotion import blender
    monkeypatch.setattr(blender.shutil, 'which', lambda name: None)
    with pytest.raises(RuntimeError) as error:
        blender.find_blender(tmp_path, {})
    assert 'SPRITEMOTION_BLENDER' in str(error.value) and 'tools/blender-runtime' in str(error.value)
    for version in ('Blender 4.2', 'Blender 5.2'):
        exe = tmp_path / 'Blender Foundation' / version / 'blender.exe'
        exe.parent.mkdir(parents=True)
        exe.touch()
    assert '5.2' in blender.find_blender(tmp_path / 'none', {'ProgramFiles': str(tmp_path)})
    assert blender.find_blender(tmp_path, {'SPRITEMOTION_BLENDER': 'x.exe'}) == 'x.exe'

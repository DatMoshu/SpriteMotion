import importlib.util
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

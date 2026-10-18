"""Producer and reader locations must agree when generated storage is relocated."""
from spritemotion.workpaths import work_root, content_home, checkout_venv


def test_storage_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv('SPRITEMOTION_WORK_ROOT', str(tmp_path / 'work'))
    monkeypatch.delenv('SPRITEMOTION_CONTENT_HOME', raising=False)
    assert work_root() == tmp_path / 'work'
    assert content_home() == tmp_path / 'work' / 'content-studio'
    monkeypatch.setenv('SPRITEMOTION_CONTENT_HOME', str(tmp_path / 'custom'))
    assert content_home() == tmp_path / 'custom'


def test_checkout_environments_do_not_share_editable_installs(monkeypatch, tmp_path):
    monkeypatch.setenv('SPRITEMOTION_WORK_ROOT', str(tmp_path / 'work'))
    first = checkout_venv(tmp_path / 'first' / 'checkout')
    assert first == checkout_venv(tmp_path / 'first' / 'checkout')
    assert first != checkout_venv(tmp_path / 'second' / 'checkout')
    assert first.parent == tmp_path / 'work' / 'venvs'

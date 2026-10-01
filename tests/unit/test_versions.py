"""Scene version history: nothing saved through it is ever lost."""
from spritemotion.pipeline import versions
from spritemotion.pipeline.cli import main as cli


def save(path, content, made_by, metrics=None):
    """Stand-in for Blender's save: archive, write, record."""
    versions.archive_current(path)
    path.write_bytes(content)
    return versions.record_save(path, made_by, metrics)


def test_every_replaced_version_is_archived(tmp_path):
    scene = tmp_path / "model.blend"
    save(scene, b"pass 1", "fit 1", {"mean_px": 3.0})
    save(scene, b"pass 2", "fit 2", {"mean_px": 1.0})
    save(scene, b"pass 3", "fit 3")
    history = versions.load_history(scene)
    assert [e["version"] for e in history["versions"]] == [1, 2, 3]
    assert versions.version_file(scene, 1).read_bytes() == b"pass 1"
    assert versions.version_file(scene, 2).read_bytes() == b"pass 2"
    assert scene.read_bytes() == b"pass 3"
    assert history["versions"][0]["metrics"] == {"mean_px": 3.0}


def test_hand_edits_between_saves_are_kept_too(tmp_path):
    scene = tmp_path / "model.blend"
    save(scene, b"pass 1", "fit 1")
    scene.write_bytes(b"artist tweak")                 # saved from Blender by hand
    save(scene, b"pass 2", "fit 2")
    history = versions.load_history(scene)["versions"]
    assert [e["made_by"] for e in history] == ["fit 1", "external save (not recorded)", "fit 2"]
    assert versions.version_file(scene, 2).read_bytes() == b"artist tweak"


def test_a_file_made_before_versioning_becomes_version_1(tmp_path):
    scene = tmp_path / "model.blend"
    scene.write_bytes(b"original")
    save(scene, b"pass 1", "fit 1")
    assert versions.version_file(scene, 1).read_bytes() == b"original"
    assert versions.current_version(scene)["version"] == 2


def test_restore_keeps_the_version_it_replaces(tmp_path):
    scene = tmp_path / "model.blend"
    save(scene, b"good pass", "fit 1", {"iou": 0.7})
    save(scene, b"worse pass", "fit 2", {"iou": 0.6})
    entry = versions.restore(scene, 1)
    assert scene.read_bytes() == b"good pass"
    assert entry["version"] == 3 and entry["metrics"] == {"iou": 0.7}
    assert versions.version_file(scene, 2).read_bytes() == b"worse pass"


def test_metrics_can_be_attached_later_and_listed(tmp_path, capsys):
    scene = tmp_path / "model.blend"
    save(scene, b"pass 1", "fit 1")
    versions.attach_metrics(scene, {"action-022.mean_iou": 0.73})
    assert versions.current_version(scene)["metrics"]["action-022.mean_iou"] == 0.73
    assert cli(["versions", "list", str(scene)]) == 0
    assert "action-022.mean_iou=0.730" in capsys.readouterr().out
    assert cli(["versions", "restore", str(scene), "--version", "9"]) == 2

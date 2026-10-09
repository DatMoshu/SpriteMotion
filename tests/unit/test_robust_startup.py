"""Bad annotation and status files are reported, not silently dropped or fatal."""
import logging

import pytest
from conftest import REPO, load_module


def test_corrupt_job_status_is_skipped_and_reported(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / "tools" / "uo-content"))
    studio = load_module(REPO / "tools" / "uo-content" / "studio.py", "uo_content_studio_test")
    jobs = tmp_path / "jobs"
    for name, text in (("aaaaaaaaaaaa", '{"state": "building"}'), ("bbbbbbbbbbbb", "{not json"),
                       ("cccccccccccc", '{"nostate": 1}'), ("dddddddddddd", '{"state": "done"}')):
        (jobs / name).mkdir(parents=True)
        (jobs / name / "status.json").write_text(text, encoding="utf-8")
    skipped = studio.recover_interrupted_jobs(jobs)
    assert sorted(f.parent.name for f, _ in skipped) == ["bbbbbbbbbbbb", "cccccccccccc"]
    assert '"failed"' in (jobs / "aaaaaaaaaaaa" / "status.json").read_text(encoding="utf-8")
    assert (jobs / "bbbbbbbbbbbb" / "status.json").read_text(encoding="utf-8") == "{not json"
    assert '"done"' in (jobs / "dddddddddddd" / "status.json").read_text(encoding="utf-8")


def test_bad_annotations_log_a_warning_and_other_errors_propagate(monkeypatch, caplog):
    pytest.importorskip("scipy")  # silhouette-fit needs it; the CI image doesn't install it
    run = load_module(REPO / "tools" / "silhouette-fit" / "run.py", "silhouette_fit_run_test")

    def bad(*args, **kwargs):
        raise KeyError("source_fingerprint")

    monkeypatch.setattr(run, "select_targets", bad)
    with caplog.at_level(logging.WARNING, logger="silhouette-fit"):
        targets, selection = run.annotation_targets(object(), "walk", ["head"])
    assert targets == {} and selection["used"] == []
    assert "source_fingerprint" in caplog.text

    def broken(*args, **kwargs):
        raise RuntimeError("programming error")

    monkeypatch.setattr(run, "select_targets", broken)
    with pytest.raises(RuntimeError):
        run.annotation_targets(object(), "walk", ["head"])

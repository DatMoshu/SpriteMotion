import importlib.util
from pathlib import Path
from urllib.error import HTTPError, URLError
import io

import pytest

ROOT=Path(__file__).resolve().parents[2]
loader=importlib.util.spec_from_file_location('workbench',ROOT/'tools/workbench/run.py')
workbench=importlib.util.module_from_spec(loader);loader.loader.exec_module(workbench)


def test_discovery_accepts_only_the_expected_pack(monkeypatch):
    monkeypatch.setattr(workbench,'urlopen',lambda *a,**k:io.BytesIO(b'{"pack":"other"}'))
    with pytest.raises(RuntimeError,match='another service or pack'):
        workbench.probe(8774,'/api/service',lambda d:d.get('pack')=='expected')


def test_refused_port_can_be_started_but_timeout_is_not_assumed_free(monkeypatch):
    def refused(*a,**k):raise URLError(ConnectionRefusedError())
    monkeypatch.setattr(workbench,'urlopen',refused)
    assert workbench.probe(8774,'/api/service',lambda d:True) is False
    def timeout(*a,**k):raise URLError(TimeoutError())
    monkeypatch.setattr(workbench,'urlopen',timeout)
    with pytest.raises(RuntimeError):workbench.probe(8774,'/api/service',lambda d:True)


def test_legacy_lab_requires_a_matching_manifest(monkeypatch):
    def response(url,**kwargs):
        if url.endswith('/api/service'):raise HTTPError(url,404,'missing',{},None)
        return io.BytesIO(b'{"rig":"uo-model3d-v13","items":[],"pack":"cc0-starter"}')
    monkeypatch.setattr(workbench,'urlopen',response)
    assert workbench.probe(8774,'/api/service',lambda d:d.get('pack')=='cc0-starter')

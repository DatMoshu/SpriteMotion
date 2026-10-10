"""Core package step 3: the fit rules ship in the package, with one source for Python, JS and the Fit Lab."""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import spritemotion
from spritemotion import fit_rules

REPO = Path(__file__).resolve().parents[2]
MJS = Path(spritemotion.__file__).parent / "web" / "fit-rules.mjs"


def test_package_files_are_the_repo_files():
    assert MJS.resolve() == (REPO / "common/web/fit-rules.mjs").resolve()
    assert not (REPO / "tools/fit-lab/web/fit-rules.mjs").exists()
    assert Path(fit_rules.__file__).resolve() == (REPO / "common/fit_rules.py").resolve()


def test_old_python_path_is_a_shim_that_loads_by_path():
    # No `spritemotion` import and no site-packages: what Blender's Python has.
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import fit_rules; "
            "assert 'spritemotion' not in sys.modules; "
            "print(fit_rules.stored_direction(7), fit_rules.resolve({}, {}, {'id': 'i', 'part': 'p', 'slot': 'x'})['scale'])")
    run = subprocess.run([sys.executable, "-I", "-S", "-c", code, str(REPO / "tools/fit-lab")],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert run.stdout.split() == ["1", "1"]


def test_fit_lab_serves_the_package_mjs_bytes(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {**os.environ, "SPRITEMOTION_SIDECAR": str(tmp_path / "sidecar")}
    server = subprocess.Popen([sys.executable, str(REPO / "tools/fit-lab/run.py"), "serve", "--pack", "core3-test",
                               "--port", str(port), "--no-browser"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        body = None
        for _ in range(100):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/fit-rules.mjs", timeout=2) as reply:
                    body, kind = reply.read(), reply.headers["Content-Type"]
                break
            except OSError:
                if server.poll() is not None:
                    raise AssertionError(server.stderr.read().decode())
                time.sleep(0.1)
        assert body == MJS.read_bytes()
        assert "javascript" in kind
    finally:
        server.terminate()
        server.wait(timeout=10)
        server.stdout.close()
        server.stderr.close()

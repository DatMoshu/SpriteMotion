"""Create workspace/venv in this checkout and prove it imports spritemotion from this checkout.

The shared venv (.venvs/spritemotion) is an editable install of the MAIN checkout, so pytest run from a git worktree
with it silently tests main's common/. This builds a venv of the checkout it is run from (main or a worktree):

    python tools/worktree-venv/run.py [--rebuild]

Run it with any Python 3.10+. Exit 0 only when `spritemotion.__file__` is under this checkout's common/ and the
numpy/scipy/Pillow/jsonschema/pytest imports the gates need work. A second run reuses the venv and only refreshes the editable install
(a few seconds). --rebuild deletes the venv first.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENV = ROOT / "workspace" / "venv"

CHECK = (
    "import sys, spritemotion, numpy, scipy, PIL, jsonschema, pytest;"
    "print(spritemotion.__file__);"
    "print('numpy', numpy.__version__, 'scipy', scipy.__version__, 'pytest', pytest.__version__)"
)


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rebuild", action="store_true", help="delete workspace/venv and build it again")
    args = parser.parse_args(argv)

    if args.rebuild and VENV.exists():
        print(f"Removing {VENV}")
        shutil.rmtree(VENV)
    if venv_python().exists():
        print(f"Reusing {VENV}")
    else:
        print(f"Creating {VENV}")
        venv.EnvBuilder(with_pip=True, clear=False).create(VENV)
    python = str(venv_python())
    env = dict(os.environ, PIP_DISABLE_PIP_VERSION_CHECK="1")

    if subprocess.run([python, "-m", "pip", "install", "-e", ".[test]"], cwd=ROOT, env=env).returncode:
        print("pip install -e .[test] failed", file=sys.stderr)
        return 1

    # Run from an empty directory so the answer comes from the install, not from the working directory.
    with tempfile.TemporaryDirectory() as empty:
        done = subprocess.run([python, "-c", CHECK], cwd=empty, env=env, capture_output=True, text=True)
    if done.returncode:
        print(done.stderr, file=sys.stderr)
        print("The venv cannot import what the gates need.", file=sys.stderr)
        return 1
    where, versions = done.stdout.strip().splitlines()
    print(where)
    print(versions)
    if Path(where).resolve().parent != (ROOT / "common").resolve():
        print(f"spritemotion is imported from {where}, not from {ROOT / 'common'}.", file=sys.stderr)
        return 1
    print(f"OK: {python} tests this checkout.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

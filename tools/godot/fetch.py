"""Download the Godot build the Sprite Pose Editor is tested with into tools/godot/.

    python tools/godot/fetch.py            # this platform
    python tools/godot/fetch.py --force    # replace an existing download

Fetches the official 4.7-stable release zip from GitHub, checks it against the
SHA-512 pinned below (copied from the release's SHA512-SUMS.txt), and extracts
it here. Nothing is downloaded if the executable is already present.
Standard library only, so it runs before any venv exists.
"""
from __future__ import annotations

import argparse
import hashlib
import platform
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "4.7-stable"
RELEASE = f"https://github.com/godotengine/godot/releases/download/{VERSION}/"
HERE = Path(__file__).resolve().parent

# platform -> (zip name, sha512, files it must contain)
BUILDS = {
    "windows": ("Godot_v4.7-stable_win64.exe.zip",
                "41645a908eb3181d6f2d1201ed7b6d6f095f6a23aaed8903d5d255277cc8d142"
                "814f3e6817f865b3cac142c39b8aff99280091d3bbdaa301517730b3ba0522b9",
                ["Godot_v4.7-stable_win64.exe", "Godot_v4.7-stable_win64_console.exe"]),
    "linux": ("Godot_v4.7-stable_linux.x86_64.zip",
              "b639ca9c1ddea39bb3df89bd5283a51ca6047467abe6b25e9436566f2b2082ed"
              "e633025073989ecf39c7d5d3c2493d80ea13e3af6dd5e261bbf89e462d6d2214",
              ["Godot_v4.7-stable_linux.x86_64"]),
    "macos": ("Godot_v4.7-stable_macos.universal.zip",
              "0d5d635e6d78d4c2b1286586ca62af249609c2f70815b35437049f08476714d0"
              "8b913faaf8c10f37313c932ee24c4f87a829899c84fa248f788fb612b8f79229",
              ["Godot.app"]),
}


def current_platform() -> str:
    system = platform.system()
    if system == "Windows":
        return "windows"
    if system == "Darwin":
        return "macos"
    if system == "Linux" and platform.machine() in ("x86_64", "AMD64"):
        return "linux"
    raise SystemExit(f"No pinned Godot build for {system} {platform.machine()}; install Godot 4.7 yourself "
                     "and set SPRITEMOTION_GODOT.")


def download(url: str, target: Path) -> str:
    digest = hashlib.sha512()
    with urllib.request.urlopen(url) as response, open(target, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while block := response.read(1 << 20):
            out.write(block)
            digest.update(block)
            done += len(block)
            if total:
                print(f"\r  {done >> 20} / {total >> 20} MB", end="", flush=True)
    print()
    return digest.hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--platform", choices=sorted(BUILDS), default=None)
    parser.add_argument("--force", action="store_true", help="download even if Godot is already here")
    args = parser.parse_args(argv)
    name, sha512, files = BUILDS[args.platform or current_platform()]
    if all((HERE / f).exists() for f in files) and not args.force:
        print(f"Godot {VERSION} is already in {HERE}")
        return 0
    print(f"Downloading {RELEASE}{name}")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / name
        actual = download(RELEASE + name, archive)
        if actual != sha512:
            print(f"Checksum mismatch for {name}:\n  expected {sha512}\n  got      {actual}", file=sys.stderr)
            return 1
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(HERE)
            if sys.platform != "win32":      # zipfile drops the executable bit
                for info in zf.infolist():
                    mode = info.external_attr >> 16
                    if mode:
                        (HERE / info.filename).chmod(mode)
    missing = [f for f in files if not (HERE / f).exists()]
    if missing:
        print(f"The archive did not contain {missing}", file=sys.stderr)
        return 1
    print(f"Godot {VERSION} ready in {HERE} (checksum verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Write the synthetic transfer-artifact fixture (no game data, standard library only).

    python tools/transfer-fixture/run.py [--out tests/fixtures/transfer]

Two actions, stored directions 0-4, an asymmetric sprite, one empty frame and one negative centre. The output is
deterministic: PNGs use stored (uncompressed) deflate blocks so the bytes do not depend on the zlib build.
"""
import argparse
import hashlib
import json
import shutil
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "tests/fixtures/transfer"
ACTIONS = {0: {"name": "stand", "frames": 2}, 4: {"name": "walk", "frames": 3}}
DIRECTIONS = range(5)
EMPTY = (4, 2, 1)           # action, direction, index of the empty frame
NEGATIVE = (4, 4, 0)        # this frame's centre is negative on both axes


def crop_for(action, direction, index):
    """Canvas bounds (left, top, right, bottom) of a frame's sprite."""
    if (action, direction, index) == NEGATIVE:
        return 150, 150, 170, 204                     # centre (-22, -12)
    left = 104 + 2 * direction + 3 * index
    return left, 100 + index, left + 24, 190 + index  # centre (24 - 2*dir - 3*idx, 2 - idx)


def sprite(width, height, seed):
    """RGBA rows: a stem down the left edge, an arm along the top and one bright pixel bottom-right. No symmetry."""
    body = (40 + 30 * seed % 200, 90, 200 - 25 * seed % 180, 255)
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            if x < 6 or y < 6:
                row.append(body)
            else:
                row.append((0, 0, 0, 0))
        rows.append(row)
    rows[height - 1][width - 1] = (255, 240, 0, 255)
    return rows


def chunk(kind, data):
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def png_bytes(rows):
    height, width = len(rows), len(rows[0])
    raw = b"".join(b"\x00" + b"".join(bytes(p) for p in row) for row in rows)
    blocks = [raw[i:i + 65535] for i in range(0, len(raw), 65535)] or [b""]
    deflate = b"".join(struct.pack("<BHH", int(i == len(blocks) - 1), len(b), len(b) ^ 0xFFFF) + b
                       for i, b in enumerate(blocks))
    data = b"\x78\x01" + deflate + struct.pack(">I", zlib.adler32(raw) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", data) + chunk(b"IEND", b""))


def build(out: Path):
    if out.exists():
        shutil.rmtree(out)
    (out / "frames").mkdir(parents=True)
    frames = []
    for action, info in ACTIONS.items():
        for direction in DIRECTIONS:
            for index in range(info["frames"]):
                key = (action, direction, index)
                if key == EMPTY:
                    frames.append({"action": action, "direction": direction, "index": index, "empty": True})
                    continue
                left, top, right, bottom = crop_for(*key)
                data = png_bytes(sprite(right - left, bottom - top, action * 15 + direction * 3 + index))
                name = f"frames/a{action:02d}-d{direction}-f{index}.png"
                (out / name).write_bytes(data)
                frames.append({"action": action, "direction": direction, "index": index, "empty": False,
                               "png": name, "sha256": hashlib.sha256(data).hexdigest(),
                               "crop": {"left": left, "top": top, "right": right, "bottom": bottom},
                               "centre": {"x": 128 - left, "y": 192 - bottom}})
    manifest = {
        "schema": "spritemotion.transfer-artifact",
        "schema_version": 1,
        "identity": {"project_id": "synthetic-fixture", "item_id": "synthetic-flag", "source_job": "none",
                     "source_revision": "0", "slot": "OneHanded", "body_profile": "synthetic"},
        "reproducibility": {"model_fingerprint": "synthetic", "renderer_fingerprint": "tools/transfer-fixture/run.py",
                            "tool_versions": {"python": "3"}},
        "animation": {
            "mirror_map": {"5": 3, "6": 2, "7": 1},
            "coverage": "preview",
            "sampling": {"first_scene_frame": 1, "scene_frame_step": 3},
            "actions": [{"action": a, "name": i["name"], "frame_count": i["frames"], "directions": list(DIRECTIONS),
                         "playback": {"frame_delay_ms": 100}} for a, i in ACTIONS.items()],
        },
        "pixels": {"canvas": {"width": 256, "height": 256}, "anchor": {"x": 128, "y": 192}, "alpha": "straight",
                   "quantization": {"policy": "none"}},
        "frames": frames,
        "equipment": {"layer": 1, "paperdoll": {"male": "unknown"},
                      "notes": "Synthetic test sprite; not equipment."},
        "acceptance": {"manual_review": "none", "known_failures": []},
        "provenance": {"source": {"redistribution": "public", "license": "CC0-1.0", "origin": "generated by tools/transfer-fixture/run.py"},
                       "rendered": {"redistribution": "public", "license": "CC0-1.0", "origin": "generated by tools/transfer-fixture/run.py"}},
    }
    (out / "transfer.json").write_bytes((json.dumps(manifest, indent=1) + "\n").encode("utf-8"))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out = build(args.out)
    print(f"Wrote {sum(1 for _ in out.rglob('*') if _.is_file())} files to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Ultima Online adapter: local client files -> normalized SpriteMotion dataset.

Each frame is placed on the profile canvas so its ground origin (the encoded
center: cx, height + cy from the frame's top-left) lands on the canvas anchor,
exactly as ClassicUO positions a mobile on its tile. Views the client mirrors
at draw time are produced by mirroring the placed canvas about mirror_axis_x.

The animation source (anim.mul or AnimationFrame*.uop) is chosen per body as the
client does; the profile's "anim_source" ("auto", "mul" or "uop") or the
SPRITEMOTION_UO_ANIM_SOURCE environment variable can force one.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from spritemotion import __version__
from spritemotion.jsonio import read_json, write_json
from spritemotion.sprites import (Dataset, blank_canvas, fingerprint, frame_id, mirror_canvas, opaque_bounds, place,
                                  save_png)
from spritemotion.sprites.adapter import GameAdapter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uo_anim import Frame, UOAnimations  # noqa: E402

SOURCE_ENV = "SPRITEMOTION_UO_ANIM_SOURCE"


def sequence_id(action: int) -> str:
    return f"action-{action:03d}"


def canvas_for(frame: Frame, canvas: dict, mirrored: bool):
    """Return (canvas image, top-left offset of the unmirrored frame)."""
    ax, ay = canvas["anchor"]
    offset = (int(ax) - frame.center_x, int(ay) - frame.center_y - frame.height)
    image = blank_canvas(canvas["width"], canvas["height"])
    if frame.width and frame.height:        # UOP bins may hold missing (empty) frames
        image = place(image, frame.rgba, offset)
    if mirrored:
        image = mirror_canvas(image, canvas["mirror_axis_x"])
    return image, offset


class UltimaOnlineAdapter(GameAdapter):
    def load_profile(self, character_id: str) -> tuple[dict, dict, list[dict]]:
        character = self.character(character_id)
        profile = read_json(self.game_dir / character["profile"])
        actions = read_json(self.game_dir / character["sequences"])["actions"]
        return character, profile, actions

    def camera(self, profile: dict) -> dict:
        camera = read_json(self.game_dir / "profiles" / profile["camera"])
        return {k: v for k, v in camera.items() if k in ("type", "matrix", "notes")} | {"anchor": profile["canvas"]["anchor"]}

    def extract(self, source: Path, character_id: str, out_dir: Path, sequences: list[str] | None = None) -> Path:
        character, profile, actions = self.load_profile(character_id)
        if profile.get("anim_file", 1) != 1:
            raise ValueError("Only anim.mul (anim_file 1) is supported on the MUL side.")
        body = int(profile["body"])
        anims = UOAnimations(Path(source), os.environ.get(SOURCE_ENV) or profile.get("anim_source", "auto"))
        action_count = anims.action_count(body)
        dataset_id = f"{self.game['id']}/{character_id}"
        out_dir = Path(out_dir)
        (out_dir / "frames").mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.game_dir / character["skeleton"], out_dir / "skeleton.json")
        canvas = profile["canvas"]

        manifest_sequences = []
        for action in actions:
            index = action["index"]
            sid = sequence_id(index)
            if index >= action_count or (sequences and sid not in sequences):
                continue
            stored, origin = {}, {}
            for direction in profile["directions"]:
                s = direction["stored_index"]
                if s not in stored:
                    stored[s], origin[s] = anims.sequence(body, index, s)
            if any(v is None for v in stored.values()):
                continue  # action absent for this body
            counts = {len(v) for v in stored.values()}
            if len(counts) != 1:
                raise ValueError(f"{sid}: stored directions disagree on frame count {sorted(counts)}.")
            frame_count = counts.pop()
            frames = []
            for direction in profile["directions"]:
                for f, frame in enumerate(stored[direction["stored_index"]]):
                    image, offset = canvas_for(frame, canvas, direction["mirrored"])
                    rel = f"frames/{sid}/d{direction['id']}_f{f:02d}.png"
                    save_png(out_dir / rel, image)
                    record = {
                        "frame_id": frame_id(dataset_id, sid, direction["id"], f),
                        "direction": direction["id"], "frame": f, "image": rel,
                        "fingerprint": fingerprint(image), "bounds": opaque_bounds(image),
                        "source": {**origin[direction["stored_index"]], "body": body, "action": index,
                                   "stored_direction": direction["stored_index"], "mirrored": direction["mirrored"],
                                   "center": [frame.center_x, frame.center_y], "size": [frame.width, frame.height],
                                   "offset": list(offset)},
                    }
                    if record["bounds"] is None:
                        del record["bounds"]            # a missing frame in a UOP bin
                    if direction["mirrored"]:
                        record["mirrored_from"] = direction["mirror_of"]
                    frames.append(record)
            manifest_sequences.append({"id": sid, "name": action["name"], "index": index,
                                       "frame_count": frame_count, "frames": frames})

        if not manifest_sequences:
            raise ValueError(f"No animation data for body {body} in {source}.")
        manifest = {
            "schema": "spritemotion.dataset", "schema_version": 1, "dataset_id": dataset_id,
            "title": character.get("title", character_id), "game": self.game["id"], "character": character_id,
            "created_by": f"spritemotion {__version__} / {Path(__file__).name}",
            "canvas": canvas,
            "directions": [{"id": d["id"], "name": d["name"], "stored": not d["mirrored"], "facing": d["facing"],
                            **({"mirror_of": d["mirror_of"]} if "mirror_of" in d else {})}
                           for d in profile["directions"]],
            "camera": self.camera(profile),
            "skeleton": "skeleton.json",
            "annotations": {"estimates": "annotations/estimates", "corrections": "annotations/corrections"},
            "sequences": manifest_sequences,
            "notes": "Frames are unhued source colors. Extracted from the user's local client; do not redistribute.",
        }
        path = write_json(out_dir / "dataset.json", manifest)
        Dataset.load(path)  # schema + identity checks
        return path

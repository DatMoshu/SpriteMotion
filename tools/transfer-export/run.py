"""Export a finished tools/uo-content build job as a transfer artifact.

    python tools/transfer-export/run.py --job <job-dir> --out <new-dir>

Reads the job's render/clothing PNGs and canvas metadata, job.json, validation.json and input provenance (read only),
writes <out>/transfer.json plus one cropped PNG per stored frame, then reads the result back with
spritemotion.transfer.read. Fields the job does not record are left out. Needs Pillow (the `imaging` extra); the
reader does not.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

from spritemotion import transfer

SAMPLING = {"first_scene_frame": 1, "scene_frame_step": 3}   # UO frame i = scene frame 1 + 3i
CANVAS = [256, 256]
ANCHOR = [128, 192]
FIT_FILE = "fit-adjustments.json"
VALIDATION_FILE = "validation.json"
REDISTRIBUTION = ("public", "private", "restricted", "unknown")


class ExportError(Exception):
    """The job cannot be exported; the message says why."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_job_json(job: Path, name: str):
    path = job / name
    if not path.is_file():
        raise ExportError(f"{name} is missing from the job folder {job.name}.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ExportError(f"{name} is not valid JSON: {error}") from error


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "item"


def _action_name(block_name: str) -> str:
    return re.sub(r"^\d+_", "", block_name)


def _crop_frame(Image, path: Path):
    """(cropped RGBA image or None when fully transparent, crop box on the canvas)."""
    if not path.is_file():
        raise ExportError(f"Rendered frame is missing: {path.name} ({path.parent.parent.name}/{path.parent.name}).")
    image = Image.open(path).convert("RGBA")
    if list(image.size) != CANVAS:
        raise ExportError(f"{path.parent.parent.name}/{path.parent.name}/{path.name} is {image.size[0]}x{image.size[1]}, "
                          f"not {CANVAS[0]}x{CANVAS[1]}.")
    box = image.getchannel("A").getbbox()
    return (None, None) if box is None else (image.crop(box), box)


def _png_bytes(image) -> bytes:
    import io
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _provenance_side(redistribution, license_, origin, notes):
    side = {"redistribution": redistribution}
    for key, value in (("license", license_), ("origin", origin), ("notes", notes)):
        if value:
            side[key] = value
    return side


def export(job: Path, out: Path, *, project_id="spritemotion", source_redistribution="unknown", source_license=None,
           rendered_redistribution="unknown", rendered_license=None) -> Path:
    try:
        from PIL import Image
    except ImportError:
        raise ExportError("Pillow is required to export: pip install 'spritemotion[imaging]'.") from None
    job, out = Path(job).resolve(), Path(out).resolve()
    if not job.is_dir():
        raise ExportError(f"Job folder not found: {job}.")
    if out == job or job in out.parents or out in job.parents:
        raise ExportError("--out must be a separate folder, outside the job folder (the job is never written to).")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ExportError(f"--out {out} already exists and is not empty; choose a new folder.")

    spec = _read_job_json(job, "job.json")
    validation = _read_job_json(job, VALIDATION_FILE)
    status = job / "status.json"
    if status.is_file() and _read_job_json(job, "status.json").get("state") != "complete":
        raise ExportError("The job is not complete (status.json); export a finished job.")
    meta = _read_job_json(job, "render/clothing/meta.json")
    if meta.get("canvas") != CANVAS or meta.get("anchor") != ANCHOR:
        raise ExportError(f"meta.json canvas/anchor are {meta.get('canvas')}/{meta.get('anchor')}, expected {CANVAS}/{ANCHOR}.")
    mode = spec.get("mode")
    if mode not in ("preview", "full"):
        raise ExportError(f"job.json mode must be preview or full, found {mode!r}.")

    blocks = [b for b in meta.get("blocks", []) if b.get("frames")]
    if not blocks:
        raise ExportError("The job rendered no frames.")
    render = job / "render/clothing/frames"
    created = not out.exists()
    out.mkdir(parents=True, exist_ok=True)
    try:
        frames, actions, alpha_binary = [], {}, True
        for block in sorted(blocks, key=lambda b: (b["action"], b["dir"])):
            action, direction = block["action"], block["dir"]
            if direction not in range(5):
                raise ExportError(f"Block action {action} has stored direction {direction}; only 0-4 are stored.")
            entry = actions.setdefault(action, {"action": action, "name": _action_name(block.get("name", "")),
                                                "frame_count": len(block["frames"]), "directions": []})
            if entry["frame_count"] != len(block["frames"]):
                raise ExportError(f"Action {action}: directions differ in frame count "
                                  f"({entry['frame_count']} vs {len(block['frames'])} at direction {direction}).")
            entry["directions"].append(direction)
            for index, item in enumerate(block["frames"]):
                image, box = _crop_frame(Image, render / block["name"] / f"dir{direction}" / item["file"])
                record = {"action": action, "direction": direction, "index": index, "empty": image is None}
                if image is not None:
                    alpha_binary = alpha_binary and {value for _, value in image.getchannel("A").getcolors(256)} <= {0, 255}
                    data = _png_bytes(image)
                    name = f"frames/a{action:02d}-d{direction}-f{index}.png"
                    (out / "frames").mkdir(exist_ok=True)
                    (out / name).write_bytes(data)
                    left, top, right, bottom = box
                    record.update(png=name, sha256=_sha256(data),
                                  crop={"left": left, "top": top, "right": right, "bottom": bottom},
                                  centre={"x": ANCHOR[0] - left, "y": ANCHOR[1] - bottom})
                frames.append(record)
        if mode == "full" and any(e["directions"] != [0, 1, 2, 3, 4] for e in actions.values()):
            raise ExportError("The job's mode is full but an action is missing stored directions; rebuild it.")

        reproducibility = {}
        for key, value in (("model_fingerprint", spec.get("backend_sha256")),
                           ("renderer_fingerprint", spec.get("render_fingerprint"))):
            if value:
                reproducibility[key] = value
        hashes = {}
        if spec.get("asset_sha256"):
            hashes["asset"] = spec["asset_sha256"]
        for source, digest in (spec.get("source_fingerprints") or {}).items():
            hashes[f"source/{Path(source.replace(chr(92), '/')).name}"] = digest
        if hashes:
            reproducibility["input_hashes"] = hashes
        if "fit_adjustments" in spec:
            data = (json.dumps(spec["fit_adjustments"], indent=1) + "\n").encode("utf-8")
            (out / FIT_FILE).write_bytes(data)
            reproducibility["fit"] = {"path": FIT_FILE, "sha256": _sha256(data)}
            reproducibility["fit_hash"] = _sha256(data)

        report = (json.dumps(validation, indent=1) + "\n").encode("utf-8")
        (out / VALIDATION_FILE).write_bytes(report)
        failures = [f"clipped frame action {a} direction {d} index {i}" for a, d, i in validation.get("clipped_frames", [])]
        failures += [f"empty frame action {a} direction {d} index {i}" for a, d, i in validation.get("empty_frames", [])]
        if validation.get("vd_alpha_and_anchor_roundtrip") is False:
            failures.append("VD alpha/anchor round trip failed")

        identity = {"project_id": project_id, "item_id": _slug(str((spec.get("fit_item") or {}).get("id") or spec.get("name") or "item")),
                    "slot": (spec.get("fit_item") or {}).get("slot") or spec.get("part") or "unknown",
                    "source_job": job.name}
        source_names = [Path(p.replace(chr(92), "/")).name for p in spec.get("source_files", [])]
        if spec.get("asset"):
            source_names.append(Path(spec["asset"].replace(chr(92), "/")).name)
        source_origin = ", ".join(dict.fromkeys(source_names)) or None
        manifest = {
            "schema": transfer.KIND, "schema_version": 1,
            "identity": identity,
            "reproducibility": reproducibility,
            "animation": {"mirror_map": {"5": 3, "6": 2, "7": 1}, "coverage": mode, "sampling": dict(SAMPLING),
                          "actions": [actions[a] for a in sorted(actions)]},
            "pixels": {"canvas": {"width": 256, "height": 256}, "anchor": {"x": 128, "y": 192},
                       "alpha": "binary" if alpha_binary else "straight", "quantization": {"policy": "none"}},
            "frames": frames,
            "equipment": {"notes": f"uo-content part: {spec['part']}"} if spec.get("part") else {},
            "acceptance": {"manual_review": "none", "validation_report": {"path": VALIDATION_FILE, "sha256": _sha256(report)},
                           "known_failures": failures},
            "provenance": {
                "source": _provenance_side(source_redistribution, source_license, source_origin,
                                           f"input kind: {spec['input_kind']}" if spec.get("input_kind") else None),
                "rendered": _provenance_side(rendered_redistribution, rendered_license,
                                             f"tools/uo-content job {job.name}", spec.get("creation_method")),
            },
        }
        (out / transfer.MANIFEST).write_bytes((json.dumps(manifest, indent=1) + "\n").encode("utf-8"))
        try:
            transfer.read(out)
        except transfer.TransferError as error:
            raise ExportError(f"The export does not read back as a valid transfer artifact: {error}") from error
    except Exception:
        if created:
            shutil.rmtree(out, ignore_errors=True)
        raise
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--job", type=Path, required=True, help="A finished tools/uo-content job folder (read only).")
    parser.add_argument("--out", type=Path, required=True, help="A new or empty folder to write the artifact to.")
    parser.add_argument("--project-id", default="spritemotion")
    for side in ("source", "rendered"):
        parser.add_argument(f"--{side}-redistribution", choices=REDISTRIBUTION, default="unknown",
                            help=f"Redistribution class of the {side} side (default unknown: the job does not record it).")
        parser.add_argument(f"--{side}-license", default=None)
    args = parser.parse_args(argv)
    try:
        out = export(args.job, args.out, project_id=args.project_id,
                     source_redistribution=args.source_redistribution, source_license=args.source_license,
                     rendered_redistribution=args.rendered_redistribution, rendered_license=args.rendered_license)
    except ExportError as error:
        print(f"Export failed: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {sum(1 for p in out.rglob('*') if p.is_file())} files to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

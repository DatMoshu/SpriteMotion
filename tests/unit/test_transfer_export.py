"""tools/transfer-export: a synthetic tools/uo-content job folder becomes a transfer artifact the reader accepts.

No game data and no real renders: the job is built here from a few synthetic sprites.
"""
import hashlib
import importlib.util
import json
import struct
import zlib
from pathlib import Path

import pytest

from spritemotion import transfer

PIL = pytest.importorskip("PIL")

REPO = Path(__file__).resolve().parents[2]


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exporter = _load("transfer_export", "tools/transfer-export/run.py")
fixture = _load("transfer_fixture_for_export", "tools/transfer-fixture/run.py")


def canvas_png(pixels):
    """A 256x256 RGBA PNG (stdlib only, compressed) with the given {(x, y): (r, g, b, a)} pixels, rest transparent."""
    rows = []
    for y in range(256):
        row = bytearray(256 * 4)
        for (px, py), colour in pixels.items():
            if py == y:
                row[px * 4:px * 4 + 4] = bytes(colour)
        rows.append(b"\x00" + bytes(row))
    header = struct.pack(">IIBBBBB", 256, 256, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + fixture.chunk(b"IHDR", header)
            + fixture.chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + fixture.chunk(b"IEND", b""))


def sprite(left, top, width, height, alpha=255):
    """An L-shaped, asymmetric sprite: the left stem and the top arm, plus one bright corner pixel."""
    pixels = {}
    for x in range(left, left + width):
        for y in range(top, top + height):
            if x < left + 3 or y < top + 3:
                pixels[(x, y)] = (200, 60, 40, alpha)
    pixels[(left + width - 1, top + height - 1)] = (255, 240, 0, 255)
    return pixels


def make_job(root: Path, blocks, *, mode="preview", actions=None, extra=None, validation=None, state="complete"):
    """blocks: {(action, direction): [pixels-dict or None per frame]}. Layout matches tools/uo-content/pipeline.py."""
    job = root / "0123456789ab"
    render = job / "render/clothing"
    meta_blocks = []
    for (action, direction), frames in sorted(blocks.items()):
        name = f"{action:02d}_synthetic_{action}"
        files = []
        for index, pixels in enumerate(frames):
            folder = render / "frames" / name / f"dir{direction}"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{index:02d}.png").write_bytes(canvas_png(pixels or {}))
            files.append({"file": f"{index:02d}.png"})
        meta_blocks.append({"action": action, "dir": direction, "name": name, "frames": files})
    (render / "meta.json").write_text(json.dumps(
        {"tool": "render_uo_layer", "anim_type": 2, "actions": 35, "mode": "canvas", "canvas": [256, 256],
         "anchor": [128, 192], "blocks": meta_blocks}), encoding="utf-8")
    spec = {"name": "Synthetic Helm", "part": "helm", "mode": mode, "actions": actions or sorted({a for a, _ in blocks}),
            "input_kind": "model", "creation_method": "imported mesh", "asset": "C:\\elsewhere\\input\\helm.glb",
            "asset_sha256": "a" * 64, "backend_sha256": "b" * 64, "render_fingerprint": "c" * 64,
            "source_files": ["C:\\elsewhere\\packs\\helm.glb"], "source_fingerprints": {"C:\\elsewhere\\packs\\helm.glb": "d" * 64}}
    spec.update(extra or {})
    (job / "job.json").write_text(json.dumps(spec), encoding="utf-8")
    (job / "validation.json").write_text(json.dumps(validation or {
        "frames": sum(len(f) for f in blocks.values()), "blocks": len(blocks), "vd_alpha_and_anchor_roundtrip": True,
        "full_animation_set": mode == "full", "clipped_frames": [], "empty_frames": [], "deployed": False}), encoding="utf-8")
    (job / "status.json").write_text(json.dumps({"state": state, "name": "Synthetic Helm", "mode": mode}), encoding="utf-8")
    return job


def tree_hashes(folder: Path):
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob("*")) if p.is_file()}


@pytest.fixture
def preview_job(tmp_path):
    blocks = {(a, d): [sprite(100 + 4 * d, 90, 20 + d, 30), sprite(104, 100, 12, 40)]
              for a in (0, 4) for d in range(5)}
    blocks[(4, 2)][1] = None                       # an all-transparent frame
    blocks[(4, 4)][0] = sprite(180, 60, 30, 60)    # right of the anchor: positive crop, negative centre x
    return make_job(tmp_path, blocks)


def test_export_reads_back_and_centres_match_the_crops(preview_job, tmp_path):
    out = exporter.export(preview_job, tmp_path / "out")
    artifact = transfer.read(out)
    assert artifact.actions == [0, 4]
    assert artifact.manifest["animation"]["coverage"] == "preview"
    assert artifact.manifest["animation"]["sampling"] == {"first_scene_frame": 1, "scene_frame_step": 3}
    frame = artifact.frame(0, 0, 0)
    assert (frame.crop.left, frame.crop.top, frame.crop.right, frame.crop.bottom) == (100, 90, 120, 120)
    for f in artifact.frames:
        if not f.empty:
            assert f.centre == (128 - f.crop.left, 192 - f.crop.bottom)
            assert transfer.png_size(f.path) == (f.crop.width, f.crop.height)
    assert artifact.frame(4, 4, 0).centre == (128 - 180, 192 - 120)
    assert artifact.resolve(4, 7, 0).mirrored            # direction 7 reads stored direction 1


def test_all_transparent_frame_becomes_empty(preview_job, tmp_path):
    artifact = transfer.read(exporter.export(preview_job, tmp_path / "out"))
    empty = artifact.frame(4, 2, 1)
    assert empty.empty and empty.path is None and empty.crop is None
    entry = next(f for f in artifact.manifest["frames"] if (f["action"], f["direction"], f["index"]) == (4, 2, 1))
    assert entry == {"action": 4, "direction": 2, "index": 1, "empty": True}
    assert not (tmp_path / "out/frames/a04-d2-f1.png").exists()


def test_manifest_records_what_the_job_records_and_nothing_else(preview_job, tmp_path):
    manifest = transfer.read(exporter.export(preview_job, tmp_path / "out")).manifest
    assert manifest["identity"] == {"project_id": "spritemotion", "item_id": "Synthetic-Helm", "slot": "helm",
                                    "source_job": "0123456789ab"}
    assert manifest["reproducibility"] == {"model_fingerprint": "b" * 64, "renderer_fingerprint": "c" * 64,
                                           "input_hashes": {"asset": "a" * 64, "source/helm.glb": "d" * 64}}
    assert manifest["pixels"]["alpha"] == "binary" and manifest["pixels"]["quantization"] == {"policy": "none"}
    assert "playback" not in manifest["animation"]["actions"][0]
    assert manifest["provenance"]["source"] == {"redistribution": "unknown", "origin": "helm.glb", "notes": "input kind: model"}
    assert manifest["provenance"]["rendered"]["origin"] == "tools/uo-content job 0123456789ab"
    assert manifest["acceptance"]["manual_review"] == "none"
    assert "C:" not in json.dumps(manifest) and "elsewhere" not in json.dumps(manifest)


def test_job_folder_is_never_written(preview_job, tmp_path):
    before = tree_hashes(preview_job)
    exporter.export(preview_job, tmp_path / "out")
    assert tree_hashes(preview_job) == before


def test_out_reuse_is_refused_and_a_failed_export_leaves_nothing(preview_job, tmp_path):
    out = exporter.export(preview_job, tmp_path / "out")
    kept = tree_hashes(out)
    with pytest.raises(exporter.ExportError, match="not empty"):
        exporter.export(preview_job, out)
    assert tree_hashes(out) == kept
    with pytest.raises(exporter.ExportError, match="outside the job folder"):
        exporter.export(preview_job, preview_job / "transfer")
    assert not (preview_job / "transfer").exists()
    (preview_job / "status.json").write_text(json.dumps({"state": "building"}), encoding="utf-8")
    with pytest.raises(exporter.ExportError, match="not complete"):
        exporter.export(preview_job, tmp_path / "unfinished")
    assert not (tmp_path / "unfinished").exists()


def test_empty_existing_out_is_accepted(preview_job, tmp_path):
    (tmp_path / "empty").mkdir()
    assert transfer.read(exporter.export(preview_job, tmp_path / "empty")).actions == [0, 4]


def test_partial_alpha_makes_the_alpha_convention_straight(tmp_path):
    job = make_job(tmp_path, {(0, d): [sprite(100, 90, 20, 30, alpha=128)] for d in range(5)})
    assert transfer.read(exporter.export(job, tmp_path / "out")).manifest["pixels"]["alpha"] == "straight"


def test_full_coverage_needs_every_stored_direction(tmp_path):
    blocks = {(a, d): [{(128, 150): (10, 200, 10, 255)}] for a in range(35) for d in range(5)}
    job = make_job(tmp_path / "full", blocks, mode="full")
    artifact = transfer.read(exporter.export(job, tmp_path / "full-out"))
    assert artifact.manifest["animation"]["coverage"] == "full"
    assert len(artifact.actions) == 35 and len(artifact.frames) == 175
    short = make_job(tmp_path / "short", {(0, d): [{(128, 150): (1, 2, 3, 255)}] for d in range(4)}, mode="full")
    with pytest.raises(exporter.ExportError, match="missing stored directions"):
        exporter.export(short, tmp_path / "short-out")
    assert not (tmp_path / "short-out").exists()


def test_fit_snapshot_and_validation_report_are_exported_with_hashes(tmp_path):
    fit = {"parts": {"helm": {"scale": 1.1}}, "items": {}}
    validation = {"frames": 5, "blocks": 5, "vd_alpha_and_anchor_roundtrip": True, "clipped_frames": [[0, 1, 0]],
                  "empty_frames": [[0, 2, 0]]}
    job = make_job(tmp_path, {(0, d): [sprite(100, 90, 20, 30)] for d in range(5)}, extra={"fit_adjustments": fit},
                   validation=validation)
    out = exporter.export(job, tmp_path / "out")
    manifest = transfer.read(out).manifest
    fit_ref = manifest["reproducibility"]["fit"]
    assert json.loads((out / fit_ref["path"]).read_text(encoding="utf-8")) == fit
    assert manifest["reproducibility"]["fit_hash"] == fit_ref["sha256"]
    assert manifest["acceptance"]["known_failures"] == ["clipped frame action 0 direction 1 index 0",
                                                        "empty frame action 0 direction 2 index 0"]
    assert json.loads((out / "validation.json").read_text(encoding="utf-8")) == validation


def test_job_without_a_fit_snapshot_leaves_the_fit_fields_out(preview_job, tmp_path):
    reproducibility = transfer.read(exporter.export(preview_job, tmp_path / "out")).manifest["reproducibility"]
    assert "fit" not in reproducibility and "fit_hash" not in reproducibility


def test_wrong_canvas_size_is_refused(tmp_path):
    job = make_job(tmp_path, {(0, d): [{}] for d in range(5)})
    meta = job / "render/clothing/meta.json"
    data = json.loads(meta.read_text(encoding="utf-8"))
    data["canvas"] = [136, 120]
    meta.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(exporter.ExportError, match="canvas"):
        exporter.export(job, tmp_path / "out")


def test_cli_exit_codes(preview_job, tmp_path, capsys):
    assert exporter.main(["--job", str(preview_job), "--out", str(tmp_path / "out"), "--source-redistribution", "private",
                          "--source-license", "test-licence"]) == 0
    assert transfer.read(tmp_path / "out").manifest["provenance"]["source"]["license"] == "test-licence"
    assert exporter.main(["--job", str(preview_job), "--out", str(tmp_path / "out")]) == 1
    assert "Export failed" in capsys.readouterr().err

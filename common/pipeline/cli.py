"""SpriteMotion command line: spritemotion <command> ...

Typical flow:
  spritemotion extract --game ultima-online --character body-400 --source "<game folder>" --out workspace/ultima-online/body-400
  spritemotion status  workspace/ultima-online/body-400
  (review in the Sprite Pose Editor)
  spritemotion fit     workspace/ultima-online/body-400 --sequence action-022 --rig rig.json --mapping <mapping> --out fit.json
  (key the solution and render in Blender, see tools/blender)
  spritemotion compare workspace/ultima-online/body-400 --renders <renders> --out report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .. import __version__
from ..jsonio import read_json, write_json


def _dataset(path):
    from ..sprites.dataset import Dataset
    return Dataset.load(path)


def cmd_games(args) -> int:
    from .games import GAMES_DIR, load_game
    for game_file in sorted(GAMES_DIR.glob("*/game.json")):
        _, game = load_game(game_file.parent.name)
        print(f"{game['id']}: {game['title']}")
        for character in game["characters"]:
            print(f"  {character['id']}: {character.get('title', '')}")
    return 0


def cmd_extract(args) -> int:
    from .annotate import apply_bundle
    from .games import annotation_bundle, load_adapter
    adapter = load_adapter(args.game)
    sequences = args.sequences.split(",") if args.sequences else None
    manifest = adapter.extract(Path(args.source), args.character, Path(args.out), sequences)
    print(f"Wrote {manifest}")
    bundle = annotation_bundle(args.game, args.character)
    if bundle and not args.no_annotations and bundle.exists():
        report = apply_bundle(_dataset(manifest), bundle, args.overwrite_corrections).to_dict()
        print("Annotations:", json.dumps(report["totals"]))
        if report["totals"]["mismatched"]:
            print("WARNING: some bundled poses were drawn for different pixels and were NOT applied; "
                  "see annotations/apply-report.json.")
    return 0


def cmd_apply(args) -> int:
    from .annotate import apply_bundle
    report = apply_bundle(_dataset(args.dataset), Path(args.bundle), args.overwrite_corrections).to_dict()
    print(json.dumps(report["totals"]))
    return 1 if report["totals"]["mismatched"] and args.strict else 0


def cmd_promote(args) -> int:
    from .annotate import promote_corrections
    sequences = args.sequences.split(",") if args.sequences else None
    result = promote_corrections(_dataset(args.dataset), Path(args.bundle), sequences)
    print(json.dumps(result, indent=1))
    return 1 if any("refused" in v for v in result.values()) else 0


def cmd_status(args) -> int:
    from .status import dataset_status
    report = dataset_status(_dataset(args.dataset))
    if args.json:
        print(json.dumps(report, indent=1))
        return 0
    print(f"{report['dataset_id']}")
    print(f"{'sequence':<14}{'name':<22}{'frames':>7}{'annot':>7}{'corr':>6}{'approved':>9}{'mismatch':>9}  methods")
    for row in report["sequences"]:
        methods = ", ".join(f"{k}:{v}" for k, v in sorted(row["methods"].items()))
        print(f"{row['sequence']:<14}{row['name'][:21]:<22}{row['frames']:>7}{row['annotated']:>7}"
              f"{row['corrections']:>6}{row['approved']:>9}{row['fingerprint_mismatches']:>9}  {methods}")
    t = report["totals"]
    print(f"TOTAL: {t['frames']} frames, {t['annotated']} annotated, {t['approved']} approved, "
          f"{t['fingerprint_mismatches']} fingerprint mismatches")
    return 0


def cmd_validate(args) -> int:
    from .status import validate_repository
    errors = []
    if args.dataset:
        from ..poses.annotations import AnnotationSet, match_to_dataset
        from ..poses.skeleton import Skeleton
        dataset = _dataset(args.dataset)
        skeleton = Skeleton.load(dataset.skeleton_path)
        for layer in ("estimate", "correction"):
            for path in sorted(dataset.annotation_dir(layer).glob("*.json")):
                if path.name.endswith(".autosave.json"):
                    continue
                report = match_to_dataset(AnnotationSet.load(path), dataset, skeleton)
                if not report.ok:
                    errors.append(f"{path}: {report.summary()}")
    else:
        errors = validate_repository()
    for error in errors:
        print(error)
    print("OK" if not errors else f"{len(errors)} problem(s)")
    return 1 if errors else 0


def cmd_estimate_mirror(args) -> int:
    from ..estimation.mirror import MirrorEstimator
    from ..poses.annotations import AnnotationSet, load_layer
    from ..poses.skeleton import Skeleton
    dataset = _dataset(args.dataset)
    skeleton = Skeleton.load(dataset.skeleton_path)
    for sequence in (args.sequences.split(",") if args.sequences else [s["id"] for s in dataset.sequences]):
        existing = load_layer(dataset, "estimate", sequence) or AnnotationSet.new(
            dataset.dataset_id, sequence, skeleton.id, "estimate")
        before = len(existing)
        MirrorEstimator(args.swap_sides).estimate(dataset, skeleton, sequence, existing)
        existing.save(dataset.annotation_path("estimate", sequence))
        print(f"{sequence}: {len(existing) - before} mirrored estimates added")
    return 0


def cmd_estimate_rig(args) -> int:
    import numpy as np
    from ..estimation.rig_projection import add_rig_projection, project_rig_joints
    from ..fitting.camera import direction_rotations
    from ..fitting.mapping import RigMapping
    from ..fitting.rig import Rig
    from ..poses.annotations import AnnotationSet, load_layer
    from ..poses.skeleton import Skeleton
    from ..sprites.images import opaque_bounds
    from ..rendering.compare import load_render
    from .fitjob import dataset_camera, read_solution
    dataset = _dataset(args.dataset)
    skeleton = Skeleton.load(dataset.skeleton_path)
    rig, mapping = Rig.load(args.rig), RigMapping.load(args.mapping, args.swap_sides)
    camera = dataset_camera(dataset, read_json(args.camera) if args.camera else None)
    rotations = direction_rotations(dataset.directions, tuple(float(v) for v in args.model_forward.split(",")))
    poses = read_solution(Path(args.poses))
    existing = load_layer(dataset, "estimate", args.sequence) or AnnotationSet.new(
        dataset.dataset_id, args.sequence, skeleton.id, "estimate")
    added = 0
    for _, record in dataset.frames(args.sequence):
        d, f = record["direction"], record["frame"]
        partner = dataset.mirror_source(d)
        view = d if partner is None else partner       # a mirrored-only view is its partner, flipped
        if f not in poses or view not in rotations:
            continue
        points = np.asarray(project_rig_joints(rig, mapping, camera, rotations[view], poses[f],
                                               skeleton.joint_names), dtype=float)
        if partner is not None:
            points[:, 0] = 2 * dataset.mirror_axis_x - points[:, 0]
        model_bounds = None
        if args.renders:
            render = load_render(dataset, Path(args.renders), args.sequence, d, f)
            model_bounds = opaque_bounds(render) if render is not None else None
        if add_rig_projection(existing, dataset, args.sequence, d, f, np.asarray(points), skeleton.joint_names,
                              model_bounds, detail=f"projected from {Path(args.rig).name} pose {Path(args.poses).name}"):
            added += 1
    existing.save(dataset.annotation_path("estimate", args.sequence))
    print(f"{args.sequence}: {added} rig-projection estimates added (independent=false)")
    return 0


def cmd_fit(args) -> int:
    from ..fitting.fit import FitSettings
    from ..fitting.mapping import RigMapping
    from ..fitting.rig import Rig
    from .fitjob import fit_sequence, read_solution
    settings = FitSettings(**read_json(args.settings)) if args.settings else FitSettings()
    frames = [int(v) for v in args.frames.split(",")] if args.frames else None
    solution = fit_sequence(_dataset(args.dataset), args.sequence, Rig.load(args.rig),
                            RigMapping.load(args.mapping, args.swap_sides), Path(args.out), args.targets,
                            args.allow_dependent_targets, read_solution(Path(args.seed)) if args.seed else None,
                            frames, settings, tuple(float(v) for v in args.model_forward.split(",")),
                            read_json(args.camera) if args.camera else None)
    for frame in solution["frames"]:
        views = ", ".join(f"d{d}: {v['mean_px']:.2f}px" for d, v in frame["report"]["views"].items())
        print(f"frame {frame['frame']}: {views}")
    print(f"Wrote {args.out}")
    return 0


def cmd_compare(args) -> int:
    from ..rendering.compare import compare_dataset
    sequences = args.sequences.split(",") if args.sequences else None
    report = compare_dataset(_dataset(args.dataset), Path(args.renders), sequences)
    write_json(args.out, report)
    print(json.dumps(report["summary"], indent=1))
    if args.attach:
        from . import versions
        label = args.label or ",".join(sequences or []) or "all"
        summary = report["summary"]
        entry = versions.attach_metrics(args.attach, {f"{label}.mean_iou": summary.get("mean_iou"),
                                                      f"{label}.iou_by_direction": summary.get("by_direction")})
        print(f"Attached to {Path(args.attach).name} version {entry['version']}")
    return 0


def cmd_versions(args) -> int:
    from . import versions
    if args.action == "restore":
        if args.version is None:
            raise ValueError("restore needs --version N")
        entry = versions.restore(args.file, args.version)
        print(f"Restored version {args.version} as version {entry['version']} of {Path(args.file).name}")
        return 0
    history = versions.load_history(args.file)
    if args.json:
        print(json.dumps(history, indent=1))
        return 0
    if not history["versions"]:
        print(f"{Path(args.file).name}: no recorded versions")
        return 0
    for entry in history["versions"]:
        metrics = ", ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}"
                            for k, v in entry.get("metrics", {}).items() if not isinstance(v, dict))
        kept = "" if entry is history["versions"][-1] else ("" if entry.get("archived") else "  (not archived)")
        current = "  <- current" if entry is history["versions"][-1] else ""
        print(f"v{entry['version']:03d}  {entry['saved_at']}  {entry['made_by']}{current}{kept}")
        if entry.get("note"):
            print(f"      note: {entry['note']}")
        if metrics:
            print(f"      {metrics}")
    return 0


def cmd_sheet(args) -> int:
    from ..poses.annotations import effective_poses, load_layer
    from ..poses.skeleton import Skeleton
    from ..rendering.sheets import contact_sheet
    dataset = _dataset(args.dataset)
    skeleton = Skeleton.load(dataset.skeleton_path)
    merged = effective_poses(load_layer(dataset, "estimate", args.sequence),
                             load_layer(dataset, "correction", args.sequence))
    poses = {k: pose for k, (_, pose) in merged.items()} if not args.no_joints else None
    out = contact_sheet(dataset, args.sequence, Path(args.out), Path(args.renders) if args.renders else None,
                        poses, skeleton, args.scale)
    print(f"Wrote {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spritemotion", description=__doc__.split("\n")[0])
    parser.add_argument("--version", action="version", version=f"spritemotion {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("games", help="list game adapters and characters")
    p.set_defaults(func=cmd_games)

    p = sub.add_parser("extract", help="extract frames from a local game installation into a dataset")
    p.add_argument("--game", required=True)
    p.add_argument("--character", required=True)
    p.add_argument("--source", required=True, help="the user's local game folder")
    p.add_argument("--out", required=True)
    p.add_argument("--sequences", help="comma-separated sequence ids (default: all)")
    p.add_argument("--no-annotations", action="store_true", help="do not apply bundled annotations")
    p.add_argument("--overwrite-corrections", action="store_true")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("apply-annotations", help="apply a bundled annotation set to a dataset")
    p.add_argument("dataset")
    p.add_argument("--bundle", required=True)
    p.add_argument("--overwrite-corrections", action="store_true")
    p.add_argument("--strict", action="store_true", help="exit 1 if any pose was drawn for different pixels")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("promote", help="copy reviewed workspace corrections into a bundle")
    p.add_argument("dataset")
    p.add_argument("--bundle", required=True)
    p.add_argument("--sequences")
    p.set_defaults(func=cmd_promote)

    p = sub.add_parser("status", help="annotation coverage for a dataset")
    p.add_argument("dataset")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("validate", help="validate bundled repository data, or a dataset's annotations")
    p.add_argument("dataset", nargs="?")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("estimate-mirror", help="fill mirrored directions from their partners")
    p.add_argument("dataset")
    p.add_argument("--sequences")
    p.add_argument("--swap-sides", action="store_true")
    p.set_defaults(func=cmd_estimate_mirror)

    p = sub.add_parser("estimate-rig", help="add rig-projection estimates (not independent evidence)")
    p.add_argument("dataset")
    p.add_argument("--sequence", required=True)
    p.add_argument("--rig", required=True)
    p.add_argument("--mapping", required=True)
    p.add_argument("--poses", required=True, help="pose solution with the rig's pose per frame")
    p.add_argument("--renders", help="renders of the rig; registers projected joints to the sprite bounds")
    p.add_argument("--model-forward", default="0,-1")
    p.add_argument("--camera", help="camera JSON overriding the dataset's")
    p.add_argument("--swap-sides", action="store_true")
    p.set_defaults(func=cmd_estimate_rig)

    p = sub.add_parser("fit", help="fit rig poses to annotations and write a pose solution")
    p.add_argument("dataset")
    p.add_argument("--sequence", required=True)
    p.add_argument("--rig", required=True)
    p.add_argument("--mapping", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--targets", default="approved", choices=["approved", "independent", "all"])
    p.add_argument("--allow-dependent-targets", action="store_true",
                   help="also fit to rig projections (circular evidence; for experiments only)")
    p.add_argument("--seed", help="pose solution to start from (e.g. the rig's current action)")
    p.add_argument("--frames")
    p.add_argument("--settings", help="JSON with FitSettings fields")
    p.add_argument("--model-forward", default="0,-1", help="the rig's rest forward vector in world x,y")
    p.add_argument("--camera", help="camera JSON overriding the dataset's (e.g. a candidate variant)")
    p.add_argument("--swap-sides", action="store_true")
    p.set_defaults(func=cmd_fit)

    p = sub.add_parser("compare", help="silhouette comparison of renders against source frames")
    p.add_argument("dataset")
    p.add_argument("--renders", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--sequences")
    p.add_argument("--attach", help="record the summary on the current version of this scene file (e.g. model.blend)")
    p.add_argument("--label", help="metric name prefix when attaching (default: the sequence ids)")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("versions", help="list or restore saved versions of a scene file")
    p.add_argument("action", choices=["list", "restore"])
    p.add_argument("file", help="the scene file, e.g. workspace/ultima-online/model.blend")
    p.add_argument("--version", type=int)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_versions)

    p = sub.add_parser("sheet", help="contact sheet with joints, and renders/diffs when given")
    p.add_argument("dataset")
    p.add_argument("--sequence", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--renders")
    p.add_argument("--scale", type=int, default=2)
    p.add_argument("--no-joints", action="store_true")
    p.set_defaults(func=cmd_sheet)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

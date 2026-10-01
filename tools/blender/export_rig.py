"""Export an armature's rest pose as a spritemotion.rig file for the numpy fitter.

    blender -b model.blend --python tools/blender/export_rig.py -- --out rig.json [--armature NAME]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smblender as sb  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True)
    parser.add_argument("--armature")
    args = sb.parse_args(parser)
    obj = sb.armature(args.armature)
    rig = sb.rig_from_armature(obj)
    rig.save(args.out)
    print(f"Wrote {args.out}: {len(rig.bones)} bones from {obj.name}")


if __name__ == "__main__":
    main()

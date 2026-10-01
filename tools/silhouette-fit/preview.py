"""Local preview page for a silhouette-fit pass: every action, every view, sprite / fitted bones / render / diff.

    python tools/silhouette-fit/preview.py --pass-dir PASS --body "male|DS|RENDERS|SOLUTIONS|RIG" [--body "female|..."]
        --mapping MAPPING.json --camera CAMERA.json

Writes PASS/preview/index.html (overview), hands.html (hand-state review, exports hand-states.json for
blender_pass.py hands) and data.js, plus diff images. The page links to the sprite frames and renders
by relative path, so it only works next to them and must stay local: it shows art extracted from the game.
Diff colours: green = both, red = sprite only, blue = render only (render alpha > 127, as spritemotion compare).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from spritemotion.fitting.camera import direction_rotations  # noqa: E402
from spritemotion.fitting.mapping import RigMapping  # noqa: E402
from spritemotion.fitting.rig import Rig  # noqa: E402
from spritemotion.jsonio import read_json  # noqa: E402
from spritemotion.pipeline.fitjob import dataset_camera, read_solution  # noqa: E402
from spritemotion.poses.annotations import effective_poses, load_layer  # noqa: E402
from spritemotion.poses.skeleton import Skeleton  # noqa: E402
from spritemotion.rendering.compare import compare_frame  # noqa: E402
from spritemotion.sprites.dataset import Dataset  # noqa: E402

PAD = 6


def rel(path: Path, start: Path) -> str:
    return os.path.relpath(path, start).replace("\\", "/")


def body_data(label, ds_dir, renders, solutions, rig_path, mapping_path, camera_path, out_dir, shaded=None):
    dataset = Dataset.load(ds_dir)
    skeleton = Skeleton.load(dataset.skeleton_path)
    names = skeleton.joint_names
    rig = Rig.load(rig_path)
    mapping = RigMapping.load(mapping_path)
    camera = dataset_camera(dataset, read_json(camera_path))
    rotations = direction_rotations(dataset.directions, (0.0, -1.0))
    summary = read_json(Path(solutions) / "fit-summary.json")["sequences"]
    fit_stats = {s["sequence"]: s for s in summary}
    keyed = read_json(Path(solutions) / "keyed-report.json") if (Path(solutions) / "keyed-report.json").exists() else {}
    actions = []
    for seq in dataset.sequences:
        sid = seq["id"]
        sol_path = Path(solutions) / f"{sid}.json"
        if not sol_path.exists():
            continue
        solved = read_solution(sol_path)
        merged = effective_poses(load_layer(dataset, "estimate", sid), load_layer(dataset, "correction", sid))
        records = [r for r in dataset.data["sequences"] if r["id"] == sid][0]["frames"]
        x0 = min(r["bounds"][0] for r in records) - PAD
        y0 = min(r["bounds"][1] for r in records) - PAD
        x1 = max(r["bounds"][2] for r in records) + PAD
        y1 = max(r["bounds"][3] for r in records) + PAD
        views, ious = {}, []
        for record in records:
            d, f = record["direction"], record["frame"]
            partner = dataset.mirror_source(d)
            view = partner if partner is not None else d
            render_file = Path(renders) / sid / f"d{view}_f{f:02d}.png"
            sprite = np.array(Image.open(Path(ds_dir) / record["image"]).convert("RGBA"))
            entry = {"sprite": record["image"], "flip": partner is not None, "render": f"d{view}_f{f:02d}.png"}
            if render_file.exists():
                render = np.array(Image.open(render_file).convert("RGBA"))
                if partner is not None:
                    render = render[:, ::-1]
                iou = compare_frame(sprite, render)[0]
                ious.append(iou)
                entry["iou"] = round(float(iou), 4)
                sm, rm = sprite[:, :, 3] > 127, render[:, :, 3] > 127
                diff = np.zeros(sprite.shape, np.uint8)
                diff[sm & rm] = (60, 200, 110, 255)
                diff[sm & ~rm] = (235, 70, 70, 255)
                diff[~sm & rm] = (70, 130, 255, 255)
                dpath = out_dir / f"diff-{label}" / sid / f"d{d}_f{f:02d}.png"
                dpath.parent.mkdir(parents=True, exist_ok=True)
                Image.fromarray(diff).crop((x0, y0, x1, y1)).save(dpath)
                entry["diff"] = rel(dpath, out_dir)
            if f in solved:
                matrices = rig.pose_matrices(solved[f])
                joints = mapping.joint_positions(rig, matrices, names)
                p = camera.project(joints @ rotations[view].T)
                if partner is not None:
                    p[:, 0] = 2 * dataset.mirror_axis_x - p[:, 0]
                entry["fit"] = [[round(float(a) - x0, 2), round(float(b) - y0, 2)] for a, b in p]
            pose = merged.get((d, f))
            if pose:
                entry["target"] = [[round(pose[1]["joints"][n]["x"] - x0, 2), round(pose[1]["joints"][n]["y"] - y0, 2)]
                                   for n in names]
            views.setdefault(str(d), {})[str(f)] = entry
        stats = fit_stats.get(sid, {})
        actions.append({"id": sid, "name": seq["name"], "frames": seq["frame_count"], "crop": [x0, y0, x1, y1],
                        "canvas": [dataset.width, dataset.height],
                        "sprite_base": rel(Path(ds_dir), out_dir), "render_base": rel(Path(renders) / sid, out_dir),
                        "shaded_base": rel(Path(shaded) / sid, out_dir) if shaded else None,
                        "iou": round(float(np.mean(ious)), 4) if ious else None,
                        "joint_px": stats.get("mean_joint_px"), "outside_px": stats.get("mean_outside_px"),
                        "keyed_px": (keyed.get(sid) or {}).get("mean_px"), "views": views})
        print(f"{label} {sid}: IoU {actions[-1]['iou']}")
    edges = [[names.index(a), names.index(b)] for a, b, _ in skeleton.edges()]
    colors = [skeleton.color(n) for n in names]
    return {"label": label, "actions": actions, "edges": edges, "colors": colors, "names": names}


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CC4 Full Pass</title><style>
:root{--bg:#12141a;--panel:#1b1e27;--line:#2c3140;--text:#e6e8ee;--muted:#9aa1b2;--accent:#7fb2ff}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#f4f5f8;--panel:#fff;--line:#dde0e8;--text:#1b1e27;--muted:#5d6475;--accent:#2f6fdb}}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,Segoe UI,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--panel);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;flex-wrap:wrap;gap:10px 16px;align-items:center}
h1{font-size:16px;margin:0 8px 0 0}select,button,input{font:inherit}select,button{background:var(--bg);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:4px 8px}
button.on{border-color:var(--accent);color:var(--accent)}label{color:var(--muted);display:inline-flex;gap:4px;align-items:center}
main{padding:16px;max-width:1500px;margin:0 auto}.stats{color:var(--muted);margin:0 0 12px}.stats b{color:var(--text)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px}
.view{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px}.view h3{margin:0 0 6px;font-size:13px;color:var(--muted);display:flex;justify-content:space-between}
.panels{display:flex;gap:6px}.cell{position:relative;flex:1;background:repeating-conic-gradient(#0000 0 25%,#8881 0 50%) 0 0/12px 12px;border-radius:4px;overflow:hidden}
.cell img,.cell svg{position:absolute;inset:0;width:100%;height:100%;image-rendering:pixelated}.cell img.flip{transform:scaleX(-1)}
.cell.dark{background:#262b38}.cap{font-size:11px;color:var(--muted);text-align:center;margin-top:2px}
table{border-collapse:collapse;width:100%;margin-top:22px;font-variant-numeric:tabular-nums}th,td{padding:4px 8px;border-bottom:1px solid var(--line);text-align:right}th:first-child,td:first-child{text-align:left}
tr.pick{cursor:pointer}tr.pick:hover{background:var(--panel)}tr.sel{outline:1px solid var(--accent)}.note{color:var(--muted);font-size:12px;margin-top:10px}
</style></head><body><header><h1>CC4 Full Pass</h1><a href="hands.html" style="color:var(--accent)">Hand review →</a>
<label>Body <select id="body"></select></label><label>Action <select id="action"></select></label>
<button id="play">Play</button><label>Frame <input id="frame" type="range" min="0" value="0"></label><span id="fl"></span>
<label>FPS <select id="fps"><option>4</option><option selected>8</option><option>12</option></select></label>
<label><input type="checkbox" id="sh" checked>Shaded render</label><label><input type="checkbox" id="tg" checked>Targets</label><label><input type="checkbox" id="fb" checked>Fitted bones</label>
</header><main><p class="stats" id="stats"></p><div class="grid" id="grid"></div>
<table><thead><tr id="thead"></tr></thead><tbody id="tbl"></tbody></table>
<p class="note">Panels: sprite with 2D targets (dots) and fitted 3D bones projected (lines) · render of the CC4 model (shaded, or the flat silhouette used for scoring) · diff (green both, red sprite only, blue render only).
IoU is spritemotion's silhouette overlap (render alpha &gt; 127); the sprite's 1&nbsp;px outline and anti-aliased render edges keep it below 100% even for a perfect shape.
Mirrored views (N, NE, E) are the partner render flipped, as the game draws them.</p></main>
<script src="data.js"></script><script>
const DATA=window.DATA;const DIRS=["N","NE","E","SE","S","SW","W","NW"];const SCALE=3;
let b=0,a=0,f=0,timer=null;const $=id=>document.getElementById(id);
DATA.bodies.forEach((x,i)=>$("body").add(new Option(x.label,i)));
function fill(){const acts=DATA.bodies[b].actions;$("action").innerHTML="";acts.forEach((x,i)=>$("action").add(new Option(`${x.id} ${x.name}${x.iou!=null?" · "+(x.iou*100).toFixed(1)+"%":""}`,i)));$("action").value=a;}
function pct(v){return v==null?"–":(v*100).toFixed(1)+"%"}function px(v){return v==null?"–":v.toFixed(2)}
function svg(e,body,w,h){let s=`<svg viewBox="0 0 ${w} ${h}">`;
 if($("fb").checked&&e.fit){for(const[i,j]of body.edges){const p=e.fit[i],q=e.fit[j];s+=`<line x1="${p[0]}" y1="${p[1]}" x2="${q[0]}" y2="${q[1]}" stroke="${body.colors[j]}" stroke-width="0.6" stroke-linecap="round"/>`}}
 if($("tg").checked&&e.target){e.target.forEach((p,k)=>{s+=`<circle cx="${p[0]}" cy="${p[1]}" r="0.9" fill="none" stroke="${body.colors[k]}" stroke-width="0.35"/>`})}return s+"</svg>"}
function draw(){const body=DATA.bodies[b],act=body.actions[a];const[x0,y0,x1,y1]=act.crop,w=x1-x0,h=y1-y0,[CW,CH]=act.canvas||[256,256];
 $("frame").max=act.frames-1;$("fl").textContent=`${f+1}/${act.frames}`;
 $("stats").innerHTML=`<b>${body.label}</b> · ${act.id} ${act.name} · IoU <b>${pct(act.iou)}</b> · fit joint error <b>${px(act.joint_px)}px</b> · keyed reprojection <b>${px(act.keyed_px)}px</b> · bone samples outside sprite <b>${px(act.outside_px)}px</b>`;
 let html="";for(let d=0;d<8;d++){const e=(act.views[d]||{})[f];if(!e)continue;
  const pos=`left:${-x0*100/w}%;top:${-y0*100/h}%;width:${CW*100/w}%;height:${CH*100/h}%`;
  const spr=`<img style="${pos}" src="${act.sprite_base}/${e.sprite}">`;
  const ren=`<img class="${e.flip?"flip":""}" style="${pos}" src="${($("sh").checked&&act.shaded_base)?act.shaded_base:act.render_base}/${e.render}">`;
  const box=`style="aspect-ratio:${w}/${h}"`;
  html+=`<div class="view"><h3><span>${DIRS[d]} (d${d})${e.flip?" · mirrored":""}</span><span>${pct(e.iou)}</span></h3><div class="panels">
  <div><div class="cell" ${box}>${spr}${svg(e,body,w,h)}</div><div class="cap">sprite + bones</div></div>
  <div><div class="cell dark" ${box}>${ren}</div><div class="cap">render</div></div>
  <div><div class="cell" ${box}>${e.diff?`<img src="${e.diff}">`:""}</div><div class="cap">diff</div></div></div></div>`}
 $("grid").innerHTML=html;document.querySelectorAll(".panels>div").forEach(x=>x.style.flex="1");
 document.querySelectorAll("#tbl tr").forEach((r,i)=>r.classList.toggle("sel",i===a));}
function table(){const bs=DATA.bodies,m=bs[0];let s="";
 $("thead").innerHTML="<th>Action</th><th>Frames</th>"+bs.map(x=>{const n=x.label.split(" (")[0];return `<th>${n} IoU</th><th>${n} joints px</th>`}).join("");
 m.actions.forEach((x,i)=>{s+=`<tr class="pick" data-i="${i}"><td>${x.id} ${x.name}</td><td>${x.frames}</td>`+bs.map(bd=>{const y=bd.actions[i];return `<td>${y?pct(y.iou):"–"}</td><td>${y?px(y.joint_px):"–"}</td>`}).join("")+"</tr>"});
 const mean=(bd)=>{const v=bd.actions.map(x=>x.iou).filter(x=>x!=null);return v.reduce((p,q)=>p+q,0)/v.length};
 s+=`<tr><td><b>Mean</b></td><td></td>`+bs.map(bd=>`<td><b>${pct(mean(bd))}</b></td><td></td>`).join("")+"</tr>";
 $("tbl").innerHTML=s;document.querySelectorAll("#tbl tr.pick").forEach(r=>r.onclick=()=>{a=+r.dataset.i;f=0;fill();draw();scrollTo({top:0,behavior:"smooth"})});}
$("body").onchange=e=>{b=+e.target.value;fill();draw()};$("action").onchange=e=>{a=+e.target.value;f=0;draw()};
$("frame").oninput=e=>{f=+e.target.value;draw()};$("tg").onchange=draw;$("sh").onchange=draw;$("fb").onchange=draw;
function stop(){clearInterval(timer);timer=null;$("play").textContent="Play";$("play").classList.remove("on")}
$("play").onclick=()=>{if(timer)return stop();$("play").textContent="Pause";$("play").classList.add("on");timer=setInterval(()=>{f=(f+1)%DATA.bodies[b].actions[a].frames;$("frame").value=f;draw()},1000/+$("fps").value)};
$("fps").onchange=()=>{if(timer){stop();$("play").click()}};
document.addEventListener("keydown",e=>{if(e.key==="ArrowRight"){f=(f+1)%DATA.bodies[b].actions[a].frames;draw()}if(e.key==="ArrowLeft"){const n=DATA.bodies[b].actions[a].frames;f=(f+n-1)%n;draw()}if(e.key===" "){e.preventDefault();$("play").click()}});
fill();table();draw();
</script></body></html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--pass-dir", required=True)
    parser.add_argument("--body", action="append", required=True, help="label|dataset|renders|solutions|rig[|shaded renders]")
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--camera", required=True)
    args = parser.parse_args()
    out = Path(args.pass_dir) / "preview"
    out.mkdir(parents=True, exist_ok=True)
    bodies = []
    for spec in args.body:
        label, ds, renders, solutions, rig, *shaded = spec.split("|")
        bodies.append(body_data(label, Path(ds), Path(renders), Path(solutions), rig, args.mapping, args.camera, out,
                                Path(shaded[0]) if shaded else None))
    for body in bodies:
        for act in body["actions"]:
            act["views"] = {d: {int(f): e for f, e in fr.items()} for d, fr in act["views"].items()}
    (out / "data.js").write_text("window.DATA=" + json.dumps({"bodies": bodies}, separators=(",", ":")) + ";",
                                 encoding="utf-8")
    (out / "index.html").write_text(PAGE, encoding="utf-8")
    (out / "hands.html").write_text((Path(__file__).parent / "hands.html").read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Wrote {out / 'index.html'}")


if __name__ == "__main__":
    main()

bl_info = {
    "name": "SpriteMotion Sheet Reference",
    "author": "Moshu",
    "version": (0, 6, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > SpriteMotion",
    "description": "Shows frames from UOFiddler packed sprite sheets (anim_<body>_<action>.png + .json) on a "
                   "camera-aligned plane, with viewport controls next to the model for frame, action, "
                   "direction, opacity, outline/edge views, model display and a see-through bone overlay; "
                   "renders a rigged model into UO mobile frames through the SpriteMotion UO camera.",
    "category": "3D View",
}

# Sheet JSON is UOFiddler's PackedOutput: meta{image,size{w,h}}, frames[{direction,index,frame{x,y,w,h},center{x,y}}].
# Anchor: ClassicUO draws a mobile with the frame's top-left at (pos - center.x, pos - (h + center.y)),
# so the sprite origin (tile centre on the ground) is pixel (center.x, h + center.y) from the frame top-left.
# A plane parented to the camera gets its size from the camera's pixels per unit: camera_px() reads the row norms
# of the SpriteMotion camera matrix that "Set up UO camera" stored on it (ground grid: 31.113 px per unit
# horizontally, 44 px per camera-vertical unit). The frame renderer below uses the same camera, so the overlay and
# the rendered frames cannot disagree.
#
# Frame renderer: SpriteMotion's affine orthographic camera (canvas = anchor + M @ world; world units = UO tiles,
# x east, y north, z up), converted to a Blender camera exactly as common/rendering/ortho.py
# blender_camera_params(). Only the 5 stored rows are rendered (the client mirrors N, NE, E); the model is turned
# about world z so it faces each stored row's facing.
#
# Directions: anim.mul stores 5 of the 8 facings; ClassicUO AnimationsLoader.GetAnimDirection maps
#   UO dir 3 (SE, screen down)   -> stored 0        UO dir 7 (NW, screen up)  -> stored 4
#   UO dir 4 (S, down-left)      -> stored 1        UO dir 2 (E, down-right)  -> stored 1 mirrored
#   UO dir 5 (SW, left)          -> stored 2        UO dir 1 (NE, right)      -> stored 2 mirrored
#   UO dir 6 (W, up-left)        -> stored 3        UO dir 0 (N, up-right)    -> stored 3 mirrored
# (UOFiddler's row names SW/S/SE/E/NE for stored 0..4 are its own labels, not the client's mapping.)

import bpy, blf, gpu, json, os, math, hashlib
import numpy as np
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix
from bpy_extras import view3d_utils

# Legacy fallback only (a stage camera made before 0.6 carries uo_px_per_unit and no uo_px_x/uo_px_y). Cameras set up
# by "Set up UO camera" store the row norms of their camera matrix instead, so overlay and renderer share one source.
PX_PER_UNIT_X = 44.0 / math.sqrt(2)   # 31.113
PX_PER_UNIT_Y = 44.0                  # camera-local Y (screen up) after the sqrt2 stretch
_sheet_cache = {}
_index_cache = {}
_action_enum_cache = {}
_data_errors = {}
_hud = {}   # "layout": the last hud_layout result (set by the HUD gizmo group), "skel_status": text
DOCKS = [("TOP_LEFT", "Top left", "Dock the controls in the top-left corner of the viewport"),
         ("TOP_RIGHT", "Top right", "Dock the controls in the top-right corner of the viewport"),
         ("BOTTOM_LEFT", "Bottom left", "Dock the controls in the bottom-left corner of the viewport"),
         ("BOTTOM_RIGHT", "Bottom right", "Dock the controls in the bottom-right corner of the viewport")]
HUD_ANCHORS = [("DOCK", "Docked", "Controls stay in a corner of the viewport, whatever the camera does"),
               ("PLANE", "Follow plane", "Controls sit next to the sheet plane, clamped so they never leave the viewport")]

# uo dir -> (name, stored, mirror, screen (x,y) unit vector, blender facing (x,y))
UO_DIRS = [
    ("N",  3, True,  ( 0.707,  0.707), ( 0,  1)),
    ("NE", 2, True,  ( 1.0,    0.0),   ( 1,  1)),
    ("E",  1, True,  ( 0.707, -0.707), ( 1,  0)),
    ("SE", 0, False, ( 0.0,   -1.0),   ( 1, -1)),
    ("S",  1, False, (-0.707, -0.707), ( 0, -1)),
    ("SW", 2, False, (-1.0,    0.0),   (-1, -1)),
    ("W",  3, False, (-0.707,  0.707), (-1,  0)),
    ("NW", 4, False, ( 0.0,    1.0),   (-1,  1)),
]
VIEW_MODES = [("COLOR", "Color", "The frame as packed"),
              ("OUTLINE", "Outline", "1 px silhouette outline only"),
              ("EDGES", "Edges", "Sobel edge detection inside the sprite (Canny-like) plus the silhouette outline"),
              ("SILHOUETTE", "Silhouette", "Flat fill of the sprite's alpha")]
MODEL_MODES = [("SOLID", "Solid", ""), ("WIRE", "Wire", ""), ("HIDDEN", "Hidden", "")]


# ---------------- data ----------------
def sheet_path(props, ext):
    return os.path.join(bpy.path.abspath(props.sheet_dir), f"anim_{props.body}_{props.action}{ext}")


def _cached_json(path, cache, validator=None):
    try:
        stat = os.stat(path)
        stamp = (stat.st_mtime_ns, stat.st_size)
        hit = cache.get(path)
        if hit and hit[0] == stamp:
            return hit[1]
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        if validator:
            validator(data)
        cache[path] = (stamp, data)
        _data_errors.pop(path, None)
        return data
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        cache.pop(path, None)
        _data_errors[path] = str(exc)
        return None


def _validate_sheet(data):
    size = data["meta"]["size"]
    W, H = size["w"], size["h"]
    if not all(type(v) is int and v > 0 for v in (W, H)):
        raise ValueError("Sheet dimensions must be positive integer pixels")
    if not isinstance(data["frames"], list):
        raise ValueError("Sheet frames must be a list")
    seen = set()
    for fr in data["frames"]:
        x, y, w, h = (fr["frame"][k] for k in ("x", "y", "w", "h"))
        cx, cy = fr["center"]["x"], fr["center"]["y"]
        direction, index = fr["direction"], fr["index"]
        if not all(type(v) is int for v in (x, y, w, h, cx, cy, direction, index)):
            raise ValueError("Frame rectangles, anchors and IDs must be integers")
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x+w > W or y+h > H:
            raise ValueError("Frame rectangle lies outside the sheet")
        if not 0 <= direction <= 4 or index < 0 or (direction, index) in seen:
            raise ValueError("Invalid or duplicate frame ID")
        seen.add((direction, index))


def _validate_index(data):
    entries = data["animations"]
    if not isinstance(entries, list):
        raise ValueError("Animation index must contain a list")
    seen = set()
    for entry in entries:
        aid = entry["action"]
        if type(aid) is not int or aid < 0 or aid in seen:
            raise ValueError("Invalid or duplicate action ID")
        if entry.get("name") is not None and not isinstance(entry["name"], str):
            raise ValueError("Action names must be strings")
        seen.add(aid)


def _validate_skeleton(data):
    if not isinstance(data["frames"], list) or not isinstance(data["bones"], list):
        raise ValueError("Skeleton frames and bones must be lists")
    for pair in data["bones"]:
        if not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(n, str) for n in pair):
            raise ValueError("Each skeleton bone must name two joints")
    for fr in data["frames"]:
        if type(fr["direction"]) is not int or not 0 <= fr["direction"] <= 4 or type(fr["index"]) is not int or fr["index"] < 0:
            raise ValueError("Invalid skeleton frame ID")
        if not isinstance(fr["joints"], dict):
            raise ValueError("Skeleton joints must be a mapping")
        for name, xy in fr["joints"].items():
            if not isinstance(xy, list) or len(xy) != 2 or not all(type(v) in (int, float) and math.isfinite(v) for v in xy):
                raise ValueError("Joint coordinates must be two finite numbers")


def load_sheet(props):
    return _cached_json(sheet_path(props, ".json"), _sheet_cache, _validate_sheet)


_skel_cache = {}


def load_skeleton(props):
    """anim_<body>_<action>_skeleton.json next to the sheet, or None."""
    return _cached_json(sheet_path(props, "_skeleton.json"), _skel_cache, _validate_skeleton)


def skeleton_frame(props):
    sk = load_skeleton(props)
    if sk is None:
        return None, None
    data = load_sheet(props)
    n = len(frames_for(data, props.direction)) if data else 0
    if not n:
        return None, None
    idx = props.frame % n
    for f in sk["frames"]:
        if f["direction"] == props.direction and f["index"] == idx:
            return sk, f
    return sk, None


# sprite joint -> (rig bone, use 'tail'?)  for the Mixamo-named Meshy rig; sides resolved per facing
RIG_JOINTS = {"head_top": ("mixamorig:HeadTop_End", False), "head": ("mixamorig:Head", False),
              "neck": ("mixamorig:Neck", False), "pelvis": ("mixamorig:Hips", False),
              "shoulder": ("mixamorig:{S}Arm", False), "elbow": ("mixamorig:{S}ForeArm", False),
              "hand": ("mixamorig:{S}Hand", False), "hip": ("mixamorig:{S}UpLeg", False),
              "knee": ("mixamorig:{S}Leg", False), "ankle": ("mixamorig:{S}Foot", False),
              "toe": ("mixamorig:{S}ToeBase", False)}
# which rig side is on screen-left, per UO dir: front views show the rig's right on screen-left
# Skeleton coordinates remain in the UNMIRRORED stored frame. Mirrored E/N
# therefore swap anatomical sides relative to their displayed screen sides.
SCREEN_LEFT_IS = {3: "Right", 4: "Right", 2: "Left", 1: "Right", 5: "Left", 0: "Right", 7: "Left", 6: "Left"}

# Generated Rigify deform chains use different names from the original Mixamo rig.
RIGIFY_JOINTS = {"head_top": ("DEF-spine.006", True), "head": ("DEF-spine.006", False),
                "neck": ("DEF-spine.004", False), "pelvis": ("DEF-spine", False),
                "shoulder": ("DEF-upper_arm.{S}", False), "elbow": ("DEF-forearm.{S}", False),
                "hand": ("DEF-hand.{S}", False), "hip": ("DEF-thigh.{S}", False),
                "knee": ("DEF-shin.{S}", False), "ankle": ("DEF-foot.{S}", False),
                "toe": ("DEF-toe.{S}", False)}


def rig_joint_world(arm, name, uo_dir):
    base, side = (name.rsplit("_", 1) + [None])[:2] if name.endswith(("_sl", "_sr")) else (name, None)
    is_rigify = arm.get("uo_rig_type") == "Rigify"
    entry = (RIGIFY_JOINTS if is_rigify else RIG_JOINTS).get(base)
    if entry is None:
        return None
    bone, use_tail = entry
    if side:
        left = SCREEN_LEFT_IS[uo_dir]
        S = left if side == "sl" else ("Left" if left == "Right" else "Right")
        if is_rigify:
            S = "L" if S == "Left" else "R"
        bone = bone.replace("{S}", S)
    pb = arm.pose.bones.get(bone)
    if pb is None:
        return None
    return arm.matrix_world @ (pb.tail if use_tail else pb.head)


def load_index(props):
    return _cached_json(os.path.join(bpy.path.abspath(props.sheet_dir), f"anim_{props.body}_index.json"), _index_cache, _validate_index)


def frames_for(data, direction):
    return [f for f in data["frames"] if f["direction"] == direction]


def action_list(props):
    idx = load_index(props)
    if idx:
        return [(a["action"], a.get("name") or f"action {a['action']}") for a in idx["animations"]]
    return []


def action_name(props):
    for a, n in action_list(props):
        if a == props.action:
            return n
    return ""


def get_image(path):
    for im in bpy.data.images:
        if bpy.path.abspath(im.filepath) == path:
            return im
    return bpy.data.images.load(path)


# ---------------- derived (outline / edges / silhouette) sheets ----------------
def _sheet_pixels(img):
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(h, w, 4)          # row 0 = bottom


def _dilate(mask):
    out = mask.copy()
    out[1:, :] |= mask[:-1, :]; out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]; out[:, :-1] |= mask[:, 1:]
    return out


def _sobel(lum):
    p = np.pad(lum, 1, mode="edge")
    gx = (p[1:-1, 2:] - p[1:-1, :-2]) * 2 + (p[2:, 2:] - p[2:, :-2]) + (p[:-2, 2:] - p[:-2, :-2])
    gy = (p[2:, 1:-1] - p[:-2, 1:-1]) * 2 + (p[2:, 2:] - p[:-2, 2:]) + (p[2:, :-2] - p[:-2, :-2])
    return np.sqrt(gx * gx + gy * gy) / 8.0


def derived_image(props, base_img, force=False):
    """Image for the current view mode, computed with numpy and cached in <sheets>/derived/."""
    mode = props.view_mode
    if mode == "COLOR":
        return base_img
    col = tuple(props.outline_color)
    parameters = json.dumps((4, mode, col, props.edge_threshold))
    key = mode.lower() + "_" + hashlib.sha256(parameters.encode()).hexdigest()[:16]
    src = bpy.path.abspath(base_img.filepath)
    out_dir = os.path.join(os.path.dirname(src), "derived")
    out_path = os.path.join(out_dir, os.path.splitext(os.path.basename(src))[0] + f"_{key}.png")
    if not force and os.path.exists(out_path) and os.path.getmtime(out_path) >= os.path.getmtime(src):
        return get_image(out_path)
    os.makedirs(out_dir, exist_ok=True)
    px = _sheet_pixels(base_img)
    alpha = px[..., 3] > 0.01
    out = np.zeros_like(px)
    if mode == "SILHOUETTE":
        sel = alpha
    elif mode == "OUTLINE":
        sel = _dilate(alpha) & ~alpha
    else:  # EDGES
        lum = 0.299 * px[..., 0] + 0.587 * px[..., 1] + 0.114 * px[..., 2]
        lum = np.where(alpha, lum, 0.0)
        sel = ((_sobel(lum) > props.edge_threshold) & alpha) | (_dilate(alpha) & ~alpha)
    out[sel, 0] = col[0]; out[sel, 1] = col[1]; out[sel, 2] = col[2]; out[sel, 3] = 1.0
    w, h = base_img.size
    img = bpy.data.images.new(os.path.basename(out_path), w, h, alpha=True)
    img.pixels.foreach_set(out.reshape(-1))
    img.filepath_raw = out_path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    result = get_image(out_path)
    result.reload()
    return result


# ---------------- material ----------------
def ensure_material(obj, img):
    mat = obj.data.materials[0] if obj.data.materials else None
    if mat is None or not mat.get("uo_sheet_mat"):
        mat = bpy.data.materials.new(obj.name + "_mat")
        mat["uo_sheet_mat"] = True
        if not mat.use_nodes:           # always on (and deprecated) in Blender 5
            mat.use_nodes = True
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    nt = mat.node_tree
    tex = next((n for n in nt.nodes if n.type == "TEX_IMAGE"), None)
    if tex is None:
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        emit = nt.nodes.new("ShaderNodeEmission")
        mix = nt.nodes.new("ShaderNodeMixShader")
        transp = nt.nodes.new("ShaderNodeBsdfTransparent")
        alpha_mul = nt.nodes.new("ShaderNodeMath"); alpha_mul.operation = "MULTIPLY"; alpha_mul.name = "uo_alpha"
        tex = nt.nodes.new("ShaderNodeTexImage"); tex.interpolation = "Closest"; tex.extension = "CLIP"
        uv = nt.nodes.new("ShaderNodeUVMap")
        nt.links.new(uv.outputs["UV"], tex.inputs["Vector"])
        nt.links.new(tex.outputs["Color"], emit.inputs["Color"])
        nt.links.new(tex.outputs["Alpha"], alpha_mul.inputs[0])
        nt.links.new(alpha_mul.outputs[0], mix.inputs["Fac"])
        nt.links.new(transp.outputs[0], mix.inputs[1])
        nt.links.new(emit.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
        if hasattr(mat, "blend_method"):          # legacy EEVEE; Blender 5 uses surface_render_method only
            mat.blend_method = "BLEND"
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "BLENDED"
        if hasattr(mat, "shadow_method"):
            mat.shadow_method = "NONE"
        if hasattr(mat, "show_transparent_back"):
            mat.show_transparent_back = False
    tex.image = img
    return mat


def _set_uvs(obj, uvs):
    u0, v0, u1, v1 = uvs
    uv_layer = obj.data.uv_layers[0]
    for i, (u, v) in enumerate(((u0, v0), (u1, v0), (u1, v1), (u0, v1))):
        uv_layer.data[i].uv = (u, v)
    obj.data.update()


def _update_side_panel(obj, props, cam, img, uvs, w, h, px_x, px_y, la, dx, dy):
    """Opaque copy of the current frame beside the model, viewport only (hide_render)."""
    name = obj.name + "_side"
    side = bpy.data.objects.get(name)
    if not props.side_panel:
        if side is not None:
            bpy.data.objects.remove(side, do_unlink=True)
        return
    if side is None:
        mesh = obj.data.copy(); mesh.name = name
        mesh.materials.clear()
        side = bpy.data.objects.new(name, mesh)
        for c in obj.users_collection:
            c.objects.link(side)
        side.hide_select = True
        side["uo_sheet_side"] = True
    _set_uvs(side, uvs)
    mat = ensure_material(side, img)
    mat.node_tree.nodes["uo_alpha"].inputs[1].default_value = 1.0
    mat.diffuse_color = (1, 1, 1, 1)
    side.color = (1, 1, 1, 1)
    side.parent = cam
    side.matrix_parent_inverse = Matrix.Identity(4)
    side.scale = (w / px_x, h / px_y, 1)
    # the side panel has its own anchor, side_offset_px right of the real one; frames then sit on it exactly as in game
    side.location = (la.x + props.side_offset_px / px_x + dx, la.y + dy, la.z + props.depth + 0.5)
    side.rotation_euler = (0, 0, 0)
    side.hide_render = True


def _update_decal(obj, props, cam, img, uvs):
    """Frame projected along the camera view direction onto z=0, as a textured quad (affine, so plain UVs are exact)."""
    name = obj.name + "_decal"
    dec = bpy.data.objects.get(name)
    if not props.show_decal:
        if dec is not None:
            bpy.data.objects.remove(dec, do_unlink=True)
        return
    if dec is None:
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
        mesh.uv_layers.new()
        dec = bpy.data.objects.new(name, mesh)
        for c in obj.users_collection:
            c.objects.link(dec)
        dec.hide_select = True
        dec.hide_render = True
        dec["uo_sheet_decal"] = True
    fwd = (cam.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()     # view direction
    # obj.matrix_world is stale until the depsgraph runs (apply_sheet just moved the plane), so
    # rebuild it from the values that were just set: parent = cam, identity parent inverse, no rotation
    plane_mw = cam.matrix_world @ Matrix.Translation(obj.location) @ Matrix.Diagonal((obj.scale[0], obj.scale[1], obj.scale[2], 1.0))
    corners = []
    for co in ((-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)):
        w = plane_mw @ Vector(co)
        t = -w.z / fwd.z
        corners.append(w + fwd * t + Vector((0, 0, 0.002)))
    for v, c in zip(dec.data.vertices, corners):
        v.co = c
    _set_uvs(dec, uvs)
    mat = ensure_material(dec, img)
    mat.node_tree.nodes["uo_alpha"].inputs[1].default_value = props.decal_alpha
    mat.diffuse_color = (1, 1, 1, props.decal_alpha)
    dec.color = (1, 1, 1, props.decal_alpha)
    dec.parent = None
    dec.matrix_world = Matrix.Identity(4)


def _model_objects(props):
    model = props.model
    if model is None:
        return []
    return [model] + list(model.children_recursive)


def _model_armature(props):
    for o in _model_objects(props):
        if o.type == "ARMATURE":
            return o
    return None


def _model_yaw(props):
    # the glTF/Mixamo rig faces -Y (UO south) at zero rotation
    return facing_yaw(UO_DIRS[props.uo_dir][4], (0, -1), props.model_yaw_offset)


def _sync_model_action(props):
    arm = _model_armature(props)
    name = action_name(props)
    if arm is None or not name:
        return
    dname = UO_DIRS[props.uo_dir][0]
    # Human-readable index names are not unique: body 400 actions 4/5 are
    # both Idle_01 and actions 7/8 are both CombatIdle1H_01.
    qualified = f"UO_{props.body}_{props.action:03d}_{name}"
    for cand in (f"{qualified}_{dname}", qualified,
                 f"UO_{name}_{dname}", f"UO_{name}", name, f"{name}_{dname}"):
        act = bpy.data.actions.get(cand)
        if act is not None:
            break
    else:
        return
    if arm.animation_data is None:
        arm.animation_data_create()
    ad = arm.animation_data
    if ad.action is not act:
        ad.action = act
    # Blender 4.4+ slotted actions: an action only animates through a slot.
    if getattr(ad, "action_slot", False) is None and getattr(act, "slots", None):
        ad.action_slot = act.slots[0]
    # Stable object-property drivers avoid dynamic Action-ID dependency paths.
    for prop in ("uo_run_fist", "uo_run_shape"):
        if prop in arm:
            value = float(act.get(prop, 0.0))
            if arm[prop] != value:
                arm[prop] = value


def _apply_model_display(props):
    for o in _model_objects(props):
        if o.type != "MESH":
            continue
        o.hide_set(props.model_display == "HIDDEN")
        o.display_type = "WIRE" if props.model_display == "WIRE" else "TEXTURED"


def apply_sheet(obj, scene=None, force_refresh=False):
    """Size, place and texture the plane for the current frame."""
    props = obj.spritemotion_sheet
    if not props.enabled:
        return
    data = load_sheet(props)
    if data is None:
        path = sheet_path(props, ".json")
        props.status = "Sheet unavailable: " + _data_errors.get(path, path)
        return
    frames = frames_for(data, props.direction)
    if not frames:
        props.status = "direction has no frames"
        return
    n = len(frames)
    fr = frames[props.frame % n]
    W, H = data["meta"]["size"]["w"], data["meta"]["size"]["h"]
    x, y, w, h = fr["frame"]["x"], fr["frame"]["y"], fr["frame"]["w"], fr["frame"]["h"]
    cx, cy = fr["center"]["x"], fr["center"]["y"]
    if props.mirror:                       # ClassicUO flips the frame and mirrors the anchor for mirrored dirs
        cx = w - cx

    try:
        base = get_image(sheet_path(props, ".png"))
        if tuple(base.size) != (W, H):
            props.status = f"Sheet image size {tuple(base.size)} does not match JSON {(W, H)}"
            return
        img = derived_image(props, base, force=force_refresh)
    except (OSError, RuntimeError, ValueError) as exc:
        props.status = "Sheet image unavailable: " + str(exc)
        return
    mat = ensure_material(obj, img)
    mat.node_tree.nodes["uo_alpha"].inputs[1].default_value = props.alpha
    mat.diffuse_color = (1, 1, 1, props.alpha)   # Solid-mode viewport alpha
    obj.color = (1, 1, 1, props.alpha)
    # the frame rectangle lives in the UVs, so Solid, Material and Render views all show one frame
    u0, u1 = x / W, (x + w) / W
    v0, v1 = 1 - (y + h) / H, 1 - y / H
    if props.mirror:
        u0, u1 = u1, u0
    _set_uvs(obj, (u0, v0, u1, v1))

    cam = (scene or bpy.context.scene).camera
    anchor = props.anchor
    if cam is None:
        props.status = "scene has no camera"
        return
    px_x, px_y = camera_px(cam)
    obj.parent = cam
    obj.matrix_parent_inverse = Matrix.Identity(4)
    world_anchor = anchor.matrix_world.translation if anchor else Vector((0, 0, 0))
    la = cam.matrix_world.inverted() @ world_anchor        # camera-local anchor
    # plane is 1x1 with origin at its centre; anchor pixel is (cx, h+cy) from the frame's top-left
    obj.scale = (w / px_x, h / px_y, 1)
    dx = (w / 2 - cx + props.nudge_px[0]) / px_x
    dy = (h / 2 + cy + props.nudge_px[1]) / px_y             # +cy is usually negative: anchor sits above the bottom
    depth = la.z + (props.depth if props.in_front else -props.depth)   # camera looks down -Z: bigger z = nearer
    obj.location = (la.x + dx, la.y + dy, depth)
    obj.rotation_euler = (0, 0, 0)
    obj.hide_set(not props.show_overlay)
    _update_side_panel(obj, props, cam, img if props.side_uses_view_mode else base, (u0, v0, u1, v1), w, h, px_x, px_y, la, dx, dy)
    _update_decal(obj, props, cam, img, (u0, v0, u1, v1))
    dname = UO_DIRS[props.uo_dir][0]
    props.status = f"{action_name(props)} ({props.action})  {dname} stored {props.direction}{' mirrored' if props.mirror else ''}  frame {props.frame % n + 1}/{n}  {w}x{h} c({cx},{cy})"

    if _render_state["busy"]:      # the frame renderer owns the model's action and turn while it runs
        return
    model = props.model
    if model is not None and props.turn_model:
        model.rotation_mode = "XYZ"
        model.rotation_euler = (0, 0, _model_yaw(props))
    _apply_model_display(props)
    if props.sync_model_action:
        _sync_model_action(props)
    grid = bpy.data.objects.get("UO_Grid")
    if grid is not None:
        grid.hide_set(not props.show_grid)
    land = bpy.data.objects.get("UO_LandPatch")
    if land is not None:
        land.hide_set(not props.show_land); land.hide_render = not props.show_land
    for o in bpy.data.objects:
        if o.get("uo_prop"):
            o.hide_set(not props.show_props); o.hide_render = not props.show_props


# ---------------- stage props ----------------
STAGE_PROPS = [   # (name, static art file, tile x, tile y)  tiles west (-x) of the model draw behind it, east in front
    ("UO_Prop_Tree_A", "Static_0x0CCD.png", -2, 1),
    ("UO_Prop_Tree_B", "Static_0x0CCA.png", -2, -1),
    ("UO_Prop_Lamp", "Static_0x0B21.png", 1, 0),
]


def build_props(props):
    cam = bpy.context.scene.camera
    if cam is None:
        return 0
    px_x, px_y = camera_px(cam)
    col = bpy.data.collections.get("UO_Props")
    if col is None:
        col = bpy.data.collections.new("UO_Props")
        (bpy.data.collections.get("UO_Stage") or bpy.context.scene.collection).children.link(col)
    art_dir = bpy.path.abspath(props.props_dir)
    made = 0
    for name, fname, tx, ty in STAGE_PROPS:
        path = os.path.join(art_dir, fname)
        if not os.path.exists(path):
            continue
        img = get_image(path)
        w, h = img.size
        obj = bpy.data.objects.get(name)
        if obj is None:
            mesh = bpy.data.meshes.new(name)
            mesh.from_pydata([(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)], [], [(0, 1, 2, 3)])
            mesh.uv_layers.new()
            obj = bpy.data.objects.new(name, mesh)
            col.objects.link(obj)
            obj["uo_prop"] = True
            obj.hide_select = True
        _set_uvs(obj, (0, 0, 1, 1))
        mat = ensure_material(obj, img)
        mat.node_tree.nodes["uo_alpha"].inputs[1].default_value = 1.0
        mat.diffuse_color = (1, 1, 1, 1)
        obj.parent = cam
        obj.matrix_parent_inverse = Matrix.Identity(4)
        la = cam.matrix_world.inverted() @ Vector((tx, ty, 0))       # camera-local tile centre
        obj.scale = (w / px_x, h / px_y, 1)
        obj.location = (la.x, la.y + (h / 2 - 22) / px_y, la.z)
        obj.rotation_euler = (0, 0, 0)
        made += 1
    return made


class SPRITEMOTION_OT_stage_props(bpy.types.Operator):
    bl_idname = "spritemotion.stage_props"
    bl_label = "Build props"
    bl_description = "Place UO static art (two trees west of the model, a lamp post east) on camera-aligned planes"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = _active_sheet(context)
        if obj is None:
            return {"CANCELLED"}
        n = build_props(obj.spritemotion_sheet)
        apply_sheet(obj)
        self.report({"INFO"}, f"{n} props placed")
        return {"FINISHED"}


# ---------------- UO camera and frame renderer ----------------
# Cameras from games/ultima-online/profiles/cameras/*.json (copied here so the add-on stays one file).
CAMERA_PRESETS = {
    "GROUND_GRID": ("Ground grid", [[22.0, 22.0, 0.0], [22.0, -22.0, -31.1127]],
                    "ClassicUO's tile maths: 45 deg elevation, sqrt2 vertical stretch. Matches the ground grid exactly "
                    "(profiles/cameras/ground-grid.json)"),
    "DEPTH_0447": ("Character depth 0.447", [[22.0, 22.0, 0.0], [9.834, -9.834, -31.1127]],
                   "Candidate character camera, ground-depth term x 1/sqrt5 (about 24 deg). Better silhouette overlap "
                   "on body 400 in 27 of 35 actions, not validated (profiles/cameras/character-depth-0447.json)"),
}
CAMERA_ITEMS = [(k, v[0], v[2]) for k, v in CAMERA_PRESETS.items()] + \
               [("FILE", "Camera file", "A SpriteMotion affine camera JSON ({type: affine_orthographic, matrix, anchor?})")]
UO_CAMERA_NAME = "SpriteMotion UO Camera"
ORTHOGONALITY_TOLERANCE = 1e-6

# stored row -> (UO direction name, facing (x east, y north)); ClassicUO GetAnimDirection, see UO_DIRS
STORED_ROWS = [("SE", (1, -1)), ("S", (0, -1)), ("SW", (-1, -1)), ("W", (-1, 0)), ("NW", (-1, 1))]
FORWARD_ITEMS = [("NEG_Y", "-Y", "Model faces -Y at zero rotation (glTF, Mixamo, Rigify)", 0),
                 ("POS_Y", "+Y", "Model faces +Y at zero rotation", 1),
                 ("POS_X", "+X", "Model faces +X at zero rotation", 2),
                 ("NEG_X", "-X", "Model faces -X at zero rotation", 3)]
FORWARD_VECTORS = {"NEG_Y": (0, -1), "POS_Y": (0, 1), "POS_X": (1, 0), "NEG_X": (-1, 0)}

# UO 'people' actions (profiles/human-actions.json): (id, name, frames per direction on body 400, loops)
PEOPLE_ACTIONS = [
    (0, "walk", 10, True), (1, "walkstaff", 10, True), (2, "run", 10, True), (3, "runstaff", 10, True),
    (4, "idle", 1, False), (5, "idle_anim", 5, False), (6, "yawn", 5, False), (7, "combat1", 1, False),
    (8, "combat2", 1, False), (9, "slash1h", 7, False), (10, "pierce1h", 7, False), (11, "bash1h", 7, False),
    (12, "bash2h", 7, False), (13, "slash2h", 7, False), (14, "pierce2h", 7, False),
    (15, "combatadvance", 10, True), (16, "spell1", 7, False), (17, "spell2", 7, False),
    (18, "bow_attack", 7, False), (19, "crossbow_attack", 7, False), (20, "get_hit", 5, False),
    (21, "death_back", 6, False), (22, "death_forward", 6, False), (23, "mounted_walk", 5, True),
    (24, "mounted_run", 5, True), (25, "mounted_idle", 1, False), (26, "mounted_slash1h", 5, False),
    (27, "mounted_bow", 5, False), (28, "mounted_crossbow", 7, False), (29, "mounted_slash2h", 5, False),
    (30, "block", 5, False), (31, "punch", 7, False), (32, "bow_gesture", 5, False), (33, "salute", 5, False),
    (34, "eat", 5, False),
]
_render_state = {"busy": False}


def camera_px(cam):
    """(px per unit along the camera's x, px per unit along its y) of a UO camera, for camera-parented planes."""
    if "uo_px_x" in cam and "uo_px_y" in cam:
        return float(cam["uo_px_x"]), float(cam["uo_px_y"])
    px_x = float(cam.get("uo_px_per_unit", PX_PER_UNIT_X))     # pre-0.6 stage camera: ground grid
    return px_x, px_x * math.sqrt(2)


def camera_matrix(settings):
    """(2x3 matrix, anchor or None, label) of the chosen camera."""
    if settings.camera != "FILE":
        label, matrix, _ = CAMERA_PRESETS[settings.camera]
        return matrix, None, label
    path = bpy.path.abspath(settings.camera_file)
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    if data.get("type") != "affine_orthographic":
        raise ValueError(f"unsupported camera type {data.get('type')!r} in {path}")
    return data["matrix"], data.get("anchor"), os.path.basename(path)


def camera_params(matrix, anchor, width, height, distance=100.0):
    """Blender camera for canvas = anchor + matrix @ world; same maths as common/rendering/ortho.py."""
    r0, r1 = np.asarray(matrix[0], dtype=float), np.asarray(matrix[1], dtype=float)
    s0, s1 = np.linalg.norm(r0), np.linalg.norm(r1)
    if s0 == 0 or s1 == 0:
        raise ValueError("Degenerate camera matrix.")
    if abs(np.dot(r0, r1)) > ORTHOGONALITY_TOLERANCE * s0 * s1:
        raise ValueError("The camera's rows are not orthogonal; a Blender orthographic camera cannot reproduce it.")
    right, up = r0 / s0, -r1 / s1
    back = np.cross(right, up)  # Blender cameras look down their local -z
    if back[2] < 0:
        raise ValueError("The camera views the ground from below or is mirrored; not representable.")
    dx = (width - 1) / 2.0 - anchor[0]
    dy = (height - 1) / 2.0 - anchor[1]
    centre = dx / s0 ** 2 * r0 + dy / s1 ** 2 * r1
    smallest = min(s0, s1)
    return {
        "location": (centre + back * distance).tolist(),
        "rotation": np.column_stack([right, up, back]).tolist(),  # columns = camera x, y, z axes
        "ortho_scale": width / s0,
        "pixel_aspect_x": s1 / smallest,
        "pixel_aspect_y": s0 / smallest,
        "px": (float(s0), float(s1)),
        "clip_start": 0.01,
        "clip_end": distance * 2.0,
    }


def setup_uo_camera(scene, settings):
    """Create or update the UO camera from the chosen camera JSON and make it the scene camera."""
    matrix, file_anchor, label = camera_matrix(settings)
    w, h = settings.canvas
    anchor = file_anchor or list(settings.anchor)
    p = camera_params(matrix, anchor, w, h)
    cam = bpy.data.objects.get(UO_CAMERA_NAME)
    if cam is None or cam.type != "CAMERA":
        cam = bpy.data.objects.new(UO_CAMERA_NAME, bpy.data.cameras.new(UO_CAMERA_NAME))
        scene.collection.objects.link(cam)
    elif cam.name not in scene.objects:
        scene.collection.objects.link(cam)
    cam.parent = None
    cam.animation_data_clear()
    cam.matrix_world = Matrix.Translation(Vector(p["location"])) @ Matrix(p["rotation"]).to_4x4()
    data = cam.data
    data.type = "ORTHO"
    data.ortho_scale = p["ortho_scale"]
    data.sensor_fit = "HORIZONTAL"
    data.shift_x = data.shift_y = 0.0
    data.clip_start, data.clip_end = p["clip_start"], p["clip_end"]
    scene.camera = cam
    render = scene.render
    render.resolution_x, render.resolution_y, render.resolution_percentage = w, h, 100
    render.pixel_aspect_x, render.pixel_aspect_y = p["pixel_aspect_x"], p["pixel_aspect_y"]
    cam["uo_px_x"], cam["uo_px_y"] = p["px"]
    cam["uo_px_per_unit"] = p["px"][0]
    cam["uo_camera"] = label
    cam["uo_camera_matrix"] = json.dumps(matrix)
    cam["uo_anchor"] = list(anchor)
    for o in scene.objects:     # sheet planes are parented to the scene camera: re-place them
        if o.spritemotion_sheet.enabled:
            apply_sheet(o, scene)
    return cam, matrix, anchor, label


def facing_yaw(facing, forward=(0, -1), offset=0.0):
    """z rotation that turns a model facing `forward` at zero rotation to face `facing`."""
    return math.atan2(facing[1], facing[0]) - math.atan2(forward[1], forward[0]) + offset


def parse_ids(text, lo, hi):
    """'0-4,9,20-22' -> sorted ids within [lo, hi]."""
    out = set()
    for part in (text or "").replace(" ", "").split(","):
        if not part:
            continue
        a, _, b = part.partition("-")
        a, b = int(a), int(b or a)
        out.update(i for i in range(min(a, b), max(a, b) + 1) if lo <= i <= hi)
    return sorted(out)


def load_action_map(settings):
    """{uo action: {clip, frames, loop, pick}} from the optional action map JSON (SWG uo_render format)."""
    path = bpy.path.abspath(settings.action_map) if settings.action_map else ""
    if not path:
        return {}
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    return {int(e["action"]): e for e in data.get("actions", [])}


def render_armature(settings):
    obj = settings.model
    if obj is None:
        return None
    if obj.type == "ARMATURE":
        return obj
    return next((o for o in obj.children_recursive if o.type == "ARMATURE"), None)


def resolve_clip(settings, uo_action, name, mapped):
    """Blender action for a UO action: the action map's clip, else the naming the sheet add-on and the
    SpriteMotion fitter use (UO_<body>_<aaa>_<name>, UO_<name>, <name>, fit_action-<aaa>)."""
    candidates = [mapped["clip"]] if mapped and mapped.get("clip") else [
        f"UO_{settings.body}_{uo_action:03d}_{name}", f"UO_{name}", name, f"fit_action-{uo_action:03d}"]
    for cand in candidates:
        act = bpy.data.actions.get(cand)
        if act is not None:
            return act
    if mapped and mapped.get("clip"):   # glTF import appends the armature name, e.g. loc_walk_male_Armature
        return next((a for a in bpy.data.actions if a.name.startswith(mapped["clip"])), None)
    return None


def sample_times(act, count, loop, pick, sampling, step):
    """Scene times (float frames) for count UO frames of an action."""
    f0, f1 = act.frame_range
    if sampling == "KEYED":
        return [f0 + i * step for i in range(count)]
    if count == 1:
        return [f0 + (f1 - f0) * pick]
    if loop:
        return [f0 + (f1 - f0) * i / count for i in range(count)]
    return [f0 + (f1 - f0) * i / (count - 1) for i in range(count)]


def character_objects(model, armature):
    """The model, everything under it, and every mesh the armature deforms."""
    keep = {model} | set(model.children_recursive)
    if armature is not None:
        keep |= {armature} | set(armature.children_recursive)
        for o in bpy.data.objects:
            if any(m.type == "ARMATURE" and m.object == armature for m in getattr(o, "modifiers", ())):
                keep.add(o)
    return keep


def crop_frame(src, dst, anchor, threshold=128):
    """Threshold alpha, crop to the opaque box and save; returns the frame's uopack entry (ClassicUO centre)."""
    img = bpy.data.images.load(src, check_existing=False)
    try:
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
    finally:
        bpy.data.images.remove(img)
    rgba = np.flipud(np.round(px.reshape(h, w, 4) * 255.0).astype(np.uint8))     # top row first
    solid = rgba[..., 3] >= threshold
    rgba[..., 3] = np.where(solid, 255, 0)
    rgba[~solid] = 0
    ys, xs = np.nonzero(solid)
    if len(xs):
        left, top, right, bottom = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    else:
        left, top, right, bottom = int(anchor[0]), int(anchor[1]), int(anchor[0]) + 1, int(anchor[1]) + 1
    crop = rgba[top:bottom, left:right]
    ch, cw = crop.shape[:2]
    out = bpy.data.images.new(os.path.basename(dst), cw, ch, alpha=True)
    try:
        out.alpha_mode = "STRAIGHT"
        out.pixels.foreach_set((np.flipud(crop).astype(np.float32) / 255.0).ravel())
        out.filepath_raw = dst
        out.file_format = "PNG"
        out.save()
    finally:
        bpy.data.images.remove(out)
    return {"png": os.path.basename(dst), "center_x": int(anchor[0]) - left,
            "center_y": (int(anchor[1]) - top) - ch, "width": cw, "height": ch}


def _silhouette_look(scene):
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "FLAT"
    shading.color_type = "SINGLE"
    shading.single_color = (0.8, 0.8, 0.8)
    shading.show_object_outline = False
    shading.show_cavity = False
    scene.render.filter_size = 0.0


def _snapshot(owner, names):
    return [(owner, n, getattr(owner, n)) for n in names]


def render_uo_frames(scene, settings, log=print):
    """Render every chosen UO action x stored row. Returns (frames written, list of problems)."""
    model = settings.model
    if model is None:
        raise ValueError("Choose the model (the object turned per direction)")
    arm = render_armature(settings)
    out_dir = bpy.path.abspath(settings.output_dir)
    if not out_dir:
        raise ValueError("Choose an output folder")
    canvas_dir = os.path.join(out_dir, "canvas")
    os.makedirs(canvas_dir, exist_ok=True)
    pack_dir = os.path.join(out_dir, f"body_{settings.body:04d}")
    if settings.crop:
        os.makedirs(pack_dir, exist_ok=True)
    amap = load_action_map(settings)
    actions = parse_ids(settings.actions, 0, len(PEOPLE_ACTIONS) - 1)
    rows = [d for d in range(5) if settings.directions[d]]
    forward = FORWARD_VECTORS[settings.model_forward]
    problems = []
    if Vector(model.matrix_world.translation[:2]).length > 1e-3:
        problems.append(f"{model.name} is not at the world origin: the ground origin (tile centre) is world (0, 0, 0)")

    render, image = scene.render, scene.render.image_settings
    saved = _snapshot(render, ("engine", "film_transparent", "filter_size", "filepath"))
    saved += _snapshot(image, ("file_format", "color_mode", "color_depth"))
    saved += _snapshot(scene.display.shading, ("light", "color_type", "single_color", "show_object_outline",
                                               "show_cavity"))
    saved += _snapshot(scene, ("frame_current",))   # the UO camera stays the scene camera, as for the overlay
    saved += _snapshot(model, ("rotation_mode",))
    saved_rot = tuple(model.rotation_euler)
    saved_hide = []
    ad = arm.animation_data if arm else None
    saved_anim = None
    if arm is not None:
        ad = arm.animation_data or arm.animation_data_create()
        saved_anim = (ad.action, getattr(ad, "action_slot", None), [(t, t.mute) for t in ad.nla_tracks])

    manifest = {"schema": "spritemotion.uo_frames", "schema_version": 1, "blender": bpy.app.version_string,
                "file": bpy.data.filepath, "model": model.name, "body": settings.body,
                "canvas": list(settings.canvas), "rows": {}, "actions": []}
    written = 0
    _render_state["busy"] = True
    try:
        cam, matrix, anchor, label = setup_uo_camera(scene, settings)
        manifest.update(camera=label, camera_matrix=matrix, anchor=list(anchor))
        render.film_transparent = True
        image.file_format, image.color_mode, image.color_depth = "PNG", "RGBA", "8"
        if settings.look == "SILHOUETTE":
            _silhouette_look(scene)
        if settings.only_model:
            keep = character_objects(model, arm)
            for o in scene.objects:
                if o not in keep and o.type not in {"LIGHT", "CAMERA"} and not o.hide_render:
                    saved_hide.append(o)
                    o.hide_render = True
        if ad is not None:
            for t in ad.nla_tracks:
                t.mute = True
        model.rotation_mode = "XYZ"
        for a in actions:
            _, name, frames, loop = PEOPLE_ACTIONS[a]
            mapped = amap.get(a)
            if amap and mapped is None:
                continue        # an action map lists exactly the actions to render
            count = int(mapped.get("frames", frames)) if mapped else frames
            loop = bool(mapped.get("loop", loop)) if mapped else loop
            pick = float(mapped.get("pick", settings.pick)) if mapped else settings.pick
            act = resolve_clip(settings, a, name, mapped)
            if act is None:
                problems.append(f"action {a} {name}: no Blender action found")
                continue
            if ad is not None:
                ad.action = act
                if hasattr(ad, "action_slot") and getattr(act, "slots", None):
                    ad.action_slot = act.slots[0]
            times = sample_times(act, count, loop, pick, settings.sampling, settings.step)
            manifest["actions"].append({"action": a, "name": name, "clip": act.name, "frames": count,
                                        "loop": loop, "times": [round(t, 4) for t in times]})
            for d in rows:
                dname, facing = STORED_ROWS[d]
                manifest["rows"][str(d)] = {"name": dname, "facing": list(facing)}
                model.rotation_euler = (saved_rot[0], saved_rot[1],
                                        facing_yaw(facing, forward, settings.model_yaw_offset))
                entries = []
                for i, t in enumerate(times):
                    scene.frame_set(int(math.floor(t)), subframe=t - math.floor(t))
                    fname = f"a{a:02d}_d{d}_f{i:02d}.png"
                    render.filepath = os.path.join(canvas_dir, fname)
                    bpy.ops.render.render(write_still=True)
                    written += 1
                    if settings.crop:
                        entries.append(crop_frame(render.filepath, os.path.join(pack_dir, fname), anchor,
                                                  settings.alpha_threshold))
                if settings.crop and entries:
                    with open(os.path.join(pack_dir, f"a{a:02d}_d{d}.json"), "w", encoding="utf-8") as f:
                        json.dump({"kind": "anim", "body": settings.body, "action": a, "direction": d,
                                   "frames": entries, "source": act.name}, f, indent=1)
            log(f"[SpriteMotion] action {a} {name}: {count} frames x {len(rows)} rows from {act.name}")
    finally:
        _render_state["busy"] = False
        for o in saved_hide:
            o.hide_render = False
        model.rotation_euler = saved_rot
        if saved_anim is not None:
            ad.action = saved_anim[0]
            if saved_anim[1] is not None and hasattr(ad, "action_slot"):
                ad.action_slot = saved_anim[1]
            for t, mute in saved_anim[2]:
                t.mute = mute
        for owner, n, v in saved:
            setattr(owner, n, v)
        scene.frame_set(scene.frame_current)
    manifest["problems"] = problems
    with open(os.path.join(out_dir, "render.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
    return written, problems


class SpriteMotionRenderProps(bpy.types.PropertyGroup):
    camera: bpy.props.EnumProperty(name="Camera", items=CAMERA_ITEMS, default="GROUND_GRID",
        description="SpriteMotion UO camera the frames are rendered through (and the overlay is sized by)")
    camera_file: bpy.props.StringProperty(name="Camera file", subtype="FILE_PATH", default="",
        description="SpriteMotion affine camera JSON, e.g. games/ultima-online/profiles/cameras/ground-grid.json")
    canvas: bpy.props.IntVectorProperty(name="Canvas", size=2, default=(256, 256), min=16, max=4096)
    anchor: bpy.props.IntVectorProperty(name="Anchor", size=2, default=(128, 192),
        description="Canvas pixel of the ground origin (the tile centre the mobile stands on)")
    model: bpy.props.PointerProperty(name="Model", type=bpy.types.Object,
        description="Object turned about world z for each direction (a pivot empty, the armature or the root); "
                    "its origin must be at the world origin, the tile centre. Scale: 1 Blender unit = 1 UO tile")
    model_forward: bpy.props.EnumProperty(name="Forward", items=FORWARD_ITEMS, default="NEG_Y")
    model_yaw_offset: bpy.props.FloatProperty(name="Yaw offset", default=0.0, subtype="ANGLE")
    body: bpy.props.IntProperty(name="Body", default=400, min=0, max=65535)
    actions: bpy.props.StringProperty(name="Actions", default="0-34",
        description="UO people actions to render, e.g. 0-4,9,20-22")
    directions: bpy.props.BoolVectorProperty(name="Rows", size=5, default=(True,) * 5,
        description="Stored rows 0..4 = SE, S, SW, W, NW; the client mirrors N, NE, E")
    action_map: bpy.props.StringProperty(name="Action map", subtype="FILE_PATH", default="",
        description="Optional JSON {actions: [{action, clip, frames, loop, pick}]} naming the Blender action per "
                    "UO action. Without it, actions are found by name: UO_<body>_<aaa>_<name>, UO_<name>, <name>, "
                    "fit_action-<aaa>")
    sampling: bpy.props.EnumProperty(name="Sampling", default="SPAN", items=[
        ("SPAN", "Clip span", "Loops sample [start, end) evenly, one-shots [start, end], 1-frame actions at Pick"),
        ("KEYED", "Keyed", "Frame f at action start + f x Step (SpriteMotion fits: step 4)")])
    step: bpy.props.IntProperty(name="Step", default=4, min=1)
    pick: bpy.props.FloatProperty(name="Pick", default=0.0, min=0.0, max=1.0,
        description="Where in the clip a 1-frame action is sampled")
    look: bpy.props.EnumProperty(name="Look", default="SCENE", items=[
        ("SCENE", "Scene", "The scene's engine, lights and materials"),
        ("SILHOUETTE", "Silhouette", "Flat unlit Workbench silhouette, hard edges (for comparing with sprites)")])
    only_model: bpy.props.BoolProperty(name="Only the model", default=True,
        description="Hide everything but the model, what is parented to it and the meshes its armature deforms "
                    "(stage, grid, sheet planes); lights stay")
    output_dir: bpy.props.StringProperty(name="Output", subtype="DIR_PATH", default="//uo_frames/")
    crop: bpy.props.BoolProperty(name="Crop + uopack JSON", default=True,
        description="Also write cropped frames with ClassicUO centres and aAA_dD.json sidecars to body_NNNN/")
    alpha_threshold: bpy.props.IntProperty(name="Alpha cut", default=128, min=1, max=255)


class SPRITEMOTION_OT_uo_camera(bpy.types.Operator):
    bl_idname = "spritemotion.uo_camera"
    bl_label = "Set up UO camera"
    bl_description = "Create or update the SpriteMotion UO camera from the chosen camera JSON, make it the scene " \
                     "camera and set the canvas resolution and pixel aspect"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            cam, _, anchor, label = setup_uo_camera(context.scene, context.scene.spritemotion_render)
        except (OSError, ValueError, KeyError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        px_x, px_y = camera_px(cam)
        self.report({"INFO"}, f"{label}: {px_x:.3f} x {px_y:.3f} px/unit, anchor {tuple(anchor)}")
        return {"FINISHED"}


class SPRITEMOTION_OT_render_frames(bpy.types.Operator):
    bl_idname = "spritemotion.render_frames"
    bl_label = "Render UO frames"
    bl_description = "Render the chosen UO actions in the 5 stored rows through the UO camera: full-canvas PNGs " \
                     "(canvas/aAA_dD_fFF.png), optionally cropped frames with uopack JSON, and render.json"

    def execute(self, context):
        try:
            n, problems = render_uo_frames(context.scene, context.scene.spritemotion_render,
                                           log=lambda m: print(m, flush=True))
        except (OSError, ValueError, KeyError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        for p in problems:
            self.report({"WARNING"}, p)
        self.report({"INFO"}, f"{n} frames rendered")
        return {"FINISHED"}


class SPRITEMOTION_PT_render(bpy.types.Panel):
    bl_label = "UO Frame Render"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SpriteMotion"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.spritemotion_render
        lay = self.layout
        lay.prop(s, "camera")
        if s.camera == "FILE":
            lay.prop(s, "camera_file")
        row = lay.row(align=True); row.prop(s, "canvas"); row = lay.row(align=True); row.prop(s, "anchor")
        lay.operator("spritemotion.uo_camera", icon="CAMERA_DATA")
        box = lay.box(); box.label(text="Model")
        box.prop(s, "model")
        row = box.row(align=True); row.prop(s, "model_forward", expand=True)
        box.prop(s, "model_yaw_offset")
        box = lay.box(); box.label(text="Frames")
        box.prop(s, "body"); box.prop(s, "actions")
        row = box.row(align=True)
        for d, (name, _) in enumerate(STORED_ROWS):
            row.prop(s, "directions", index=d, text=name, toggle=True)
        box.prop(s, "action_map")
        row = box.row(align=True); row.prop(s, "sampling", expand=True)
        row = box.row(align=True)
        row.prop(s, "step") if s.sampling == "KEYED" else row.prop(s, "pick", slider=True)
        box = lay.box(); box.label(text="Output")
        row = box.row(align=True); row.prop(s, "look", expand=True)
        box.prop(s, "only_model")
        box.prop(s, "output_dir")
        row = box.row(align=True); row.prop(s, "crop", toggle=True); row.prop(s, "alpha_threshold")
        lay.operator("spritemotion.render_frames", icon="RENDER_ANIMATION")


def _cli_render(argv):
    """blender -b scene.blend --python spritemotion_sheet_reference.py -- --render-uo-frames [options]"""
    import argparse
    parser = argparse.ArgumentParser(prog="spritemotion_sheet_reference.py --render-uo-frames")
    parser.add_argument("--render-uo-frames", action="store_true")
    parser.add_argument("--model", help="object turned per direction (default: the scene setting)")
    parser.add_argument("--out", help="output folder")
    parser.add_argument("--camera", help="GROUND_GRID, DEPTH_0447 or a camera JSON path")
    parser.add_argument("--actions", help="e.g. 0-34 or 0,4,9")
    parser.add_argument("--rows", help="stored rows, e.g. 0,1,2,3,4")
    parser.add_argument("--body", type=int)
    parser.add_argument("--action-map")
    parser.add_argument("--forward", choices=list(FORWARD_VECTORS))
    parser.add_argument("--sampling", choices=["SPAN", "KEYED"])
    parser.add_argument("--step", type=int)
    parser.add_argument("--look", choices=["SCENE", "SILHOUETTE"])
    parser.add_argument("--no-crop", action="store_true")
    args = parser.parse_args(argv)
    s = bpy.context.scene.spritemotion_render
    if args.model:
        s.model = bpy.data.objects[args.model]
    if args.out:
        s.output_dir = args.out
    if args.camera:
        if args.camera in CAMERA_PRESETS:
            s.camera = args.camera
        else:
            s.camera, s.camera_file = "FILE", args.camera
    for key in ("actions", "body", "action_map", "sampling", "step", "look"):
        if getattr(args, key) is not None:
            setattr(s, key, getattr(args, key))
    if args.forward:
        s.model_forward = args.forward
    if args.rows:
        rows = parse_ids(args.rows, 0, 4)
        s.directions = [d in rows for d in range(5)]
    if args.no_crop:
        s.crop = False
    n, problems = render_uo_frames(bpy.context.scene, s, log=lambda m: print(m, flush=True))
    for p in problems:
        print("[SpriteMotion] WARNING", p, flush=True)
    print(f"[SpriteMotion] {n} frames rendered to {bpy.path.abspath(s.output_dir)}", flush=True)
    return 0 if not problems else 1


# ---------------- property updates ----------------
def _update(self, context):
    obj = self.id_data
    if isinstance(obj, bpy.types.Object):
        apply_sheet(obj)


def _update_uo_dir(self, context):
    name, stored, mirror, _, _ = UO_DIRS[self.uo_dir]
    self["direction"] = stored
    self["mirror"] = mirror
    _update(self, context)


def _frame_count(props):
    data = load_sheet(props)
    return (len(frames_for(data, props.direction)) if data else 0) or 1


def timeline_sprite_frame(scene_frame, start, hold, count):
    """One-based Blender cycle to zero-based sheet index, including the last hold."""
    return ((scene_frame - start) // max(1, hold)) % max(1, count)


def _update_frame_t(self, context):
    n = _frame_count(self)
    f = min(n - 1, int(self.frame_t * n))
    if f != self.frame:
        self.frame = f          # triggers _update


def _update_frame(self, context):
    n = _frame_count(self)
    t = (self.frame % n + 0.5) / n
    if abs(t - self.frame_t) > 1e-4:
        self["frame_t"] = t
    if self.follow_timeline and context.scene is not None:
        scene = context.scene
        if timeline_sprite_frame(scene.frame_current, scene.frame_start, self.hold, n) != self.frame % n:
            scene.frame_set(scene.frame_start + (self.frame % n) * self.hold)
    _update(self, context)


def _update_alpha_handle(self, context):
    a = min(1.0, max(0.0, self.alpha_handle))
    if abs(a - self.alpha) > 1e-4:
        self.alpha = a          # triggers _update


def _update_alpha(self, context):
    if abs(self.alpha_handle - self.alpha) > 1e-3:
        self["alpha_handle"] = self.alpha
    _update(self, context)


def _redraw(self, context):
    for a in context.screen.areas if context.screen else []:
        if a.type == "VIEW_3D":
            a.tag_redraw()


def _action_items(self, context):
    # Keep strings alive for Blender's dynamic EnumProperty, and use action IDs
    # rather than list positions (indices can be sparse for other bodies).
    key = tuple(action_list(self)) or ((4, "Idle_01"),)
    if key not in _action_enum_cache:
        _action_enum_cache[key] = [(str(a), f"{a}: {n}", "", 0, a) for a, n in key]
    return _action_enum_cache[key]


class SpriteMotionSheetProps(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(default=False)
    sheet_dir: bpy.props.StringProperty(name="Sheets", subtype="DIR_PATH",
        default="", update=_update,
        description="Folder of UOFiddler packed sheets (anim_<body>_<action>.png/.json) exported from your own client")
    body: bpy.props.IntProperty(name="Body", default=400, min=0, update=_update)
    action: bpy.props.IntProperty(name="Action", default=4, min=0, max=200, update=_update)
    action_enum: bpy.props.EnumProperty(name="Action", items=_action_items,
        get=lambda self: self.action, set=lambda self, v: setattr(self, "action", v))
    uo_dir: bpy.props.IntProperty(name="UO direction", default=4, min=0, max=7, update=_update_uo_dir,
        description="0 N (up-right), 1 NE, 2 E, 3 SE (down), 4 S, 5 SW, 6 W, 7 NW (up)")
    direction: bpy.props.IntProperty(name="Stored row", default=1, min=0, max=4, update=_update,
        description="Stored direction row in the sheet (0..4); set by UO direction")
    mirror: bpy.props.BoolProperty(name="Mirror", default=False, update=_update,
        description="Flip horizontally, as the client does for N, NE, E")
    frame: bpy.props.IntProperty(name="Frame", default=0, min=0, update=_update_frame)
    frame_t: bpy.props.FloatProperty(name="Frame slider", default=0.0, min=0.0, max=1.0, update=_update_frame_t)
    alpha: bpy.props.FloatProperty(name="Opacity", default=0.6, min=0.0, max=1.0, update=_update_alpha)
    alpha_handle: bpy.props.FloatProperty(name="Opacity handle", default=0.6, min=0.0, max=1.0, update=_update_alpha_handle)
    view_mode: bpy.props.EnumProperty(name="View", items=VIEW_MODES, default="COLOR", update=_update)
    outline_color: bpy.props.FloatVectorProperty(name="Line colour", subtype="COLOR", size=3, min=0, max=1,
        default=(1.0, 0.9, 0.1), update=_update)
    edge_threshold: bpy.props.FloatProperty(name="Edge threshold", default=0.12, min=0.01, max=1.0, update=_update,
        description="Sobel gradient magnitude needed for an interior edge (Edges view)")
    show_overlay: bpy.props.BoolProperty(name="Overlay", default=True, update=_update,
        description="Show the frame over the model")
    in_front: bpy.props.BoolProperty(name="In front of model", default=True, update=_update)
    depth: bpy.props.FloatProperty(name="Depth offset", default=2.0, min=0.0, update=_update)
    nudge_px: bpy.props.IntVectorProperty(name="Nudge (px)", size=2, default=(0, 0), update=_update)
    anchor: bpy.props.PointerProperty(name="Anchor", type=bpy.types.Object, update=_update,
        description="Empty at the tile centre the sprite stands on (UO_Anchor)")
    model: bpy.props.PointerProperty(name="Model", type=bpy.types.Object, update=_update,
        description="Armature/model to turn with the direction (faces -Y at zero rotation)")
    turn_model: bpy.props.BoolProperty(name="Turn model", default=True, update=_update)
    model_yaw_offset: bpy.props.FloatProperty(name="Yaw offset", default=0.0, subtype="ANGLE", update=_update,
        description="Extra rotation added when turning the model, e.g. to match how the sprite was drawn")
    model_display: bpy.props.EnumProperty(name="Model", items=MODEL_MODES, default="SOLID", update=_update)
    show_bones: bpy.props.BoolProperty(name="Bones", default=True, update=_redraw,
        description="Draw the model's pose bones on top of everything, through the frame")
    bone_color: bpy.props.FloatVectorProperty(name="Bone colour", subtype="COLOR", size=4, min=0, max=1,
        default=(0.2, 1.0, 0.4, 0.9), update=_redraw)
    bone_width: bpy.props.FloatProperty(name="Bone width", default=2.0, min=0.5, max=8.0, update=_redraw)
    show_grid: bpy.props.BoolProperty(name="Grid", default=True, update=_update)
    show_land: bpy.props.BoolProperty(name="Grass", default=True, update=_update,
        description="Show the textured land patch (UO_LandPatch)")
    show_props: bpy.props.BoolProperty(name="Props", default=True, update=_update,
        description="Show the stage props (trees west of the model, lamp post east) built by Build props")
    props_dir: bpy.props.StringProperty(name="Props art", subtype="DIR_PATH",
        default="", description="Folder of static art PNGs (Static_0x....png) exported from your own client")
    show_skeleton: bpy.props.BoolProperty(name="Sprite bones", default=True, update=_redraw,
        description="Draw the frame's authored 2D skeleton (anim_<body>_<action>_skeleton.json) on the plane: "
                    "red bones, blue joints")
    show_rig_error: bpy.props.BoolProperty(name="Rig error", default=True, update=_redraw,
        description="Project the rig's joints onto the frame and draw a line to the sprite joint; "
                    "also raycast each sprite joint onto the model and mark the hit")
    skeleton_status: bpy.props.StringProperty(default="")
    show_decal: bpy.props.BoolProperty(name="Ground decal", default=False, update=_update,
        description="Project the frame along the camera direction onto the ground (z=0) as a decal, with the four "
                    "projection edges drawn, so you can see where each pixel row lands on the tile")
    decal_alpha: bpy.props.FloatProperty(name="Decal opacity", default=0.5, min=0.0, max=1.0, update=_update)
    hud_anchor: bpy.props.EnumProperty(name="Controls", items=HUD_ANCHORS, default="DOCK", update=_redraw,
        description="Where the viewport controls live. Docked keeps them in a screen corner; follow plane keeps "
                    "them next to the sheet but still inside the viewport")
    hud_dock: bpy.props.EnumProperty(name="Corner", items=DOCKS, default="BOTTOM_LEFT", update=_redraw)
    hud_margin: bpy.props.IntProperty(name="Margin (px)", default=16, min=0, max=400, update=_redraw,
        description="Gap between the docked controls and the viewport edge, before UI scaling")
    hud_scale: bpy.props.FloatProperty(name="Controls size", default=1.0, min=0.5, max=2.0, update=_redraw,
        description="Size of the viewport controls; they also shrink by themselves in small viewports")
    hud_compass_offset: bpy.props.FloatVectorProperty(name="Compass offset", size=2, default=(0.0, 0.0), update=_redraw)
    hud_rows_offset: bpy.props.FloatVectorProperty(name="Controls offset", size=2, default=(0.0, 0.0), update=_redraw)
    show_pivot_ray: bpy.props.BoolProperty(name="Pivot ray", default=True, update=_redraw,
        description="Line from the anchor (world origin / tile centre) to the camera, through the frame's pivot pixel")
    sync_model_action: bpy.props.BoolProperty(name="Model action follows", default=True, update=_update,
        description="When the UO action or direction changes, assign the matching Blender action to the armature: "
                    "UO_<name>_<dir>, UO_<name>, or <name> (e.g. UO_Idle_01_S, UO_Idle_01)")
    side_panel: bpy.props.BoolProperty(name="Side panel", default=True, update=_update,
        description="Second, opaque copy of the frame beside the model, viewport only (never renders)")
    side_uses_view_mode: bpy.props.BoolProperty(name="Side follows view", default=False, update=_update,
        description="Side panel shows the outline/edge view too, instead of always the colour frame")
    side_offset_px: bpy.props.IntProperty(name="Side offset (px)", default=72, update=_update,
        description="The side panel's own anchor sits this many sheet pixels right of the real anchor")
    follow_timeline: bpy.props.BoolProperty(name="Follow timeline", default=False,
        description="Frame = ((scene frame - scene start) // hold) mod count")
    hold: bpy.props.IntProperty(name="Hold", default=4, min=1, description="Scene frames per sprite frame")
    fit_range: bpy.props.BoolProperty(name="Fit range", default=True,
        description="Play sets the scene frame range to one sprite cycle (frame count x hold) so both loops line up")
    status: bpy.props.StringProperty(default="")


def _active_sheet(context):
    o = context.object
    if o is not None and o.spritemotion_sheet.enabled:
        return o
    # keep the controls up while the model (or anything else) is selected: use the first sheet plane
    for o in context.scene.objects:
        if o.spritemotion_sheet.enabled:
            return o
    return None


def _legacy_sheets(scene):
    """Objects that still carry settings saved by the old "UO Sheet Reference" add-on (0.4.x)."""
    return [o for o in scene.objects if "uo_sheet" in o.keys() and not o.spritemotion_sheet.enabled]


# ---------------- operators ----------------
class SPRITEMOTION_OT_import_uo_sheet(bpy.types.Operator):
    bl_idname = "spritemotion.import_uo_sheet"
    bl_label = "Import old UO Sheet settings"
    bl_description = ("Copy the settings saved by the old UO Sheet Reference add-on (0.4.x) into SpriteMotion. "
                      "The old data is kept, so the file still opens with the old add-on")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        count = 0
        for o in _legacy_sheets(context.scene):
            src, dst = o["uo_sheet"], o.spritemotion_sheet
            for key in src.keys():
                if key in dst.bl_rna.properties:
                    try:
                        dst[key] = src[key]
                    except (TypeError, ValueError, KeyError):
                        pass
            count += 1
            if dst.enabled:
                dst.frame = dst.frame       # rebuild the image, material and HUD from the copied settings
        self.report({"INFO"}, f"Imported {count} sheet plane(s)")
        return {"FINISHED"}


class SPRITEMOTION_OT_sheet_add(bpy.types.Operator):
    bl_idname = "spritemotion.sheet_add"
    bl_label = "Add sheet plane"
    bl_description = "Create a camera-aligned reference plane showing frames from the packed sheets"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        mesh = bpy.data.meshes.new("UO_SheetPlane")
        mesh.from_pydata([(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)], [], [(0, 1, 2, 3)])
        uv = mesh.uv_layers.new()
        for i, (u, v) in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
            uv.data[i].uv = (u, v)
        obj = bpy.data.objects.new("UO_SheetPlane", mesh)
        col = bpy.data.collections.get("UO_Stage") or context.scene.collection
        col.objects.link(obj)
        obj.spritemotion_sheet.enabled = True
        obj.spritemotion_sheet.anchor = bpy.data.objects.get("UO_Anchor")
        obj.spritemotion_sheet.model = bpy.data.objects.get("target_character")
        apply_sheet(obj)
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {"FINISHED"}


STEP_WHAT = [("FRAME", "Frame", ""), ("DIR", "Direction", ""), ("ACTION", "Action", ""), ("ALPHA", "Alpha", ""),
             ("FRONT", "Front/back", ""), ("VIEW", "View mode", ""), ("MODEL", "Model display", ""),
             ("MIRROR", "Mirror", ""), ("GRID", "Grid", ""), ("OVERLAY", "Overlay", ""), ("SIDE", "Side panel", ""),
             ("BONES", "Bones", ""), ("RAY", "Pivot ray", ""), ("SYNC", "Model action", ""),
             ("LAND", "Grass", ""), ("PROPS", "Props", ""), ("DECAL", "Ground decal", ""), ("ANCHOR", "Controls anchor", ""),
             ("SKEL", "Sprite bones", ""), ("RIGERR", "Rig error", "")]
STEP_DESC = {"FRAME": "Previous/next frame", "DIR": "Previous/next direction", "ACTION": "Previous/next action",
             "ALPHA": "Opacity -/+ 0.1", "FRONT": "Toggle plane in front of / behind the model",
             "VIEW": "Cycle view: colour, outline, edges, silhouette", "MODEL": "Cycle model: solid, wire, hidden",
             "MIRROR": "Flip the frame horizontally", "GRID": "Show/hide the tile grid",
             "OVERLAY": "Show/hide the frame over the model", "SIDE": "Show/hide the opaque side panel",
             "BONES": "Show/hide the see-through bone overlay", "RAY": "Show/hide the anchor-to-camera pivot ray",
             "SYNC": "The model's Blender action follows the UO action/direction",
             "LAND": "Show/hide the grass patch", "PROPS": "Show/hide the trees and lamp post",
             "DECAL": "Project the frame onto the ground along the view direction (with its projection edges)",
             "ANCHOR": "Controls: docked in a viewport corner / next to the plane",
             "SKEL": "Show/hide the frame's authored 2D skeleton (red bones, blue joints)",
             "RIGERR": "Show/hide rig-to-sprite joint error lines and raycast hits"}


class SPRITEMOTION_OT_sheet_step(bpy.types.Operator):
    bl_idname = "spritemotion.sheet_step"
    bl_label = "Step"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}
    delta: bpy.props.IntProperty(default=1)
    what: bpy.props.EnumProperty(items=STEP_WHAT, default="FRAME")

    @classmethod
    def description(cls, context, props):
        return STEP_DESC[props.what]

    def execute(self, context):
        obj = _active_sheet(context)
        if obj is None:
            return {"CANCELLED"}
        p = obj.spritemotion_sheet
        w = self.what
        if w == "FRAME":
            data = load_sheet(p)
            n = len(frames_for(data, p.direction)) if data else 1
            p.frame = (p.frame + self.delta) % max(n, 1)
        elif w == "DIR":
            p.uo_dir = (p.uo_dir + self.delta) % 8
        elif w == "ACTION":
            acts = [a for a, _ in action_list(p)] or [p.action]
            p.action = acts[(acts.index(p.action) + self.delta) % len(acts)] if p.action in acts else max(0, p.action + self.delta)
            p.frame = 0
        elif w == "ALPHA":
            p.alpha = min(1.0, max(0.0, p.alpha + 0.1 * self.delta))
        elif w == "FRONT":
            p.in_front = not p.in_front
        elif w == "VIEW":
            ids = [m[0] for m in VIEW_MODES]; p.view_mode = ids[(ids.index(p.view_mode) + self.delta) % len(ids)]
        elif w == "MODEL":
            ids = [m[0] for m in MODEL_MODES]; p.model_display = ids[(ids.index(p.model_display) + self.delta) % len(ids)]
        elif w == "MIRROR":
            p.mirror = not p.mirror
        elif w == "GRID":
            p.show_grid = not p.show_grid
        elif w == "OVERLAY":
            p.show_overlay = not p.show_overlay
        elif w == "SIDE":
            p.side_panel = not p.side_panel
        elif w == "BONES":
            p.show_bones = not p.show_bones
        elif w == "RAY":
            p.show_pivot_ray = not p.show_pivot_ray
        elif w == "SYNC":
            p.sync_model_action = not p.sync_model_action
        elif w == "LAND":
            p.show_land = not p.show_land
        elif w == "PROPS":
            p.show_props = not p.show_props
        elif w == "DECAL":
            p.show_decal = not p.show_decal
        elif w == "ANCHOR":
            p.hud_anchor = "PLANE" if p.hud_anchor == "DOCK" else "DOCK"
        elif w == "SKEL":
            p.show_skeleton = not p.show_skeleton
        elif w == "RIGERR":
            p.show_rig_error = not p.show_rig_error
        return {"FINISHED"}


class SPRITEMOTION_OT_sheet_play(bpy.types.Operator):
    bl_idname = "spritemotion.sheet_play"
    bl_label = "Play"
    bl_description = "Play the timeline with the sprite frame locked to it: sprite frame = ((scene frame - scene start) // hold) mod count, " \
                     "so the sheet and the armature keyframes move together"
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        obj = _active_sheet(context)
        if obj is None:
            return {"CANCELLED"}
        p = obj.spritemotion_sheet
        sc = context.scene
        if context.screen.is_animation_playing:
            bpy.ops.screen.animation_cancel(restore_frame=False)
            return {"FINISHED"}
        p.follow_timeline = True
        data = load_sheet(p)
        n = len(frames_for(data, p.direction)) if data else 0
        if p.fit_range and n:
            sc.frame_start = 1
            sc.frame_end = n * p.hold
            if not (sc.frame_start <= sc.frame_current <= sc.frame_end):
                sc.frame_current = sc.frame_start
        _frame_change(sc)
        bpy.ops.screen.animation_play()
        return {"FINISHED"}


class SPRITEMOTION_OT_sheet_set_dir(bpy.types.Operator):
    bl_idname = "spritemotion.sheet_set_dir"
    bl_label = "Set direction"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}
    uo_dir: bpy.props.IntProperty(default=4, min=0, max=7)

    @classmethod
    def description(cls, context, props):
        return "Face " + UO_DIRS[props.uo_dir][0]

    def execute(self, context):
        obj = _active_sheet(context)
        if obj is None:
            return {"CANCELLED"}
        obj.spritemotion_sheet.uo_dir = self.uo_dir
        return {"FINISHED"}


class SPRITEMOTION_OT_hud_reset(bpy.types.Operator):
    bl_idname = "spritemotion.hud_reset"
    bl_label = "Reset controls"
    bl_description = "Undo drags and dock the compass and controls in their viewport corner again"

    def execute(self, context):
        obj = _active_sheet(context)
        if obj is None:
            return {"CANCELLED"}
        p = obj.spritemotion_sheet
        p.hud_compass_offset = (0, 0); p.hud_rows_offset = (0, 0); p.hud_anchor = "DOCK"
        return {"FINISHED"}


class SPRITEMOTION_OT_make_actions(bpy.types.Operator):
    bl_idname = "spritemotion.make_actions"
    bl_label = "Placeholder actions"
    bl_description = "Create a Blender action UO_<name> for every UO action in the sheet index that has none yet, " \
                     "as a copy of the model's current action (so unfinished actions show the idle pose)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = _active_sheet(context)
        if obj is None:
            return {"CANCELLED"}
        p = obj.spritemotion_sheet
        arm = _model_armature(p)
        if arm is None or arm.animation_data is None or arm.animation_data.action is None:
            self.report({"WARNING"}, "model has no current action to copy")
            return {"CANCELLED"}
        src = arm.animation_data.action
        made = 0
        for a, name in action_list(p):
            qualified = f"UO_{p.body}_{a:03d}_{name}"
            for cand in (qualified,):
                if bpy.data.actions.get(cand):
                    break
            else:
                same_name_ids = [i for i, n in action_list(p) if n == name]
                legacy = (bpy.data.actions.get(f"UO_{name}") or bpy.data.actions.get(name)) if a == min(same_name_ids) else None
                act = (legacy or src).copy(); act.name = qualified; act.use_fake_user = True
                act["uo_placeholder"] = bool(legacy.get("uo_placeholder", False)) if legacy else True
                act["uo_body"] = p.body; act["uo_action_id"] = a
                made += 1
        self.report({"INFO"}, f"{made} placeholder actions created")
        return {"FINISHED"}


class SPRITEMOTION_OT_sheet_open_dir(bpy.types.Operator):
    bl_idname = "spritemotion.sheet_open_dir"
    bl_label = "Open sheets folder"
    bl_description = "Open the folder holding every action's sprite sheet in the file browser"

    def execute(self, context):
        obj = _active_sheet(context)
        if obj is None:
            return {"CANCELLED"}
        bpy.ops.wm.path_open(filepath=bpy.path.abspath(obj.spritemotion_sheet.sheet_dir))
        return {"FINISHED"}


def _action_fcurves(act):
    """All F-curves of an action: act.fcurves before Blender 5, the channelbags of its layers after."""
    legacy = getattr(act, "fcurves", None)
    if legacy is not None and not hasattr(act, "layers"):
        return list(legacy)
    out = []
    for layer in getattr(act, "layers", ()):
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", ()):
                out.extend(bag.fcurves)
    if not out and legacy is not None:
        out = list(legacy)
    return out


def authored_action_family(props):
    qualified = f"UO_{props.body}_{props.action:03d}_{action_name(props)}"
    return [a for suffix in ("", "_N", "_NE", "_E")
            if (a := bpy.data.actions.get(qualified + suffix)) is not None]


class SPRITEMOTION_OT_pose_interpolation(bpy.types.Operator):
    bl_idname = "spritemotion.pose_interpolation"
    bl_label = "Pose interpolation"
    bl_description = "Stepped matches held sprite frames; Smooth interpolates between the authored poses"
    bl_options = {"REGISTER", "UNDO"}
    mode: bpy.props.EnumProperty(items=[("CONSTANT", "Stepped", "Match sprite holds"),
                                        ("LINEAR", "Smooth", "Interpolate between poses")], default="CONSTANT")

    def execute(self, context):
        obj = _active_sheet(context)
        actions = authored_action_family(obj.spritemotion_sheet) if obj else []
        if not actions or any(a.get("uo_placeholder") for a in actions):
            self.report({"WARNING"}, "No authored action family selected")
            return {"CANCELLED"}
        for act in actions:
            for fc in _action_fcurves(act):
                for key in fc.keyframe_points:
                    key.interpolation = self.mode
                fc.update()
            act["uo_preview_interpolation"] = self.mode
        context.scene.frame_set(context.scene.frame_current)
        return {"FINISHED"}


class SPRITEMOTION_OT_retime_action(bpy.types.Operator):
    bl_idname = "spritemotion.retime_action"
    bl_label = "Retime action to hold"
    bl_description = "Retime this authored action and its mirrored variants to the selected sprite hold"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = _active_sheet(context)
        if obj is None:
            return {"CANCELLED"}
        p = obj.spritemotion_sheet
        actions = authored_action_family(p)
        if not actions or any(not a.get("uo_baked_hold") or a.get("uo_placeholder") for a in actions):
            self.report({"WARNING"}, "This action has no authored timing metadata")
            return {"CANCELLED"}
        for act in actions:
            factor = p.hold / act["uo_baked_hold"]
            start = float(act.get("uo_baked_start", 1))
            for fc in _action_fcurves(act):
                for key in fc.keyframe_points:
                    x, left, right = key.co.x, key.handle_left.x, key.handle_right.x
                    key.co.x = 1 + (x - start) * factor
                    key.handle_left.x = 1 + (left - start) * factor
                    key.handle_right.x = 1 + (right - start) * factor
                fc.update()
            act["uo_baked_hold"] = p.hold
            act["uo_baked_start"] = 1
        context.scene.frame_start = 1
        context.scene.frame_end = _frame_count(p) * p.hold
        context.scene.frame_set(1 + (p.frame % _frame_count(p)) * p.hold)
        self.report({"INFO"}, f"Retimed {len(actions)} action variants to hold {p.hold}")
        return {"FINISHED"}


class SPRITEMOTION_OT_sheet_refresh(bpy.types.Operator):
    bl_idname = "spritemotion.sheet_refresh"
    bl_label = "Refresh"
    bl_description = "Reload the sheet images and JSON from disk and rebuild the derived outline/edge sheets"

    def execute(self, context):
        obj = _active_sheet(context)
        if obj is None:
            return {"CANCELLED"}
        p = obj.spritemotion_sheet
        folder = os.path.normcase(os.path.abspath(bpy.path.abspath(p.sheet_dir)))
        prefix = f"anim_{p.body}_"
        _sheet_cache.clear(); _index_cache.clear(); _skel_cache.clear()
        _data_errors.clear()
        for im in list(bpy.data.images):
            path = os.path.normcase(os.path.abspath(bpy.path.abspath(im.filepath)))
            if os.path.dirname(path) != folder or not os.path.basename(path).startswith(prefix):
                continue
            try:
                im.reload()
            except RuntimeError as exc:
                self.report({"WARNING"}, str(exc))
        for o in context.scene.objects:
            other = o.spritemotion_sheet
            if other.enabled and other.body == p.body and os.path.normcase(os.path.abspath(bpy.path.abspath(other.sheet_dir))) == folder:
                apply_sheet(o, context.scene, force_refresh=True)
        return {"FINISHED"}


# ---------------- panel ----------------
class SPRITEMOTION_PT_sheet(bpy.types.Panel):
    bl_label = "Sheet Reference"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SpriteMotion"

    def draw(self, context):
        lay = self.layout
        lay.operator("spritemotion.sheet_add", icon="IMAGE_PLANE")
        obj = _active_sheet(context)
        if obj is None:
            lay.label(text="No sheet plane in the scene")
            if _legacy_sheets(context.scene):
                lay.operator("spritemotion.import_uo_sheet", icon="IMPORT")
            return
        p = obj.spritemotion_sheet
        row = lay.row(align=True); row.prop(p, "sheet_dir"); row.operator("spritemotion.sheet_open_dir", text="", icon="FILE_FOLDER")
        lay.prop(p, "body")
        row = lay.row(align=True)
        op = row.operator("spritemotion.sheet_step", text="", icon="TRIA_LEFT"); op.what = "ACTION"; op.delta = -1
        row.prop(p, "action_enum", text="")
        op = row.operator("spritemotion.sheet_step", text="", icon="TRIA_RIGHT"); op.what = "ACTION"; op.delta = 1
        row = lay.row(align=True)
        op = row.operator("spritemotion.sheet_step", text="", icon="TRIA_LEFT"); op.what = "FRAME"; op.delta = -1
        row.prop(p, "frame")
        op = row.operator("spritemotion.sheet_step", text="", icon="TRIA_RIGHT"); op.what = "FRAME"; op.delta = 1
        box = lay.box(); box.label(text="Direction: " + UO_DIRS[p.uo_dir][0] + f"  (stored {p.direction}{', mirrored' if p.mirror else ''})")
        grid = box.grid_flow(columns=3, align=True)
        for name in ("NW", "N", "NE", "W", "", "E", "SW", "S", "SE"):
            if not name:
                grid.label(text="")
                continue
            d = next(i for i, t in enumerate(UO_DIRS) if t[0] == name)
            grid.operator("spritemotion.sheet_set_dir", text=name, depress=(p.uo_dir == d)).uo_dir = d
        box = lay.box(); box.label(text="Model")
        row = box.row(align=True); row.prop(p, "model"); row.prop(p, "turn_model", toggle=True, text="Turn")
        row = box.row(align=True); row.prop(p, "model_yaw_offset"); row.prop(p, "model_display", text="")
        row = box.row(align=True); row.prop(p, "show_bones", toggle=True); row.prop(p, "bone_color", text=""); row.prop(p, "bone_width", text="W")
        row = box.row(align=True); row.prop(p, "show_pivot_ray", toggle=True); row.prop(p, "sync_model_action", toggle=True)
        box.operator("spritemotion.make_actions", icon="ACTION")
        row = box.row(align=True)
        row.operator("spritemotion.pose_interpolation", text="Stepped").mode = "CONSTANT"
        row.operator("spritemotion.pose_interpolation", text="Smooth").mode = "LINEAR"
        arm = _model_armature(p)
        act = arm.animation_data.action if arm and arm.animation_data else None
        if act:
            if act.get("uo_placeholder"):
                box.label(text="Placeholder: copied pose, not authored motion", icon="ERROR")
            elif act.get("uo_status"):
                box.label(text=act["uo_status"], icon="INFO")
            if "uo_render_mean_iou" in act:
                box.label(text=f"Last rendered IoU: {act['uo_render_mean_iou']:.1%} (snapshot)")
            if act.get("uo_baked_hold") and act["uo_baked_hold"] != p.hold:
                box.label(text=f"Action baked at hold {act['uo_baked_hold']}; retime before changing hold", icon="ERROR")
                box.operator("spritemotion.retime_action")
        box = lay.box(); box.label(text="Frame view")
        row = box.row(align=True); row.prop(p, "view_mode", expand=True)
        row = box.row(align=True); row.prop(p, "outline_color", text=""); row.prop(p, "edge_threshold")
        row = box.row(align=True); row.prop(p, "show_overlay", toggle=True); row.prop(p, "side_panel", toggle=True); row.prop(p, "show_grid", toggle=True)
        row = box.row(align=True); row.prop(p, "show_land", toggle=True); row.prop(p, "show_props", toggle=True); row.operator("spritemotion.stage_props", icon="OUTLINER_OB_LIGHT")
        row = box.row(align=True); row.prop(p, "show_decal", toggle=True); row.prop(p, "decal_alpha", slider=True)
        row = box.row(align=True); row.prop(p, "show_skeleton", toggle=True); row.prop(p, "show_rig_error", toggle=True)
        box.operator("spritemotion.fit_model", icon="SNAP_ON")
        if _hud.get("skel_status"):
            box.label(text=_hud["skel_status"])
        row = box.row(align=True); row.prop(p, "hud_anchor", expand=True)
        row = box.row(align=True); row.prop(p, "hud_dock", text=""); row.prop(p, "hud_margin", text="Margin")
        row = box.row(align=True); row.prop(p, "hud_scale", slider=True); row.operator("spritemotion.hud_reset", text="", icon="LOOP_BACK")
        row = box.row(align=True); row.prop(p, "side_uses_view_mode", toggle=True); row.prop(p, "side_offset_px")
        lay.prop(p, "alpha", slider=True)
        row = lay.row(align=True); row.prop(p, "in_front", toggle=True); row.prop(p, "depth")
        lay.prop(p, "nudge_px")
        lay.prop(p, "anchor")
        row = lay.row(align=True)
        row.operator("spritemotion.sheet_play", text="Pause" if context.screen.is_animation_playing else "Play",
                     icon="PAUSE" if context.screen.is_animation_playing else "PLAY")
        row.prop(p, "follow_timeline", toggle=True); row.prop(p, "hold"); row.prop(p, "fit_range", toggle=True)
        lay.operator("spritemotion.sheet_refresh", icon="FILE_REFRESH")
        lay.label(text=p.status)
        cam = context.scene.camera
        if cam:
            px_x, px_y = camera_px(cam)
            lay.label(text=f"camera {cam.name} ({cam.get('uo_camera', 'legacy stage')}): {px_x:.2f} x {px_y:.2f} px/unit")


# ---------------- gizmos ----------------
# All sizes are region pixels at UI scale 1 and scale 1; hud_layout multiplies them.
BTN = 40            # button pitch
BTN_R = 14          # button radius (GIZMO_GT_button_2d scale_basis)
COMPASS_R = 46      # compass ring radius
COMPASS_LABEL = 16  # label distance outside the ring
HEADER = 18         # strip above a block that holds its drag grip
GRIP = 14
SLIDER_W, SLIDER_H = 220, 14
SLIDER_ROW = 24
SLIDER_LABEL_W = 84
TEXT_LINE = 16
PAD = 4


def _clamp_block(x, y, w, h, vis):
    """Move a w*h block at (x, y) so it lies inside vis = (x0, y0, x1, y1). An oversized block pins to the
    top-left, so its grip and first rows stay visible."""
    x0, y0, x1, y1 = vis
    return max(x0, min(x, x1 - w)), min(y1 - h, max(y0, y))


def _panel_size(s, avail_w, n_row1, n_row2, show_sliders, n_text):
    """Size of the controls panel and its button columns at unit scale s, wrapping the rows to avail_w."""
    pitch = BTN * s
    cols = max(1, min(max(n_row1, n_row2), int(avail_w // pitch)))
    lines = -(-n_row1 // cols) + -(-n_row2 // cols)
    w = cols * pitch
    if show_sliders:
        w = max(w, (SLIDER_W + SLIDER_LABEL_W + 2 * PAD) * s)
    h = HEADER * s + lines * pitch + (2 * SLIDER_ROW * s if show_sliders else 0) + (n_text * TEXT_LINE * s + PAD * s if n_text else 0)
    return w, h, cols, lines


def hud_layout(width, height, insets=(0, 0, 0, 0), ui_scale=1.0, dock="BOTTOM_LEFT", margin=16,
               controls_offset=(0.0, 0.0), compass_offset=(0.0, 0.0), n_row1=9, n_row2=14, n_text=3,
               hud_scale=1.0, plane_rect=None):
    """Screen-space layout of every HUD element. Pure: no bpy, so it is testable without a viewport.

    width, height: the WINDOW region size; insets: (left, right, bottom, top) pixels covered by overlapping
    toolbar / N-panel / header regions. dock: corner used when plane_rect is None. plane_rect: the plane's
    region-pixel bounds (x0, y0, x1, y1) in follow-plane mode. Offsets are the user's grip drags.

    Returns a dict. "rects" maps every visible element to (x0, y0, x1, y1); drawing and hit-testing both read
    their positions from this dict. Elements that do not fit even at half size are listed in "hidden".
    Every rect in "rects" lies inside "visible".
    """
    vis = (insets[0], insets[2], max(insets[0], width - insets[1]), max(insets[2], height - insets[3]))
    m = max(0.0, margin * ui_scale)
    avail_w = max(0.0, vis[2] - vis[0] - 2 * m)
    avail_h = max(0.0, vis[3] - vis[1] - 2 * m)
    if avail_w < 1 or avail_h < 1:          # nearly nothing visible: shrink the margin away
        m = 0.0
        avail_w, avail_h = vis[2] - vis[0], vis[3] - vis[1]
    base = max(0.25, ui_scale * hud_scale)
    # Try the full HUD first, then smaller, then with less content, until it fits.
    attempts = []
    for k in (1.0, 0.9, 0.8, 0.7):
        attempts.append((k, True, True, n_text))
    for k in (0.8, 0.7, 0.6, 0.5):
        attempts.append((k, True, True, 0))
    for k in (0.6, 0.5):
        attempts.append((k, False, True, 0))
    for k in (0.5,):
        attempts.append((k, False, False, 0))
    chosen = None
    for k, want_compass, want_sliders, texts in attempts:
        s = base * k
        pw, ph, cols, lines = _panel_size(s, avail_w, n_row1, n_row2, want_sliders, texts)
        cw = 2 * (COMPASS_R + COMPASS_LABEL + 12) * s
        ch = cw + HEADER * s
        side = want_compass and pw + cw <= avail_w and max(ph, ch) <= avail_h
        stack = want_compass and not side and max(pw, cw) <= avail_w and ph + ch <= avail_h
        fits_panel = pw <= avail_w and ph <= avail_h
        loose = plane_rect is not None and cw <= avail_w and ch <= avail_h
        if fits_panel and (not want_compass or side or stack or loose):
            chosen = (s, want_compass, want_sliders, texts, pw, ph, cols, lines, cw, ch, "side" if side else "stack")
            break
    hidden = set()
    if chosen is None:                      # smallest scale, buttons only (at least one must fit); drop the overflow
        s = max(0.05, min(base * 0.5, avail_w / BTN, avail_h / (HEADER + BTN)))
        want_compass, want_sliders, texts = False, False, 0
        pw, ph, cols, lines = _panel_size(s, avail_w, n_row1, n_row2, False, 0)
        cw = ch = 0.0
        chosen = (s, False, False, 0, pw, ph, cols, lines, cw, ch, "side")
    s, want_compass, want_sliders, texts, pw, ph, cols, lines, cw, ch, arrange = chosen
    if not want_compass:
        hidden.add("compass")
    if not want_sliders:
        hidden.add("sliders")
    if texts < n_text:
        hidden.add("text")

    left = dock.endswith("LEFT"); bottom = dock.startswith("BOTTOM")
    if plane_rect is not None:
        px0, py0, px1, py1 = plane_rect
        panel_xy = ((px0 + px1) / 2 - pw / 2, py0 - ph - 12 * s)
        compass_xy = (px0 - cw - 12 * s, (py0 + py1) / 2 - ch / 2)
    else:
        if want_compass and arrange == "side":
            gw, gh = pw + cw, max(ph, ch)
        elif want_compass:
            gw, gh = max(pw, cw), ph + ch
        else:
            gw, gh = pw, ph
        gx = vis[0] + m if left else vis[2] - m - gw
        gy = vis[1] + m if bottom else vis[3] - m - gh
        if not want_compass:
            panel_xy, compass_xy = (gx, gy), (gx, gy)
        elif arrange == "side":              # panel on the corner side, compass toward the middle
            px = gx if left else gx + cw
            cx = gx + pw if left else gx
            panel_xy = (px, gy if bottom else gy + gh - ph)
            compass_xy = (cx, gy if bottom else gy + gh - ch)
        else:                                # panel in the corner, compass stacked toward the middle
            px = gx if left else gx + gw - pw
            cx = gx if left else gx + gw - cw
            panel_xy = (px, gy) if bottom else (px, gy + ch)
            compass_xy = (cx, gy + ph) if bottom else (cx, gy)
    panel_xy = _clamp_block(panel_xy[0] + controls_offset[0], panel_xy[1] + controls_offset[1], pw, ph, vis)
    compass_xy = _clamp_block(compass_xy[0] + compass_offset[0], compass_xy[1] + compass_offset[1], cw, ch, vis)

    rects = {}
    x, y = panel_xy
    top = y + ph
    g = GRIP * s
    rects["grip_controls"] = (x, top - HEADER * s + (HEADER * s - g) / 2, x + g, top - (HEADER * s - g) / 2)
    pitch = BTN * s; r = BTN_R * s
    buttons = []
    row_top = top - HEADER * s
    line = 0
    for n_row in (n_row1, n_row2):
        for i in range(n_row):
            ln = line + i // cols
            bx = x + (i % cols + 0.5) * pitch
            by = row_top - (ln + 0.5) * pitch
            buttons.append((bx, by))
        line += -(-n_row // cols)
    for i, (bx, by) in enumerate(buttons):
        rects[f"button{i}"] = (bx - r, by - r, bx + r, by + r)
    cur = row_top - lines * pitch
    sliders = []
    if want_sliders:
        sw = SLIDER_W * s; sh = SLIDER_H * s
        for name in ("slider_frame", "slider_alpha"):
            sy = cur - (SLIDER_ROW * s + sh) / 2
            rects[name] = (x + PAD * s, sy, x + PAD * s + sw, sy + sh)
            lx = x + PAD * s + sw + 2 * PAD * s
            rects[name + "_label"] = (lx, sy, min(x + pw, lx + SLIDER_LABEL_W * s), sy + sh)
            sliders.append((x + PAD * s, sy, sw, sh))
            cur -= SLIDER_ROW * s
    text_lines = []
    if texts:
        for i in range(texts):
            ty = cur - (i + 1) * TEXT_LINE * s
            rects[f"text{i}"] = (x + PAD * s, ty, x + pw, ty + TEXT_LINE * s)
            text_lines.append((x + PAD * s, ty + 3 * s, pw - PAD * s))
    compass = None
    cr = COMPASS_R * s
    if want_compass:
        cx0, cy0 = compass_xy
        ccx, ccy = cx0 + cw / 2, cy0 + cw / 2
        compass = (ccx, ccy)
        ctop = cy0 + ch
        rects["grip_compass"] = (ccx - g / 2, ctop - HEADER * s + (HEADER * s - g) / 2, ccx + g / 2, ctop - (HEADER * s - g) / 2)
        rects["compass"] = (cx0, cy0, cx0 + cw, cy0 + cw)
        lr = cr + COMPASS_LABEL * s
        for d, entry in enumerate(UO_DIRS):
            ux, uy = entry[3]
            rects[f"compass_btn{d}"] = (ccx + ux * cr - r, ccy + uy * cr - r, ccx + ux * cr + r, ccy + uy * cr + r)
            rects[f"compass_label{d}"] = (ccx + ux * lr - 10 * s, ccy + uy * lr - 6 * s, ccx + ux * lr + 10 * s, ccy + uy * lr + 6 * s)
    eps = 1e-6
    for name, (x0, y0, x1, y1) in list(rects.items()):     # whatever still overflows a tiny viewport is not drawn
        if x0 < vis[0] - eps or y0 < vis[1] - eps or x1 > vis[2] + eps or y1 > vis[3] + eps:
            del rects[name]
            hidden.add(name)
    text_lines = [tl for i, tl in enumerate(text_lines) if f"text{i}" in rects]
    return {"s": s, "visible": vis, "rects": rects, "hidden": hidden, "buttons": buttons, "btn_r": r,
            "sliders": sliders, "text_lines": text_lines, "text_size": 12 * s, "label_size": 11 * s,
            "compass": compass, "cr": cr, "label_r": cr + COMPASS_LABEL * s, "grip": g}


def _plane_region_rect(context, obj):
    """Region-pixel bounding box of the plane (x0, y0, x1, y1) or None."""
    region, rv3d = context.region, context.region_data
    if region is None or rv3d is None:
        return None
    pts = []
    for co in obj.data.vertices:
        p2 = view3d_utils.location_3d_to_region_2d(region, rv3d, obj.matrix_world @ co.co)
        if p2 is None:
            return None
        pts.append(p2)
    xs = [p.x for p in pts]; ys = [p.y for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def region_insets(region, others):
    """(left, right, bottom, top) pixels of `region` covered by overlapping side regions (toolbar, N-panel,
    headers). `others` are objects with type/x/y/width/height; non-overlapping regions do not intersect."""
    l = r = b = t = 0
    rx0, ry0, rx1, ry1 = region.x, region.y, region.x + region.width, region.y + region.height
    for o in others:
        if o.type not in {"UI", "TOOLS", "HEADER", "TOOL_HEADER", "ASSET_SHELF", "ASSET_SHELF_HEADER"}:
            continue
        if o.width <= 1 or o.height <= 1:
            continue
        ox0, oy0, ox1, oy1 = o.x, o.y, o.x + o.width, o.y + o.height
        if ox1 <= rx0 or ox0 >= rx1 or oy1 <= ry0 or oy0 >= ry1:
            continue
        if o.type in {"UI", "TOOLS"}:
            if (ox0 + ox1) / 2 > (rx0 + rx1) / 2:
                r = max(r, rx1 - ox0)
            else:
                l = max(l, ox1 - rx0)
        else:
            if (oy0 + oy1) / 2 > (ry0 + ry1) / 2:
                t = max(t, ry1 - oy0)
            else:
                b = max(b, oy1 - ry0)
    return l, r, b, t


def _hud_layout(context, obj):
    """hud_layout for this viewport and sheet, from the object's HUD settings."""
    p = obj.spritemotion_sheet
    region = context.region
    others = [o for o in context.area.regions if o != region] if context.area else []
    plane = _plane_region_rect(context, obj) if p.hud_anchor == "PLANE" else None
    return hud_layout(region.width, region.height, insets=region_insets(region, others),
                      ui_scale=context.preferences.system.ui_scale, dock=p.hud_dock, margin=p.hud_margin,
                      controls_offset=tuple(p.hud_rows_offset), compass_offset=tuple(p.hud_compass_offset),
                      n_text=3 if _hud.get("skel_status") else 2, hud_scale=p.hud_scale, plane_rect=plane)


def _fit_text(font, text, max_w):
    """Trim text with an ellipsis so it is at most max_w pixels wide."""
    if max_w <= 0:
        return ""
    if blf.dimensions(font, text)[0] <= max_w:
        return text
    while text and blf.dimensions(font, text + "…")[0] > max_w:
        text = text[:-1]
    return text + "…" if text else ""


class SPRITEMOTION_GT_grip(bpy.types.Gizmo):
    """Drag handle: moves a 2-float target by the mouse delta (region pixels)."""
    bl_idname = "SPRITEMOTION_GT_grip"
    bl_target_properties = ({"id": "offset", "type": "FLOAT", "array_length": 2},)
    __slots__ = ("_start", "_init", "size")

    def draw(self, context):
        x, y = self.matrix_basis.translation.xy
        us = context.preferences.system.ui_scale
        g = getattr(self, "size", GRIP * us)
        gpu.state.blend_set("ALPHA")
        sh = gpu.shader.from_builtin("UNIFORM_COLOR")
        col = (0.6, 0.6, 0.6, 0.9) if (self.is_highlight or self.is_modal) else (0.3, 0.3, 0.3, 0.8)
        sh.uniform_float("color", col)
        batch_for_shader(sh, "TRI_FAN", {"pos": [(x, y), (x + g, y), (x + g, y + g), (x, y + g)]}).draw(sh)
        sh.uniform_float("color", (0.05, 0.05, 0.05, 0.9))
        dots = []
        for i in (0.3, 0.7):
            for j in (0.3, 0.7):
                dots.append((x + g * i, y + g * j))
        gpu.state.point_size_set(2.5 * us)
        ps = gpu.shader.from_builtin("UNIFORM_COLOR"); ps.uniform_float("color", (0.05, 0.05, 0.05, 1))
        batch_for_shader(ps, "POINTS", {"pos": dots}).draw(ps)
        gpu.state.blend_set("NONE")

    def test_select(self, context, location):
        x, y = self.matrix_basis.translation.xy
        g = getattr(self, "size", GRIP * context.preferences.system.ui_scale)
        mx, my = location
        return 0 if (x - 3 <= mx <= x + g + 3 and y - 3 <= my <= y + g + 3) else -1

    def invoke(self, context, event):
        self._start = (event.mouse_region_x, event.mouse_region_y)
        self._init = tuple(self.target_get_value("offset"))
        return {"RUNNING_MODAL"}

    def modal(self, context, event, tweak):
        dx = event.mouse_region_x - self._start[0]; dy = event.mouse_region_y - self._start[1]
        self.target_set_value("offset", (self._init[0] + dx, self._init[1] + dy))
        context.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def exit(self, context, cancel):
        if cancel:
            self.target_set_value("offset", self._init)


class SPRITEMOTION_GT_slider(bpy.types.Gizmo):
    """Flat horizontal slider in region pixels. matrix_basis.translation = left end; 'value' 0..1."""
    bl_idname = "SPRITEMOTION_GT_slider"
    bl_target_properties = ({"id": "value", "type": "FLOAT", "array_length": 1},)
    __slots__ = ("width", "height", "fill_color", "steps", "_drag")

    def _rect(self):
        x, y = self.matrix_basis.translation.xy
        w = getattr(self, "width", SLIDER_W); h = getattr(self, "height", SLIDER_H)
        return x, y, w, h

    def _draw_quad(self, sh, x0, y0, x1, y1, col):
        sh.uniform_float("color", col)
        batch_for_shader(sh, "TRI_FAN", {"pos": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]}).draw(sh)

    def draw(self, context):
        x, y, w, h = self._rect()
        v = max(0.0, min(1.0, self.target_get_value("value")))
        steps = getattr(self, "steps", 0)
        gpu.state.blend_set("ALPHA")
        sh = gpu.shader.from_builtin("UNIFORM_COLOR")
        self._draw_quad(sh, x - 2, y - 2, x + w + 2, y + h + 2, (0.05, 0.05, 0.05, 0.9))
        self._draw_quad(sh, x, y, x + w, y + h, (0.22, 0.22, 0.22, 0.95))
        fc = getattr(self, "fill_color", (0.9, 0.7, 0.1, 1.0))
        if self.is_highlight or self.is_modal:
            fc = (min(1, fc[0] + 0.15), min(1, fc[1] + 0.15), min(1, fc[2] + 0.15), 1.0)
        if steps > 1:            # discrete: fill the current cell
            cell = w / steps
            i = min(steps - 1, int(v * steps))
            self._draw_quad(sh, x + i * cell, y, x + (i + 1) * cell, y + h, fc)
            sh.uniform_float("color", (0.05, 0.05, 0.05, 0.8))
            ticks = []
            for k in range(1, steps):
                ticks += [(x + k * cell, y), (x + k * cell, y + h)]
            batch_for_shader(sh, "LINES", {"pos": ticks}).draw(sh)
        else:
            self._draw_quad(sh, x, y, x + w * v, y + h, fc)
            kx = x + w * v
            self._draw_quad(sh, kx - 3, y - 3, kx + 3, y + h + 3, (0.95, 0.95, 0.95, 1.0))
        gpu.state.blend_set("NONE")

    def test_select(self, context, location):
        x, y, w, h = self._rect()
        mx, my = location
        return 0 if (x - 4 <= mx <= x + w + 4 and y - 6 <= my <= y + h + 6) else -1

    def _apply(self, mx):
        x, y, w, h = self._rect()
        self.target_set_value("value", max(0.0, min(1.0, (mx - x) / w)))

    def invoke(self, context, event):
        self._apply(event.mouse_region_x)
        return {"RUNNING_MODAL"}

    def modal(self, context, event, tweak):
        self._apply(event.mouse_region_x)
        context.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def exit(self, context, cancel):
        pass


class SPRITEMOTION_GGT_sheet_hud(bpy.types.GizmoGroup):
    """Screen-space buttons docked in a viewport corner (or next to the plane): frame, action, opacity, views, model, compass. Positions come from hud_layout and are always inside the visible part of the region."""
    bl_idname = "SPRITEMOTION_GGT_sheet_hud"
    bl_label = "SpriteMotion sheet HUD"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"PERSISTENT", "SCALE"}

    @classmethod
    def poll(cls, context):
        return _active_sheet(context) is not None

    def _button(self, icon, op_id, **props):
        return self._button_impl(icon, op_id, **props)

    def _button_impl(self, icon, op_id, **props):
        b = self.gizmos.new("GIZMO_GT_button_2d")
        b.icon = icon
        b.draw_options = {"BACKDROP", "OUTLINE"}
        b.color = (0.15, 0.15, 0.15); b.alpha = 0.8; b.color_highlight = (0.45, 0.45, 0.45); b.alpha_highlight = 1
        b.scale_basis = 15
        op = b.target_set_operator(op_id)
        for k, v in props.items():
            setattr(op, k, v)
        return b

    def setup(self, context):
        s = lambda icon, what, delta=1: self._button(icon, "spritemotion.sheet_step", what=what, delta=delta)
        # row 1: frame < >, action << >>, opacity - +, front/back, mirror
        self.row1 = [s("TRIA_LEFT", "FRAME", -1), s("TRIA_RIGHT", "FRAME", 1),
                     s("REW", "ACTION", -1), s("FF", "ACTION", 1),
                     s("HIDE_ON", "ALPHA", -1), s("HIDE_OFF", "ALPHA", 1),
                     s("XRAY", "FRONT"), s("MOD_MIRROR", "MIRROR"), self._button("PLAY", "spritemotion.sheet_play")]
        # row 2: view mode, model display, bones, overlay, side panel, grid
        self.row2 = [s("SHADING_RENDERED", "VIEW"), s("OUTLINER_OB_ARMATURE", "MODEL"), s("BONE_DATA", "BONES"),
                     s("IMAGE_PLANE", "OVERLAY"), s("DUPLICATE", "SIDE"), s("GRID", "GRID"),
                     s("CURVE_PATH", "RAY"), s("ACTION", "SYNC"), s("WORLD", "LAND"), s("OUTLINER_OB_LIGHT", "PROPS"),
                     s("MOD_SHRINKWRAP", "DECAL"), s("ARMATURE_DATA", "SKEL"), s("DRIVER_DISTANCE", "RIGERR"),
                     self._button("FILE_FOLDER", "spritemotion.sheet_open_dir")]
        self.compass = [self._button("RADIOBUT_OFF", "spritemotion.sheet_set_dir", uo_dir=d) for d in range(8)]
        obj = _active_sheet(context)
        self.s_alpha = self.gizmos.new("SPRITEMOTION_GT_slider")
        self.s_alpha.fill_color = (0.3, 0.7, 1.0, 1.0); self.s_alpha.steps = 0
        self.s_alpha.target_set_prop("value", obj.spritemotion_sheet, "alpha")
        self.s_frame = self.gizmos.new("SPRITEMOTION_GT_slider")
        self.s_frame.fill_color = (0.9, 0.7, 0.1, 1.0)
        self.s_frame.target_set_prop("value", obj.spritemotion_sheet, "frame_t")
        for g in (self.s_alpha, self.s_frame):
            g.use_draw_modal = True
        self.grip_compass = self.gizmos.new("SPRITEMOTION_GT_grip")
        self.grip_rows = self.gizmos.new("SPRITEMOTION_GT_grip")
        for g in (self.grip_compass, self.grip_rows):
            g.use_draw_modal = True

    def draw_prepare(self, context):
        obj = _active_sheet(context)
        if obj is None or context.region is None:
            return
        p = obj.spritemotion_sheet
        lay = _hud_layout(context, obj)
        _hud["layout"] = lay
        rects, s = lay["rects"], lay["s"]
        self.grip_compass.target_set_prop("offset", p, "hud_compass_offset")
        self.grip_rows.target_set_prop("offset", p, "hud_rows_offset")
        for g, name in ((self.grip_rows, "grip_controls"), (self.grip_compass, "grip_compass")):
            g.hide = name not in rects
            if name in rects:
                g.size = lay["grip"]
                g.matrix_basis = Matrix.Translation((rects[name][0], rects[name][1], 0))
        self.s_alpha.target_set_prop("value", p, "alpha")
        self.s_frame.target_set_prop("value", p, "frame_t")
        self.s_frame.steps = _frame_count(p)
        for g, name in ((self.s_frame, "slider_frame"), (self.s_alpha, "slider_alpha")):
            g.hide = name not in rects
            if name in rects:
                x0, y0, x1, y1 = rects[name]
                g.width = x1 - x0; g.height = y1 - y0
                g.matrix_basis = Matrix.Translation((x0, y0, 0))
        basis = BTN_R * s
        for i, b in enumerate(self.row1 + self.row2):
            rect = rects.get(f"button{i}")
            b.hide = rect is None
            b.scale_basis = basis
            if rect:
                b.matrix_basis = Matrix.Translation(((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2, 0))
        on = (0.9, 0.7, 0.1); off = (0.15, 0.15, 0.15)
        self.row2[2].color = on if p.show_bones else off
        self.row2[3].color = on if p.show_overlay else off
        self.row2[4].color = on if p.side_panel else off
        self.row2[5].color = on if p.show_grid else off
        self.row2[6].color = on if p.show_pivot_ray else off
        self.row2[7].color = on if p.sync_model_action else off
        self.row2[8].color = on if p.show_land else off
        self.row2[9].color = on if p.show_props else off
        self.row2[10].color = on if p.show_decal else off
        self.row2[11].color = on if p.show_skeleton else off
        self.row2[12].color = on if p.show_rig_error else off
        self.row1[7].color = on if p.mirror else off
        playing = context.screen.is_animation_playing
        self.row1[8].icon = "PAUSE" if playing else "PLAY"
        self.row1[8].color = (0.2, 0.8, 0.3) if playing else off
        for d, b in enumerate(self.compass):
            rect = rects.get(f"compass_btn{d}")
            b.hide = rect is None
            b.scale_basis = basis
            if rect:
                b.matrix_basis = Matrix.Translation(((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2, 0))
            b.icon = "RADIOBUT_ON" if p.uo_dir == d else "RADIOBUT_OFF"
            b.color = on if p.uo_dir == d else off


def _draw_hud():
    ctx = bpy.context
    obj = _active_sheet(ctx)
    if obj is None or ctx.region is None or ctx.area is None or ctx.area.type != "VIEW_3D" or ctx.region.type != "WINDOW":
        return
    lay = _hud.get("layout")
    if lay is None:
        return
    rects = lay["rects"]
    p = obj.spritemotion_sheet
    font = 0
    blf.enable(font, blf.SHADOW); blf.shadow(font, 3, 0, 0, 0, 0.9); blf.shadow_offset(font, 1, -1)
    blf.color(font, 1, 1, 1, 1)
    blf.size(font, lay["label_size"])
    for d, entry in enumerate(UO_DIRS):
        rect = rects.get(f"compass_label{d}")
        if rect is None:
            continue
        tw, th = blf.dimensions(font, entry[0])
        blf.position(font, (rect[0] + rect[2] - tw) / 2, (rect[1] + rect[3] - th) / 2, 0)
        blf.draw(font, entry[0])
    data = load_sheet(p)
    n = len(frames_for(data, p.direction)) if data else 0
    for name, text in (("slider_frame_label", f"frame {p.frame % max(n, 1) + 1}/{n}"),
                       ("slider_alpha_label", f"opacity {p.alpha:.2f}")):
        rect = rects.get(name)
        if rect:
            blf.position(font, rect[0], rect[1] + 2 * lay["s"], 0)
            blf.draw(font, _fit_text(font, text, rect[2] - rect[0]))
    blf.size(font, lay["text_size"])
    lines = [
        f"facing {UO_DIRS[p.uo_dir][0]} (stored {p.direction}{', mirrored' if p.mirror else ''})   "
        f"view {p.view_mode.lower()}   model {p.model_display.lower()}{'   bones' if p.show_bones else ''}",
        f"{action_name(p) or 'action'} ({p.action})   frame {p.frame % max(n, 1) + 1}/{n}   "
        f"opacity {p.alpha:.2f}   {'front' if p.in_front else 'behind'}",
    ]
    if _hud.get("skel_status"):
        lines.insert(0, _hud["skel_status"])
    for (tx, ty, tw), line in zip(lay["text_lines"], lines):
        blf.position(font, tx, ty, 0)
        blf.draw(font, _fit_text(font, line, tw))
    blf.disable(font, blf.SHADOW)


def _frame_px_to_world(obj, props, data, px, py):
    """Frame pixel (x right, y down, from the frame's top-left) -> world point on the plane."""
    frames = frames_for(data, props.direction)
    fr = frames[props.frame % len(frames)]
    w, h = fr["frame"]["w"], fr["frame"]["h"]
    if props.mirror:
        px = w - px
    return obj.matrix_world @ Vector((px / w - 0.5, 0.5 - py / h, 0))


def _world_to_frame_px(obj, props, data, pt, fwd):
    """World point -> frame pixel, by projecting it along the view direction onto the plane."""
    frames = frames_for(data, props.direction)
    fr = frames[props.frame % len(frames)]
    w, h = fr["frame"]["w"], fr["frame"]["h"]
    mi = obj.matrix_world.inverted()
    lp = mi @ pt; ld = (mi.to_3x3() @ fwd)
    if abs(ld.z) > 1e-9:
        lp = lp - ld * (lp.z / ld.z)
    px = (lp.x + 0.5) * w; py = (0.5 - lp.y) * h
    if props.mirror:
        px = w - px
    return px, py


def rig_errors(obj, p, cam):
    """[(joint, sprite_px, rig_px)] for the current frame, or []."""
    sk, f = skeleton_frame(p)
    data = load_sheet(p)
    arm = _model_armature(p)
    if f is None or data is None or arm is None:
        return []
    fwd = (cam.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()
    out = []
    for name, (sx, sy) in f["joints"].items():
        rj = rig_joint_world(arm, name, p.uo_dir)
        if rj is None:
            continue
        out.append((name, (sx, sy), _world_to_frame_px(obj, p, data, rj, fwd)))
    return out


class SPRITEMOTION_OT_fit_model(bpy.types.Operator):
    bl_idname = "spritemotion.fit_model"
    bl_label = "Fit model to sprite"
    bl_description = "Search yaw, uniform scale and screen offset of the model that minimise the mean joint error " \
                     "against this frame's authored skeleton (needs the _skeleton.json)"
    bl_options = {"REGISTER", "UNDO"}
    fit_yaw: bpy.props.BoolProperty(name="Yaw", default=True)
    fit_scale: bpy.props.BoolProperty(name="Scale", default=True)
    fit_offset: bpy.props.BoolProperty(name="Offset", default=True)

    def execute(self, context):
        obj = _active_sheet(context)
        if obj is None:
            return {"CANCELLED"}
        p = obj.spritemotion_sheet
        cam = context.scene.camera
        model = p.model
        if model is None or cam is None or not rig_errors(obj, p, cam):
            self.report({"WARNING"}, "no skeleton for this frame or no model")
            return {"CANCELLED"}
        r3 = cam.matrix_world.to_3x3()
        right = (r3 @ Vector((1, 0, 0))).normalized(); up = (r3 @ Vector((0, 1, 0))).normalized()
        px_x, px_y = camera_px(cam)
        base_yaw = p.model_yaw_offset; base_scale = model.scale.copy(); base_loc = model.location.copy()

        def evaluate():
            context.view_layer.update()
            errs = rig_errors(obj, p, cam)
            offsets = np.array([(s[0] - r[0], s[1] - r[1]) for _, s, r in errs])
            centre = offsets.mean(axis=0)
            # Geometric median minimizes the reported mean Euclidean error;
            # an arithmetic mean minimizes squared error and can make this worse.
            for _ in range(64):
                weights = 1.0 / np.maximum(np.linalg.norm(offsets - centre, axis=1), 1e-6)
                next_centre = np.average(offsets, axis=0, weights=weights)
                if np.linalg.norm(next_centre - centre) < 1e-6:
                    centre = next_centre
                    break
                centre = next_centre
            dx, dy = centre
            if not self.fit_offset:
                dx = dy = 0.0
            res = sum(math.hypot(s[0] - r[0] - dx, s[1] - r[1] - dy) for _, s, r in errs) / len(errs)
            return res, dx, dy

        best = None
        yaws = [base_yaw + math.radians(d) for d in range(-40, 41, 5)] if self.fit_yaw else [base_yaw]
        scales = [0.80 + 0.025 * i for i in range(21)] if self.fit_scale else [1.0]
        for yaw in yaws:
            for sc in scales:
                p.model_yaw_offset = yaw
                model.scale = base_scale * sc
                model.rotation_euler.z = _model_yaw(p)
                res, dx, dy = evaluate()
                if best is None or res < best[0]:
                    best = (res, yaw, sc, dx, dy)
        res, yaw, sc, dx, dy = best
        p.model_yaw_offset = yaw
        model.scale = base_scale * sc
        # screen offset: +x right, +y down in frame pixels -> a move ON THE GROUND (feet stay at z),
        # right along the camera's right, down = toward the camera along the ground (1 ground unit = sin(elevation)
        # camera-vertical units: 1/sqrt2 for the ground-grid camera)
        fwd = (r3 @ Vector((0, 0, -1))).normalized(); sin_elev = max(1e-6, -fwd.z)
        fwd.z = 0; fwd.normalize()
        # rig_errors returns unmirrored source-sheet coordinates. Convert the
        # horizontal correction back to displayed pixels before moving the rig.
        screen_dx = -dx if p.mirror else dx
        model.location = base_loc + right * (screen_dx / px_x) - fwd * (dy / (px_y * sin_elev))
        apply_sheet(obj)
        self.report({"INFO"}, f"mean error {res:.2f} px  yaw {math.degrees(yaw):+.0f}  scale x{sc:.3f}  offset ({dx:+.1f},{dy:+.1f}) px")
        return {"FINISHED"}


def _draw_skeleton(ctx, obj, p, cam, sh):
    sk, f = skeleton_frame(p)
    data = load_sheet(p)
    if f is None or data is None:
        _hud["skel_status"] = "" if sk else "no skeleton json for this action"
        return
    joints = {k: _frame_px_to_world(obj, p, data, v[0], v[1]) for k, v in f["joints"].items()}
    if p.show_skeleton:
        lines = []
        for a, b in sk["bones"]:
            if a in joints and b in joints:
                lines += [joints[a], joints[b]]
        sh.uniform_float("lineWidth", 2.0); sh.uniform_float("color", (1.0, 0.15, 0.1, 0.95))
        batch_for_shader(sh, "LINES", {"pos": lines}).draw(sh)
        ps = gpu.shader.from_builtin("UNIFORM_COLOR")
        gpu.state.point_size_set(7); ps.uniform_float("color", (0.15, 0.45, 1.0, 1.0))
        batch_for_shader(ps, "POINTS", {"pos": list(joints.values())}).draw(ps)
    if not p.show_rig_error:
        return
    arm = _model_armature(p)
    if arm is None:
        return
    fwd = (cam.matrix_world.to_3x3() @ Vector((0, 0, -1))).normalized()
    dg = ctx.evaluated_depsgraph_get()
    err_lines, hits, tot, cnt, worst = [], [], 0.0, 0, ("", 0.0)
    for name, wp in joints.items():
        rj = rig_joint_world(arm, name, p.uo_dir)
        if rj is None:
            continue
        # rig joint projected onto the plane along the view direction
        d = (rj - wp).dot(fwd)
        rj_on_plane = rj - fwd * d
        err_lines += [wp, rj_on_plane]
        ex, ey = _world_to_frame_px(obj, p, data, rj, fwd)
        sx, sy = f["joints"][name]
        e = math.hypot(ex - sx, ey - sy); tot += e; cnt += 1
        if e > worst[1]:
            worst = (name, e)
        # raycast from the plane point along the view direction onto the model (skipping sheet helper objects)
        start = wp + fwd * 0.01
        for _ in range(6):
            ok, loc, nrm, idx, hob, mat = ctx.scene.ray_cast(dg, start, fwd, distance=100.0)
            if not ok:
                break
            if hob == p.model or hob.parent == p.model:
                hits.append(loc)
                break
            start = loc + fwd * 0.01
    if err_lines:
        sh.uniform_float("lineWidth", 1.5); sh.uniform_float("color", (1.0, 1.0, 0.2, 0.9))
        batch_for_shader(sh, "LINES", {"pos": err_lines}).draw(sh)
    if hits:
        ps = gpu.shader.from_builtin("UNIFORM_COLOR")
        gpu.state.point_size_set(6); ps.uniform_float("color", (0.2, 1.0, 1.0, 1.0))
        batch_for_shader(ps, "POINTS", {"pos": hits}).draw(ps)
    _hud["skel_status"] = f"rig error {tot / cnt:.1f} px mean, worst {worst[0]} {worst[1]:.1f} px, {len(hits)}/{cnt} joints hit the mesh" if cnt else ""


def _draw_bones():
    """Pivot ray (anchor to camera) and pose bones as lines plus joint dots, depth test off so they show through the plane."""
    ctx = bpy.context
    obj = _active_sheet(ctx)
    if obj is None or ctx.region is None or ctx.region.type != "WINDOW":
        return
    p = obj.spritemotion_sheet
    region = ctx.region
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("NONE")
    sh = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    sh.uniform_float("viewportSize", (region.width, region.height))
    cam = ctx.scene.camera
    if p.show_pivot_ray and cam is not None:
        # anchor -> camera: the sight line through the sprite's pivot pixel; a cross where it meets the plane
        a = p.anchor.matrix_world.translation if p.anchor else Vector((0, 0, 0))
        c = cam.matrix_world.translation
        r3 = cam.matrix_world.to_3x3()
        right = (r3 @ Vector((1, 0, 0))).normalized(); up = (r3 @ Vector((0, 1, 0))).normalized()
        d = (c - a).normalized()
        hit = a + d * (obj.matrix_world.translation - a).dot(d)
        k = 0.25
        sh.uniform_float("lineWidth", 1.5)
        sh.uniform_float("color", (1.0, 0.2, 0.9, 0.9))
        batch_for_shader(sh, "LINES", {"pos": [a, c, hit - right * k, hit + right * k, hit - up * k, hit + up * k,
                                               a + Vector((-0.5, 0, 0)), a + Vector((0.5, 0, 0)),
                                               a + Vector((0, -0.5, 0)), a + Vector((0, 0.5, 0))]}).draw(sh)
    if cam is not None and (p.show_skeleton or p.show_rig_error):
        _draw_skeleton(ctx, obj, p, cam, sh)
    if p.show_decal and cam is not None:
        dec = bpy.data.objects.get(obj.name + "_decal")
        if dec is not None:
            edges = []
            for i, co in enumerate(((-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0))):
                edges += [obj.matrix_world @ Vector(co), dec.data.vertices[i].co.copy()]
            sh.uniform_float("lineWidth", 1.0)
            sh.uniform_float("color", (1.0, 0.85, 0.2, 0.6))
            batch_for_shader(sh, "LINES", {"pos": edges}).draw(sh)
    arm = _model_armature(p) if p.show_bones else None
    if arm is None:
        gpu.state.depth_test_set("LESS_EQUAL"); gpu.state.blend_set("NONE")
        return
    mw = arm.matrix_world
    lines, joints = [], []
    for pb in arm.pose.bones:
        head = mw @ pb.head; tail = mw @ pb.tail
        if (tail - head).length < 1e-5:
            continue
        lines += [head, tail]
        joints.append(head)
        if pb.parent is not None and (mw @ pb.parent.tail - head).length > 1e-4:
            lines += [mw @ pb.parent.tail, head]     # dotted-style connector drawn solid: shows the gap to the parent
    col = tuple(p.bone_color)
    if not lines:
        gpu.state.depth_test_set("LESS_EQUAL"); gpu.state.blend_set("NONE")
        return
    sh.uniform_float("lineWidth", p.bone_width)
    sh.uniform_float("color", col)
    batch_for_shader(sh, "LINES", {"pos": lines}).draw(sh)
    ps = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.point_size_set(p.bone_width * 3)
    ps.uniform_float("color", (col[0] * 0.6 + 0.4, col[1] * 0.6 + 0.4, col[2] * 0.6 + 0.4, col[3]))
    batch_for_shader(ps, "POINTS", {"pos": joints}).draw(ps)
    gpu.state.depth_test_set("LESS_EQUAL")
    gpu.state.blend_set("NONE")


@bpy.app.handlers.persistent
def _frame_change(scene):
    if _render_state["busy"]:   # the frame renderer owns the model's action and turn while it runs
        return
    for o in scene.objects:
        p = o.spritemotion_sheet
        if p.enabled and p.follow_timeline:
            data = load_sheet(p)
            if data is None:
                continue
            n = len(frames_for(data, p.direction)) or 1
            f = timeline_sprite_frame(scene.frame_current, scene.frame_start, p.hold, n)
            if f != p.frame:
                # Avoid a property callback seeking the timeline recursively.
                p["frame"] = f
                p["frame_t"] = (f + 0.5) / n
                apply_sheet(o, scene)
                _redraw(p, bpy.context)


classes = (SPRITEMOTION_OT_import_uo_sheet, SpriteMotionSheetProps, SPRITEMOTION_OT_sheet_add, SPRITEMOTION_OT_sheet_step, SPRITEMOTION_OT_sheet_set_dir, SPRITEMOTION_OT_sheet_refresh, SPRITEMOTION_OT_stage_props,
           SPRITEMOTION_OT_sheet_open_dir, SPRITEMOTION_OT_retime_action, SPRITEMOTION_OT_pose_interpolation, SPRITEMOTION_OT_hud_reset, SPRITEMOTION_OT_make_actions, SPRITEMOTION_OT_fit_model, SPRITEMOTION_GT_grip,
           SPRITEMOTION_OT_sheet_play, SpriteMotionRenderProps, SPRITEMOTION_OT_uo_camera, SPRITEMOTION_OT_render_frames,
           SPRITEMOTION_PT_sheet, SPRITEMOTION_PT_render, SPRITEMOTION_GT_slider, SPRITEMOTION_GGT_sheet_hud)
_hud_handle = None
_bone_handle = None


def register():
    global _hud_handle, _bone_handle
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Object.spritemotion_sheet = bpy.props.PointerProperty(type=SpriteMotionSheetProps)
    bpy.types.Scene.spritemotion_render = bpy.props.PointerProperty(type=SpriteMotionRenderProps)
    if _frame_change not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(_frame_change)
    _hud_handle = bpy.types.SpaceView3D.draw_handler_add(_draw_hud, (), "WINDOW", "POST_PIXEL")
    _bone_handle = bpy.types.SpaceView3D.draw_handler_add(_draw_bones, (), "WINDOW", "POST_VIEW")


def unregister():
    global _hud_handle, _bone_handle
    for h in (_hud_handle, _bone_handle):
        if h is not None:
            bpy.types.SpaceView3D.draw_handler_remove(h, "WINDOW")
    _hud_handle = _bone_handle = None
    if _frame_change in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(_frame_change)
    del bpy.types.Object.spritemotion_sheet
    del bpy.types.Scene.spritemotion_render
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
    import sys
    _argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--render-uo-frames" in _argv:
        sys.exit(_cli_render(_argv))

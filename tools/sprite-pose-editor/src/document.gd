extends RefCounted
## Editable poses for one sequence of a dataset.
##
## Layers: `baseline` holds the estimate layer (never modified); `poses` holds
## the working effective pose for every manifest frame (correction, else
## estimate, else a default layout). Saving writes only meaningful corrections.

signal changed

const REVIEW_STATES := ["unreviewed", "in_progress", "approved", "rejected"]
const VISIBILITY := ["visible", "occluded", "outside", "unknown"]

var dataset                           # dataset.gd instance
var sequence_id: String = ""
var baseline: Dictionary = {}         # key -> estimate pose (read-only)
var poses: Dictionary = {}            # key -> working pose
var origin: Dictionary = {}           # key -> "correction" | "estimate" | "default"
var undo_stack: Array = []
var redo_stack: Array = []
var pending: Dictionary = {}
var dirty: bool = false
var last_error: String = ""
var layer_meta: Dictionary = {}       # limb_identity / notes carried from the estimate layer


static func key(direction: int, frame: int) -> String:
	return "%d:%d" % [direction, frame]


## Opens a sequence: loads its estimate layer (optional) and builds working poses.
func open(source_dataset, sequence: String) -> bool:
	dataset = source_dataset
	sequence_id = sequence
	if dataset.sequence(sequence).is_empty():
		last_error = "Unknown sequence " + sequence
		return false
	baseline.clear()
	layer_meta.clear()
	var estimate_path: String = dataset.annotation_path("estimate", sequence)
	if FileAccess.file_exists(estimate_path):
		var value: Variant = read_json(estimate_path)
		if value == null or not validate(value, "estimate"):
			last_error = "Estimates: " + last_error
			return false
		for field in ["limb_identity", "notes"]:
			if value.has(field):
				layer_meta[field] = value[field]
		for pose in value.poses:
			baseline[key(int(pose.direction), int(pose.frame))] = _normalized(pose)
	_rebuild({})
	return true


func _rebuild(corrections: Dictionary) -> void:
	poses.clear()
	origin.clear()
	for record in dataset.sequence(sequence_id).frames:
		var k := key(int(record.direction), int(record.frame))
		if corrections.has(k):
			poses[k] = corrections[k].duplicate(true)
			origin[k] = "correction"
		elif baseline.has(k):
			poses[k] = baseline[k].duplicate(true)
			origin[k] = "estimate"
		else:
			poses[k] = default_pose(record)
			origin[k] = "default"
	undo_stack.clear()
	redo_stack.clear()
	pending.clear()
	dirty = false


## Joints spread along the vertical centre line of the sprite's opaque bounds.
func default_pose(record: Dictionary) -> Dictionary:
	var bounds: Rect2 = dataset.bounds_for(record)
	var names: Array = dataset.joint_names()
	var joints := {}
	for i in range(names.size()):
		var t := 0.5 if names.size() == 1 else float(i) / float(names.size() - 1)
		var p := Vector2(bounds.get_center().x, bounds.position.y + t * maxf(bounds.size.y - 1, 0))
		p = p.clamp(Vector2.ZERO, dataset.max_point())
		joints[names[i]] = {"x": p.x, "y": p.y, "confidence": 0.0, "visibility": "unknown", "status": "estimate"}
	return {
		"frame_id": String(record.frame_id), "direction": int(record.direction), "frame": int(record.frame),
		"source_fingerprint": String(record.get("fingerprint", "")),
		"provenance": {"method": "manual", "independent": true, "detail": "Default layout; no estimate available."},
		"review": {"status": "unreviewed"}, "joints": joints,
	}


func _normalized(pose: Dictionary) -> Dictionary:
	var result := pose.duplicate(true)
	result.direction = int(result.direction)
	result.frame = int(result.frame)
	if result.has("provenance") and result.provenance.has("mirrored_from"):
		result.provenance.mirrored_from = int(result.provenance.mirrored_from)
	if not result.has("review"):
		result["review"] = {"status": "unreviewed"}
	return result


## Reads and parses JSON, setting last_error on failure.
func read_json(path: String) -> Variant:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		last_error = "Cannot read " + path
		return null
	var parser := JSON.new()
	if parser.parse(file.get_as_text()) != OK:
		last_error = "Invalid JSON in %s (line %d)" % [path.get_file(), parser.get_error_line()]
		return null
	return parser.data


static func _is_int(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) == floor(float(value))


## Checks an annotation layer against this dataset, sequence and skeleton.
func validate(value: Variant, layer: String) -> bool:
	if not value is Dictionary or value.get("schema") != "spritemotion.pose-annotations":
		last_error = "Not a SpriteMotion pose-annotations file."
		return false
	if value.get("layer") != layer:
		last_error = "Expected a '%s' layer, found '%s'." % [layer, str(value.get("layer"))]
		return false
	if value.get("sequence") != sequence_id:
		last_error = "These annotations are for sequence '%s'; select it before loading." % str(value.get("sequence"))
		return false
	if value.get("dataset_id") != dataset.data.dataset_id:
		last_error = "These annotations belong to dataset '%s'." % str(value.get("dataset_id"))
		return false
	if not value.get("poses") is Array:
		last_error = "Annotations need a poses array."
		return false
	var names := {}
	for name in dataset.joint_names():
		names[name] = true
	var limit: Vector2 = dataset.max_point()
	var seen := {}
	for pose in value.poses:
		if not pose is Dictionary or not _is_int(pose.get("direction")) or not _is_int(pose.get("frame")):
			last_error = "Pose direction and frame must be integers."
			return false
		var d := int(pose.direction)
		var f := int(pose.frame)
		if not dataset.has_frame(sequence_id, d, f):
			last_error = "Pose %d:%d is not a frame of this sequence." % [d, f]
			return false
		var k := key(d, f)
		if seen.has(k):
			last_error = "Duplicate pose %s." % k
			return false
		seen[k] = true
		if not pose.get("frame_id") is String or not pose.get("source_fingerprint") is String:
			last_error = "Pose %s needs frame_id and source_fingerprint." % k
			return false
		if pose.has("review"):
			var review: Variant = pose.review
			if not review is Dictionary or not REVIEW_STATES.has(review.get("status")):
				last_error = "Pose %s has an invalid review status." % k
				return false
			if review.has("notes") and not review.notes is String:
				last_error = "Pose notes must be text."
				return false
		var joints: Variant = pose.get("joints")
		if not joints is Dictionary:
			last_error = "Pose %s needs a joints object." % k
			return false
		for name in names:
			if not joints.has(name):
				last_error = "Pose %s is missing joint %s." % [k, name]
				return false
		for name in joints:
			if not names.has(name):
				last_error = "Pose %s has unknown joint %s." % [k, name]
				return false
			var joint: Variant = joints[name]
			if not joint is Dictionary:
				last_error = "Joint %s must be an object." % name
				return false
			for axis in ["x", "y"]:
				var coord: Variant = joint.get(axis)
				if not (coord is float or coord is int) or not is_finite(float(coord)):
					last_error = "Joint coordinates must be finite numbers."
					return false
			if float(joint.x) < 0 or float(joint.y) < 0 or float(joint.x) > limit.x + 0.0001 or float(joint.y) > limit.y + 0.0001:
				last_error = "Joint %s of pose %s is outside the canvas." % [name, k]
				return false
			if joint.has("visibility") and not VISIBILITY.has(joint.visibility):
				last_error = "Joint %s has an invalid visibility." % name
				return false
	return true


## Loads a correction layer on top of the baseline. The document is unchanged on failure.
func load_corrections(path: String) -> bool:
	var value: Variant = read_json(path)
	if value == null or not validate(value, "correction"):
		return false
	var corrections := {}
	for pose in value.poses:
		corrections[key(int(pose.direction), int(pose.frame))] = _normalized(pose)
	_rebuild(corrections)
	changed.emit()
	return true


func has_pose(direction: int, frame: int) -> bool:
	return poses.has(key(direction, frame))


func pose(direction: int, frame: int) -> Dictionary:
	return poses.get(key(direction, frame), {})


func baseline_pose(direction: int, frame: int) -> Dictionary:
	return baseline.get(key(direction, frame), {})


func joint(direction: int, frame: int, name: String) -> Dictionary:
	return pose(direction, frame).get("joints", {}).get(name, {})


func point(direction: int, frame: int, name: String) -> Vector2:
	var item := joint(direction, frame, name)
	return Vector2(float(item.get("x", 0)), float(item.get("y", 0)))


func review_status(direction: int, frame: int) -> String:
	return String(pose(direction, frame).get("review", {}).get("status", "unreviewed"))


func is_approved(direction: int, frame: int) -> bool:
	return review_status(direction, frame) == "approved"


func approved_count() -> int:
	var count := 0
	for k in poses:
		if String(poses[k].get("review", {}).get("status", "")) == "approved":
			count += 1
	return count


## True when the stored annotation was made for different pixels than the manifest frame.
func fingerprint_mismatch(direction: int, frame: int) -> bool:
	var record: Dictionary = dataset.frame(sequence_id, direction, frame)
	var stored := String(pose(direction, frame).get("source_fingerprint", ""))
	return not record.is_empty() and stored != String(record.get("fingerprint", ""))


## Starts one undoable operation touching a pose (and its mirror partner when linked).
func begin_edit(direction: int, frame: int, link: bool = false) -> void:
	if not pending.is_empty():
		commit_edit()
	var keys := [key(direction, frame)]
	var partner: int = dataset.mirror_of(direction)
	if link and partner >= 0 and has_pose(partner, frame):
		keys.append(key(partner, frame))
	pending = {"keys": keys, "before": []}
	for k in keys:
		pending.before.append(poses[k].duplicate(true))


func _touch(p: Dictionary, status: String) -> void:
	p.review["status"] = status
	p.review["updated_at"] = Time.get_datetime_string_from_system(true) + "Z"


## Moves a joint (clamped to the canvas). Clears approval; optionally mirrors into the partner view.
func move_joint(direction: int, frame: int, name: String, position: Vector2, link: bool = false) -> void:
	var item := joint(direction, frame, name)
	if item.is_empty():
		return
	position = position.clamp(Vector2.ZERO, dataset.max_point())
	if Vector2(float(item.x), float(item.y)).is_equal_approx(position):
		return
	item.x = position.x
	item.y = position.y
	item["status"] = "corrected"
	_touch(pose(direction, frame), "in_progress")
	var partner: int = dataset.mirror_of(direction)
	if link and partner >= 0 and has_pose(partner, frame):
		var other := joint(partner, frame, name)
		other.x = clampf(dataset.mirror_x(position.x), 0, dataset.max_point().x)
		other.y = position.y
		other["status"] = "mirrored_correction"
		_touch(pose(partner, frame), "in_progress")
	changed.emit()


## Finishes the pending operation; returns true when something actually changed.
func commit_edit() -> bool:
	if pending.is_empty():
		return false
	var after := []
	for k in pending.keys:
		after.append(poses[k].duplicate(true))
	if JSON.stringify(after) == JSON.stringify(pending.before):
		pending.clear()
		return false
	pending["after"] = after
	undo_stack.append(pending.duplicate(true))
	if undo_stack.size() > 200:
		undo_stack.pop_front()
	redo_stack.clear()
	pending.clear()
	dirty = true
	changed.emit()
	return true


## Sets approval explicitly (approved, or back to in_progress).
func set_approved(direction: int, frame: int, approved: bool) -> void:
	begin_edit(direction, frame)
	_touch(pose(direction, frame), "approved" if approved else "in_progress")
	commit_edit()


## Replaces a pose's notes as one undoable edit.
func set_notes(direction: int, frame: int, text: String) -> void:
	begin_edit(direction, frame)
	pose(direction, frame).review["notes"] = text
	commit_edit()


## Restores a pose to its estimate (or default layout) as one undoable edit.
func reset_pose(direction: int, frame: int) -> void:
	var k := key(direction, frame)
	begin_edit(direction, frame)
	if baseline.has(k):
		poses[k] = baseline[k].duplicate(true)
	else:
		poses[k] = default_pose(dataset.frame(sequence_id, direction, frame))
	commit_edit()


func undo() -> bool:
	if undo_stack.is_empty():
		return false
	var operation: Dictionary = undo_stack.pop_back()
	for n in range(operation.keys.size()):
		poses[operation.keys[n]] = operation.before[n].duplicate(true)
	redo_stack.append(operation)
	dirty = true
	changed.emit()
	return true


func redo() -> bool:
	if redo_stack.is_empty():
		return false
	var operation: Dictionary = redo_stack.pop_back()
	for n in range(operation.keys.size()):
		poses[operation.keys[n]] = operation.after[n].duplicate(true)
	undo_stack.append(operation)
	dirty = true
	changed.emit()
	return true


func _joints_differ(a: Dictionary, b: Dictionary) -> bool:
	if a.size() != b.size():
		return true
	for name in a:
		if not b.has(name):
			return true
		if absf(float(a[name].x) - float(b[name].x)) > 0.0001 or absf(float(a[name].y) - float(b[name].y)) > 0.0001:
			return true
	return false


## Worth saving: moved joints vs the estimate, a review decision, or notes.
func is_meaningful(direction: int, frame: int) -> bool:
	var p := pose(direction, frame)
	var review: Dictionary = p.get("review", {})
	if String(review.get("status", "unreviewed")) != "unreviewed" or not String(review.get("notes", "")).strip_edges().is_empty():
		return true
	var base := baseline_pose(direction, frame)
	if base.is_empty():
		# No estimate: compare with the generated default layout so untouched frames are not saved.
		base = default_pose(dataset.frame(sequence_id, direction, frame))
	return _joints_differ(p.joints, base.joints)


## Provenance of a pose as a correction (never claims independence it does not have).
func correction_provenance(direction: int, frame: int) -> Dictionary:
	var p := pose(direction, frame)
	var base := baseline_pose(direction, frame)
	var source: Dictionary = base.get("provenance", {}) if not base.is_empty() else p.get("provenance", {})
	var method := String(source.get("method", "manual"))
	var result := {"method": "manual"}
	if method == "manual":
		if source.has("source_method"):
			result["source_method"] = source.source_method
	else:
		result["source_method"] = method
	if source.has("mirrored_from"):
		result["mirrored_from"] = int(source.mirrored_from)
	result["independent"] = is_approved(direction, frame) or bool(source.get("independent", false))
	return result


## The correction layer as it would be saved: only meaningful poses.
func snapshot() -> Dictionary:
	var result := {
		"schema": "spritemotion.pose-annotations", "schema_version": 1,
		"dataset_id": dataset.data.dataset_id, "sequence": sequence_id,
		"skeleton": String(dataset.skeleton.id), "layer": "correction", "coordinate_space": "canvas-px",
	}
	for field in layer_meta:
		result[field] = layer_meta[field]
	result["editor"] = "Sprite Pose Editor / Godot " + Engine.get_version_info().string
	result["saved_at_utc"] = Time.get_datetime_string_from_system(true) + "Z"
	var out := []
	for record in dataset.sequence(sequence_id).frames:
		var d := int(record.direction)
		var f := int(record.frame)
		if not is_meaningful(d, f):
			continue
		var p := pose(d, f).duplicate(true)
		p.direction = d
		p.frame = f
		p.frame_id = String(record.frame_id)
		if origin.get(key(d, f), "") != "correction" or String(p.get("source_fingerprint", "")).is_empty():
			p.source_fingerprint = String(record.get("fingerprint", p.get("source_fingerprint", "")))
		p.provenance = correction_provenance(d, f)
		out.append(p)
	out.sort_custom(func(a, b): return a.direction < b.direction or (a.direction == b.direction and a.frame < b.frame))
	result["poses"] = out
	return result


## True when path is inside the protected estimates folder.
func is_protected(path: String) -> bool:
	var target := path.replace("\\", "/").simplify_path().to_lower()
	var protected_dir: String = dataset.annotation_dir("estimate").replace("\\", "/").simplify_path().to_lower()
	return target.begins_with(protected_dir + "/") or target == protected_dir


## Atomic write via .tmp, keeping the previous file as .bak.
func save_to(path: String, mark_saved: bool = true) -> bool:
	var absolute := ProjectSettings.globalize_path(path)
	if is_protected(absolute):
		last_error = "The estimate layer is protected. Choose a corrections filename."
		return false
	if DirAccess.make_dir_recursive_absolute(absolute.get_base_dir()) != OK:
		last_error = "Cannot create folder " + absolute.get_base_dir()
		return false
	var temp := absolute + ".tmp"
	var file := FileAccess.open(temp, FileAccess.WRITE)
	if file == null:
		last_error = "Cannot write " + absolute
		return false
	file.store_string(JSON.stringify(snapshot(), "\t"))
	file.flush()
	var write_error := file.get_error()
	file.close()
	if write_error != OK:
		last_error = "Could not finish writing corrections."
		return false
	var backup := absolute + ".bak"
	if FileAccess.file_exists(absolute):
		if FileAccess.file_exists(backup) and DirAccess.remove_absolute(backup) != OK:
			last_error = "Cannot replace backup; existing corrections retained."
			return false
		if DirAccess.rename_absolute(absolute, backup) != OK:
			last_error = "Cannot back up existing corrections."
			return false
	if DirAccess.rename_absolute(temp, absolute) != OK:
		if FileAccess.file_exists(backup):
			DirAccess.rename_absolute(backup, absolute)
		last_error = "Cannot finalize correction file."
		return false
	if mark_saved:
		dirty = false
	return true


## Human-readable provenance for the inspector.
func provenance_text(direction: int, frame: int) -> String:
	var k := key(direction, frame)
	var p := pose(direction, frame)
	var prov: Dictionary = p.get("provenance", {})
	var method := String(prov.get("method", "unknown"))
	var names := {"manual": "Manual", "mirrored": "Mirrored", "rig_projection": "Rig projection",
		"estimator": "Estimator", "interpolated": "Interpolated", "imported": "Imported"}
	var text := String(names.get(method, method))
	if prov.has("mirrored_from"):
		text += " from " + dataset.direction_name(int(prov.mirrored_from))
	if prov.has("source_method") and prov.source_method != method:
		text += " (of %s)" % String(names.get(String(prov.source_method), prov.source_method)).to_lower()
	var layer := String(origin.get(k, "estimate"))
	var prefix: String = {"correction": "Correction", "estimate": "Estimate", "default": "No estimate"}.get(layer, layer)
	text = prefix + " · " + text
	if not bool(prov.get("independent", false)):
		text += " — not independent evidence"
	return text

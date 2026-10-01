extends SceneTree
## Headless test suite for the Sprite Pose Editor.
##
##   godot --headless --path . --script res://tests/test_editor.gd -- --dataset=<fixture dataset folder>
##
## The fixture is copied to tests/output/work/ first, so every real save path
## (Ctrl+S, autosave, switch-sequence save, .bak rotation) runs without touching
## the committed fixture. Results: tests/output/test-report.json.

const Dataset = preload("res://src/dataset.gd")
const Document = preload("res://src/document.gd")

var failures: Array = []
var checks: int = 0


func verify(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)
		push_error("FAIL: " + message)


func _initialize() -> void:
	call_deferred("run")


func copy_dir(from: String, to: String) -> void:
	DirAccess.make_dir_recursive_absolute(to)
	for file in DirAccess.get_files_at(from):
		DirAccess.copy_absolute(from.path_join(file), to.path_join(file))
	for dir in DirAccess.get_directories_at(from):
		copy_dir(from.path_join(dir), to.path_join(dir))


func remove_dir(path: String) -> void:
	if not DirAccess.dir_exists_absolute(path):
		return
	for file in DirAccess.get_files_at(path):
		DirAccess.remove_absolute(path.path_join(file))
	for dir in DirAccess.get_directories_at(path):
		remove_dir(path.path_join(dir))
	DirAccess.remove_absolute(path)


func write_text(path: String, text: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(text)
	file.close()


func canonical(value: Variant) -> String:
	# Stable comparison independent of key order and int/float spelling.
	return JSON.stringify(JSON.parse_string(JSON.stringify(value)), "", true)


func run() -> void:
	var source := ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--dataset="):
			source = arg.substr(10)
	if source.is_empty():
		source = ProjectSettings.globalize_path("res://tests/fixtures/tiny")
	if source.ends_with("dataset.json"):
		source = source.get_base_dir()
	var out := ProjectSettings.globalize_path("res://tests/output")
	var work := out.path_join("work")
	DirAccess.make_dir_recursive_absolute(out)
	write_text(out.path_join(".gdignore"), "")
	remove_dir(work)
	copy_dir(source, work)
	await document_tests(work)
	await gui_tests(work)
	var report := {"checks": checks, "failures": failures, "passed": failures.is_empty(), "dataset": source,
		"scope": "Dataset/skeleton loading, layer merge, edits, approval invalidation, linked mirrors, undo/redo, reset, save roundtrip (meaningful poses only), backups, malformed input, protected estimates, sequence switching, every sprite, GUI drag + nudge, snapping, playback"}
	DirAccess.make_dir_recursive_absolute(out)
	write_text(out.path_join("test-report.json"), JSON.stringify(report, "\t"))
	print(JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)


func document_tests(work: String) -> void:
	var ds = Dataset.new()
	verify(ds.load_manifest(work), "Load dataset manifest: " + ds.last_error)
	verify(ds.width() == 48 and ds.height() == 64, "Canvas size comes from the manifest")
	verify(ds.mirror_of(0) == 2 and ds.mirror_of(2) == 0 and ds.mirror_of(1) == 3, "Mirror pairs come from the manifest")
	verify(ds.joint_names().size() == 6, "Skeleton joints come from the skeleton file")
	var bad = Dataset.new()
	verify(not bad.load_manifest(work.path_join("missing")), "Missing manifest rejected")
	write_text(work.path_join("broken.json"), "{")
	verify(not bad.load_manifest(work.path_join("broken.json")), "Malformed manifest rejected")

	var doc = Document.new()
	verify(doc.open(ds, "wave"), "Open wave sequence: " + doc.last_error)
	verify(doc.poses.size() == 12, "Every manifest frame has a working pose")
	verify(doc.baseline.size() == 11, "Partial estimate layer loaded")
	verify(doc.origin[Document.key(3, 2)] == "default", "Frame without an estimate gets a default layout")
	verify(not doc.is_approved(0, 1), "Estimate-only pose starts unapproved")
	verify(doc.load_corrections(ds.annotation_path("correction", "wave")), "Load committed corrections: " + doc.last_error)
	verify(doc.is_approved(0, 1), "Approved correction preserved")
	verify(doc.provenance_text(0, 0).contains("not independent"), "Rig projection flagged as not independent")
	verify(not doc.provenance_text(0, 1).contains("not independent"), "Approved correction is independent")
	var untouched := canonical(doc.baseline)

	var old: Vector2 = doc.point(0, 1, "hand")
	doc.begin_edit(0, 1)
	doc.move_joint(0, 1, "hand", old + Vector2(2.3, -1.7))
	doc.commit_edit()
	verify(doc.point(0, 1, "hand").is_equal_approx(old + Vector2(2.3, -1.7)), "Subpixel edit retained")
	verify(not doc.is_approved(0, 1), "Editing clears approval")
	verify(doc.review_status(0, 1) == "in_progress", "Edited pose is in progress")
	verify(doc.joint(0, 1, "hand").status == "corrected", "Edited joint marked corrected")
	verify(doc.undo() and doc.point(0, 1, "hand").is_equal_approx(old) and doc.is_approved(0, 1), "Undo restores coordinates and approval")
	verify(doc.redo() and not doc.is_approved(0, 1), "Redo restores edit")

	var partner_before: Vector2 = doc.point(2, 0, "head")
	var main_before: Vector2 = doc.point(0, 0, "head")
	doc.begin_edit(0, 0, true)
	doc.move_joint(0, 0, "head", Vector2(20.25, 11.5), true)
	doc.commit_edit()
	verify(doc.point(2, 0, "head").is_equal_approx(Vector2(47 - 20.25, 11.5)), "Linked mirror uses 2*axis - x")
	verify(doc.joint(2, 0, "head").status == "mirrored_correction", "Partner marked mirrored correction")
	doc.undo()
	verify(doc.point(2, 0, "head").is_equal_approx(partner_before) and doc.point(0, 0, "head").is_equal_approx(main_before), "Mirror pair undone atomically")
	doc.redo()

	doc.begin_edit(1, 0)
	doc.move_joint(1, 0, "head", Vector2(-5, 500))
	doc.commit_edit()
	verify(doc.point(1, 0, "head") == Vector2(0, 63), "Canvas clamp uses width-1/height-1")
	doc.reset_pose(1, 0)
	verify(doc.point(1, 0, "head") != Vector2(0, 63), "Reset restores the estimate")
	doc.undo()
	verify(doc.point(1, 0, "head") == Vector2(0, 63), "Reset is undoable")
	doc.reset_pose(1, 0)
	doc.set_approved(1, 0, true)
	verify(doc.is_approved(1, 0), "Approval set explicitly")
	doc.set_notes(3, 2, "Foot hidden behind body.")
	verify(canonical(doc.baseline) == untouched, "Estimate layer never mutated")

	var snap: Dictionary = doc.snapshot()
	var saved_keys := []
	for p in snap.poses:
		saved_keys.append(Document.key(int(p.direction), int(p.frame)))
	saved_keys.sort()
	verify(saved_keys == ["0:0", "0:1", "1:0", "2:0", "3:2"], "Only meaningful poses are written: %s" % str(saved_keys))
	for p in snap.poses:
		verify(p.direction is int and p.frame is int, "Direction/frame written as integers")
		verify(p.source_fingerprint == ds.frame("wave", int(p.direction), int(p.frame)).fingerprint, "Correction carries the manifest fingerprint")
	var approved_pose: Dictionary = snap.poses.filter(func(p): return p.direction == 1 and p.frame == 0)[0]
	verify(approved_pose.provenance.independent == true and approved_pose.provenance.source_method == "rig_projection", "Approved correction becomes independent, keeps source method")
	var edited_pose: Dictionary = snap.poses.filter(func(p): return p.direction == 0 and p.frame == 0)[0]
	verify(edited_pose.provenance.independent == false, "Unapproved correction of a projection stays dependent")

	verify(not doc.save_to(ds.annotation_path("estimate", "wave")), "Estimate layer is protected")
	verify(not doc.save_to(ds.annotation_dir("estimate").path_join("other.json")), "Whole estimates folder is protected")
	var path := work.path_join("roundtrip/wave.json")
	verify(doc.save_to(path), "First atomic save: " + doc.last_error)
	verify(doc.save_to(path), "Overwrite succeeds")
	verify(FileAccess.file_exists(path + ".bak"), "Previous revision kept as .bak")
	verify(not FileAccess.file_exists(path + ".tmp"), "Temporary file cleaned up")
	var reloaded = Document.new()
	reloaded.open(ds, "wave")
	verify(reloaded.load_corrections(path), "Saved corrections reload: " + reloaded.last_error)
	verify(_same_effective(reloaded, doc), "Reloaded effective poses identical")
	verify(reloaded.point(2, 0, "head").is_equal_approx(Vector2(47 - 20.25, 11.5)), "Mirror edit survives roundtrip")
	verify(String(reloaded.pose(3, 2).review.notes) == "Foot hidden behind body.", "Notes survive roundtrip")

	var saved := canonical(reloaded.poses)
	write_text(work.path_join("malformed.json"), "{")
	verify(not reloaded.load_corrections(work.path_join("malformed.json")), "Malformed JSON rejected")
	var mutated: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	mutated.poses[0].joints.head.x = "bad"
	write_text(work.path_join("bad-coord.json"), JSON.stringify(mutated))
	verify(not reloaded.load_corrections(work.path_join("bad-coord.json")), "Non-numeric coordinate rejected")
	mutated = JSON.parse_string(FileAccess.get_file_as_string(path))
	mutated.poses[0].joints.head.x = 999
	write_text(work.path_join("outside.json"), JSON.stringify(mutated))
	verify(not reloaded.load_corrections(work.path_join("outside.json")), "Coordinate outside canvas rejected")
	mutated = JSON.parse_string(FileAccess.get_file_as_string(path))
	mutated.poses.append(mutated.poses[0])
	write_text(work.path_join("dupe.json"), JSON.stringify(mutated))
	verify(not reloaded.load_corrections(work.path_join("dupe.json")), "Duplicate pose rejected")
	mutated = JSON.parse_string(FileAccess.get_file_as_string(path))
	mutated.poses[0].joints.erase("head")
	write_text(work.path_join("missing-joint.json"), JSON.stringify(mutated))
	verify(not reloaded.load_corrections(work.path_join("missing-joint.json")), "Missing joint rejected")
	mutated = JSON.parse_string(FileAccess.get_file_as_string(path))
	mutated.poses[0].review.status = "yes"
	write_text(work.path_join("bad-review.json"), JSON.stringify(mutated))
	verify(not reloaded.load_corrections(work.path_join("bad-review.json")), "Invalid review status rejected")
	mutated = JSON.parse_string(FileAccess.get_file_as_string(path))
	mutated.sequence = "hop"
	write_text(work.path_join("other-seq.json"), JSON.stringify(mutated))
	verify(not reloaded.load_corrections(work.path_join("other-seq.json")), "Corrections for another sequence rejected")
	verify(canonical(reloaded.poses) == saved, "Failed loads leave the document unchanged")

	var hop = Document.new()
	verify(hop.open(ds, "hop"), "Sequence without any annotations opens")
	verify(hop.poses.size() == 8 and hop.origin.values().all(func(o): return o == "default"), "All hop poses use the default layout")
	verify(hop.snapshot().poses.is_empty(), "Untouched default poses are not saved")

	# Fingerprint mismatch detection.
	var tampered: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	tampered.poses[0].source_fingerprint = "sha256:" + "0".repeat(64)
	write_text(work.path_join("tampered.json"), JSON.stringify(tampered))
	var check_doc = Document.new()
	check_doc.open(ds, "wave")
	check_doc.load_corrections(work.path_join("tampered.json"))
	var p0: Dictionary = tampered.poses[0]
	verify(check_doc.fingerprint_mismatch(int(p0.direction), int(p0.frame)), "Fingerprint mismatch detected")
	verify(not check_doc.fingerprint_mismatch(1, 1), "Matching fingerprint not flagged")


func _same_effective(a, b) -> bool:
	for k in b.poses:
		var pa: Dictionary = a.poses.get(k, {})
		var pb: Dictionary = b.poses[k]
		if canonical(pa.joints) != canonical(pb.joints):
			return false
		if String(pa.review.get("status", "")) != String(pb.review.get("status", "")):
			return false
		if String(pa.review.get("notes", "")) != String(pb.review.get("notes", "")):
			return false
	return true


func gui_tests(work: String) -> void:
	# Fresh copy so the GUI starts from the committed state.
	var gui_dir := work + "-gui"
	remove_dir(gui_dir)
	copy_dir(work, gui_dir)
	remove_dir(gui_dir.path_join("roundtrip"))
	var app = load("res://main.tscn").instantiate()
	app.testing = true
	app.dataset_override = gui_dir
	root.add_child(app)
	await process_frame
	await process_frame
	await process_frame
	verify(app.document != null and app.sequence_id == "wave", "Editor opens the first sequence")
	verify(app.canvas.size.x >= 500 and app.canvas.size.y >= 300, "Usable canvas layout %s" % str(app.canvas.size))
	verify(app.frame_buttons.size() == 3, "Frame strip sized from frame_count")
	verify(app.direction_select.item_count == 4, "Direction selector from manifest")
	verify(app.document.is_approved(0, 1), "Committed approval restored on open")

	app.select_pose(0, 0)
	await process_frame
	var canvas = app.canvas
	app.select_joint("hand")
	var start: Vector2 = app.document.point(0, 0, "hand")
	verify(canvas.color_for("hand").is_equal_approx(Color("28d9ff")), "Joint colors from skeleton chains")
	var global_start: Vector2 = canvas.global_position + canvas.to_screen(start)
	var before_segments: Array = canvas.line_segments()
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	press.position = global_start
	root.push_input(press, true)
	await process_frame
	verify(canvas.dragging and canvas.selected == "hand", "GUI press picks the hand joint")
	var delta := Vector2(2, -2)
	var motion := InputEventMouseMotion.new()
	motion.position = global_start + delta * canvas.zoom
	motion.relative = delta * canvas.zoom
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	root.push_input(motion, true)
	await process_frame
	verify(app.document.point(0, 0, "hand").is_equal_approx(start + delta), "GUI drag moves joint in canvas pixels")
	var after_segments: Array = canvas.line_segments()
	var hand_edge: int = -1
	var edges: Array = app.dataset.edges()
	for i in range(edges.size()):
		if edges[i][1] == "hand":
			hand_edge = i
	verify(hand_edge >= 0 and not before_segments[hand_edge][1].is_equal_approx(after_segments[hand_edge][1]), "Connected bone follows the drag")
	var release := InputEventMouseButton.new()
	release.button_index = MOUSE_BUTTON_LEFT
	release.pressed = false
	release.position = motion.position
	root.push_input(release, true)
	await process_frame
	verify(not canvas.dragging and app.document.undo_stack.size() == 1, "Whole drag is one undo step")
	app.undo()
	verify(app.document.point(0, 0, "hand").is_equal_approx(start), "UI undo restores drag")
	app.redo()
	canvas.grab_focus()
	var key := InputEventKey.new()
	key.pressed = true
	key.keycode = KEY_RIGHT
	root.push_input(key)
	await process_frame
	verify(app.document.point(0, 0, "hand").is_equal_approx(start + delta + Vector2.RIGHT), "Arrow key nudges 1 px")
	var fine := InputEventKey.new()
	fine.pressed = true
	fine.keycode = KEY_DOWN
	fine.shift_pressed = true
	root.push_input(fine)
	await process_frame
	verify(app.document.point(0, 0, "hand").is_equal_approx(start + delta + Vector2(1, 0.1)), "Shift+arrow nudges 0.1 px")

	app.select_pose(2, 1)
	app.canvas.link_mirror = true
	app.select_joint("pelvis")
	var position: Vector2 = app.document.point(2, 1, "pelvis")
	app.x_input.value = position.x + 1.5
	verify(is_equal_approx(app.document.point(0, 1, "pelvis").x, 47 - position.x - 1.5), "Numeric edit updates linked mirror")
	verify(not app.document.is_approved(0, 1), "Linked edit clears the partner's approval")
	app.canvas.link_mirror = false

	for sequence in app.dataset.sequences():
		for record in sequence.frames:
			verify(app.dataset.texture_for(record) != null, "Sprite loads: " + String(record.frame_id))
	for d in app.dataset.direction_ids():
		for f in range(3):
			app.select_pose(d, f)
			verify(app.canvas.sprite != null and app.joint_list.item_count == 6, "Pose %d:%d shows sprite and 6 joints" % [d, f])

	app.select_pose(0, 0)
	app.frame_buttons[2].pressed.emit()
	verify(app.frame == 2, "Frame strip selects a frame")
	app.toggle_play()
	app._process(0.2)
	verify(app.frame == 0 and app.playing, "Preview wraps and keeps playing")
	app.select_joint("head")
	verify(not app.playing, "Editing stops preview")

	app.select_pose(1, 1)
	canvas.snap_pixels = true
	app.select_joint("neck")
	var start2: Vector2 = app.document.point(1, 1, "neck")
	var local: Vector2 = canvas.to_screen(start2)
	var press2 := InputEventMouseButton.new()
	press2.button_index = MOUSE_BUTTON_LEFT
	press2.pressed = true
	press2.position = canvas.global_position + local
	root.push_input(press2, true)
	await process_frame
	var motion2 := InputEventMouseMotion.new()
	motion2.position = canvas.global_position + local + Vector2(0.37, 0.39) * canvas.zoom
	motion2.button_mask = MOUSE_BUTTON_MASK_LEFT
	root.push_input(motion2, true)
	await process_frame
	verify(app.document.point(1, 1, "neck").is_equal_approx((start2 + Vector2(0.37, 0.39)).round()), "Snap gives whole pixels")
	app.autosave()
	verify(not app.document.pending.is_empty(), "Autosave defers during a drag")
	var release2 := InputEventMouseButton.new()
	release2.button_index = MOUSE_BUTTON_LEFT
	release2.position = Vector2(3, 3)
	release2.pressed = false
	root.push_input(release2, true)
	await process_frame
	verify(not canvas.dragging, "Release outside the canvas ends the drag")
	canvas.snap_pixels = false
	var native := Vector2(12.7, 33.2)
	verify(canvas.to_native(canvas.to_screen(native)).is_equal_approx(native), "Pan/zoom transform roundtrip")

	# Switching sequence saves dirty work to the correction layer.
	var save_path: String = app.save_path
	app.switch_sequence(1)
	await process_frame
	verify(app.sequence_id == "hop" and app.frame_buttons.size() == 2, "Switched to hop; strip resized")
	verify(FileAccess.file_exists(save_path), "Switching saved the previous sequence's corrections")
	var written: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(save_path))
	verify(written.layer == "correction" and written.sequence == "wave", "Saved file is the wave correction layer")
	app.switch_sequence(0)
	await process_frame
	verify(app.document.point(0, 0, "hand").is_equal_approx(start + delta + Vector2(1, 0.1)), "Edits restored after switching back")

	# Unreadable recovery file pauses autosave instead of being replaced.
	write_text(app.auto_path, "{ broken")
	app.switch_sequence(1)
	await process_frame
	app.switch_sequence(0)
	await process_frame
	verify(not app.autosave_allowed, "Unreadable autosave pauses autosave")
	verify(FileAccess.get_file_as_string(app.auto_path) == "{ broken", "Unreadable autosave preserved")
	app.queue_free()
	await process_frame

extends Control
## Sprite Pose Editor: review and correct 2D joint annotations for any
## SpriteMotion dataset. Layout, directions, sequences, canvas and skeleton all
## come from the dataset manifest.

const Dataset = preload("res://src/dataset.gd")
const Document = preload("res://src/document.gd")
const PoseCanvas = preload("res://src/pose_canvas.gd")
const SETTINGS_PATH := "user://settings.cfg"
const DEFAULT_PLAY_SECONDS := 0.25

## Set before adding to the tree to open a specific dataset (tests, reloads).
var dataset_override: String = ""
## Test mode: no autosave timer writes and no settings writes.
var testing: bool = false

var dataset
var document
var sequence_id: String = ""
var direction: int = 0
var frame: int = 0
var selected: String = ""
var save_path: String = ""
var auto_path: String = ""
var updating: bool = false
var autosave_allowed: bool = true
var playing: bool = false
var play_elapsed: float = 0.0

var canvas
var sequence_select: OptionButton
var direction_select: OptionButton
var joint_list: ItemList
var frame_strip: HBoxContainer
var frame_buttons: Array = []
var approval: CheckBox
var x_input: SpinBox
var y_input: SpinBox
var selected_name: Label
var provenance_label: Label
var warning_panel: PanelContainer
var warning_label: Label
var status: Label
var pose_title: Label
var subtitle: Label
var progress: Label
var zoom_label: Label
var notes: TextEdit
var undo_button: Button
var redo_button: Button
var play_button: Button
var export_dialog: FileDialog
var import_dialog: FileDialog
var open_dialog: FileDialog
var reset_dialog: ConfirmationDialog
var autosave_timer: Timer
var welcome: Label


func _ready() -> void:
	get_tree().auto_accept_quit = false
	get_window().min_size = Vector2i(1100, 760)
	var args := OS.get_cmdline_user_args()
	var path := _choose_dataset_path(args)
	if path.is_empty() or not open_dataset(path):
		_show_welcome(path)
		return
	var capture := _arg_value(args, "--capture")
	if not capture.is_empty():
		await get_tree().process_frame
		await get_tree().process_frame
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png(capture)
		get_tree().quit()


static func _arg_value(args: PackedStringArray, name: String) -> String:
	for arg in args:
		if arg.begins_with(name + "="):
			return arg.substr(name.length() + 1).strip_edges().trim_prefix("\"").trim_suffix("\"")
	return ""


func _choose_dataset_path(args: PackedStringArray) -> String:
	if not dataset_override.is_empty():
		return dataset_override
	if Engine.has_meta("sprite_pose_editor_next"):
		var next := String(Engine.get_meta("sprite_pose_editor_next"))
		Engine.remove_meta("sprite_pose_editor_next")
		return next
	var from_args := _arg_value(args, "--dataset")
	if not from_args.is_empty():
		return from_args
	var from_env := OS.get_environment("SPRITEMOTION_DATASET")
	if not from_env.is_empty():
		return from_env
	var config := ConfigFile.new()
	if config.load(SETTINGS_PATH) == OK:
		return String(config.get_value("editor", "last_dataset", ""))
	return ""


func _show_welcome(attempted: String) -> void:
	_apply_theme()
	var box := VBoxContainer.new()
	box.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	box.add_theme_constant_override("separation", 14)
	add_child(box)
	box.add_child(label("SPRITE POSE EDITOR", 26, "f2f7fc"))
	var message := "No dataset loaded. Open a dataset.json written by a SpriteMotion adapter,\nor start with --dataset=<path> or SPRITEMOTION_DATASET."
	if not attempted.is_empty():
		var reason: String = dataset.last_error if dataset != null else ""
		message = "Could not open %s\n%s\n\n%s" % [attempted, reason, message]
	welcome = label(message, 15, "dbe4ee")
	box.add_child(welcome)
	box.add_child(button("Open dataset…", func(): open_dialog.popup_centered_ratio(0.7)))
	_build_open_dialog()


func _build_open_dialog() -> void:
	open_dialog = FileDialog.new()
	open_dialog.access = FileDialog.ACCESS_FILESYSTEM
	open_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	open_dialog.filters = PackedStringArray(["dataset.json ; SpriteMotion dataset", "*.json ; JSON"])
	open_dialog.file_selected.connect(_open_selected_dataset)
	add_child(open_dialog)


func _open_selected_dataset(path: String) -> void:
	if document != null and not _preserve_current():
		return
	Engine.set_meta("sprite_pose_editor_next", path)
	get_tree().reload_current_scene()


## Loads a dataset and opens its first sequence. Returns false (with dataset.last_error) on failure.
func open_dataset(path: String) -> bool:
	dataset = Dataset.new()
	if not dataset.load_manifest(path):
		push_warning(dataset.last_error)
		return false
	if not testing:
		var config := ConfigFile.new()
		config.load(SETTINGS_PATH)
		config.set_value("editor", "last_dataset", dataset.manifest_path)
		config.save(SETTINGS_PATH)
	build_ui()
	var first: String = String(dataset.sequences()[0].id)
	if not _open_sequence(first):
		set_status(document.last_error if document != null else dataset.last_error)
		return true
	return true


# ---------------------------------------------------------------- UI helpers

func style(bg: String, border: String = "", radius: int = 8) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = Color(bg)
	box.set_corner_radius_all(radius)
	box.content_margin_left = 12
	box.content_margin_right = 12
	box.content_margin_top = 8
	box.content_margin_bottom = 8
	if not border.is_empty():
		box.border_color = Color(border)
		box.set_border_width_all(1)
	return box


func label(text: String, size_px: int = 15, color: String = "dbe4ee") -> Label:
	var item := Label.new()
	item.text = text
	item.add_theme_font_size_override("font_size", size_px)
	item.add_theme_color_override("font_color", Color(color))
	return item


func button(text: String, callback: Callable, hint: String = "") -> Button:
	var item := Button.new()
	item.text = text
	item.tooltip_text = hint
	item.pressed.connect(callback)
	return item


func check(text: String, value: bool, callback: Callable) -> CheckBox:
	var item := CheckBox.new()
	item.text = text
	item.button_pressed = value
	item.toggled.connect(callback)
	return item


func _apply_theme() -> void:
	var ui_theme := Theme.new()
	ui_theme.default_font_size = 15
	ui_theme.set_stylebox("normal", "Button", style("253142", "35465b"))
	ui_theme.set_stylebox("hover", "Button", style("30435a", "73d9ce"))
	ui_theme.set_stylebox("pressed", "Button", style("245d60", "73d9ce"))
	ui_theme.set_stylebox("focus", "Button", style("253142", "91d9ff"))
	ui_theme.set_stylebox("panel", "PanelContainer", style("1a2330", "2c3a4c", 10))
	theme = ui_theme
	var background := ColorRect.new()
	background.color = Color(0.055, 0.068, 0.087)
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	background.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(background)


## Builds the whole editor UI from the loaded dataset.
func build_ui() -> void:
	_apply_theme()
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 18)
	add_child(margin)
	var root := VBoxContainer.new()
	root.add_theme_constant_override("separation", 12)
	margin.add_child(root)

	var heading := HBoxContainer.new()
	root.add_child(heading)
	var titles := VBoxContainer.new()
	titles.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading.add_child(titles)
	titles.add_child(label(dataset.title().to_upper(), 24, "f2f7fc"))
	subtitle = label("", 14, "91a6bb")
	titles.add_child(subtitle)
	progress = label("", 15, "81dfbd")
	heading.add_child(progress)
	heading.add_child(button("Save corrections", save_corrections, "Ctrl+S · saves this sequence's correction layer"))
	heading.add_child(button("Save as…", func(): export_dialog.popup_centered_ratio(0.7)))
	heading.add_child(button("Load…", func(): import_dialog.popup_centered_ratio(0.7), "Load a correction file for the selected sequence"))
	heading.add_child(button("Open dataset…", func(): open_dialog.popup_centered_ratio(0.7)))

	var bar := HBoxContainer.new()
	bar.add_theme_constant_override("separation", 10)
	root.add_child(bar)
	bar.add_child(label("Sequence", 14, "91a6bb"))
	sequence_select = OptionButton.new()
	for i in range(dataset.sequences().size()):
		var entry: Dictionary = dataset.sequences()[i]
		sequence_select.add_item("%s  ·  %s" % [entry.id, entry.get("name", entry.id)], i)
	sequence_select.item_selected.connect(switch_sequence)
	bar.add_child(sequence_select)
	bar.add_child(label("Direction", 14, "91a6bb"))
	direction_select = OptionButton.new()
	for item in dataset.directions():
		direction_select.add_item(String(item.name), int(item.id))
	direction_select.item_selected.connect(func(index): select_pose(direction_select.get_item_id(index), frame))
	bar.add_child(direction_select)
	bar.add_child(button("‹ Previous", func(): step_frame(-1), "A or Page Up"))
	bar.add_child(button("Next ›", func(): step_frame(1), "D or Page Down"))
	play_button = button("▶ Preview", toggle_play, "Space · pauses when you start editing")
	bar.add_child(play_button)
	pose_title = label("", 18, "f1f7ff")
	pose_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bar.add_child(pose_title)
	undo_button = button("Undo", undo, "Ctrl+Z")
	bar.add_child(undo_button)
	redo_button = button("Redo", redo, "Ctrl+Y or Ctrl+Shift+Z")
	bar.add_child(redo_button)

	var body := HBoxContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 12)
	root.add_child(body)
	var canvas_column := VBoxContainer.new()
	canvas_column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_child(canvas_column)
	warning_panel = PanelContainer.new()
	warning_panel.add_theme_stylebox_override("panel", style("5a1d24", "ff6b6b", 8))
	warning_label = label("", 14, "ffd6d6")
	warning_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	warning_panel.add_child(warning_label)
	warning_panel.visible = false
	canvas_column.add_child(warning_panel)
	var canvas_panel := PanelContainer.new()
	canvas_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	canvas_column.add_child(canvas_panel)
	canvas = PoseCanvas.new()
	canvas.custom_minimum_size = Vector2(560, 330)
	canvas_panel.add_child(canvas)
	canvas.joint_selected.connect(select_joint)
	canvas.edit_finished.connect(after_edit)
	canvas.keyboard_input.connect(_unhandled_key_input)
	canvas.zoom_changed.connect(func(value): zoom_label.text = "%.1f×" % value)
	var view_bar := HBoxContainer.new()
	canvas_column.add_child(view_bar)
	view_bar.add_child(button("Fit view", func(): canvas.fit_view(), "F · mouse wheel zooms; middle button pans"))
	zoom_label = label("", 13, "91a6bb")
	zoom_label.custom_minimum_size.x = 48
	view_bar.add_child(zoom_label)
	view_bar.add_child(check("Bones", true, func(v): canvas.show_bones = v; canvas.queue_redraw()))
	view_bar.add_child(check("IDs", true, func(v): canvas.show_labels = v; canvas.queue_redraw()))
	view_bar.add_child(check("Pixel grid", false, func(v): canvas.show_grid = v; canvas.queue_redraw()))
	view_bar.add_child(check("Original ghost", false, func(v): canvas.show_original = v; canvas.queue_redraw()))
	view_bar.add_child(label("Sprite", 13, "91a6bb"))
	var alpha := HSlider.new()
	alpha.min_value = 0.1
	alpha.max_value = 1
	alpha.step = 0.05
	alpha.value = 1
	alpha.custom_minimum_size.x = 85
	alpha.value_changed.connect(func(v): canvas.opacity = v; canvas.queue_redraw())
	view_bar.add_child(alpha)

	var inspector_panel := PanelContainer.new()
	inspector_panel.custom_minimum_size.x = 310
	body.add_child(inspector_panel)
	var inspector := VBoxContainer.new()
	inspector.add_theme_constant_override("separation", 7)
	inspector_panel.add_child(inspector)
	provenance_label = label("", 13, "c7d3e0")
	provenance_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	provenance_label.custom_minimum_size.x = 280
	inspector.add_child(provenance_label)
	inspector.add_child(label("JOINTS", 13, "91a6bb"))
	joint_list = ItemList.new()
	joint_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	joint_list.custom_minimum_size.y = 160
	joint_list.item_selected.connect(func(index): select_joint(dataset.joint_names()[index]))
	inspector.add_child(joint_list)
	selected_name = label("", 15, "f2f7fc")
	inspector.add_child(selected_name)
	var xy := HBoxContainer.new()
	inspector.add_child(xy)
	xy.add_child(label("X", 14))
	x_input = SpinBox.new()
	x_input.min_value = 0
	x_input.max_value = dataset.max_point().x
	x_input.step = 0.1
	x_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	xy.add_child(x_input)
	xy.add_child(label("Y", 14))
	y_input = SpinBox.new()
	y_input.min_value = 0
	y_input.max_value = dataset.max_point().y
	y_input.step = 0.1
	y_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	xy.add_child(y_input)
	x_input.value_changed.connect(numeric_changed)
	y_input.value_changed.connect(numeric_changed)
	inspector.add_child(check("Snap to whole pixels", false, func(v): canvas.snap_pixels = v))
	var linked := check("Link mirrored view", false, func(v): canvas.link_mirror = v)
	linked.tooltip_text = "Optional: edits also update the direction's mirror partner (x' = 2·axis − x). Undoable together."
	inspector.add_child(linked)
	approval = check("Pose approved", false, func(v):
		if not updating:
			stop_play()
			document.set_approved(direction, frame, v)
			after_edit())
	inspector.add_child(approval)
	inspector.add_child(label("POSE NOTES", 12, "91a6bb"))
	notes = TextEdit.new()
	notes.custom_minimum_size.y = 60
	notes.placeholder_text = "Hidden elbow, ambiguous limb, etc."
	notes.text_changed.connect(note_changed)
	inspector.add_child(notes)
	inspector.add_child(button("Reset this pose to estimate…", func(): reset_dialog.popup_centered(), "Only this pose; reset can be undone."))
	inspector.add_child(label("Drag points · lines follow\nArrow keys: nudge 1 px · Shift: 0.1 px\nWheel: zoom · Middle drag: pan", 12, "91a6bb"))

	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size.y = 108
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	root.add_child(scroll)
	frame_strip = HBoxContainer.new()
	frame_strip.add_theme_constant_override("separation", 8)
	scroll.add_child(frame_strip)

	var footer := HBoxContainer.new()
	root.add_child(footer)
	status = label("", 13, "91a6bb")
	status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	status.clip_text = true
	footer.add_child(status)
	footer.add_child(button("Corrections folder", func():
		DirAccess.make_dir_recursive_absolute(dataset.annotation_dir("correction"))
		OS.shell_open(dataset.annotation_dir("correction"))))

	export_dialog = FileDialog.new()
	export_dialog.access = FileDialog.ACCESS_FILESYSTEM
	export_dialog.file_mode = FileDialog.FILE_MODE_SAVE_FILE
	export_dialog.filters = PackedStringArray(["*.json ; Pose corrections"])
	export_dialog.file_selected.connect(export_selected)
	add_child(export_dialog)
	import_dialog = FileDialog.new()
	import_dialog.access = FileDialog.ACCESS_FILESYSTEM
	import_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	import_dialog.filters = PackedStringArray(["*.json ; Pose corrections"])
	import_dialog.file_selected.connect(import_selected)
	add_child(import_dialog)
	_build_open_dialog()
	reset_dialog = ConfirmationDialog.new()
	reset_dialog.dialog_text = "Restore this pose's estimate? You can Undo the reset."
	reset_dialog.confirmed.connect(func():
		stop_play()
		document.reset_pose(direction, frame)
		after_edit())
	add_child(reset_dialog)
	autosave_timer = Timer.new()
	autosave_timer.one_shot = true
	autosave_timer.wait_time = 0.8
	autosave_timer.timeout.connect(autosave)
	add_child(autosave_timer)


func _rebuild_frame_strip() -> void:
	for child in frame_strip.get_children():
		frame_strip.remove_child(child)
		child.queue_free()
	frame_buttons.clear()
	for f in range(dataset.frame_count(sequence_id)):
		var thumb := button("", func(): select_pose(direction, f))
		thumb.custom_minimum_size = Vector2(92, 92)
		thumb.toggle_mode = true
		thumb.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
		thumb.vertical_icon_alignment = VERTICAL_ALIGNMENT_TOP
		thumb.expand_icon = true
		thumb.add_theme_constant_override("icon_max_width", 64)
		frame_strip.add_child(thumb)
		frame_buttons.append(thumb)


func _refresh_thumbnails() -> void:
	for f in range(frame_buttons.size()):
		var record: Dictionary = dataset.frame(sequence_id, direction, f)
		var image: Image = dataset.image_for(record)
		frame_buttons[f].disabled = image == null
		if image == null:
			frame_buttons[f].icon = null
			continue
		var rect := Rect2i(dataset.bounds_for(record)).grow(3).intersection(Rect2i(0, 0, image.get_width(), image.get_height()))
		if rect.size.x < 1 or rect.size.y < 1:
			rect = Rect2i(0, 0, image.get_width(), image.get_height())
		var cropped := image.get_region(rect)
		var scale := maxi(1, int(80.0 / maxf(rect.size.x, rect.size.y)))
		cropped.resize(rect.size.x * scale, rect.size.y * scale, Image.INTERPOLATE_NEAREST)
		frame_buttons[f].icon = ImageTexture.create_from_image(cropped)


# ---------------------------------------------------------------- sequences and poses

func _open_sequence(next_id: String) -> bool:
	var next_doc = Document.new()
	if not next_doc.open(dataset, next_id):
		document = next_doc
		return false
	if document != null and document.changed.is_connected(refresh):
		document.changed.disconnect(refresh)
	document = next_doc
	sequence_id = next_id
	canvas.document = document
	save_path = dataset.annotation_path("correction", sequence_id)
	auto_path = dataset.autosave_path(sequence_id)
	export_dialog.current_dir = dataset.annotation_dir("correction")
	export_dialog.current_file = sequence_id + ".json"
	import_dialog.current_dir = dataset.annotation_dir("correction")
	autosave_allowed = true
	var restored := "Ready. Drag a joint; its connected lines follow. Estimates are never modified."
	var candidates := []
	for path in [save_path, auto_path]:
		if FileAccess.file_exists(path):
			candidates.append(path)
	candidates.sort_custom(func(a, b):
		var ta := correction_timestamp(a)
		var tb := correction_timestamp(b)
		if ta != tb:
			return ta > tb
		return FileAccess.get_modified_time(a) > FileAccess.get_modified_time(b))
	if not candidates.is_empty():
		if document.load_corrections(candidates[0]):
			restored = "Restored corrections from %s." % String(candidates[0]).get_file()
		else:
			autosave_allowed = false
			restored = document.last_error + "  Autosave paused; existing files preserved — use Save As."
	document.changed.connect(refresh)
	for i in range(dataset.sequences().size()):
		if String(dataset.sequences()[i].id) == sequence_id:
			sequence_select.select(i)
	_rebuild_frame_strip()
	var d := direction if dataset.direction_ids().has(direction) else int(dataset.direction_ids()[0])
	var f := mini(frame, dataset.frame_count(sequence_id) - 1)
	if not document.has_pose(d, f):
		for key in document.poses:
			d = int(document.poses[key].direction)
			f = int(document.poses[key].frame)
			break
	direction = d
	select_pose(d, f)
	set_status(restored)
	return true


## Saves pending work, then opens another sequence (by selector index).
func switch_sequence(index: int) -> void:
	var entry: Dictionary = dataset.sequences()[index]
	if String(entry.id) == sequence_id:
		return
	stop_play()
	canvas.finish_drag()
	if not document.pending.is_empty():
		document.commit_edit()
	if document.dirty and (not autosave_allowed or not document.save_to(save_path)):
		_select_sequence_item(sequence_id)
		set_status("Switch cancelled. Save As first: " + document.last_error)
		return
	autosave_timer.stop()
	var previous_doc = document
	if not _open_sequence(String(entry.id)):
		var reason: String = document.last_error
		document = previous_doc
		canvas.document = document
		_select_sequence_item(sequence_id)
		set_status("Cannot open %s: %s" % [entry.id, reason])


func _select_sequence_item(id: String) -> void:
	for i in range(dataset.sequences().size()):
		if String(dataset.sequences()[i].id) == id:
			sequence_select.select(i)


## Shows one pose (direction, frame) of the current sequence.
func select_pose(d: int, f: int) -> void:
	if canvas == null or document == null:
		return
	canvas.finish_drag()
	if not document.pending.is_empty():
		document.commit_edit()
	if not document.has_pose(d, f):
		set_status("%s has no frame %d in direction %s." % [sequence_id, f, dataset.direction_name(d)])
		return
	var direction_changed := d != direction or frame_buttons.is_empty() or frame_buttons[0].icon == null
	direction = d
	frame = f
	direction_select.select(direction_select.get_item_index(d))
	if not canvas.set_pose(d, f):
		set_status(dataset.last_error)
	updating = true
	notes.text = String(document.pose(d, f).get("review", {}).get("notes", ""))
	updating = false
	joint_list.clear()
	for name in dataset.joint_names():
		joint_list.add_item("%02d  %s" % [joint_list.item_count + 1, dataset.joint_label(name)])
		joint_list.set_item_custom_fg_color(joint_list.item_count - 1, canvas.color_for(name))
	if selected.is_empty() or not dataset.joint_names().has(selected):
		selected = dataset.joint_names()[0]
	if direction_changed:
		_refresh_thumbnails()
	select_joint(selected)


func select_joint(name: String) -> void:
	stop_play()
	selected = name
	canvas.selected = name
	var index: int = dataset.joint_names().find(name)
	if index >= 0:
		joint_list.select(index)
		joint_list.ensure_current_is_visible()
	refresh()


## Syncs every widget with the document.
func refresh() -> void:
	if canvas == null or document == null or not document.has_pose(direction, frame):
		return
	updating = true
	var j: Dictionary = document.joint(direction, frame, selected)
	selected_name.text = "%s" % dataset.joint_label(selected)
	x_input.set_value_no_signal(float(j.get("x", 0)))
	y_input.set_value_no_signal(float(j.get("y", 0)))
	approval.set_pressed_no_signal(document.is_approved(direction, frame))
	progress.text = "%d / %d approved" % [document.approved_count(), document.poses.size()]
	var entry: Dictionary = dataset.sequence(sequence_id)
	subtitle.text = "%s · %s · %d poses · %d joints" % [dataset.data.dataset_id, entry.get("name", sequence_id), document.poses.size(), dataset.joint_names().size()]
	pose_title.text = "%s  ·  F%d  ·  %s" % [dataset.direction_name(direction), frame, document.review_status(direction, frame).replace("_", " ")]
	provenance_label.text = document.provenance_text(direction, frame)
	var mismatch: bool = document.fingerprint_mismatch(direction, frame)
	warning_panel.visible = mismatch
	if mismatch:
		warning_label.text = "⚠ This annotation was made for different pixels (source fingerprint differs from the extracted frame). Its joints may not fit this sprite; review every point before approving."
	undo_button.disabled = document.undo_stack.is_empty()
	redo_button.disabled = document.redo_stack.is_empty()
	for f in range(frame_buttons.size()):
		frame_buttons[f].set_pressed_no_signal(f == frame)
		frame_buttons[f].text = "F%d%s" % [f, "  ✓" if document.has_pose(direction, f) and document.is_approved(direction, f) else ""]
	updating = false
	canvas.queue_redraw()


# ---------------------------------------------------------------- editing

func numeric_changed(_value: float) -> void:
	if updating:
		return
	stop_play()
	document.begin_edit(direction, frame, canvas.link_mirror)
	document.move_joint(direction, frame, selected, Vector2(x_input.value, y_input.value), canvas.link_mirror)
	document.commit_edit()
	after_edit()


func note_changed() -> void:
	if updating:
		return
	if document.pending.is_empty():
		document.begin_edit(direction, frame)
	document.pose(direction, frame).review["notes"] = notes.text
	autosave_timer.start()


func after_edit() -> void:
	if testing:
		return
	autosave_timer.start()
	set_status("Correction updated. Autosaving…" if autosave_allowed else "Autosave paused to preserve an unreadable file. Use Save As.")


func autosave() -> void:
	if canvas.dragging:
		autosave_timer.start()
		return
	if not document.pending.is_empty():
		document.commit_edit()
	if testing or not autosave_allowed:
		return
	if document.save_to(auto_path, false):
		set_status("Autosaved · Ctrl+S saves the correction layer.")
	else:
		set_status(document.last_error)


func save_corrections() -> void:
	canvas.finish_drag()
	if not document.pending.is_empty():
		document.commit_edit()
	if not autosave_allowed:
		set_status("Use Save As to preserve the unreadable recovery file.")
		export_dialog.popup_centered_ratio(0.7)
		return
	if document.save_to(save_path):
		autosave_timer.stop()
		if document.save_to(auto_path, false):
			set_status("Saved %s — only corrected, reviewed or annotated poses are written." % save_path.get_file())
		else:
			set_status("Correction file saved; recovery copy failed: " + document.last_error)
	else:
		set_status(document.last_error)


func export_selected(path: String) -> void:
	canvas.finish_drag()
	if not document.pending.is_empty():
		document.commit_edit()
	if path.get_extension().to_lower() != "json":
		path += ".json"
	if document.save_to(path):
		set_status("Saved " + path)
	else:
		set_status(document.last_error)


func import_selected(path: String) -> void:
	stop_play()
	canvas.finish_drag()
	if not document.pending.is_empty():
		document.commit_edit()
	if document.dirty and not autosave_allowed:
		set_status("Save As first so your current edits are preserved before loading.")
		return
	if document.dirty and not document.save_to(auto_path, false):
		set_status("Load cancelled: could not preserve current edits. " + document.last_error)
		return
	if document.load_corrections(path):
		select_pose(direction, frame)
		set_status("Loaded corrections from " + path)
	else:
		set_status(document.last_error + "  Current edits are unchanged.")


func undo() -> void:
	stop_play()
	canvas.finish_drag()
	if not document.pending.is_empty():
		document.commit_edit()
	if document.undo():
		sync_notes()
		after_edit()


func redo() -> void:
	stop_play()
	canvas.finish_drag()
	if document.redo():
		sync_notes()
		after_edit()


func sync_notes() -> void:
	updating = true
	notes.text = String(document.pose(direction, frame).get("review", {}).get("notes", ""))
	updating = false


func step_frame(step: int) -> void:
	stop_play()
	select_pose(direction, posmod(frame + step, dataset.frame_count(sequence_id)))


func toggle_play() -> void:
	canvas.finish_drag()
	playing = not playing
	play_elapsed = 0
	play_button.text = "❚❚ Pause" if playing else "▶ Preview"


func stop_play() -> void:
	playing = false
	if play_button:
		play_button.text = "▶ Preview"


func _play_interval() -> float:
	var ms := float(dataset.sequence(sequence_id).get("frame_duration_ms", 0))
	return ms / 1000.0 if ms > 0 else DEFAULT_PLAY_SECONDS


func _process(delta: float) -> void:
	if playing:
		play_elapsed += delta
		if play_elapsed >= _play_interval():
			play_elapsed = 0
			select_pose(direction, posmod(frame + 1, dataset.frame_count(sequence_id)))
			playing = true
			play_button.text = "❚❚ Pause"


func _unhandled_key_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or canvas == null or document == null:
		return
	var focused := get_viewport().gui_get_focus_owner()
	if focused is LineEdit or focused is TextEdit:
		return
	if event.ctrl_pressed:
		if event.keycode == KEY_S:
			save_corrections()
		elif event.keycode == KEY_Z:
			if event.shift_pressed:
				redo()
			else:
				undo()
		elif event.keycode == KEY_Y:
			redo()
		else:
			return
	elif event.keycode in [KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN]:
		stop_play()
		var delta: Vector2 = {KEY_LEFT: Vector2.LEFT, KEY_RIGHT: Vector2.RIGHT, KEY_UP: Vector2.UP, KEY_DOWN: Vector2.DOWN}[event.keycode]
		document.begin_edit(direction, frame, canvas.link_mirror)
		document.move_joint(direction, frame, selected, document.point(direction, frame, selected) + delta * (0.1 if event.shift_pressed else 1.0), canvas.link_mirror)
		document.commit_edit()
		after_edit()
	elif event.keycode in [KEY_A, KEY_PAGEUP]:
		step_frame(-1)
	elif event.keycode in [KEY_D, KEY_PAGEDOWN]:
		step_frame(1)
	elif event.keycode == KEY_F:
		canvas.fit_view()
	elif event.keycode == KEY_SPACE:
		toggle_play()
	else:
		return
	get_viewport().set_input_as_handled()


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.ctrl_pressed and event.keycode == KEY_S and canvas != null and document != null:
		save_corrections()
		get_viewport().set_input_as_handled()


func set_status(text: String) -> void:
	if status != null:
		status.text = text
		status.tooltip_text = text


## saved_at_utc as a sortable number; unreadable files sort first (INF) so they are surfaced, never replaced.
func correction_timestamp(path: String) -> float:
	var parser := JSON.new()
	if parser.parse(FileAccess.get_file_as_string(path)) != OK or not parser.data is Dictionary:
		return INF
	var parsed: Dictionary = parser.data
	var stamp: Variant = parsed.get("saved_at_utc")
	if not stamp is String:
		return float(FileAccess.get_modified_time(path))
	return Time.get_unix_time_from_datetime_string(String(stamp).trim_suffix("Z"))


func _preserve_current() -> bool:
	canvas.finish_drag()
	if not document.pending.is_empty():
		document.commit_edit()
	if document.dirty and (not autosave_allowed or not document.save_to(auto_path, false)):
		set_status("Could not save before leaving. Use Save As first.")
		return false
	return true


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		if document != null and canvas != null and not testing and not _preserve_current():
			return
		get_tree().quit()

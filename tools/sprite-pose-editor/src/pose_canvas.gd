extends Control
## Zoomable sprite view with draggable joints. Coordinates in "native" space are
## canvas pixels of the dataset (x right, y down), independent of zoom and pan.

signal joint_selected(name: String)
signal edit_finished
signal zoom_changed(value: float)
signal keyboard_input(event: InputEvent)

var document                          # document.gd instance
var direction: int = 0
var frame: int = 0
var selected: String = ""
var sprite: Texture2D
var sprite_bounds := Rect2(0, 0, 1, 1)
var zoom: float = 4.0
var center := Vector2.ZERO
var show_bones: bool = true
var show_labels: bool = true
var show_grid: bool = false
var show_original: bool = false
var snap_pixels: bool = false
var link_mirror: bool = false
var opacity: float = 1.0
var dragging: bool = false
var panning: bool = false
var drag_offset := Vector2.ZERO
## Refit on resize until the user zooms or pans (the first fit can happen before layout).
var auto_fit: bool = true


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	focus_mode = Control.FOCUS_ALL
	clip_contents = true
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	resized.connect(_on_resized)


## Shows a pose; returns false when its sprite cannot be loaded.
func set_pose(d: int, f: int) -> bool:
	finish_drag()
	direction = d
	frame = f
	var record: Dictionary = document.dataset.frame(document.sequence_id, d, f)
	sprite = document.dataset.texture_for(record)
	if sprite == null:
		push_error("Cannot load sprite for %s" % str(record.get("frame_id", "%d:%d" % [d, f])))
		queue_redraw()
		return false
	sprite_bounds = document.dataset.bounds_for(record)
	auto_fit = true
	fit_view()
	return true


func _on_resized() -> void:
	if auto_fit and sprite != null:
		fit_view()
	queue_redraw()


## Centres and zooms onto the sprite's opaque bounds.
func fit_view() -> void:
	center = sprite_bounds.get_center()
	zoom = clampf(minf(maxf(size.x - 150, 200) / (sprite_bounds.size.x + 14), maxf(size.y - 130, 200) / (sprite_bounds.size.y + 14)), 1, 48)
	zoom_changed.emit(zoom)
	queue_redraw()


func to_screen(point: Vector2) -> Vector2:
	return size * 0.5 + (point - center) * zoom


func to_native(point: Vector2) -> Vector2:
	return center + (point - size * 0.5) / zoom


func color_for(name: String) -> Color:
	return document.dataset.color_for(name)


## Screen-space endpoints of every drawn connection, in edge order.
func line_segments() -> Array:
	var result := []
	if document == null:
		return result
	for edge in document.dataset.edges():
		result.append([to_screen(document.point(direction, frame, edge[0])), to_screen(document.point(direction, frame, edge[1]))])
	return result


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color("151b23"))
	if document == null or not document.has_pose(direction, frame):
		return
	for x in range(0, int(size.x), 32):
		draw_line(Vector2(x, 0), Vector2(x, size.y), Color(0.3, 0.4, 0.5, 0.06))
	for y in range(0, int(size.y), 32):
		draw_line(Vector2(0, y), Vector2(size.x, y), Color(0.3, 0.4, 0.5, 0.06))
	var canvas_size := Vector2(document.dataset.width(), document.dataset.height())
	draw_rect(Rect2(to_screen(Vector2.ZERO), canvas_size * zoom), Color(1, 1, 1, 0.08), false, 1.0)
	if sprite != null:
		draw_texture_rect(sprite, Rect2(to_screen(Vector2.ZERO), canvas_size * zoom), false, Color(1, 1, 1, opacity))
	if show_grid and zoom >= 5:
		var lo := to_native(Vector2.ZERO).floor().clamp(Vector2.ZERO, canvas_size)
		var hi := to_native(size).ceil().clamp(Vector2.ZERO, canvas_size)
		for x in range(int(lo.x), int(hi.x) + 1):
			draw_line(to_screen(Vector2(x, lo.y)), to_screen(Vector2(x, hi.y)), Color(1, 1, 1, 0.1))
		for y in range(int(lo.y), int(hi.y) + 1):
			draw_line(to_screen(Vector2(lo.x, y)), to_screen(Vector2(hi.x, y)), Color(1, 1, 1, 0.1))
	var edges: Array = document.dataset.edges()
	if show_original:
		var original: Dictionary = document.baseline_pose(direction, frame)
		if not original.is_empty():
			for edge in edges:
				var a: Dictionary = original.joints.get(edge[0], {})
				var b: Dictionary = original.joints.get(edge[1], {})
				if not a.is_empty() and not b.is_empty():
					draw_line(to_screen(Vector2(a.x, a.y)), to_screen(Vector2(b.x, b.y)), Color(1, 1, 1, 0.24), 1.0, true)
	if not show_bones:
		return
	for edge in edges:
		var a := to_screen(document.point(direction, frame, edge[0]))
		var b := to_screen(document.point(direction, frame, edge[1]))
		draw_line(a, b, Color(0, 0, 0, 0.65), 4.5, true)
		if edge[3]:
			draw_dashed_line(a, b, edge[2], 2.0, 6, true)
		else:
			draw_line(a, b, edge[2], 2.0, true)
	var font := ThemeDB.fallback_font
	var names: Array = document.dataset.joint_names()
	for i in range(names.size()):
		var name: String = names[i]
		var pos := to_screen(document.point(direction, frame, name))
		var color := color_for(name)
		if name == selected:
			draw_arc(pos, 12, 0, TAU, 32, Color.WHITE, 2, true)
		draw_circle(pos, 6, Color("11161c"))
		draw_arc(pos, 6, 0, TAU, 20, color, 2, true)
		if show_labels:
			var label_pos := pos + Vector2(10, -9)
			draw_string_outline(font, label_pos, str(i + 1), HORIZONTAL_ALIGNMENT_LEFT, -1, 14, 4, Color("10151b"))
			draw_string(font, label_pos, str(i + 1), HORIZONTAL_ALIGNMENT_LEFT, -1, 14, color)


## Nearest joint within 16 screen pixels, or "".
func pick_joint(position: Vector2) -> String:
	if not show_bones or document == null or not document.has_pose(direction, frame):
		return ""
	var picked := ""
	var distance := 16.0
	for name in document.dataset.joint_names():
		var delta := to_screen(document.point(direction, frame, name)).distance_to(position)
		if delta < distance:
			distance = delta
			picked = name
	return picked


## Ends any drag (committing it as one undo step) or pan.
func finish_drag() -> void:
	if dragging:
		dragging = false
		if document.commit_edit():
			edit_finished.emit()
	panning = false


func _gui_input(event: InputEvent) -> void:
	if document == null:
		return
	if event is InputEventKey:
		keyboard_input.emit(event)
	elif event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed:
				grab_focus()
				var name := pick_joint(event.position)
				if not name.is_empty():
					selected = name
					joint_selected.emit(name)
					drag_offset = document.point(direction, frame, name) - to_native(event.position)
					document.begin_edit(direction, frame, link_mirror)
					dragging = true
			else:
				finish_drag()
			queue_redraw()
			accept_event()
		elif event.button_index == MOUSE_BUTTON_MIDDLE:
			panning = event.pressed
			auto_fit = false
			accept_event()
		elif event.pressed and event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]:
			auto_fit = false
			var anchor := to_native(event.position)
			zoom = clampf(zoom * (1.15 if event.button_index == MOUSE_BUTTON_WHEEL_UP else 1 / 1.15), 1.0, 48.0)
			center = anchor - (event.position - size * 0.5) / zoom
			zoom_changed.emit(zoom)
			queue_redraw()
			accept_event()
	elif event is InputEventMouseMotion:
		if dragging:
			var position := to_native(event.position) + drag_offset
			if snap_pixels:
				position = position.round()
			document.move_joint(direction, frame, selected, position, link_mirror)
			queue_redraw()
			accept_event()
		elif panning:
			center -= event.relative / zoom
			queue_redraw()
			accept_event()
		else:
			mouse_default_cursor_shape = CURSOR_POINTING_HAND if not pick_joint(event.position).is_empty() else CURSOR_ARROW

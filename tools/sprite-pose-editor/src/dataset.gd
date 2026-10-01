extends RefCounted
## A SpriteMotion dataset manifest (dataset.json) plus its skeleton.
##
## Everything the editor knows about canvases, directions, sequences, frames and
## joints comes from here; nothing is assumed about any particular game.

var manifest_path: String = ""
var root_dir: String = ""
var data: Dictionary = {}
var skeleton: Dictionary = {}
var last_error: String = ""

var _frames: Dictionary = {}        # "seq|d|f" -> frame record
var _textures: Dictionary = {}      # absolute path -> ImageTexture
var _images: Dictionary = {}        # absolute path -> Image
var _joint_colors: Dictionary = {}  # joint name -> Color


## Loads a manifest from a dataset.json path or the folder that contains one.
func load_manifest(path: String) -> bool:
	var resolved := path.strip_edges().replace("\\", "/")
	if resolved.is_empty():
		last_error = "No dataset path given."
		return false
	if DirAccess.dir_exists_absolute(resolved):
		resolved = resolved.path_join("dataset.json")
	if not FileAccess.file_exists(resolved):
		last_error = "Dataset manifest not found: " + resolved
		return false
	var value: Variant = read_json(resolved)
	if value == null:
		return false
	if not _validate_manifest(value):
		return false
	manifest_path = resolved
	root_dir = resolved.get_base_dir()
	data = value
	var skeleton_value: Variant = read_json(resolve(String(data.skeleton)))
	if skeleton_value == null:
		return false
	if not _validate_skeleton(skeleton_value):
		return false
	skeleton = skeleton_value
	_index()
	return true


## Reads and parses a JSON file, setting last_error on failure.
func read_json(path: String) -> Variant:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		last_error = "Cannot read " + path
		return null
	var parser := JSON.new()
	if parser.parse(file.get_as_text()) != OK:
		last_error = "Invalid JSON in %s (line %d)" % [path, parser.get_error_line()]
		return null
	return parser.data


func _validate_manifest(value: Variant) -> bool:
	if not value is Dictionary or value.get("schema") != "spritemotion.dataset":
		last_error = "Not a SpriteMotion dataset manifest (schema spritemotion.dataset)."
		return false
	for key in ["dataset_id", "canvas", "directions", "skeleton", "sequences"]:
		if not value.has(key):
			last_error = "Dataset manifest is missing '%s'." % key
			return false
	var canvas: Variant = value.canvas
	if not canvas is Dictionary or not _is_int(canvas.get("width")) or not _is_int(canvas.get("height")) \
			or int(canvas.width) < 1 or int(canvas.height) < 1:
		last_error = "Dataset canvas needs integer width and height."
		return false
	if not value.directions is Array or value.directions.is_empty():
		last_error = "Dataset needs at least one direction."
		return false
	var ids := {}
	for item in value.directions:
		if not item is Dictionary or not _is_int(item.get("id")) or not item.get("name") is String:
			last_error = "Every direction needs an integer id and a name."
			return false
		ids[int(item.id)] = true
	for item in value.directions:
		if item.has("mirror_of") and not ids.has(int(item.mirror_of)):
			last_error = "Direction %s mirrors unknown direction %s." % [item.name, str(item.mirror_of)]
			return false
	if not value.sequences is Array or value.sequences.is_empty():
		last_error = "Dataset needs at least one sequence."
		return false
	for sequence in value.sequences:
		if not sequence is Dictionary or not sequence.get("id") is String or not _is_int(sequence.get("frame_count")) \
				or not sequence.get("frames") is Array:
			last_error = "Every sequence needs an id, frame_count and frames."
			return false
		for record in sequence.frames:
			if not record is Dictionary or not _is_int(record.get("direction")) or not _is_int(record.get("frame")) \
					or not record.get("image") is String or not record.get("frame_id") is String:
				last_error = "Invalid frame record in sequence %s." % sequence.id
				return false
			if not ids.has(int(record.direction)) or int(record.frame) < 0 or int(record.frame) >= int(sequence.frame_count):
				last_error = "Frame %s is out of range." % record.frame_id
				return false
	return true


func _validate_skeleton(value: Variant) -> bool:
	if not value is Dictionary or value.get("schema") != "spritemotion.skeleton" or not value.get("joints") is Array \
			or value.joints.is_empty():
		last_error = "Skeleton file is not a spritemotion.skeleton with joints."
		return false
	var names := {}
	for joint in value.joints:
		if not joint is Dictionary or not joint.get("name") is String or String(joint.name).is_empty() or names.has(joint.name):
			last_error = "Skeleton joints need unique names."
			return false
		names[joint.name] = true
	for chain in value.get("chains", []):
		for name in chain.get("joints", []):
			if not names.has(name):
				last_error = "Skeleton chain uses unknown joint %s." % name
				return false
	for pair in value.get("inferred_connections", []):
		for name in pair:
			if not names.has(name):
				last_error = "Skeleton connection uses unknown joint %s." % name
				return false
	return true


func _index() -> void:
	_frames.clear()
	_joint_colors.clear()
	for sequence in data.sequences:
		for record in sequence.frames:
			_frames[_key(String(sequence.id), int(record.direction), int(record.frame))] = record
	for chain in skeleton.get("chains", []):
		for name in chain.joints:
			if not _joint_colors.has(name):
				_joint_colors[name] = Color(String(chain.get("color", "#ffffff")))


static func _is_int(value: Variant) -> bool:
	return (value is int or value is float) and float(value) == floor(float(value))


static func _key(sequence_id: String, direction: int, frame: int) -> String:
	return "%s|%d|%d" % [sequence_id, direction, frame]


## Absolute path for a manifest-relative path.
func resolve(relative: String) -> String:
	if relative.is_absolute_path():
		return relative
	return root_dir.path_join(relative).simplify_path()


func title() -> String:
	return String(data.get("title", data.dataset_id))


func width() -> int:
	return int(data.canvas.width)


func height() -> int:
	return int(data.canvas.height)


## Clamp bounds for joint coordinates: [0, width-1] x [0, height-1].
func max_point() -> Vector2:
	return Vector2(width() - 1, height() - 1)


func mirror_axis_x() -> float:
	return float(data.canvas.get("mirror_axis_x", (width() - 1) / 2.0))


func mirror_x(x: float) -> float:
	return 2.0 * mirror_axis_x() - x


func directions() -> Array:
	return data.directions


func direction_ids() -> Array:
	var result := []
	for item in data.directions:
		result.append(int(item.id))
	return result


func direction_name(direction: int) -> String:
	for item in data.directions:
		if int(item.id) == direction:
			return String(item.name)
	return "d%d" % direction


## Mirror partner of a direction, or -1 when it has none.
func mirror_of(direction: int) -> int:
	for item in data.directions:
		if int(item.id) == direction and item.has("mirror_of"):
			return int(item.mirror_of)
	return -1


func sequences() -> Array:
	return data.sequences


func sequence(sequence_id: String) -> Dictionary:
	for item in data.sequences:
		if String(item.id) == sequence_id:
			return item
	return {}


func frame_count(sequence_id: String) -> int:
	return int(sequence(sequence_id).get("frame_count", 0))


## Manifest frame record, or an empty dictionary when the frame does not exist.
func frame(sequence_id: String, direction: int, frame_index: int) -> Dictionary:
	return _frames.get(_key(sequence_id, direction, frame_index), {})


func has_frame(sequence_id: String, direction: int, frame_index: int) -> bool:
	return _frames.has(_key(sequence_id, direction, frame_index))


func joint_names() -> Array:
	var result := []
	for joint in skeleton.joints:
		result.append(String(joint.name))
	return result


func joint_label(name: String) -> String:
	for joint in skeleton.joints:
		if joint.name == name:
			return String(joint.get("label", name.replace("_", " ")))
	return name


func color_for(name: String) -> Color:
	return _joint_colors.get(name, Color.WHITE)


## [joint_a, joint_b, color, inferred] for every drawn connection.
func edges() -> Array:
	var result := []
	for chain in skeleton.get("chains", []):
		var joints: Array = chain.joints
		for i in range(joints.size() - 1):
			result.append([String(joints[i]), String(joints[i + 1]), Color(String(chain.get("color", "#ffffff"))), false])
	for pair in skeleton.get("inferred_connections", []):
		result.append([String(pair[0]), String(pair[1]), Color("ffe45e"), true])
	return result


func annotation_dir(layer: String) -> String:
	var key := "estimates" if layer == "estimate" else "corrections"
	var dirs: Dictionary = data.get("annotations", {})
	return resolve(String(dirs.get(key, "annotations/" + key)))


func annotation_path(layer: String, sequence_id: String) -> String:
	return annotation_dir(layer).path_join(sequence_id + ".json")


func autosave_path(sequence_id: String) -> String:
	return annotation_dir("correction").path_join(sequence_id + ".autosave.json")


## Image for a frame record (cached), or null when it cannot be loaded.
func image_for(record: Dictionary) -> Image:
	if record.is_empty():
		return null
	var path := resolve(String(record.image))
	if not _images.has(path):
		var image := Image.load_from_file(path)
		if image == null or image.is_empty():
			last_error = "Cannot load sprite " + path
			return null
		if image.get_format() != Image.FORMAT_RGBA8:
			image.convert(Image.FORMAT_RGBA8)
		_images[path] = image
	return _images[path]


## Texture for a frame record (cached), or null.
func texture_for(record: Dictionary) -> Texture2D:
	var image := image_for(record)
	if image == null:
		return null
	var path := resolve(String(record.image))
	if not _textures.has(path):
		_textures[path] = ImageTexture.create_from_image(image)
	return _textures[path]


## Opaque bounds of a frame as a Rect2 (manifest bounds when present, else computed).
func bounds_for(record: Dictionary) -> Rect2:
	var bounds: Variant = record.get("bounds")
	if bounds is Array and bounds.size() == 4:
		return Rect2(float(bounds[0]), float(bounds[1]), float(bounds[2]) - float(bounds[0]), float(bounds[3]) - float(bounds[1]))
	var image := image_for(record)
	if image == null:
		return Rect2(0, 0, width(), height())
	var used := image.get_used_rect()
	if used.size == Vector2i.ZERO:
		return Rect2(0, 0, width(), height())
	return Rect2(used)

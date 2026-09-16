import bpy
import bmesh
import math

from mathutils import Matrix, Vector
from . import utilities_uv
from . import utilities_ui



class op(bpy.types.Operator):
	bl_idname = "uv.textools_unwrap_faces_iron"
	bl_label = "Iron"
	bl_description = "Unwrap selected faces into a single UV island while preserving their UV bounds"
	bl_options = {'REGISTER', 'UNDO'}

	align_to_axes: bpy.props.BoolProperty(
		name="Align to Axes",
		description="Preserve the original orientation and align a clear dominant island axis horizontally or vertically",
		default=True,
	)

	@classmethod
	def poll(cls, context):
		if not bpy.context.active_object:
			return False
		if bpy.context.active_object.type != 'MESH':
			return False
		if bpy.context.active_object.mode != 'EDIT':
			return False
		return True


	def execute(self, context):
		with utilities_uv.preserve_mesh_selection_context():
			utilities_uv.multi_object_loop(main, self, context)
		return {'FINISHED'}


def main(self, context):
	pre_selection_mode = tuple(bpy.context.scene.tool_settings.mesh_select_mode)
	me = bpy.context.active_object.data

	bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type='FACE')
	bm = bmesh.from_edit_mesh(me)
	bm.faces.ensure_lookup_table()
	uv_layers = bm.loops.layers.uv.verify()
	selected_face_indices = [face.index for face in bm.faces if face.select]
	if not selected_face_indices:
		bpy.context.scene.tool_settings.mesh_select_mode = pre_selection_mode
		self.report({'WARNING'}, "Select faces to iron")
		return
	selected_faces = [bm.faces[index] for index in selected_face_indices]
	original_points = [loop[uv_layers].uv.copy() for face in selected_faces for loop in face.loops]
	original_bounds = _uv_bounds(selected_faces, uv_layers)

	bpy.ops.mesh.mark_seam(clear=True)

	# Hard edges to seams
	bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type='EDGE')
	bpy.ops.mesh.region_to_loop()
	bpy.ops.mesh.mark_seam(clear=False)

	bm = bmesh.from_edit_mesh(me)
	bm.faces.ensure_lookup_table()
	seams = False
	for face_index in selected_face_indices:
		face = bm.faces[face_index]
		face.select_set(True)
		if not seams:
			for edge in face.edges:
				if edge.seam:
					seams = True
					break
	if not seams:
		self.report({'INFO'}, "Unwrap not possible; don't select the entire object if it is manifold")
		bpy.context.scene.tool_settings.mesh_select_mode = pre_selection_mode
		return

	padding = utilities_ui.get_padding()
	bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=padding)

	# UV operators may rebuild the edit BMesh. Reacquire faces by their stable
	# indices, then fit the result back into the exact original bounds.
	bm = bmesh.from_edit_mesh(me)
	bm.faces.ensure_lookup_table()
	uv_layers = bm.loops.layers.uv.verify()
	selected_faces = [bm.faces[index] for index in selected_face_indices]
	_stabilize_orientation(selected_faces, uv_layers, original_points, self.align_to_axes)
	_restore_uv_bounds(selected_faces, uv_layers, original_bounds)
	bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)

	bpy.context.scene.tool_settings.mesh_select_mode = pre_selection_mode


def _uv_bounds(faces, uv_layer):
	coords = [loop[uv_layer].uv for face in faces for loop in face.loops]
	return (
		min(uv.x for uv in coords),
		max(uv.x for uv in coords),
		min(uv.y for uv in coords),
		max(uv.y for uv in coords),
	)


def _restore_uv_bounds(faces, uv_layer, original_bounds):
	faces = list(faces)
	new_min_x, new_max_x, new_min_y, new_max_y = _uv_bounds(faces, uv_layer)
	original_min_x, original_max_x, original_min_y, original_max_y = original_bounds
	new_width = new_max_x - new_min_x
	new_height = new_max_y - new_min_y
	original_width = original_max_x - original_min_x
	original_height = original_max_y - original_min_y

	for face in faces:
		for loop in face.loops:
			uv = loop[uv_layer].uv
			uv.x = (
				original_min_x + (uv.x - new_min_x) * original_width / new_width
				if new_width > 1e-12
				else original_min_x
			)
			uv.y = (
				original_min_y + (uv.y - new_min_y) * original_height / new_height
				if new_height > 1e-12
				else original_min_y
			)


def _stabilize_orientation(faces, uv_layer, original_points, align_to_axes):
	loops = [loop for face in faces for loop in face.loops]
	new_points = [loop[uv_layer].uv.copy() for loop in loops]
	if len(new_points) != len(original_points) or not new_points:
		return

	new_center = sum(new_points, Vector((0.0, 0.0))) / len(new_points)
	original_center = sum(original_points, Vector((0.0, 0.0))) / len(original_points)
	dot = 0.0
	cross = 0.0
	for new_point, original_point in zip(new_points, original_points):
		new_delta = new_point - new_center
		original_delta = original_point - original_center
		dot += new_delta.dot(original_delta)
		cross += new_delta.x * original_delta.y - new_delta.y * original_delta.x

	if abs(dot) + abs(cross) > 1e-12:
		_match_angle = math.atan2(cross, dot)
		_rotate_loops(loops, uv_layer, new_center, _match_angle)

	if not align_to_axes:
		return

	# Snap a clearly elongated island's principal direction to its nearest UV
	# axis. Near-radial islands deliberately skip this because their rotation
	# is undefined and attempting to align them would reintroduce randomness.
	points = [loop[uv_layer].uv - new_center for loop in loops]
	cov_xx = sum(point.x * point.x for point in points)
	cov_yy = sum(point.y * point.y for point in points)
	cov_xy = sum(point.x * point.y for point in points)
	discriminant = math.sqrt((cov_xx - cov_yy) ** 2 + 4.0 * cov_xy * cov_xy)
	major = (cov_xx + cov_yy + discriminant) * 0.5
	minor = (cov_xx + cov_yy - discriminant) * 0.5
	if major <= 1e-12 or major < max(minor, 0.0) * 1.1:
		return

	principal_angle = 0.5 * math.atan2(2.0 * cov_xy, cov_xx - cov_yy)
	axis_correction = -principal_angle
	while axis_correction > math.pi * 0.25:
		axis_correction -= math.pi * 0.5
	while axis_correction < -math.pi * 0.25:
		axis_correction += math.pi * 0.5
	_rotate_loops(loops, uv_layer, new_center, axis_correction)


def _rotate_loops(loops, uv_layer, center, angle):
	if abs(angle) <= 1e-12:
		return
	rotation = Matrix.Rotation(angle, 2)
	for loop in loops:
		loop[uv_layer].uv = center + rotation @ (loop[uv_layer].uv - center)

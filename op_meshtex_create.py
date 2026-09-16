import bmesh
import bpy

from . import op_select_islands_outline
from . import utilities_uv
from .services import uv_morph_service


_RELAX_ISLAND_LAYER = "_textools_relax_island"
_ORIGINAL_FACE_LAYER = "_textools_original_face"


def _tag_relax_faces(bm, faces_by_island):
    """Persist island and source-face identity across edit-mode topology operators."""
    bm.faces.ensure_lookup_table()
    bm.faces.index_update()
    island_face_indices = [[face.index for face in faces] for faces in faces_by_island]
    island_layer = bm.faces.layers.int.get(_RELAX_ISLAND_LAYER)
    if island_layer is None:
        island_layer = bm.faces.layers.int.new(_RELAX_ISLAND_LAYER)
    original_layer = bm.faces.layers.int.get(_ORIGINAL_FACE_LAYER)
    if original_layer is None:
        original_layer = bm.faces.layers.int.new(_ORIGINAL_FACE_LAYER)

    for face in bm.faces:
        face[island_layer] = 0
        face[original_layer] = face.index + 1
    bm.faces.ensure_lookup_table()
    for island_index, face_indices in enumerate(island_face_indices, start=1):
        for face_index in face_indices:
            bm.faces[face_index][island_layer] = island_index
    return _get_tagged_relax_faces(bm)


def _get_tagged_relax_faces(bm):
    """Reacquire valid BMFace handles after an operator rebuilt the edit BMesh."""
    island_layer = bm.faces.layers.int.get(_RELAX_ISLAND_LAYER)
    if island_layer is None:
        return []
    island_count = max((face[island_layer] for face in bm.faces), default=0)
    faces_by_island = [[] for _ in range(island_count)]
    for face in bm.faces:
        island_index = face[island_layer]
        if island_index > 0:
            faces_by_island[island_index - 1].append(face)
    return faces_by_island


class op(bpy.types.Operator):
    bl_idname = "uv.textools_meshtex_create"
    bl_label = "UV Mesh"
    bl_description = "Create a new Mesh from the selected UVs of the active Object"
    bl_options = {'REGISTER', 'UNDO'}

    # apply_scale : bpy.props.BoolProperty(name="Scale to Object", default=True, description="Apply scale to the UV Mesh for its extent to be similar to the Object dimensions.")

    @classmethod
    def poll(cls, context):
        if not bpy.context.active_object:
            return False
        if bpy.context.active_object.type != 'MESH':
            return False
        if not bpy.context.object.data.uv_layers:
            return False
        return True

    def execute(self, context):
        if context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        obj = context.active_object
        service_mod_name = uv_morph_service.MOD_NAME
        added_temp = False

        if service_mod_name not in obj.modifiers:
            uv_morph_service.toggle_uv_morph_modifier(obj)
            added_temp = True

        try:
            new_obj = uv_morph_service.execute_bake_process(context, obj)
            self.report({'INFO'}, "UV Mesh Baked: " + new_obj.name)
        except Exception as e:
            self.report({'ERROR'}, f"Bake failed: {str(e)}")
            if added_temp and service_mod_name in obj.modifiers:
                obj.modifiers.remove(obj.modifiers[service_mod_name])
            return {'CANCELLED'}

        if added_temp and service_mod_name in obj.modifiers:
            obj.modifiers.remove(obj.modifiers[service_mod_name])

        return {'FINISHED'}


def create_uv_mesh(self, context, obj, sk_create=True, bool_scale=True, delete_unselected=True, restore_selected=False):
    # New object management
    mode = bpy.context.active_object.mode
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')

    mesh_obj = obj.copy()
    mesh_obj.data = obj.data.copy()
    obj.users_collection[0].objects.link(mesh_obj)

    mesh_obj.select_set(state=True, view_layer=None)
    bpy.context.view_layer.objects.active = mesh_obj

    obj_name = mesh_obj.name = obj.name + "_UV_Mesh"

    # Shape Keys management
    if mesh_obj.data.shape_keys:
        if len(mesh_obj.data.shape_keys.key_blocks) > 1:
            for i in range(len(mesh_obj.data.shape_keys.key_blocks)):
                bpy.context.object.active_shape_key_index = 0
                bpy.ops.object.shape_key_remove(all=False)

    bpy.ops.object.mode_set(mode='EDIT')

    selection_mode = bpy.context.scene.tool_settings.uv_select_mode
    pre_sync = bpy.context.scene.tool_settings.use_uv_select_sync
    uv_area = next((a for a in context.screen.areas if a.type == 'IMAGE_EDITOR'), None)
    if pre_sync == True:
        bpy.context.scene.tool_settings.use_uv_select_sync = False
        if uv_area:
            try:
                with context.temp_override(area=uv_area):
                    bpy.ops.uv.select_all(action='SELECT')
            except:
                pass

    if mode == 'OBJECT':
        bpy.ops.mesh.select_all(action='SELECT')
        if uv_area:
            try:
                with context.temp_override(area=uv_area):
                    bpy.ops.uv.select_all(action='SELECT')
            except:
                pass

    if uv_area:
        try:
            with context.temp_override(area=uv_area):
                bpy.ops.uv.select_split()
        except:
            pass

    bm = bmesh.from_edit_mesh(mesh_obj.data)
    uv_layers = bm.loops.layers.uv.verify()

    faces_by_island = utilities_uv.getSelectionIslands(bm, uv_layers, need_faces_selected=False)
    bm = bmesh.from_edit_mesh(mesh_obj.data)
    uv_layers = bm.loops.layers.uv.verify()

    if not faces_by_island:
        bpy.data.objects.remove(bpy.data.objects[obj_name], do_unlink=True)
        obj.select_set(state=True, view_layer=None)
        bpy.context.view_layer.objects.active = obj
        bpy.context.scene.tool_settings.use_uv_select_sync = pre_sync
        bpy.ops.object.mode_set(mode=mode)
        if not restore_selected:
            return {'CANCELLED'}
        else:  # For the Relax operator
            return {'CANCELLED'}, None, None

    if restore_selected:
        faces_by_island = _tag_relax_faces(bm, faces_by_island)
        uv_layers = bm.loops.layers.uv.verify()

    if delete_unselected:
        if mode != 'OBJECT':
            delete_faces = list({face for faces in faces_by_island for face in faces}.symmetric_difference(bm.faces))
            if delete_faces:
                bmesh.ops.delete(bm, geom=delete_faces, context='FACES')
    else:  # Needed for the Relax operator
        # for face in {face for faces in faces_by_island for face in faces}.symmetric_difference(bm.faces):
        #	if face.select:
        #		face.select_set(False)
        # bpy.ops.mesh.split()
        bpy.ops.mesh.select_all(action='DESELECT')
        selection_loops = {loop for faces in faces_by_island for face in faces for loop in face.loops}
        for faces in faces_by_island:
            for face in faces:
                for edge in face.edges:
                    if not set(edge.link_loops).issubset(selection_loops):
                        edge.select_set(True)
        bpy.ops.mesh.edge_split(type='EDGE')
        bm = bmesh.from_edit_mesh(mesh_obj.data)
        uv_layers = bm.loops.layers.uv.verify()
        faces_by_island = _get_tagged_relax_faces(bm)
        bmesh.update_edit_mesh(mesh_obj.data)
        bpy.ops.mesh.select_all(action='SELECT')  # TODO REFINE

    bpy.context.scene.tool_settings.use_uv_select_sync = True
    op_select_islands_outline.select_outline(self, context, bm, uv_layers)
    bmesh.update_edit_mesh(mesh_obj.data)

    scale = 1.0
    if bool_scale:
        length_view = 0.0
        length_uv = 0.0
        for faces in faces_by_island:
            for face in faces:
                try:
                    length_uv += (face.loops[0].link_loop_next[uv_layers].uv - face.loops[0][uv_layers].uv).length
                    length_view += face.loops[0].edge.calc_length()
                except:
                    pass
        if length_uv > 0:
            scale = length_view / length_uv

    bpy.ops.mesh.edge_split(type='EDGE')
    bpy.ops.object.mode_set(mode='OBJECT')

    if sk_create:
        if not mesh_obj.data.shape_keys:
            mesh_obj.shape_key_add(name="model", from_mix=True)
        mesh_obj.shape_key_add(name="uv", from_mix=True)
        mesh_obj.active_shape_key_index = 1
        mesh_obj.data.shape_keys.key_blocks["uv"].value = 1.0

    bpy.ops.object.mode_set(mode='EDIT')

    bm = bmesh.from_edit_mesh(mesh_obj.data)
    uv_layers = bm.loops.layers.uv.verify()
    if restore_selected:
        faces_by_island = _get_tagged_relax_faces(bm)

    visited_verts = set()
    for face in bm.faces:
        for loop in face.loops:
            vert = loop.vert
            if vert not in visited_verts:
                u = loop[uv_layers].uv.x * scale
                v = loop[uv_layers].uv.y * scale
                vert.co = (u, v, 0.0)
                visited_verts.add(vert)

    bmesh.update_edit_mesh(mesh_obj.data)
    bpy.context.scene.tool_settings.use_uv_select_sync = False

    # bm.select_flush(True)
    bpy.context.scene.tool_settings.use_uv_select_sync = pre_sync

    if restore_selected:  # For the Relax operator
        bpy.ops.uv.select_all(action='DESELECT')
        for faces in faces_by_island:
            for face in faces:
                for loop in face.loops:
                    utilities_uv.set_loop_selection(loop, uv_layers, True)

    if mode == 'EDIT' and not restore_selected:
        # Workaround for selection not flushing properly from loops to EDGE Selection Mode, apparently since UV edge selection support was added to the UV space
        bpy.ops.uv.select_mode(type='VERTEX')
        bpy.context.scene.tool_settings.uv_select_mode = selection_mode
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.mode_set(mode=mode)
    else:
        bpy.ops.object.mode_set(mode=mode)

    if not restore_selected:
        return {'FINISHED'}
    else:  # For the Relax operator
        return bm, uv_layers, faces_by_island

import bmesh
import bpy
from . import utilities_uv
from .services.rectify_service import align_uv_rectify


class op(bpy.types.Operator):
    bl_idname = "uv.textools_rectify"
    bl_label = "Rectify"
    bl_description = "Align selected UV faces to rectangular distribution (Quads only)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not context.active_object:
            return False
        if context.active_object.mode != 'EDIT':
            return False
        if not context.object.data.uv_layers:
            return False
        return True

    def execute(self, context):
        active_object = context.view_layer.objects.active
        processed = False

        try:
            for obj in utilities_uv.selected_unique_objects_in_mode_with_uv():
                bm = bmesh.from_edit_mesh(obj.data)
                uv_layer = bm.loops.layers.uv.active
                if uv_layer is None:
                    continue

                selected_faces = utilities_uv.get_selected_uv_faces(bm, uv_layer)
                if not selected_faces:
                    continue

                context.view_layer.objects.active = obj
                if align_uv_rectify(
                    obj, bm, uv_layer.name, keep_bounds=True, target_faces=selected_faces
                ):
                    bmesh.update_edit_mesh(obj.data)
                    processed = True
        finally:
            context.view_layer.objects.active = active_object

        if not processed:
            self.report({'WARNING'}, "No quads selected or operation failed.")
            return {'CANCELLED'}

        return {'FINISHED'}

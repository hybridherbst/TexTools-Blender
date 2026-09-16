import bmesh
import bpy

from . import utilities_uv
from .services.grid_straighten_service import straighten_uv_grid


class op(bpy.types.Operator):
    bl_idname = "uv.textools_island_grid_straighten"
    bl_label = "Grid Straighten"
    bl_description = "Make selected UV edge loops horizontal and vertical while preserving their distribution"
    bl_options = {'REGISTER', 'UNDO'}

    relax: bpy.props.BoolProperty(
        name="Surface Relax",
        description="Redistribute grid lines to minimize 3D face-aspect error",
        default=False,
    )

    free_boundary: bpy.props.EnumProperty(
        name="Movable Boundary",
        description="Optionally release one outer boundary so both UV axes can use one surface scale",
        items=(
            ('LOCKED', "Fixed AABB", "Keep all four sides of the UV bounding box unchanged"),
            ('AUTO', "Auto (Least Straight)", "Release the boundary that was least straight before the operation"),
            ('TOP', "Top", "Keep left, right, and bottom fixed; allow the top boundary to move"),
            ('BOTTOM', "Bottom", "Keep left, right, and top fixed; allow the bottom boundary to move"),
            ('LEFT', "Left", "Keep right, top, and bottom fixed; allow the left boundary to move"),
            ('RIGHT', "Right", "Keep left, top, and bottom fixed; allow the right boundary to move"),
        ),
        default='AUTO',
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "relax")
        if self.relax:
            layout.prop(self, "free_boundary")

    @classmethod
    def poll(cls, context):
        return (
            context.active_object
            and context.active_object.type == 'MESH'
            and context.active_object.mode == 'EDIT'
            and context.active_object.data.uv_layers
        )

    def execute(self, context):
        processed = False
        for obj in utilities_uv.selected_unique_objects_in_mode_with_uv():
            bm = bmesh.from_edit_mesh(obj.data)
            uv_layer = bm.loops.layers.uv.active
            if uv_layer is None or not straighten_uv_grid(
                obj,
                bm,
                uv_layer.name,
                self.relax,
                self.free_boundary,
            ):
                continue
            bmesh.update_edit_mesh(obj.data)
            processed = True

        if not processed:
            self.report({'WARNING'}, "Select a connected grid of UV edges.")
            return {'CANCELLED'}
        return {'FINISHED'}

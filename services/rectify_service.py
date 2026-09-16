# SPDX-License-Identifier: GPL-3.0-or-later

import bmesh
import bpy
from bmesh.types import BMesh
from bpy.types import Object


def align_uv_rectify(
    obj: Object,
    bm: BMesh,
    uv_layer_name: str,
    keep_bounds: bool = False,
    target_faces=None,
):
    """
    Rectify logic as a wrapper for Blender's native 'follow_active_quads'.

    NOTE: Only processes Quads. Triangles and N-gons are explicitly excluded
    to prevent UV layout distortion during normalization.
    """
    mesh_data = obj.data
    uv_layer = bm.loops.layers.uv.get(uv_layer_name)
    if uv_layer is None:
        print(f"Error: UV layer '{uv_layer_name}' not found.")
        return False

    if target_faces is None:
        target_faces = [f for f in bm.faces if f.select]
    target_faces = [f for f in target_faces if len(f.verts) == 4]

    if not target_faces:
        return False

    bm.faces.index_update()
    target_face_indices = {face.index for face in target_faces}

    orig_bounds = _get_uv_bounds(target_faces, uv_layer) if keep_bounds else None

    active_face = bm.faces.active
    if not active_face or active_face not in target_faces:
        active_face = target_faces[0]
        bm.faces.active = active_face

    _rectify_active_face(active_face, uv_layer)

    bmesh.update_edit_mesh(mesh_data)

    try:
        bpy.ops.uv.follow_active_quads(mode="EVEN")
    except RuntimeError:
        return False

    returned_bmesh: BMesh = bmesh.from_edit_mesh(mesh_data)
    uv_layer = returned_bmesh.loops.layers.uv.get(uv_layer_name)
    returned_bmesh.faces.ensure_lookup_table()
    selected_faces = [returned_bmesh.faces[index] for index in target_face_indices]

    if not selected_faces:
        return True

    current_bounds = _get_uv_bounds(selected_faces, uv_layer)
    if current_bounds:
        _apply_uv_remap(selected_faces, uv_layer, current_bounds, orig_bounds)

    bmesh.update_edit_mesh(mesh_data)
    return True


def _rectify_active_face(face, uv_layer):
    """Make the seed quad axis-aligned without changing its UV orientation."""
    loops = list(face.loops)
    coords = {loop: loop[uv_layer].uv.copy() for loop in loops}
    min_x = min(uv.x for uv in coords.values())
    max_x = max(uv.x for uv in coords.values())
    min_y = min(uv.y for uv in coords.values())
    max_y = max(uv.y for uv in coords.values())

    # Pairing by height mirrors TexTools' original Rectify behavior and keeps
    # the existing top/bottom and left/right orientation of the UV patch.
    by_height = sorted(loops, key=lambda loop: coords[loop].y, reverse=True)
    upper = sorted(by_height[:2], key=lambda loop: coords[loop].x)
    lower = sorted(by_height[2:], key=lambda loop: coords[loop].x)

    upper[0][uv_layer].uv = (min_x, max_y)
    upper[1][uv_layer].uv = (max_x, max_y)
    lower[0][uv_layer].uv = (min_x, min_y)
    lower[1][uv_layer].uv = (max_x, min_y)


def _get_uv_bounds(faces, uv_layer):
    min_x, max_x = float("inf"), float("-inf")
    min_y, max_y = float("inf"), float("-inf")
    has_verts = False
    for face in faces:
        for loop in face.loops:
            u, v = loop[uv_layer].uv
            if u < min_x:
                min_x = u
            if u > max_x:
                max_x = u
            if v < min_y:
                min_y = v
            if v > max_y:
                max_y = v
            has_verts = True
    return (min_x, max_x, min_y, max_y) if has_verts else None


def _apply_uv_remap(faces, uv_layer, src_bounds, dst_bounds=None):
    s_min_x, s_max_x, s_min_y, s_max_y = src_bounds
    width = s_max_x - s_min_x
    height = s_max_y - s_min_y
    if width == 0:
        width = 1
    if height == 0:
        height = 1

    if dst_bounds:
        d_min_x, d_max_x, d_min_y, d_max_y = dst_bounds
        d_width = d_max_x - d_min_x
        d_height = d_max_y - d_min_y
        for face in faces:
            for loop in face.loops:
                u, v = loop[uv_layer].uv
                loop[uv_layer].uv = (
                    ((u - s_min_x) / width) * d_width + d_min_x,
                    ((v - s_min_y) / height) * d_height + d_min_y,
                )
    else:
        for face in faces:
            for loop in face.loops:
                u, v = loop[uv_layer].uv
                loop[uv_layer].uv = ((u - s_min_x) / width, (v - s_min_y) / height)

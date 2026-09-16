# SPDX-License-Identifier: GPL-3.0-or-later

from collections import defaultdict
import math
from typing import NamedTuple

from bmesh.types import BMLoop, BMesh
from bpy.types import Object
from mathutils import Vector

from .. import utilities_uv

UVKey = tuple[float, float, int]
AdjacencyGraph = dict[UVKey, set[UVKey]]


class UVNodeData(NamedTuple):
    uv: Vector
    loops: list[BMLoop]


class UVEdgeData(NamedTuple):
    first: UVKey
    second: UVKey
    surface_length: float


def straighten_uv_grid(
    obj: Object,
    bm: BMesh,
    uv_layer_name: str,
    relax: bool = False,
    free_boundary: str = 'LOCKED',
) -> bool:
    """Make selected UV rows/columns orthogonal, optionally redistributing them from surface lengths."""
    uv_layer = bm.loops.layers.uv.get(uv_layer_name)
    if uv_layer is None:
        return False

    node_data, edges = _collect_selection(obj, bm, uv_layer)
    if not edges:
        return False

    updates: dict[UVKey, Vector] = {}
    for grid_nodes in _selected_grid_components(edges):
        grid_edges = [
            edge for edge in edges if edge.first in grid_nodes and edge.second in grid_nodes
        ]
        _collect_grid_updates(
            bm,
            uv_layer,
            grid_edges,
            node_data,
            relax,
            free_boundary,
            updates,
        )

    for key, new_uv in updates.items():
        for loop in node_data[key].loops:
            loop[uv_layer].uv = new_uv

    return bool(updates)


def _selected_grid_components(edges):
    graph: AdjacencyGraph = {}
    for edge in edges:
        graph.setdefault(edge.first, set()).add(edge.second)
        graph.setdefault(edge.second, set()).add(edge.first)
    return [set(component) for component in _connected_components(graph)]


def _collect_grid_updates(
    bm,
    uv_layer,
    edges,
    node_data,
    relax,
    free_boundary,
    updates,
):
    grid_keys = {key for edge in edges for key in (edge.first, edge.second)}
    grid_node_data = {key: node_data[key] for key in grid_keys}
    horizontal_graph, vertical_graph, horizontal_edges, vertical_edges = _split_by_axis(
        edges, grid_node_data
    )
    horizontal_components = _connected_components(horizontal_graph)
    vertical_components = _connected_components(vertical_graph)
    if not horizontal_components and not vertical_components:
        return

    horizontal_targets = _component_targets(horizontal_components, grid_node_data, axis=1)
    vertical_targets = _component_targets(vertical_components, grid_node_data, axis=0)

    if relax:
        horizontal_targets, vertical_targets = _relaxed_grid_targets(
            bm,
            uv_layer,
            horizontal_components,
            vertical_components,
            horizontal_edges,
            vertical_edges,
            grid_node_data,
            free_boundary,
        )

    for component, target_y in zip(horizontal_components, horizontal_targets):
        for key in component:
            updates.setdefault(key, grid_node_data[key].uv.copy()).y = target_y

    for component, target_x in zip(vertical_components, vertical_targets):
        for key in component:
            updates.setdefault(key, grid_node_data[key].uv.copy()).x = target_x


def _collect_selection(obj, bm, uv_layer) -> tuple[dict[UVKey, UVNodeData], list[UVEdgeData]]:
    node_data: dict[UVKey, UVNodeData] = {}

    for face in bm.faces:
        for loop in face.loops:
            if not utilities_uv.get_loop_selection(loop, uv_layer, bm=bm):
                continue
            key = _uv_key(loop, uv_layer)
            if key not in node_data:
                node_data[key] = UVNodeData(loop[uv_layer].uv.copy(), [])
            node_data[key].loops.append(loop)

    edges = []
    handled = set()
    world_matrix = obj.matrix_world
    for key, data in node_data.items():
        for loop in data.loops:
            if not utilities_uv.get_loop_edge_selection(loop, uv_layer):
                continue
            next_loop = loop.link_loop_next
            next_key = _uv_key(next_loop, uv_layer)
            if next_key not in node_data:
                continue

            edge_key = frozenset((key, next_key))
            if edge_key in handled:
                continue
            handled.add(edge_key)

            first_co = world_matrix @ loop.vert.co
            second_co = world_matrix @ next_loop.vert.co
            edges.append(UVEdgeData(key, next_key, (second_co - first_co).length))

    return node_data, edges


def _uv_key(loop, uv_layer) -> UVKey:
    uv = loop[uv_layer].uv
    return round(uv.x, 6), round(uv.y, 6), loop.vert.index


def _split_by_axis(edges, node_data):
    horizontal_graph: AdjacencyGraph = {}
    vertical_graph: AdjacencyGraph = {}
    horizontal_edges = []
    vertical_edges = []

    # Treat perpendicular grid edges as the same orientation modulo 90 degrees.
    # This derives the two families from the grid itself, so a grid rotated by
    # 45 degrees cannot have both families classified against the same UV axis.
    orientation_x = 0.0
    orientation_y = 0.0
    longest_delta = None
    for edge in edges:
        delta = node_data[edge.second].uv - node_data[edge.first].uv
        if delta.length_squared <= 1e-24:
            continue
        angle = math.atan2(delta.y, delta.x)
        orientation_x += math.cos(4.0 * angle) * delta.length
        orientation_y += math.sin(4.0 * angle) * delta.length
        if longest_delta is None or delta.length_squared > longest_delta.length_squared:
            longest_delta = delta

    if longest_delta is None:
        return horizontal_graph, vertical_graph, horizontal_edges, vertical_edges

    if math.hypot(orientation_x, orientation_y) <= 1e-12:
        family_angle = math.atan2(longest_delta.y, longest_delta.x)
    else:
        family_angle = 0.25 * math.atan2(orientation_y, orientation_x)

    first_axis = Vector((math.cos(family_angle), math.sin(family_angle)))
    second_axis = Vector((-first_axis.y, first_axis.x))
    if abs(first_axis.x) >= abs(second_axis.x):
        horizontal_axis, vertical_axis = first_axis, second_axis
    else:
        horizontal_axis, vertical_axis = second_axis, first_axis

    for edge in edges:
        delta = node_data[edge.second].uv - node_data[edge.first].uv
        if abs(delta.dot(horizontal_axis)) >= abs(delta.dot(vertical_axis)):
            graph = horizontal_graph
            horizontal_edges.append(edge)
        else:
            graph = vertical_graph
            vertical_edges.append(edge)
        graph.setdefault(edge.first, set()).add(edge.second)
        graph.setdefault(edge.second, set()).add(edge.first)

    return horizontal_graph, vertical_graph, horizontal_edges, vertical_edges


def _connected_components(graph: AdjacencyGraph) -> list[list[UVKey]]:
    components = []
    visited = set()

    for start in sorted(graph):
        if start in visited:
            continue
        component = []
        stack = [start]
        visited.add(start)
        while stack:
            key = stack.pop()
            component.append(key)
            for neighbor in graph[key]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        if len(component) > 1:
            components.append(component)

    return components


def _component_targets(components, node_data, axis):
    components.sort(key=lambda component: _component_mean(component, node_data, axis))
    return [_component_mean(component, node_data, axis) for component in components]


def _component_mean(component, node_data, axis):
    return sum(node_data[key].uv[axis] for key in component) / len(component)


def _relaxed_grid_targets(
    bm,
    uv_layer,
    horizontal_components,
    vertical_components,
    horizontal_edges,
    vertical_edges,
    node_data,
    free_boundary='LOCKED',
):
    """Solve line spacing jointly for minimum face-aspect error."""
    if len(horizontal_components) < 2 or len(vertical_components) < 2:
        return (
            _component_targets(horizontal_components, node_data, axis=1),
            _component_targets(vertical_components, node_data, axis=0),
        )

    selected_uvs = [data.uv for data in node_data.values()]
    min_x = min(uv.x for uv in selected_uvs)
    max_x = max(uv.x for uv in selected_uvs)
    min_y = min(uv.y for uv in selected_uvs)
    max_y = max(uv.y for uv in selected_uvs)
    width = max_x - min_x
    height = max_y - min_y
    if width <= 1e-12 or height <= 1e-12:
        return (
            _component_targets(horizontal_components, node_data, axis=1),
            _component_targets(vertical_components, node_data, axis=0),
        )

    horizontal_index = {
        key: index for index, component in enumerate(horizontal_components) for key in component
    }
    vertical_index = {
        key: index for index, component in enumerate(vertical_components) for key in component
    }
    horizontal_lengths = {
        frozenset((edge.first, edge.second)): edge.surface_length for edge in horizontal_edges
    }
    vertical_lengths = {
        frozenset((edge.first, edge.second)): edge.surface_length for edge in vertical_edges
    }
    cells = _collect_cell_aspects(
        bm,
        uv_layer,
        horizontal_index,
        vertical_index,
        horizontal_lengths,
        vertical_lengths,
    )
    if not cells:
        return (
            _component_targets(horizontal_components, node_data, axis=1),
            _component_targets(vertical_components, node_data, axis=0),
        )

    row_count = len(horizontal_components) - 1
    column_count = len(vertical_components) - 1
    by_row = defaultdict(list)
    by_column = defaultdict(list)
    for row, column, log_surface_aspect in cells:
        by_row[row].append((column, log_surface_aspect))
        by_column[column].append((row, log_surface_aspect))

    # In log space the aspect objective is linear:
    # log(width[column]) - log(height[row]) = log(surface_width / surface_height).
    # Alternating least squares finds the best separable orthogonal grid for
    # all faces together; final normalization enforces the original AABB.
    log_widths = [0.0] * column_count
    log_heights = [0.0] * row_count
    for _ in range(32):
        for column in range(column_count):
            observations = by_column.get(column)
            if observations:
                log_widths[column] = sum(
                    aspect + log_heights[row] for row, aspect in observations
                ) / len(observations)
        for row in range(row_count):
            observations = by_row.get(row)
            if observations:
                log_heights[row] = sum(
                    log_widths[column] - aspect for column, aspect in observations
                ) / len(observations)

        gauge = sum(log_heights) / len(log_heights)
        log_widths = [value - gauge for value in log_widths]
        log_heights = [value - gauge for value in log_heights]

    widths = [math.exp(value) for value in log_widths]
    heights = [math.exp(value) for value in log_heights]
    free_boundary = _resolve_free_boundary(
        free_boundary,
        horizontal_components,
        vertical_components,
        node_data,
        width,
        height,
    )

    if free_boundary in {'TOP', 'BOTTOM'}:
        # The locked horizontal span determines one shared UV-to-surface scale
        # for both axes. The released vertical side absorbs the overall aspect
        # mismatch instead of distributing it across every face.
        scale = width / sum(widths)
        widths = [value * scale for value in widths]
        heights = [value * scale for value in heights]
    elif free_boundary in {'LEFT', 'RIGHT'}:
        scale = height / sum(heights)
        widths = [value * scale for value in widths]
        heights = [value * scale for value in heights]
    else:
        width_scale = width / sum(widths)
        height_scale = height / sum(heights)
        widths = [value * width_scale for value in widths]
        heights = [value * height_scale for value in heights]

    start_x = max_x - sum(widths) if free_boundary == 'LEFT' else min_x
    start_y = max_y - sum(heights) if free_boundary == 'BOTTOM' else min_y
    vertical_targets = _accumulate_targets(widths, start_x)
    horizontal_targets = _accumulate_targets(heights, start_y)
    return horizontal_targets, vertical_targets


def _resolve_free_boundary(
    free_boundary,
    horizontal_components,
    vertical_components,
    node_data,
    width,
    height,
):
    if free_boundary != 'AUTO':
        return free_boundary

    candidates = (
        ('BOTTOM', horizontal_components[0], 1, height),
        ('TOP', horizontal_components[-1], 1, height),
        ('LEFT', vertical_components[0], 0, width),
        ('RIGHT', vertical_components[-1], 0, width),
    )
    # Release the boundary that was least straight before the operation. The
    # normalization makes horizontal and vertical deviations comparable.
    def normalized_deviation(candidate):
        _, component, axis, span = candidate
        mean = _component_mean(component, node_data, axis)
        variance = sum((node_data[key].uv[axis] - mean) ** 2 for key in component)
        return math.sqrt(variance / len(component)) / span

    return max(candidates, key=normalized_deviation)[0]


def _collect_cell_aspects(
    bm,
    uv_layer,
    horizontal_index,
    vertical_index,
    horizontal_lengths,
    vertical_lengths,
):
    cells = []
    for face in bm.faces:
        if len(face.loops) != 4:
            continue
        keys = [_uv_key(loop, uv_layer) for loop in face.loops]
        if any(key not in horizontal_index or key not in vertical_index for key in keys):
            continue

        face_horizontal_lengths = []
        face_vertical_lengths = []
        for loop in face.loops:
            edge_key = frozenset((_uv_key(loop, uv_layer), _uv_key(loop.link_loop_next, uv_layer)))
            if edge_key in horizontal_lengths:
                face_horizontal_lengths.append(horizontal_lengths[edge_key])
            elif edge_key in vertical_lengths:
                face_vertical_lengths.append(vertical_lengths[edge_key])

        rows = {horizontal_index[key] for key in keys}
        columns = {vertical_index[key] for key in keys}
        if (
            len(rows) != 2
            or len(columns) != 2
            or not face_horizontal_lengths
            or not face_vertical_lengths
        ):
            continue

        surface_width = sum(face_horizontal_lengths) / len(face_horizontal_lengths)
        surface_height = sum(face_vertical_lengths) / len(face_vertical_lengths)
        if surface_width <= 1e-12 or surface_height <= 1e-12:
            continue
        cells.append((min(rows), min(columns), math.log(surface_width / surface_height)))
    return cells


def _accumulate_targets(intervals, start):
    targets = [start]
    for interval in intervals:
        targets.append(targets[-1] + interval)
    return targets

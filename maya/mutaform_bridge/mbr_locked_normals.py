"""Convert imported locked mesh normals to Maya soft/hard edges (Maya 2025)."""

from __future__ import annotations

import maya.cmds as cmds
import maya.api.OpenMaya as om


_EPSILON_SQUARED = 1.0e-10
_WINDOW_NAME = "lockNormalsToHSProgressWindow"
_UI = {}


def _mesh_shapes(selection):
    """Return unique, non-intermediate mesh shapes from a Maya selection."""
    shapes = []
    for item in selection:
        node = item.split(".", 1)[0]
        if not cmds.objExists(node):
            continue
        if cmds.nodeType(node) == "mesh":
            candidates = [node]
        else:
            candidates = cmds.listRelatives(
                node, shapes=True, noIntermediate=True, fullPath=True, type="mesh"
            ) or []
        for shape in candidates:
            if shape not in shapes:
                shapes.append(shape)
    return shapes


def _different_normals(first, second):
    return sum((a - b) ** 2 for a, b in zip(first, second)) > _EPSILON_SQUARED


def _hard_edges_from_locked_normals(shape, progress_callback=None):
    """Find discontinuous edges using the mesh API, without per-vertex cmds calls."""
    selection = om.MSelectionList()
    selection.add(shape)
    mesh_dag = selection.getDagPath(0)
    mesh = om.MFnMesh(mesh_dag)
    normals = mesh.getNormals(om.MSpace.kObject)
    face_vertex_counts, all_normal_ids = mesh.getNormalIds()
    face_offsets = [0]
    for count in face_vertex_counts:
        face_offsets.append(face_offsets[-1] + count)

    def face_normal_ids(face_index):
        start, end = face_offsets[face_index], face_offsets[face_index + 1]
        return dict(zip(mesh.getPolygonVertices(face_index), all_normal_ids[start:end]))

    hard_edges = set()
    edge_iterator = om.MItMeshEdge(mesh_dag)
    for edge_index in range(mesh.numEdges):
        edge_iterator.setIndex(edge_index)
        connected_faces = edge_iterator.getConnectedFaces()
        if len(connected_faces) != 2:
            continue
        edge_vertices = (edge_iterator.vertexId(0), edge_iterator.vertexId(1))
        first = face_normal_ids(connected_faces[0])
        second = face_normal_ids(connected_faces[1])
        for vertex in edge_vertices:
            if vertex not in first or vertex not in second:
                continue
            if _different_normals(normals[first[vertex]], normals[second[vertex]]):
                hard_edges.add(edge_index)
                break
        if progress_callback and (edge_index % 100 == 0 or edge_index + 1 == mesh.numEdges):
            progress_callback(edge_index + 1, mesh.numEdges)
    return ["{}.e[{}]".format(shape, edge) for edge in sorted(hard_edges)]


def _short_name(node):
    return node.rsplit("|", 1)[-1]


def _create_progress_ui(mesh_count):
    if cmds.window(_WINDOW_NAME, exists=True):
        cmds.deleteUI(_WINDOW_NAME)
    window = cmds.window(
        _WINDOW_NAME,
        title="Locked normals to Hard / Soft Edges",
        sizeable=False,
        widthHeight=(460, 150),
    )
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnAttach=("both", 12))
    _UI["overall_text"] = cmds.text(label="Objects: 0 / {}".format(mesh_count), align="left")
    _UI["overall_bar"] = cmds.progressBar(maxValue=max(mesh_count, 1), width=430)
    _UI["object_text"] = cmds.text(label="Waiting...", align="left")
    _UI["object_bar"] = cmds.progressBar(maxValue=1, width=430)
    cmds.showWindow(window)


def _set_object_progress(shape, current, maximum):
    if not _UI:
        return
    cmds.text(
        _UI["object_text"],
        edit=True,
        label="{}: {} / {} edges".format(_short_name(shape), current, maximum),
    )
    cmds.progressBar(_UI["object_bar"], edit=True, maxValue=max(maximum, 1), progress=current)
    cmds.refresh(force=True)


def _set_overall_progress(done, maximum, shape):
    if not _UI:
        return
    cmds.text(
        _UI["overall_text"],
        edit=True,
        label="Objects: {} / {}   ({})".format(done, maximum, _short_name(shape)),
    )
    cmds.progressBar(_UI["overall_bar"], edit=True, progress=done)
    cmds.refresh(force=True)


def _delete_progress_ui():
    _UI.clear()
    if cmds.window(_WINDOW_NAME, exists=True):
        cmds.deleteUI(_WINDOW_NAME)


def convert_selected(*_):
    """Convert the selected meshes; returns the number of processed meshes."""
    original_selection = cmds.ls(selection=True, long=True) or []
    meshes = _mesh_shapes(original_selection)
    if not meshes:
        cmds.warning("Select at least one polygon mesh or mesh transform.")
        return 0

    failed = []
    processed = 0
    cmds.undoInfo(openChunk=True, chunkName="Locked normals to hard/soft edges")
    _create_progress_ui(len(meshes))
    try:
        for mesh_index, shape in enumerate(meshes, start=1):
            _set_overall_progress(mesh_index - 1, len(meshes), shape)
            try:
                edge_count = cmds.polyEvaluate(shape, edge=True)
                _set_object_progress(shape, 0, edge_count)
                hard_edges = _hard_edges_from_locked_normals(
                    shape,
                    lambda current, maximum: _set_object_progress(shape, current, maximum),
                )
                cmds.polyNormalPerVertex(shape, unFreezeNormal=True)
                cmds.polySoftEdge(shape, angle=180, constructionHistory=False)
                if hard_edges:
                    cmds.polySoftEdge(hard_edges, angle=0, constructionHistory=False)
                _set_object_progress(shape, edge_count, edge_count)
                processed += 1
            except Exception as error:
                name = _short_name(shape)
                failed.append((name, str(error)))
                cmds.warning("Skipped {}: {}".format(name, error))
            finally:
                _set_overall_progress(mesh_index, len(meshes), shape)
        cmds.inViewMessage(
            amg="Converted <hl>{}</hl> of <hl>{}</hl> mesh(es).".format(processed, len(meshes)),
            pos="midCenter",
            fade=True,
        )
    finally:
        cmds.select(original_selection, replace=True) if original_selection else cmds.select(clear=True)
        _delete_progress_ui()
        cmds.undoInfo(closeChunk=True)

    if failed:
        lines = ["{}\n  {}".format(name, error) for name, error in failed]
        cmds.confirmDialog(
            title="Locked normals: skipped objects",
            message="The following object(s) were not converted:\n\n{}".format("\n\n".join(lines)),
            button=["OK"],
            defaultButton="OK",
            icon="warning",
        )
    return processed


if __name__ == "__main__":
    convert_selected()

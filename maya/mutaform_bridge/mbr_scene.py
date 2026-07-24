# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene cleanup and validation helpers for Mutaform Bridge in Maya."""

from __future__ import annotations

from typing import Any

import maya.api.OpenMaya as om
import maya.cmds as cmds

from mbr_core import _leaf, _set_report, find_empty_candidates, iter_transforms_under

RANDOM_SHARP_UV_TOLERANCE = 0.001

def _restore_protected_transforms() -> int:
    restored = 0
    for _pass in range(20):
        protected = [
            node for node in (cmds.ls(type="transform", long=True) or [])
            if _leaf(node).endswith("__MBR_PROTECT")
        ]
        if not protected:
            break
        changed = False
        for node in sorted(protected, key=lambda path: path.count("|"), reverse=True):
            if not cmds.objExists(node):
                continue
            clean_leaf = _leaf(node).replace("__MBR_PROTECT", "")
            try:
                cmds.rename(node, clean_leaf)
                restored += 1
                changed = True
            except Exception:
                pass
        if not changed:
            break
    return restored



def clean_geometry_history(roots: list[str] | None = None) -> dict[str, Any]:
    """Delete construction history on mesh transforms."""
    transforms = iter_transforms_under(roots)
    mesh_transforms = []
    for transform in transforms:
        shapes = cmds.listRelatives(transform, shapes=True, fullPath=True) or []
        if any(cmds.nodeType(shape) == "mesh" for shape in shapes):
            mesh_transforms.append(transform)

    cleaned = 0
    failed = 0
    for transform in sorted(set(mesh_transforms)):
        if not cmds.objExists(transform):
            continue
        try:
            cmds.delete(transform, constructionHistory=True)
            cleaned += 1
        except Exception:
            failed += 1
    return {"mesh_transforms": len(set(mesh_transforms)), "cleaned": cleaned, "failed": failed}


def unlock_transforms(roots: list[str] | None = None) -> dict[str, Any]:
    attrs = ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz", "v")
    changed = []
    for node in iter_transforms_under(roots):
        for attr in attrs:
            plug = f"{node}.{attr}"
            if not cmds.objExists(plug):
                continue
            try:
                if cmds.getAttr(plug, lock=True):
                    cmds.setAttr(plug, lock=False)
                    changed.append(plug)
            except Exception:
                pass
    return {"unlocked": len(changed), "attrs": changed}


def _mesh_shapes_under(roots: list[str] | None = None) -> list[tuple[str, str]]:
    mesh_shapes: list[tuple[str, str]] = []
    for transform in iter_transforms_under(roots):
        shapes = cmds.listRelatives(transform, shapes=True, fullPath=True) or []
        for shape in shapes:
            if cmds.nodeType(shape) != "mesh":
                continue
            try:
                if cmds.getAttr(f"{shape}.intermediateObject"):
                    continue
            except Exception:
                pass
            mesh_shapes.append((transform, shape))
    return mesh_shapes


def _dag_path(node: str) -> om.MDagPath:
    selection = om.MSelectionList()
    selection.add(node)
    return selection.getDagPath(0)


def _uv_point_key(uv: tuple[float, float], tolerance: float) -> tuple[int, int]:
    step = max(tolerance, 1e-9)
    return (round(float(uv[0]) / step), round(float(uv[1]) / step))


def _uv_edge_key(a: tuple[float, float], b: tuple[float, float], tolerance: float) -> tuple[tuple[int, int], tuple[int, int]]:
    return tuple(sorted((_uv_point_key(a, tolerance), _uv_point_key(b, tolerance))))  # type: ignore[return-value]


def _uv_border_edges(dag_path: om.MDagPath, tolerance: float) -> set[int]:
    mesh_fn = om.MFnMesh(dag_path)
    uv_sets = list(mesh_fn.getUVSetNames())
    if not uv_sets:
        return set()

    border_edges: set[int] = set()
    for uv_set in uv_sets:
        edge_uvs: dict[int, set[tuple[tuple[int, int], tuple[int, int]]]] = {}
        edge_use_count: dict[int, int] = {}
        poly_it = om.MItMeshPolygon(dag_path)
        while not poly_it.isDone():
            try:
                edges = list(poly_it.getEdges())
                count = poly_it.polygonVertexCount()
                for local_index in range(count):
                    edge_id = int(edges[local_index])
                    edge_use_count[edge_id] = edge_use_count.get(edge_id, 0) + 1
                    try:
                        uv_a = poly_it.getUV(local_index, uv_set)
                        uv_b = poly_it.getUV((local_index + 1) % count, uv_set)
                    except Exception:
                        continue
                    edge_uvs.setdefault(edge_id, set()).add(_uv_edge_key(uv_a, uv_b, tolerance))
            except Exception:
                pass
            poly_it.next()
        for edge_id, uv_keys in edge_uvs.items():
            if edge_use_count.get(edge_id, 0) < 2 or len(uv_keys) > 1:
                border_edges.add(edge_id)
    return border_edges


def _edge_is_smooth(edge_it: om.MItMeshEdge) -> bool:
    value = getattr(edge_it, "isSmooth", None)
    if callable(value):
        return bool(value())
    if value is not None:
        return bool(value)
    return True


def _random_sharp_edges_for_shape(shape: str, tolerance: float = RANDOM_SHARP_UV_TOLERANCE) -> list[int]:
    dag_path = _dag_path(shape)
    uv_borders = _uv_border_edges(dag_path, tolerance)
    bad_edges: list[int] = []
    edge_it = om.MItMeshEdge(dag_path)
    while not edge_it.isDone():
        edge_id = int(edge_it.index())
        if not _edge_is_smooth(edge_it) and edge_id not in uv_borders:
            bad_edges.append(edge_id)
        edge_it.next()
    return bad_edges


def _select_edge_components(components: list[str]) -> None:
    """Switch Maya to mesh edge component mode and select the passed edges."""
    transforms = sorted({component.split(".", 1)[0] for component in components})
    if transforms:
        try:
            cmds.hilite(transforms, replace=True)
        except Exception:
            pass
    try:
        cmds.selectMode(component=True)
    except Exception:
        pass
    try:
        cmds.selectType(allComponents=False)
    except Exception:
        pass
    try:
        cmds.selectType(polymeshEdge=True)
    except Exception:
        try:
            cmds.selectType(edge=True)
        except Exception:
            pass
    if components:
        cmds.select(components, replace=True)
    else:
        cmds.select(clear=True)


def find_random_sharp_edges(
    roots: list[str] | None = None,
    tolerance: float = RANDOM_SHARP_UV_TOLERANCE,
    select_edges: bool = True,
) -> dict[str, Any]:
    """Find hard edges that are not UV borders, matching Blender Random Sharp."""
    meshes = _mesh_shapes_under(roots)
    issues: list[dict[str, Any]] = []
    components: list[str] = []
    for transform, shape in meshes:
        try:
            edges = _random_sharp_edges_for_shape(shape, tolerance)
        except Exception as exc:
            issues.append({"transform": transform, "shape": shape, "edges": [], "error": str(exc)})
            continue
        if not edges:
            continue
        components.extend(f"{transform}.e[{edge}]" for edge in edges)
        issues.append({"transform": transform, "shape": shape, "edges": edges, "count": len(edges)})
    if select_edges:
        _select_edge_components(components)
    total = sum(len(item.get("edges", [])) for item in issues)
    _set_report(f"Random Sharp: {total} edge(s) on {len([item for item in issues if item.get('edges')])} mesh(es).")
    return {"meshes": len(meshes), "issues": issues, "components": components, "edges": total}


def fix_random_sharp_edges(
    roots: list[str] | None = None,
    tolerance: float = RANDOM_SHARP_UV_TOLERANCE,
    select_edges: bool = True,
) -> dict[str, Any]:
    """Soften hard edges that are not UV borders."""
    found = find_random_sharp_edges(roots=roots, tolerance=tolerance, select_edges=False)
    fixed_components: list[str] = []
    failed = 0
    for item in found["issues"]:
        transform = item.get("transform")
        shape = item.get("shape")
        edges = item.get("edges") or []
        if not transform or not shape or not edges:
            continue
        components = [f"{transform}.e[{edge}]" for edge in edges]
        try:
            mesh_fn = om.MFnMesh(_dag_path(shape))
            fixed_edges = []
            for edge in edges:
                try:
                    mesh_fn.setEdgeSmoothing(int(edge), True)
                    fixed_edges.append(edge)
                except Exception:
                    failed += 1
            if fixed_edges:
                mesh_fn.cleanupEdgeSmoothing()
                mesh_fn.updateSurface()
                fixed_components.extend(f"{transform}.e[{edge}]" for edge in fixed_edges)
        except Exception:
            try:
                cmds.polySoftEdge(components, angle=180, constructionHistory=False)
                fixed_components.extend(components)
            except Exception:
                failed += len(components)
    if select_edges:
        _select_edge_components(fixed_components)
    _set_report(f"Random Sharp fixed: {len(fixed_components)} edge(s), {failed} failed.")
    return {
        "meshes": found["meshes"],
        "edges": found["edges"],
        "fixed": len(fixed_components),
        "failed": failed,
        "components": fixed_components,
        "issues": found["issues"],
    }


def check_scene(roots: list[str] | None = None) -> dict[str, Any]:
    transforms = iter_transforms_under(roots)
    meshes = cmds.ls(type="mesh", long=True) or []
    locators = cmds.ls(type="locator", long=True) or []
    suffix_nodes = cmds.ls("*FBXASC046*") or []
    locked = []
    for node in transforms:
        for attr in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz", "v"):
            plug = f"{node}.{attr}"
            if cmds.objExists(plug):
                try:
                    if cmds.getAttr(plug, lock=True):
                        locked.append(plug)
                except Exception:
                    pass
    candidates = find_empty_candidates(
        roots=roots,
        include_transform_groups=True,
        include_locators=True,
        only_with_children=True,
    )
    report = {
        "roots": roots or ["<scene>"],
        "transforms": len(transforms),
        "meshes": len(meshes),
        "locators": len(locators),
        "empty_candidates": len(candidates),
        "fbx_suffix": len(suffix_nodes),
        "locked_attrs": len(locked),
    }
    issues = []
    if report["fbx_suffix"]:
        issues.append(f"{report['fbx_suffix']} FBX suffix names")
    if report["locators"]:
        issues.append(f"{report['locators']} locator shapes")
    if report["locked_attrs"]:
        issues.append(f"{report['locked_attrs']} locked attrs")
    issue_text = "OK" if not issues else "; ".join(issues)
    _set_report(
        f"Scene: {report['meshes']} mesh, {report['transforms']} transforms, "
        f"{report['empty_candidates']} group candidates. {issue_text}."
    )
    return report


def _format_auto_fix(convert_stats: dict[str, Any] | None = None, unlock_stats: dict[str, Any] | None = None) -> str:
    parts = []
    if convert_stats:
        if convert_stats.get("converted"):
            parts.append(f"{convert_stats['converted']} groups converted")
        if convert_stats.get("names_cleaned"):
            parts.append(f"{convert_stats['names_cleaned']} names cleaned")
        if convert_stats.get("locator_shapes_removed"):
            parts.append(f"{convert_stats['locator_shapes_removed']} locators removed")
    if unlock_stats and unlock_stats.get("unlocked"):
        parts.append(f"{unlock_stats['unlocked']} attrs unlocked")
    return ", ".join(parts) if parts else "no fixes needed"




# SPDX-License-Identifier: GPL-3.0-or-later
# Mutaform Bridge - Mutaform Studio
"""Core Maya helpers for Mutaform Bridge."""

from __future__ import annotations

import os
import re
from typing import Any

import maya.cmds as cmds
import maya.mel as mel
BRIDGE_VERSION = "1.1.1"
BRIDGE_VERSION_LABEL = f"ver {BRIDGE_VERSION}"
DEFAULT_EXCHANGE_DIR = os.path.join(os.path.expanduser("~"), "Documents", "MutaformBridge")
DEFAULT_EXCHANGE_NAME = "mutaform_bridge.fbx"
LAST_REPORT = "Ready."
TEXTURE_SEARCH_DEPTH = 5
PIVOT_ATTRS = ("mbr_pivot_world_x", "mbr_pivot_world_y", "mbr_pivot_world_z")
LOCATOR_SHAPE_TYPES = {"locator"}
DEFAULT_CAMERA_TRANSFORMS = {"persp", "top", "front", "side"}
BLENDER_FBX_DOT_SUFFIX_RE = re.compile(r"FBXASC046\d{3}")
FBX_ASCII_RE = re.compile(r"FBXASC(\d{3})")


def _set_report(message: str) -> str:
    global LAST_REPORT
    LAST_REPORT = message
    return message


def _long(node: str) -> str:
    matches = cmds.ls(node, long=True) or []
    return matches[0] if matches else node


def _short(node: str) -> str:
    return node.rsplit("|", 1)[-1]


def _leaf(node: str) -> str:
    return _short(node).split(":", 1)[-1] if ":" in _short(node) else _short(node)


def _namespace(node: str) -> str:
    short_name = _short(node)
    return short_name.rsplit(":", 1)[0] if ":" in short_name else ""


def _parent(node: str) -> str | None:
    parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
    return parents[0] if parents else None


def _transform_children(node: str) -> list[str]:
    children = cmds.listRelatives(node, children=True, type="transform", fullPath=True) or []
    return children


def _shape_types(node: str) -> list[str]:
    shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
    return [cmds.nodeType(shape) for shape in shapes]


def _locator_shapes(node: str) -> list[str]:
    shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
    return [shape for shape in shapes if cmds.nodeType(shape) in LOCATOR_SHAPE_TYPES]


def _is_default_camera(node: str) -> bool:
    if _short(node) in DEFAULT_CAMERA_TRANSFORMS:
        return True
    return any(shape_type == "camera" for shape_type in _shape_types(node))


def is_empty_candidate(
    node: str,
    include_transform_groups: bool = True,
    include_locators: bool = True,
    only_with_children: bool = True,
) -> bool:
    """Return True when a transform can be treated as a FBX Empty/null."""
    if not cmds.objExists(node) or cmds.nodeType(node) != "transform":
        return False
    if _is_default_camera(node):
        return False

    child_transforms = _transform_children(node)
    if only_with_children and not child_transforms:
        return False

    shape_types = set(_shape_types(node))
    if not shape_types:
        return include_transform_groups
    if shape_types.issubset(LOCATOR_SHAPE_TYPES):
        return include_locators
    return False


def iter_transforms_under(roots: list[str] | None = None) -> list[str]:
    """List transforms under roots, including roots, using long paths."""
    if roots:
        result: list[str] = []
        for root in roots:
            if not cmds.objExists(root):
                continue
            root_long = _long(root)
            if cmds.nodeType(root_long) == "transform":
                result.append(root_long)
            descendants = cmds.listRelatives(root_long, allDescendents=True, type="transform", fullPath=True) or []
            result.extend(descendants)
        return sorted(set(result), key=lambda path: (path.count("|"), path))
    return sorted(cmds.ls(type="transform", long=True) or [], key=lambda path: (path.count("|"), path))


def find_empty_candidates(
    roots: list[str] | None = None,
    include_transform_groups: bool = True,
    include_locators: bool = True,
    only_with_children: bool = True,
) -> list[str]:
    """Find candidate FBX Empty/null transforms."""
    return [
        node
        for node in iter_transforms_under(roots)
        if is_empty_candidate(
            node,
            include_transform_groups=include_transform_groups,
            include_locators=include_locators,
            only_with_children=only_with_children,
        )
    ]


def _copy_simple_user_attrs(source: str, target: str) -> None:
    """Copy simple custom attrs that Maya can recreate safely."""
    for attr in cmds.listAttr(source, userDefined=True) or []:
        source_attr = f"{source}.{attr}"
        target_attr = f"{target}.{attr}"
        if cmds.objExists(target_attr):
            continue
        try:
            attr_type = cmds.getAttr(source_attr, type=True)
            if attr_type == "string":
                cmds.addAttr(target, longName=attr, dataType="string")
                value = cmds.getAttr(source_attr)
                if value is not None:
                    cmds.setAttr(target_attr, value, type="string")
            else:
                value = cmds.getAttr(source_attr)
                if isinstance(value, (int, float, bool)):
                    cmds.addAttr(target, longName=attr, attributeType="double")
                    cmds.setAttr(target_attr, float(value))
        except Exception:
            pass


def _tag_pivots_for_blender_export(roots: list[str]) -> list[tuple[str, str]]:
    tagged: list[tuple[str, str]] = []
    for transform in iter_transforms_under(roots):
        if not cmds.objExists(transform):
            continue
        try:
            pivot = cmds.xform(transform, query=True, worldSpace=True, rotatePivot=True)
        except Exception:
            continue
        for attr, value in zip(PIVOT_ATTRS, pivot):
            plug = f"{transform}.{attr}"
            try:
                if not cmds.objExists(plug):
                    cmds.addAttr(transform, longName=attr, attributeType="double")
                    tagged.append((transform, attr))
                cmds.setAttr(plug, float(value))
            except Exception:
                pass
    return tagged


def _remove_pivot_export_tags(tagged: list[tuple[str, str]]) -> None:
    for transform, attr in tagged:
        plug = f"{transform}.{attr}"
        if not cmds.objExists(plug):
            continue
        try:
            cmds.deleteAttr(plug)
        except Exception:
            pass


def _strip_blender_fbx_suffix(name: str) -> str:
    """Turn Blender FBX names like MeshFBXASC046003 back into Mesh."""
    clean = BLENDER_FBX_DOT_SUFFIX_RE.sub("", name)
    clean = FBX_ASCII_RE.sub("_", clean)
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean or name


def _rename_leaf_preserving_namespace(node: str, new_leaf: str) -> str:
    namespace = _namespace(node)
    new_name = f"{namespace}:{new_leaf}" if namespace else new_leaf
    return _long(cmds.rename(node, new_name))


def _related_nodes_for_name_cleanup(roots: list[str] | None = None) -> list[str]:
    transforms = iter_transforms_under(roots)
    related: set[str] = set(transforms)

    shapes: set[str] = set()
    for transform in transforms:
        shapes.update(cmds.listRelatives(transform, shapes=True, fullPath=True) or [])
    related.update(shapes)

    frontier = set(shapes)
    for _depth in range(4):
        if not frontier:
            break
        connections = set(cmds.listConnections(list(frontier), source=True, destination=True) or [])
        connections -= related
        related.update(connections)
        frontier = connections

    return sorted(related, key=lambda name: (0 if "|" in name and name.count("|") > 1 else 1, name), reverse=True)


def clean_blender_fbx_suffixes(roots: list[str] | None = None, dry_run: bool = False) -> dict[str, Any]:
    """
    Clean Maya names created from Blender's .001/.002 FBX suffixes.

    Blender duplicate names often export as Name.001. Maya cannot use dots in
    node names, so FBX imports these as NameFBXASC046001. In a Maya hierarchy,
    duplicate leaf names are fine when they live under different parents, so the
    best round-trip default is to strip the generated suffix.
    """
    def current_plan() -> list[dict[str, str]]:
        planned: list[dict[str, str]] = []
        for node in _related_nodes_for_name_cleanup(roots):
            if not cmds.objExists(node):
                continue
            leaf = _leaf(node)
            clean_leaf = _strip_blender_fbx_suffix(leaf)
            if clean_leaf and clean_leaf != leaf:
                kind = "dag" if "|" in node else "dependency"
                planned.append({"node": node, "new_leaf": clean_leaf, "kind": kind})
        return planned

    planned = current_plan()

    if dry_run:
        return {"planned": len(planned), "renamed": 0, "nodes": planned}

    renamed = []
    failed: set[str] = set()
    for _pass in range(10):
        planned = [item for item in current_plan() if item["node"] not in failed]
        if not planned:
            break
        changed = False
        for item in sorted(planned, key=lambda value: 0 if value.get("kind") == "dag" else 1):
            node = item["node"]
            if not cmds.objExists(node):
                continue
            try:
                renamed_node = _rename_leaf_preserving_namespace(node, item["new_leaf"])
                renamed.append({"from": node, "to": renamed_node})
                changed = True
            except Exception as exc:
                failed.add(node)
                renamed.append({"from": node, "error": str(exc)})
        if not changed:
            break

    remaining = current_plan()
    return {
        "planned": len(renamed) + len(remaining),
        "renamed": len([r for r in renamed if "to" in r]),
        "remaining": len(remaining),
        "nodes": renamed,
    }


def _delete_locator_shapes(node: str) -> int:
    shapes = _locator_shapes(node)
    if shapes:
        cmds.delete(shapes)
    return len(shapes)


def _rebuild_as_clean_group(node: str) -> str:
    """Replace a candidate transform with a fresh empty Maya group."""
    node = _long(node)
    name = _leaf(node)
    namespace = _namespace(node)
    parent = _parent(node)
    child_transforms = _transform_children(node)
    child_world = {child: cmds.xform(child, query=True, matrix=True, worldSpace=True) for child in child_transforms}
    node_world = cmds.xform(node, query=True, matrix=True, worldSpace=True)

    temp_name = f"{namespace}:{name}__QC_TMP_GROUP" if namespace else f"{name}__QC_TMP_GROUP"
    final_name = f"{namespace}:{name}" if namespace else name
    temp = cmds.group(empty=True, name=temp_name)
    if parent:
        temp = cmds.parent(temp, parent)[0]
    temp = _long(temp)
    cmds.xform(temp, matrix=node_world, worldSpace=True)
    _copy_simple_user_attrs(node, temp)

    for child in child_transforms:
        if cmds.objExists(child):
            new_child = cmds.parent(child, temp)[0]
            cmds.xform(new_child, matrix=child_world[child], worldSpace=True)

    cmds.delete(node)
    renamed = cmds.rename(temp, final_name)
    return _long(renamed)


def convert_empties_to_groups(
    roots: list[str] | None = None,
    include_transform_groups: bool = True,
    include_locators: bool = True,
    only_with_children: bool = True,
    rebuild: bool = False,
    clean_names: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Convert FBX Empty/null transforms into Maya-native groups.

    If rebuild is False, locator shapes are removed and transform-only groups
    are left in place. If rebuild is True, every candidate is replaced with a
    clean empty transform group of the same name.
    """
    candidates = find_empty_candidates(
        roots=roots,
        include_transform_groups=include_transform_groups,
        include_locators=include_locators,
        only_with_children=only_with_children,
    )

    stats: dict[str, Any] = {
        "candidates": len(candidates),
        "converted": 0,
        "locator_shapes_removed": 0,
        "rebuilt": 0,
        "names_cleaned": 0,
        "name_cleanup": None,
        "skipped": [],
        "nodes": candidates,
    }
    if dry_run and clean_names:
        stats["name_cleanup"] = clean_blender_fbx_suffixes(roots=roots, dry_run=True)
    if dry_run:
        return stats

    cmds.undoInfo(openChunk=True, chunkName="Mutaform Bridge: Empties to Groups")
    try:
        for node in sorted(candidates, key=lambda path: path.count("|"), reverse=True):
            if not cmds.objExists(node):
                continue
            if not is_empty_candidate(
                node,
                include_transform_groups=include_transform_groups,
                include_locators=include_locators,
                only_with_children=only_with_children,
            ):
                stats["skipped"].append(node)
                continue
            if rebuild:
                _rebuild_as_clean_group(node)
                stats["rebuilt"] += 1
            else:
                stats["locator_shapes_removed"] += _delete_locator_shapes(node)
            stats["converted"] += 1
        if clean_names:
            cleanup = clean_blender_fbx_suffixes(roots=roots, dry_run=False)
            stats["name_cleanup"] = cleanup
            stats["names_cleaned"] = cleanup["renamed"]
    finally:
        cmds.undoInfo(closeChunk=True)

    return stats


def analyze_roots(roots: list[str] | None = None) -> dict[str, Any]:
    """Return a compact hierarchy report for UI/tests."""
    candidates = find_empty_candidates(roots=roots)
    return {
        "roots": roots or ["<scene>"],
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def exchange_path(folder: str | None = None, filename: str | None = None) -> str:
    folder = folder or DEFAULT_EXCHANGE_DIR
    filename = filename or DEFAULT_EXCHANGE_NAME
    if not filename.lower().endswith(".fbx"):
        filename += ".fbx"
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, filename).replace("\\", "/")


def _ensure_fbx_plugin() -> None:
    if not cmds.pluginInfo("fbxmaya", query=True, loaded=True):
        cmds.loadPlugin("fbxmaya")


def _configure_fbx_import_options() -> None:
    """Apply studio FBX import options before importing bridge files."""
    mel.eval("FBXResetImport")
    mel.eval("FBXImportHardEdges -v true")
    mel.eval("FBXImportSmoothingGroups -v true")
    mel.eval("FBXImportUnlockNormals -v true")



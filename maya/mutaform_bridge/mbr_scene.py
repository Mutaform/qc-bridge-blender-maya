# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene cleanup and validation helpers for Mutaform Bridge in Maya."""

from __future__ import annotations

from typing import Any

import maya.cmds as cmds

from mbr_core import _leaf, _set_report, find_empty_candidates, iter_transforms_under

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




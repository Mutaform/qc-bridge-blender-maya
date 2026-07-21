# SPDX-License-Identifier: GPL-3.0-or-later
"""FBX import/export commands for Mutaform Bridge in Maya."""

from __future__ import annotations

import os
from typing import Any

import maya.cmds as cmds
import maya.mel as mel

import mbr_core as core
from mbr_core import (
    DEFAULT_EXCHANGE_NAME,
    _configure_fbx_import_options,
    _ensure_fbx_plugin,
    _is_default_camera,
    _leaf,
    _long,
    _parent,
    _remove_pivot_export_tags,
    _rename_leaf_preserving_namespace,
    _set_report,
    _tag_pivots_for_blender_export,
    clean_blender_fbx_suffixes,
    convert_empties_to_groups,
    exchange_path,
)
from mbr_scene import (
    _format_auto_fix,
    _restore_protected_transforms,
    check_scene,
    clean_geometry_history,
    unlock_transforms,
)
from mbr_materials import (
    normalize_materials_to_blinn,
    read_material_sidecar,
    write_material_sidecar,
)


def _import_fbx_path(
    path: str,
    convert: bool = True,
    rebuild: bool = False,
    clean_names: bool = True,
    namespace: str = "",
    normalize_materials: bool = True,
    clean_history: bool = True,
    unlock_transform_attrs: bool = True,
    use_material_sidecar: bool = True,
) -> dict[str, Any]:
    if not os.path.exists(path):
        raise RuntimeError(f"FBX not found: {path}")
    _ensure_fbx_plugin()
    _configure_fbx_import_options()
    before = set(cmds.ls(long=True) or [])
    protected: list[tuple[str, str]] = []
    protected_leafs: set[str] = set()
    import_temp_suffix = "__MBR_IMPORT"
    protect_roots = [node for node in (cmds.ls(assemblies=True, long=True) or []) if not _is_default_camera(node)]
    protect_nodes: list[str] = []
    for root in protect_roots:
        protect_nodes.append(root)
        protect_nodes.extend(cmds.listRelatives(root, allDescendents=True, type="transform", fullPath=True) or [])
    for node in sorted(set(protect_nodes), key=lambda path: path.count("|"), reverse=True):
        if not cmds.objExists(node):
            continue
        leaf = _leaf(node)
        protected_leafs.add(leaf)
        temp = cmds.rename(node, f"{leaf}__MBR_PROTECT")
        protected.append((_long(temp), leaf))
    try:
        new_nodes = cmds.file(
            path,
            i=True,
            type="FBX",
            ignoreVersion=True,
            ra=True,
            mergeNamespacesOnClash=False,
            returnNewNodes=True,
            options="fbx",
        ) or []
        new_transforms = cmds.ls(new_nodes, type="transform", long=True) or []
        new_set = set(new_transforms)
        roots = []
        for node in new_transforms:
            parent = _parent(node)
            if not parent or parent not in new_set:
                roots.append(node)
        prefix = (namespace.strip("_") + "_") if namespace else ""
        renamed_roots = []
        if prefix:
            for root in roots:
                if cmds.objExists(root):
                    renamed_roots.append(_rename_leaf_preserving_namespace(root, prefix + _leaf(root)))
            roots = renamed_roots
        if protected_leafs:
            conflict_safe_roots = []
            for root in roots:
                if cmds.objExists(root) and _leaf(root) in protected_leafs:
                    temp = cmds.rename(root, f"{_leaf(root)}{import_temp_suffix}")
                    conflict_safe_roots.append(_long(temp))
                else:
                    conflict_safe_roots.append(root)
            roots = conflict_safe_roots
    finally:
        _restore_protected_transforms()
    if roots:
        restored_import_roots = []
        for root in roots:
            if cmds.objExists(root) and _leaf(root).endswith(import_temp_suffix):
                clean_leaf = _leaf(root)[: -len(import_temp_suffix)]
                restored_import_roots.append(_long(cmds.rename(root, clean_leaf)))
            else:
                restored_import_roots.append(root)
        roots = restored_import_roots
    stats: dict[str, Any] | None = None
    unlock_stats: dict[str, Any] | None = None
    if convert and roots:
        stats = convert_empties_to_groups(
            roots=roots,
            include_transform_groups=True,
            include_locators=True,
            only_with_children=True,
            rebuild=rebuild,
            clean_names=clean_names,
            dry_run=False,
        )
    unlock_stats = unlock_transforms(roots) if unlock_transform_attrs else None
    material_metadata = read_material_sidecar(path) if use_material_sidecar else {}
    material_stats = (
        normalize_materials_to_blinn(roots, material_metadata=material_metadata)
        if normalize_materials and roots
        else None
    )
    history_stats = clean_geometry_history(roots) if clean_history and roots else None
    final_check = check_scene(roots if roots else None)
    report = {
        "path": path,
        "new_node_count": len(new_nodes),
        "new_transform_count": len(new_transforms),
        "roots": roots,
        "convert": stats,
        "unlock": unlock_stats,
        "materials": material_stats,
        "history": history_stats,
        "check": final_check,
        "scene_delta": len(set(cmds.ls(long=True) or []) - before),
    }
    mat_text = f", {material_stats['normalized']} blinn materials" if material_stats else ""
    history_text = f", {history_stats['cleaned']} history cleaned" if history_stats else ""
    _set_report(
        f"Imported {len(roots)} root(s); {_format_auto_fix(stats, unlock_stats)}"
        f"{mat_text}{history_text}. {core.LAST_REPORT}"
    )
    return report


def import_from_blender(
    folder: str | None = None,
    filename: str | None = None,
    convert: bool = True,
    rebuild: bool = False,
    clean_names: bool = True,
    namespace: str = "",
    normalize_materials: bool = True,
    clean_history: bool = True,
    unlock_transform_attrs: bool = True,
) -> dict[str, Any]:
    return _import_fbx_path(
        exchange_path(folder, filename),
        convert=convert,
        rebuild=rebuild,
        clean_names=clean_names,
        namespace=namespace,
        normalize_materials=normalize_materials,
        clean_history=clean_history,
        unlock_transform_attrs=unlock_transform_attrs,
        use_material_sidecar=True,
    )


def import_fbx_file(
    path: str,
    convert: bool = True,
    rebuild: bool = False,
    clean_names: bool = True,
    namespace: str = "",
    normalize_materials: bool = True,
    clean_history: bool = True,
    unlock_transform_attrs: bool = True,
) -> dict[str, Any]:
    """Import any FBX file using the studio bridge cleanup pipeline."""
    return _import_fbx_path(
        path,
        convert=convert,
        rebuild=rebuild,
        clean_names=clean_names,
        namespace=namespace,
        normalize_materials=normalize_materials,
        clean_history=clean_history,
        unlock_transform_attrs=unlock_transform_attrs,
        use_material_sidecar=False,
    )


def export_selected_to_blender(folder: str | None = None, filename: str | None = None) -> dict[str, Any]:
    path = exchange_path(folder, filename)
    selection = cmds.ls(selection=True, long=True) or []
    if not selection:
        raise RuntimeError("Select a root or objects to export.")
    _ensure_fbx_plugin()
    unlock_stats = unlock_transforms(selection)
    cleanup = clean_blender_fbx_suffixes(roots=selection, dry_run=False)
    check = check_scene(selection)
    mel.eval("FBXResetExport")
    mel.eval("FBXExportInputConnections -v true")
    mel.eval("FBXExportSmoothingGroups -v true")
    mel.eval("FBXExportTangents -v true")
    mel.eval("FBXExportBakeComplexAnimation -v false")
    pivot_tags = _tag_pivots_for_blender_export(selection)
    try:
        mel.eval('FBXExport -f "{}" -s'.format(path.replace("\\", "/")))
    finally:
        _remove_pivot_export_tags(pivot_tags)
    material_sidecar = write_material_sidecar(path, selection)
    report = {
        "path": path,
        "selection": selection,
        "exists": os.path.exists(path),
        "size": os.path.getsize(path),
        "unlock": unlock_stats,
        "cleanup": cleanup,
        "check": check,
        "material_sidecar": material_sidecar,
    }
    _set_report(
        f"Exported selected: {len(selection)} item(s), {report['size']} bytes; "
        f"{_format_auto_fix({'names_cleaned': cleanup['renamed']}, unlock_stats)}."
    )
    return report


def export_scene_to_blender(folder: str | None = None, filename: str | None = None) -> dict[str, Any]:
    previous_selection = cmds.ls(selection=True, long=True) or []
    default_cameras = {"|persp", "|top", "|front", "|side"}
    roots = [
        node
        for node in (cmds.ls(assemblies=True, long=True, type="transform") or [])
        if node not in default_cameras
    ]
    if not roots:
        raise RuntimeError("No scene roots to export.")
    try:
        cmds.select(roots, replace=True)
        result = export_selected_to_blender(folder=folder, filename=filename)
        result["scene_roots"] = roots
        _set_report(f"Exported scene: {len(roots)} root(s), {result['size']} bytes.")
        return result
    finally:
        if previous_selection:
            cmds.select(previous_selection, replace=True)
        else:
            cmds.select(clear=True)



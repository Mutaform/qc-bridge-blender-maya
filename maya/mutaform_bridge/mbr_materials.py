# SPDX-License-Identifier: GPL-3.0-or-later
"""Material conversion helpers for Mutaform Bridge Maya imports."""

from __future__ import annotations

import re
import json
import os
from typing import Any

import maya.cmds as cmds

from mbr_core import (
    TEXTURE_SEARCH_DEPTH,
    _leaf,
    _strip_blender_fbx_suffix,
    iter_transforms_under,
)

DEFAULT_BLINN_COLOR = (0.5, 0.5, 0.5)


def _safe_node_name(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_]+", "_", name)
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean or "MutaformMaterial"


def _first_connected_file(node: str, attrs: tuple[str, ...]) -> str | None:
    visited: set[str] = set()
    frontier: list[str] = []
    for attr in attrs:
        plug = f"{node}.{attr}"
        if cmds.objExists(plug):
            frontier.extend(cmds.listConnections(plug, source=True, destination=False) or [])
    for _depth in range(TEXTURE_SEARCH_DEPTH):
        next_frontier: list[str] = []
        for item in frontier:
            if item in visited or not cmds.objExists(item):
                continue
            visited.add(item)
            if cmds.nodeType(item) == "file":
                return item
            next_frontier.extend(cmds.listConnections(item, source=True, destination=False) or [])
        frontier = next_frontier
    return None


def _file_texture_name(file_node: str) -> str:
    if not file_node or not cmds.objExists(file_node):
        return ""
    try:
        return cmds.getAttr(f"{file_node}.fileTextureName") or ""
    except Exception:
        return ""


def _file_role_score(file_node: str, role: str) -> int:
    name = f"{_leaf(file_node)} {_file_texture_name(file_node)}".lower()
    if role == "normal":
        needles = ("normal", "_nrm", " nrm", "_nor", " nor", "bump")
    elif role == "opacity":
        needles = ("opacity", "alpha", "trans", "mask", "cutout")
    else:
        needles = ("diffuse", "basecolor", "base_color", "albedo", "color", "col", "diff")
    return sum(1 for item in needles if item in name)


def _connected_file_candidates(shader: str, shading_engine: str | None = None) -> list[str]:
    seeds = [shader]
    if shading_engine:
        seeds.append(shading_engine)
    files: list[str] = []
    visited: set[str] = set()
    frontier = [node for node in seeds if node and cmds.objExists(node)]
    for _depth in range(TEXTURE_SEARCH_DEPTH):
        next_frontier: list[str] = []
        for node in frontier:
            if node in visited or not cmds.objExists(node):
                continue
            visited.add(node)
            if cmds.nodeType(node) == "file":
                files.append(node)
                continue
            next_frontier.extend(cmds.listConnections(node, source=True, destination=False) or [])
        frontier = next_frontier
    return sorted(set(files), key=lambda item: _leaf(item))


def _best_connected_file(shader: str, shading_engine: str, role: str, attrs: tuple[str, ...]) -> str | None:
    direct = _first_connected_file(shader, attrs)
    if direct:
        return direct
    candidates = _connected_file_candidates(shader, shading_engine)
    if not candidates:
        return None
    ranked = sorted(candidates, key=lambda item: (_file_role_score(item, role), _leaf(item)), reverse=True)
    if ranked and (_file_role_score(ranked[0], role) > 0 or role == "diffuse"):
        return ranked[0]
    return None


def _texture_file_attrs(file_node: str | None) -> dict[str, Any]:
    if not file_node or not cmds.objExists(file_node):
        return {}
    attrs: dict[str, Any] = {"node": _leaf(file_node)}
    for attr in ("fileTextureName", "colorSpace", "ignoreColorSpaceFileRules", "alphaIsLuminance"):
        plug = f"{file_node}.{attr}"
        if not cmds.objExists(plug):
            continue
        try:
            attrs[attr] = cmds.getAttr(plug)
        except Exception:
            pass
    return attrs


def _shader_display_attrs(shader: str) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for attr in (
        "color",
        "diffuse",
        "ambientColor",
        "incandescence",
        "transparency",
        "specularColor",
        "reflectivity",
        "eccentricity",
        "specularRollOff",
    ):
        plug = f"{shader}.{attr}"
        if not cmds.objExists(plug):
            continue
        try:
            attrs[attr] = cmds.getAttr(plug)
        except Exception:
            pass
    return attrs


def _set_shader_attr(shader: str, attr: str, value: Any) -> bool:
    plug = f"{shader}.{attr}"
    if not cmds.objExists(plug):
        return False
    try:
        if isinstance(value, list) and value and isinstance(value[0], (list, tuple)):
            value = value[0]
        if isinstance(value, (list, tuple)) and len(value) == 3:
            cmds.setAttr(plug, float(value[0]), float(value[1]), float(value[2]), type="double3")
        elif isinstance(value, str):
            cmds.setAttr(plug, value, type="string")
        else:
            cmds.setAttr(plug, value)
        return True
    except Exception:
        return False


def _apply_shader_display_metadata(blinn: str, material_metadata: dict[str, Any]) -> int:
    attrs = material_metadata.get("shaderAttrs") if isinstance(material_metadata, dict) else None
    if not isinstance(attrs, dict):
        return 0
    applied = 0
    for attr in (
        "color",
        "diffuse",
        "ambientColor",
        "incandescence",
        "transparency",
        "specularColor",
        "reflectivity",
        "eccentricity",
        "specularRollOff",
    ):
        if attr in attrs and _set_shader_attr(blinn, attr, attrs[attr]):
            applied += 1
    return applied


def _sidecar_path(fbx_path: str) -> str:
    return os.path.splitext(fbx_path)[0] + ".mbr_materials.json"


def write_material_sidecar(fbx_path: str, roots: list[str] | None = None) -> dict[str, Any]:
    """Write Maya-authored texture metadata next to the bridge FBX."""
    transforms = iter_transforms_under(roots)
    shapes: list[str] = []
    for transform in transforms:
        shapes.extend(cmds.listRelatives(transform, shapes=True, fullPath=True) or [])
    mesh_shapes = [shape for shape in shapes if cmds.nodeType(shape) == "mesh"]

    shading_engines: set[str] = set()
    for shape in mesh_shapes:
        shading_engines.update(cmds.listConnections(shape, type="shadingEngine") or [])

    materials: dict[str, Any] = {}
    for sg in sorted(shading_engines):
        if sg in {"initialShadingGroup", "initialParticleSE"}:
            continue
        shader = (cmds.listConnections(f"{sg}.surfaceShader", source=True, destination=False) or [None])[0]
        if not shader:
            continue
        clean_name = _clean_material_name(shader)
        diffuse_file = _best_connected_file(shader, sg, "diffuse", ("color", "baseColor", "diffuseColor", "outColor"))
        normal_file = _best_connected_file(shader, sg, "normal", ("normalCamera", "normal", "normalMap", "bumpValue"))
        opacity_file = _best_connected_file(shader, sg, "opacity", ("transparency", "opacity", "opacityR", "alpha", "outTransparency"))
        materials[clean_name] = {
            "shader": _leaf(shader),
            "shaderType": cmds.nodeType(shader),
            "shaderAttrs": _shader_display_attrs(shader),
            "shadingEngine": _leaf(sg),
            "textures": {
                "diffuse": _texture_file_attrs(diffuse_file),
                "normal": _texture_file_attrs(normal_file),
                "opacity": _texture_file_attrs(opacity_file),
            },
        }

    payload = {"version": 1, "materials": materials}
    path = _sidecar_path(fbx_path)
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
    except Exception:
        return {"path": path, "written": False, "materials": len(materials)}
    return {"path": path, "written": True, "materials": len(materials)}


def read_material_sidecar(fbx_path: str) -> dict[str, Any]:
    path = _sidecar_path(fbx_path)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return {}
    if not isinstance(payload, dict) or not isinstance(payload.get("materials"), dict):
        return {}
    return payload


def _connect_file_to_blinn(
    file_node: str | None,
    blinn: str,
    kind: str,
    texture_metadata: dict[str, Any] | None = None,
) -> bool:
    if not file_node or not cmds.objExists(file_node):
        return False
    try:
        if kind == "diffuse":
            cmds.connectAttr(f"{file_node}.outColor", f"{blinn}.color", force=True)
        elif kind == "opacity":
            reverse = cmds.shadingNode("reverse", asUtility=True, name=f"{blinn}_opacity_reverse")
            cmds.connectAttr(f"{file_node}.outColor", f"{reverse}.input", force=True)
            cmds.connectAttr(f"{reverse}.output", f"{blinn}.transparency", force=True)
        elif kind == "normal":
            if cmds.objExists(f"{file_node}.ignoreColorSpaceFileRules"):
                cmds.setAttr(f"{file_node}.ignoreColorSpaceFileRules", True)
            if cmds.objExists(f"{file_node}.colorSpace"):
                cmds.setAttr(f"{file_node}.colorSpace", "Raw", type="string")
            if texture_metadata and "alphaIsLuminance" in texture_metadata and cmds.objExists(f"{file_node}.alphaIsLuminance"):
                cmds.setAttr(f"{file_node}.alphaIsLuminance", bool(texture_metadata["alphaIsLuminance"]))
            bump = cmds.shadingNode("bump2d", asUtility=True, name=f"{blinn}_normal_bump")
            cmds.setAttr(f"{bump}.bumpInterp", 1)
            cmds.connectAttr(f"{file_node}.outAlpha", f"{bump}.bumpValue", force=True)
            cmds.connectAttr(f"{bump}.outNormal", f"{blinn}.normalCamera", force=True)
        else:
            return False
        return True
    except Exception:
        return False


def _disconnect_inputs(node: str, attrs: tuple[str, ...]) -> None:
    for attr in attrs:
        plug = f"{node}.{attr}"
        if not cmds.objExists(plug):
            continue
        for source in cmds.listConnections(plug, source=True, destination=False, plugs=True) or []:
            try:
                cmds.disconnectAttr(source, plug)
            except Exception:
                pass


def _clean_material_name(shader: str) -> str:
    base_name = _safe_node_name(_strip_blender_fbx_suffix(_leaf(shader)))
    if base_name.startswith("MBR_"):
        base_name = base_name[4:]
    if base_name.endswith("_blinn"):
        base_name = base_name[:-6]
    return base_name or "material"


def _metadata_key_variants(material_name: str) -> list[str]:
    variants = [material_name]
    stripped_number = re.sub(r"(?<!_)\d+$", "", material_name)
    if stripped_number and stripped_number not in variants:
        variants.append(stripped_number)
    if material_name.endswith("_blinn"):
        without_blinn = material_name[:-6]
        if without_blinn and without_blinn not in variants:
            variants.append(without_blinn)
    return variants


def _material_metadata_for_name(metadata_by_name: dict[str, Any], material_name: str) -> dict[str, Any]:
    for key in _metadata_key_variants(material_name):
        value = metadata_by_name.get(key)
        if isinstance(value, dict):
            return value
    return {}


def normalize_materials_to_blinn(
    roots: list[str] | None = None,
    material_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replace imported surface shaders with clean Maya blinn materials.

    Blender-authored colors and roughness are intentionally discarded. Only
    linked file textures for diffuse/color, normal, and opacity are preserved.
    Existing shadingEngine assignments are reused, so mesh assignments stay put.
    """
    transforms = iter_transforms_under(roots)
    shapes: list[str] = []
    for transform in transforms:
        shapes.extend(cmds.listRelatives(transform, shapes=True, fullPath=True) or [])
    mesh_shapes = [shape for shape in shapes if cmds.nodeType(shape) == "mesh"]

    shading_engines: set[str] = set()
    for shape in mesh_shapes:
        shading_engines.update(cmds.listConnections(shape, type="shadingEngine") or [])

    normalized = []
    reused = 0
    metadata_by_name = (material_metadata or {}).get("materials", {})
    for sg in sorted(shading_engines):
        if sg in {"initialShadingGroup", "initialParticleSE"}:
            continue
        old_shader = (cmds.listConnections(f"{sg}.surfaceShader", source=True, destination=False) or [None])[0]
        if not old_shader:
            continue

        diffuse_file = _best_connected_file(
            old_shader,
            sg,
            "diffuse",
            ("color", "baseColor", "diffuseColor", "outColor"),
        )
        normal_file = _best_connected_file(
            old_shader,
            sg,
            "normal",
            ("normalCamera", "normal", "normalMap", "bumpValue"),
        )
        opacity_file = _best_connected_file(
            old_shader,
            sg,
            "opacity",
            ("transparency", "opacity", "opacityR", "alpha", "outTransparency"),
        )

        base_name = _clean_material_name(old_shader)
        mat_metadata = _material_metadata_for_name(metadata_by_name, base_name)
        texture_metadata = mat_metadata.get("textures", {}) if isinstance(mat_metadata, dict) else {}
        if cmds.nodeType(old_shader) == "blinn":
            blinn = old_shader
            if _leaf(blinn) != base_name:
                try:
                    blinn = cmds.rename(blinn, base_name)
                except Exception:
                    pass
            reused += 1
        else:
            old_temp = cmds.rename(old_shader, f"{base_name}__MBR_OLD_SHADER")
            blinn = cmds.shadingNode("blinn", asShader=True, name=base_name)
            try:
                if cmds.objExists(old_temp):
                    cmds.delete(old_temp)
            except Exception:
                pass

        _disconnect_inputs(blinn, ("color", "transparency", "normalCamera", "diffuse", "specularColor"))
        cmds.setAttr(f"{blinn}.color", *DEFAULT_BLINN_COLOR, type="double3")
        cmds.setAttr(f"{blinn}.transparency", 0.0, 0.0, 0.0, type="double3")
        cmds.setAttr(f"{blinn}.diffuse", 0.8)
        cmds.setAttr(f"{blinn}.specularColor", 0.5, 0.5, 0.5, type="double3")
        attrs_applied = _apply_shader_display_metadata(blinn, mat_metadata)
        cmds.setAttr(f"{blinn}.color", *DEFAULT_BLINN_COLOR, type="double3")

        links = {
            "diffuse": _connect_file_to_blinn(diffuse_file, blinn, "diffuse", texture_metadata.get("diffuse")),
            "normal": _connect_file_to_blinn(normal_file, blinn, "normal", texture_metadata.get("normal")),
            "opacity": _connect_file_to_blinn(opacity_file, blinn, "opacity", texture_metadata.get("opacity")),
        }
        cmds.connectAttr(f"{blinn}.outColor", f"{sg}.surfaceShader", force=True)
        normalized.append({
            "shadingEngine": sg,
            "old": old_shader,
            "new": blinn,
            "links": links,
            "attrsApplied": attrs_applied,
        })

    return {
        "mesh_shapes": len(mesh_shapes),
        "shading_engines": len(shading_engines),
        "normalized": len(normalized),
        "reused": reused,
        "materials": normalized,
    }




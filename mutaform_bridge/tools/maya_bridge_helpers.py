# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender side of Mutaform Bridge."""

import os
import re

import bpy
from mathutils import Matrix, Vector

from .base import QCTool


QC_MATRIX_KEY = "qc_maya_matrix_local"
FBX_SUFFIX_RE = re.compile(r"FBXASC046\d{3}")
FBX_ASCII_RE = re.compile(r"FBXASC(\d{3})")
PIVOT_ATTRS = ("mbr_pivot_world_x", "mbr_pivot_world_y", "mbr_pivot_world_z")
MAYA_TO_BLENDER_UNIT_SCALE = 0.01


def _empty_roots(objects):
    objset = set(objects)
    return [
        obj for obj in objects
        if obj.type == "EMPTY" and (obj.parent is None or obj.parent not in objset)
    ]


def _ensure_child_collection(parent_coll, name):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    if coll.name not in parent_coll.children:
        parent_coll.children.link(coll)
    return coll


def _unlink_everywhere(obj):
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)


def _move_to_collection(obj, coll):
    _unlink_everywhere(obj)
    coll.objects.link(obj)


def _mat_to_list(matrix):
    return [list(row) for row in matrix]


def _list_to_mat(values):
    return Matrix(values)


def _exchange_path(context):
    props = context.scene.mutaform_bridge
    folder = bpy.path.abspath(props.exchange_dir)
    name = props.exchange_name.strip() or "mutaform_bridge.fbx"
    if not name.lower().endswith(".fbx"):
        name += ".fbx"
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, name)


def _set_report(context, message):
    context.scene.mutaform_bridge.last_report = message


def _maya_world_to_blender(value):
    x, y, z = value
    scale = MAYA_TO_BLENDER_UNIT_SCALE
    return Vector((float(x) * scale, -float(z) * scale, float(y) * scale))


def _custom_float(obj, name):
    if name not in obj:
        return None
    try:
        return float(obj[name])
    except Exception:
        return None


def _maya_pivot_world_from_props(obj):
    values = [_custom_float(obj, attr) for attr in PIVOT_ATTRS]
    if any(value is None for value in values):
        return None
    return _maya_world_to_blender(values)


def _set_origin_world_preserve_geometry(obj, origin_world):
    if obj.type != "MESH" or not obj.data or origin_world is None:
        return False
    old_world = obj.matrix_world.copy()
    if (old_world.translation - origin_world).length < 0.000001:
        return False
    new_world = old_world.copy()
    new_world.translation = origin_world
    new_world_inv = new_world.inverted()
    for vert in obj.data.vertices:
        vert.co = new_world_inv @ (old_world @ vert.co)
    obj.matrix_world = new_world
    obj.data.update()
    return True


def _maya_safe_name(name):
    clean = FBX_ASCII_RE.sub("_", name)
    clean = re.sub(r"[^A-Za-z0-9_]+", "_", clean)
    clean = re.sub(r"_+", "_", clean).strip("_")
    if not clean:
        clean = "Collection"
    if clean[0].isdigit():
        clean = f"_{clean}"
    return clean


def _mesh_objects(objects):
    return [obj for obj in objects if obj.type == "MESH" and obj.data]


def _objects_with_children(objects):
    result = set(objects)
    stack = list(objects)
    while stack:
        obj = stack.pop()
        for child in obj.children:
            if child not in result:
                result.add(child)
                stack.append(child)
    return list(result)


def _select_only(context, objects):
    objects = [obj for obj in objects if obj and obj.name in bpy.data.objects]
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    context.view_layer.objects.active = objects[0] if objects else None


def _clear_mesh_creases_temporarily(objects):
    backups = []
    meshes = {obj.data for obj in _mesh_objects(objects)}
    for mesh in meshes:
        for attr_name in ("crease_edge", "crease_vert"):
            attr = mesh.attributes.get(attr_name)
            if not attr or not hasattr(attr.data, "foreach_get"):
                continue
            values = [0.0] * len(attr.data)
            attr.data.foreach_get("value", values)
            backups.append((mesh, attr_name, attr.data_type, attr.domain, values))
            mesh.attributes.remove(attr)
            mesh.update()
    return backups


def _restore_mesh_creases(backups):
    for mesh, attr_name, data_type, domain, values in backups:
        attr = mesh.attributes.get(attr_name)
        if attr is None:
            attr = mesh.attributes.new(attr_name, data_type, domain)
        if len(attr.data) != len(values):
            continue
        attr.data.foreach_set("value", values)
        mesh.update()


def _collection_roots(context):
    scene_root = context.scene.collection
    return [coll for coll in scene_root.children if coll.objects or coll.children or QC_MATRIX_KEY in coll]


def _collection_parent_map(scene_root):
    parents = {}
    stack = [scene_root]
    while stack:
        parent = stack.pop()
        for child in parent.children:
            parents[child] = parent
            stack.append(child)
    return parents


def _collection_path_from_scene_root(scene_root, collection, parents):
    path = []
    coll = collection
    while coll and coll != scene_root:
        path.append(coll)
        coll = parents.get(coll)
    if coll != scene_root:
        return []
    path.reverse()
    return path


def _find_layer_collection(layer_collection, collection_name):
    if layer_collection.collection.name == collection_name:
        return layer_collection
    for child in layer_collection.children:
        found = _find_layer_collection(child, collection_name)
        if found:
            return found
    return None


def _selected_collection_roots(context, selected_objects):
    scene_root = context.scene.collection
    parents = _collection_parent_map(scene_root)
    wanted = set()
    for obj in selected_objects:
        for coll in obj.users_collection:
            path = _collection_path_from_scene_root(scene_root, coll, parents)
            if path:
                wanted.add(path[0])
    return [coll for coll in _collection_roots(context) if coll in wanted]


def _selected_empty_roots(selected_objects):
    roots = []
    seen = set()
    for obj in selected_objects:
        current = obj
        while current.parent is not None:
            current = current.parent
        if current.type == "EMPTY" and current not in seen:
            roots.append(current)
            seen.add(current)
    return roots


def _scene_empty_roots(context):
    return _empty_roots([obj for obj in context.scene.objects if obj.type == "EMPTY"])


def _clear_scene_data():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)


def _clean_fbx_suffixes(objects=None, collections=None):
    renamed = 0
    if objects is None:
        objects = list(bpy.data.objects)
    else:
        objects = [obj for obj in objects if obj and obj.name in bpy.data.objects]
    meshes = {obj.data for obj in objects if obj.type == "MESH" and obj.data}
    materials = {
        slot.material
        for obj in objects
        if obj.type == "MESH"
        for slot in obj.material_slots
        if slot.material
    }
    if collections is None:
        collections = list(bpy.data.collections)
    else:
        collections = [coll for coll in collections if coll and coll.name in bpy.data.collections]
    datablocks = list(objects) + list(meshes) + list(materials) + list(collections)
    for block in datablocks:
        clean = FBX_SUFFIX_RE.sub("", block.name)
        if clean and clean != block.name:
            block.name = clean
            renamed += 1
    return renamed


def _fix_orphan_objects(context, objects=None):
    fixed = 0
    scene_root = context.scene.collection
    if objects is None:
        objects = list(bpy.data.objects)
    for obj in objects:
        if not obj or obj.name not in bpy.data.objects:
            continue
        if obj.parent is None and not obj.users_collection:
            scene_root.objects.link(obj)
            fixed += 1
    return fixed


def auto_fix_scene(context, objects=None, collections=None):
    return {
        "orphans_fixed": _fix_orphan_objects(context, objects),
        "names_cleaned": _clean_fbx_suffixes(objects, collections),
    }


def scene_report(context):
    objects = list(bpy.data.objects)
    meshes = [obj for obj in objects if obj.type == "MESH"]
    empties = [obj for obj in objects if obj.type == "EMPTY"]
    root_empties = _empty_roots(empties)
    collections = list(bpy.data.collections)
    fbx_suffix = [obj.name for obj in objects if "FBXASC046" in obj.name]
    orphan_objects = [obj.name for obj in objects if not obj.users_collection and obj.parent is None]
    return {
        "objects": len(objects),
        "meshes": len(meshes),
        "empties": len(empties),
        "root_empties": len(root_empties),
        "collections": len(collections),
        "fbx_suffix": len(fbx_suffix),
        "orphan_objects": len(orphan_objects),
        "root_empty_names": [obj.name for obj in root_empties[:8]],
    }


def _format_scene_report(report):
    issues = []
    if report["fbx_suffix"]:
        issues.append(f"{report['fbx_suffix']} FBX suffix names")
    if report["orphan_objects"]:
        issues.append(f"{report['orphan_objects']} orphan objects")
    issue_text = "OK" if not issues else "; ".join(issues)
    return (
        f"Scene: {report['meshes']} mesh, {report['empties']} empties, "
        f"{report['collections']} collections. {issue_text}."
    )


def _format_fix_report(fix):
    parts = []
    if fix["orphans_fixed"]:
        parts.append(f"{fix['orphans_fixed']} orphan fixed")
    if fix["names_cleaned"]:
        parts.append(f"{fix['names_cleaned']} names cleaned")
    return ", ".join(parts) if parts else "no fixes needed"


def unpack_maya_to_collections(context, roots, bake_transforms=True):
    stats = {"collections": 0, "meshes": 0, "empties_removed": 0, "pivots_restored": 0}
    scene_root = context.scene.collection
    empties_to_remove = []

    def recurse(empty, parent_coll):
        coll = _ensure_child_collection(parent_coll, empty.name)
        stats["collections"] += 1
        coll[QC_MATRIX_KEY] = _mat_to_list(empty.matrix_basis)
        for child in list(empty.children):
            if child.type == "EMPTY":
                recurse(child, coll)
            else:
                world = child.matrix_world.copy()
                child.parent = None
                if bake_transforms:
                    child.matrix_world = world
                if _set_origin_world_preserve_geometry(child, _maya_pivot_world_from_props(child)):
                    stats["pivots_restored"] += 1
                _move_to_collection(child, coll)
                stats["meshes"] += 1
        empties_to_remove.append(empty)

    for root in roots:
        recurse(root, scene_root)

    for empty in empties_to_remove:
        bpy.data.objects.remove(empty, do_unlink=True)
        stats["empties_removed"] += 1

    return stats


def pack_collections_to_maya(context, roots):
    stats = {"empties": 0, "meshes": 0, "collections_removed": 0, "root_empties": []}
    scene_root = context.scene.collection
    to_remove = []

    def recurse(coll, parent_empty):
        empty = bpy.data.objects.new(_maya_safe_name(coll.name), None)
        empty.empty_display_type = "PLAIN_AXES"
        scene_root.objects.link(empty)
        if parent_empty is not None:
            empty.parent = parent_empty
        if QC_MATRIX_KEY in coll:
            empty.matrix_basis = _list_to_mat(coll[QC_MATRIX_KEY])
        context.view_layer.update()
        stats["empties"] += 1

        for obj in list(coll.objects):
            world = obj.matrix_world.copy()
            obj.parent = empty
            obj.matrix_parent_inverse = empty.matrix_world.inverted()
            obj.matrix_world = world
            _move_to_collection(obj, scene_root)
            stats["meshes"] += 1

        for child in list(coll.children):
            recurse(child, empty)
        to_remove.append(coll)
        return empty

    for coll in roots:
        root_empty = recurse(coll, None)
        stats["root_empties"].append(root_empty)

    for coll in to_remove:
        bpy.data.collections.remove(coll)
        stats["collections_removed"] += 1

    return stats



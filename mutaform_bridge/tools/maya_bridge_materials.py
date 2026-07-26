# SPDX-License-Identifier: GPL-3.0-or-later
"""FBX-friendly material export helpers for Mutaform Bridge."""

import json
import os

import bpy

def _mesh_objects(objects):
    return [obj for obj in objects if obj.type == "MESH" and obj.data]


def _image_connection_from_socket(socket, max_depth=6):
    visited = set()

    def walk(sock, depth):
        if depth > max_depth:
            return None
        for link in sock.links:
            node = link.from_node
            if node in visited:
                continue
            visited.add(node)
            if node.bl_idname == "ShaderNodeTexImage" and node.image:
                return node.image, link.from_socket.name
            for input_socket in getattr(node, "inputs", []):
                connection = walk(input_socket, depth + 1)
                if connection:
                    return connection
        return None

    return walk(socket, 0)


def _image_from_socket(socket, max_depth=6):
    connection = _image_connection_from_socket(socket, max_depth=max_depth)
    return connection[0] if connection else None


def _image_role_score(image, role):
    name = f"{image.name} {bpy.path.basename(image.filepath)}".lower() if image else ""
    if role == "normal":
        needles = ("normal", "_nrm", " nrm", "_nor", " nor", "bump")
    elif role == "opacity":
        needles = ("opacity", "alpha", "trans", "mask", "cutout")
    else:
        needles = ("diffuse", "basecolor", "base_color", "albedo", "color", "col", "diff", "ao")
    return sum(1 for item in needles if item in name)


def _material_export_images(material):
    images = {"diffuse": None, "normal": None, "opacity": None}
    outputs = {"diffuse": "Color", "normal": "Color", "opacity": "Alpha"}
    if not material or not material.use_nodes or not material.node_tree:
        return images, outputs

    nodes = list(material.node_tree.nodes)
    for node in nodes:
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            for socket_name in ("Base Color", "Color"):
                socket = node.inputs.get(socket_name)
                if socket and not images["diffuse"]:
                    images["diffuse"] = _image_from_socket(socket)
            socket = node.inputs.get("Alpha")
            if socket and not images["opacity"]:
                connection = _image_connection_from_socket(socket)
                if connection:
                    images["opacity"], outputs["opacity"] = connection
            socket = node.inputs.get("Normal")
            if socket and not images["normal"]:
                images["normal"] = _image_from_socket(socket)
        elif node.bl_idname == "ShaderNodeBsdfDiffuse":
            socket = node.inputs.get("Color")
            if socket and not images["diffuse"]:
                images["diffuse"] = _image_from_socket(socket)
        elif node.bl_idname == "ShaderNodeNormalMap":
            socket = node.inputs.get("Color")
            if socket and not images["normal"]:
                images["normal"] = _image_from_socket(socket)

    texture_images = [node.image for node in nodes if node.bl_idname == "ShaderNodeTexImage" and node.image]
    for role in ("normal", "opacity", "diffuse"):
        if images[role]:
            continue
        ranked = sorted(texture_images, key=lambda image: _image_role_score(image, role), reverse=True)
        if ranked and (_image_role_score(ranked[0], role) > 0 or role == "diffuse"):
            images[role] = ranked[0]
    return images, outputs


def _image_metadata(image):
    if not image:
        return {}
    path = bpy.path.abspath(image.filepath) if image.filepath else ""
    return {
        "node": image.name,
        "fileTextureName": path,
    }


def _material_metadata(images, outputs):
    opacity = _image_metadata(images.get("opacity"))
    if opacity:
        opacity["output"] = outputs.get("opacity", "Alpha")
    return {
        "textures": {
            "diffuse": _image_metadata(images.get("diffuse")),
            "normal": _image_metadata(images.get("normal")),
            "opacity": opacity,
        }
    }


def _make_export_material(source_material, images, outputs):
    original_name = source_material.name
    source_material.name = f"{original_name}__MBR_ORIGINAL"
    export_material = bpy.data.materials.new(original_name)
    export_material.use_nodes = True
    nodes = export_material.node_tree.nodes
    links = export_material.node_tree.links
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (360, 0)
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.location = (120, 0)
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    principled.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1.0)

    diffuse = images.get("diffuse")
    if diffuse:
        tex = nodes.new("ShaderNodeTexImage")
        tex.location = (-360, 80)
        tex.image = diffuse
        links.new(tex.outputs["Color"], principled.inputs["Base Color"])

    opacity = images.get("opacity")
    if opacity:
        tex = nodes.new("ShaderNodeTexImage")
        tex.location = (-360, -140)
        tex.image = opacity
        source_socket = tex.outputs.get(outputs.get("opacity", "Alpha")) or tex.outputs.get("Alpha")
        if source_socket and "Alpha" in principled.inputs:
            links.new(source_socket, principled.inputs["Alpha"])
            export_material.blend_method = "BLEND"

    normal = images.get("normal")
    if normal:
        tex = nodes.new("ShaderNodeTexImage")
        tex.location = (-560, -360)
        tex.image = normal
        tex.image.colorspace_settings.name = "Non-Color"
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.location = (-160, -300)
        links.new(tex.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])

    return export_material


def _prepare_export_materials(objects):
    backups = []
    material_map = {}
    metadata = {}
    for obj in _mesh_objects(objects):
        for slot in obj.material_slots:
            material = slot.material
            if not material:
                continue
            if material not in material_map:
                images, outputs = _material_export_images(material)
                if any(images.values()):
                    material_map[material] = _make_export_material(material, images, outputs)
                    metadata[material.name[:-14] if material.name.endswith("__MBR_ORIGINAL") else material.name] = _material_metadata(images, outputs)
            export_material = material_map.get(material)
            if export_material:
                backups.append((slot, material))
                slot.material = export_material
    return backups, list(material_map.items()), {"version": 1, "materials": metadata}


def write_export_material_sidecar(fbx_path, material_metadata):
    """Write Blender texture paths for the Maya material reconstruction pass."""
    path = os.path.splitext(fbx_path)[0] + ".mbr_materials.json"
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(material_metadata, handle, indent=2, sort_keys=True)
    except OSError:
        return False
    return True


def _restore_export_materials(slot_backups, material_pairs):
    for slot, original_material in slot_backups:
        slot.material = original_material
    for original_material, export_material in material_pairs:
        if export_material.name in bpy.data.materials:
            bpy.data.materials.remove(export_material)
        if original_material.name.endswith("__MBR_ORIGINAL"):
            original_material.name = original_material.name[:-14]



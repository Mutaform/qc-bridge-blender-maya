# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender operators and UI for Mutaform Bridge."""

import os

import bpy

from .base import QCTool
from .maya_bridge_helpers import (
    QC_MATRIX_KEY,
    _clear_mesh_creases_temporarily,
    _collection_roots,
    _collection_tree,
    _collection_tree_objects,
    _default_suzanne_names,
    _empty_roots,
    _exclude_default_suzanne,
    _exchange_path,
    _find_layer_collection,
    _format_fix_report,
    _format_scene_report,
    _objects_with_children,
    _remove_new_default_suzanne,
    _restore_mesh_creases,
    _select_only,
    _set_report,
    auto_fix_scene,
    pack_collections_to_maya,
    scene_report,
    unpack_maya_to_collections,
)
from .maya_bridge_materials import (
    _prepare_export_materials,
    _restore_export_materials,
    write_export_material_sidecar,
)

class MUTAFORMBRIDGE_OT_convert_from_maya(bpy.types.Operator):
    bl_idname = "mutaform_bridge.convert_from_maya"
    bl_label = "Convert Maya Empties to Collections"
    bl_description = "Convert imported Maya empty hierarchy into Blender collections"
    bl_options = {"REGISTER", "UNDO"}

    scope: bpy.props.EnumProperty(
        name="Scope",
        items=[
            ("SCENE", "Whole Scene", "Process every root Empty"),
            ("SELECTED", "Selected", "Process selected Empties only"),
        ],
        default="SCENE",
    )
    bake_transforms: bpy.props.BoolProperty(
        name="Bake Transforms",
        description="Keep child meshes visually in place when removing empties",
        default=True,
    )

    def execute(self, context):
        if self.scope == "SELECTED":
            pool = [obj for obj in context.selected_objects if obj.type == "EMPTY"]
        else:
            pool = [obj for obj in context.scene.objects if obj.type == "EMPTY"]
        roots = _empty_roots(pool)
        if not roots:
            self.report({"WARNING"}, "No Maya empty roots found.")
            return {"CANCELLED"}
        stats = unpack_maya_to_collections(context, roots, self.bake_transforms)
        message = f"Ready for Blender: {stats['collections']} collections, {stats['meshes']} meshes."
        _set_report(context, message)
        self.report({"INFO"}, message)
        return {"FINISHED"}


class MUTAFORMBRIDGE_OT_convert_to_maya(bpy.types.Operator):
    bl_idname = "mutaform_bridge.convert_to_maya"
    bl_label = "Convert Collections to Maya Empties"
    bl_description = "Convert Blender collections into Maya-style empties"
    bl_options = {"REGISTER", "UNDO"}

    scope: bpy.props.EnumProperty(
        name="Scope",
        items=[
            ("SCENE", "Whole Scene", "Process every top-level collection"),
            ("ACTIVE", "Active Collection", "Process only the active collection"),
        ],
        default="SCENE",
    )

    def execute(self, context):
        scene_root = context.scene.collection
        if self.scope == "ACTIVE":
            active = context.view_layer.active_layer_collection.collection
            if active == scene_root:
                self.report({"WARNING"}, "Active collection is the scene root.")
                return {"CANCELLED"}
            roots = [active]
        else:
            roots = _collection_roots(context)
        if not roots:
            self.report({"WARNING"}, "No collections found.")
            return {"CANCELLED"}
        stats = pack_collections_to_maya(context, roots)
        message = f"Ready for Maya: {stats['empties']} empties, {stats['meshes']} meshes."
        _set_report(context, message)
        self.report({"INFO"}, message)
        return {"FINISHED"}


class MUTAFORMBRIDGE_OT_receive_from_maya(bpy.types.Operator):
    bl_idname = "mutaform_bridge.receive_from_maya"
    bl_label = "Import From Maya"
    bl_description = "Import exchange FBX and convert Maya empties to Blender collections"
    bl_options = {"REGISTER", "UNDO"}

    clear_scene: bpy.props.BoolProperty(
        name="Clear Scene First",
        description="Legacy option: remove existing Blender scene objects and collections before importing",
        default=False,
    )

    def execute(self, context):
        path = _exchange_path(context)
        if not os.path.exists(path):
            self.report({"ERROR"}, f"FBX not found: {path}")
            _set_report(context, "Receive failed: FBX not found.")
            return {"CANCELLED"}
        before_objects = set(bpy.data.objects)
        before_collections = set(bpy.data.collections)
        bpy.ops.import_scene.fbx(filepath=path)
        imported = [obj for obj in bpy.data.objects if obj not in before_objects]
        imported_names = {obj.name for obj in imported}
        roots = _empty_roots([obj for obj in imported if obj.type == "EMPTY"])
        if roots:
            stats = unpack_maya_to_collections(context, roots, bake_transforms=True)
            new_collections = [coll for coll in bpy.data.collections if coll not in before_collections]
            imported_alive = [obj for obj in bpy.data.objects if obj.name in imported_names]
            fix = auto_fix_scene(context, objects=imported_alive, collections=new_collections)
            check = scene_report(context)
            message = (
                f"Imported from Maya and converted to Blender style: "
                f"{stats['collections']} collections, {stats['meshes']} meshes; "
                f"{_format_fix_report(fix)}. {_format_scene_report(check)}"
            )
        else:
            fix = auto_fix_scene(context, objects=imported, collections=[])
            message = f"Imported {len(imported)} objects. No Maya empties found; {_format_fix_report(fix)}."
        _set_report(context, message)
        self.report({"INFO"}, message)
        return {"FINISHED"}


class MUTAFORMBRIDGE_OT_send_scene_to_maya(bpy.types.Operator):
    bl_idname = "mutaform_bridge.send_scene_to_maya"
    bl_label = "Export Selected To Maya"
    bl_description = "Export selected Blender objects to the exchange FBX"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        path = _exchange_path(context)
        props = context.scene.mutaform_bridge
        selection = list(context.selected_objects)
        if not selection:
            _set_report(context, "Export selected failed: select objects to export.")
            self.report({"WARNING"}, "Select objects to export.")
            return {"CANCELLED"}
        previous_active = context.view_layer.objects.active
        suzanne_before = _default_suzanne_names()
        export_objects = _exclude_default_suzanne(_objects_with_children(selection))
        if not export_objects:
            _set_report(context, "Export selected failed: nothing to export.")
            self.report({"WARNING"}, "Nothing to export.")
            return {"CANCELLED"}
        pre_fix = auto_fix_scene(context, objects=export_objects, collections=[])
        export_objects = _exclude_default_suzanne([obj for obj in export_objects if obj.name in bpy.data.objects])
        material_slot_backups, export_material_pairs, material_metadata = _prepare_export_materials(export_objects)
        crease_backups = [] if props.export_creases else _clear_mesh_creases_temporarily(export_objects)
        _select_only(context, export_objects)
        try:
            bpy.ops.export_scene.fbx(
                filepath=path,
                use_selection=True,
                object_types={"EMPTY", "MESH"},
                mesh_smooth_type="EDGE",
                add_leaf_bones=False,
                bake_anim=False,
            )
            write_export_material_sidecar(path, material_metadata)
        finally:
            _restore_mesh_creases(crease_backups)
            _restore_export_materials(material_slot_backups, export_material_pairs)
            _remove_new_default_suzanne(suzanne_before)
            _select_only(context, selection)
            if previous_active and previous_active.name in bpy.data.objects:
                context.view_layer.objects.active = previous_active
        check = scene_report(context)
        message = (
            f"Exported selected: {os.path.basename(path)}, {len(export_objects)} objects; "
            f"{_format_fix_report(pre_fix)}. {_format_scene_report(check)}"
        )
        self.report({"INFO"}, f"Exported selected to Maya: {path}")
        _set_report(context, message)
        return {"FINISHED"}


class MUTAFORMBRIDGE_OT_send_selection_to_maya(bpy.types.Operator):
    bl_idname = "mutaform_bridge.send_selection_to_maya"
    bl_label = "Export Selected Collection To Maya"
    bl_description = "Export the active Blender collection to the exchange FBX"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        path = _exchange_path(context)
        props = context.scene.mutaform_bridge
        selection = list(context.selected_objects)
        previous_active = context.view_layer.objects.active
        active_coll = context.view_layer.active_layer_collection.collection
        active_coll_name = active_coll.name
        suzanne_before = _default_suzanne_names()
        scene_root = context.scene.collection
        if active_coll == scene_root:
            _set_report(context, "Send collection failed: select a collection in the Outliner.")
            self.report({"WARNING"}, "Select a collection in the Outliner.")
            return {"CANCELLED"}
        if not (active_coll.objects or active_coll.children or QC_MATRIX_KEY in active_coll):
            _set_report(context, "Send collection failed: selected collection is empty.")
            self.report({"WARNING"}, "Selected collection is empty.")
            return {"CANCELLED"}
        collection_tree = _collection_tree(active_coll)
        pre_fix = auto_fix_scene(
            context,
            objects=_collection_tree_objects(active_coll),
            collections=collection_tree,
        )
        export_selection = []
        packed_roots = []
        stats = pack_collections_to_maya(context, [active_coll])
        packed_roots = stats["root_empties"]
        export_selection = packed_roots
        if not export_selection:
            _set_report(context, "Send collection failed: nothing to export.")
            self.report({"WARNING"}, "Nothing to export.")
            return {"CANCELLED"}
        export_objects = _exclude_default_suzanne(_objects_with_children(export_selection))
        _select_only(context, export_objects)
        material_slot_backups, export_material_pairs, material_metadata = _prepare_export_materials(export_objects)
        crease_backups = [] if props.export_creases else _clear_mesh_creases_temporarily(export_objects)
        try:
            bpy.ops.export_scene.fbx(
                filepath=path,
                use_selection=True,
                object_types={"EMPTY", "MESH"},
                mesh_smooth_type="EDGE",
                add_leaf_bones=False,
                bake_anim=False,
            )
            write_export_material_sidecar(path, material_metadata)
        finally:
            _restore_mesh_creases(crease_backups)
            _restore_export_materials(material_slot_backups, export_material_pairs)
            _remove_new_default_suzanne(suzanne_before)
            if packed_roots:
                unpack_maya_to_collections(context, packed_roots, bake_transforms=True)
                restored_layer = _find_layer_collection(context.view_layer.layer_collection, active_coll_name)
                if restored_layer:
                    context.view_layer.active_layer_collection = restored_layer
            _select_only(context, selection)
            if previous_active and previous_active.name in bpy.data.objects:
                context.view_layer.objects.active = previous_active
        check = scene_report(context)
        _set_report(
            context,
            f"Sent collection: {active_coll_name}; {_format_fix_report(pre_fix)}. {_format_scene_report(check)}",
        )
        self.report({"INFO"}, f"Sent collection to Maya: {path}")
        return {"FINISHED"}


class MayaBridgeTool(QCTool):
    idname = "maya_bridge"
    label = "Blender / Maya"
    icon = "OUTLINER"
    classes = (
        MUTAFORMBRIDGE_OT_convert_from_maya,
        MUTAFORMBRIDGE_OT_convert_to_maya,
        MUTAFORMBRIDGE_OT_receive_from_maya,
        MUTAFORMBRIDGE_OT_send_scene_to_maya,
        MUTAFORMBRIDGE_OT_send_selection_to_maya,
    )
    scene_props = {
        "unpack_scope": bpy.props.EnumProperty(
            name="Scope",
            items=[
                ("SCENE", "Whole Scene", "Process every root Empty"),
                ("SELECTED", "Selected", "Process selected Empties only"),
            ],
            default="SELECTED",
        ),
        "unpack_bake": bpy.props.BoolProperty(
            name="Bake Transforms",
            description="Keep meshes visually in place when removing empties",
            default=True,
        ),
        "pack_scope": bpy.props.EnumProperty(
            name="Scope",
            items=[
                ("SCENE", "Whole Scene", "Process every top-level collection"),
                ("ACTIVE", "Active Collection", "Process the active collection"),
            ],
            default="SCENE",
        ),
        "receive_clear_scene": bpy.props.BoolProperty(
            name="Clear Scene Before Receive",
            description="Remove existing Blender scene content before receiving the Maya FBX",
            default=False,
        ),
        "export_creases": bpy.props.BoolProperty(
            name="Export Creases",
            description="Send Blender crease edges/vertices to Maya FBX",
            default=False,
        ),
        "show_advanced": bpy.props.BoolProperty(
            name="Advanced",
            default=False,
        ),
    }

    def draw(self, layout, context):
        props = context.scene.mutaform_bridge

        col = layout.column(align=True)
        op = col.operator(MUTAFORMBRIDGE_OT_receive_from_maya.bl_idname, text="Import From Maya", icon="IMPORT")
        op.clear_scene = False
        row = col.row(align=True)
        row.operator(MUTAFORMBRIDGE_OT_send_scene_to_maya.bl_idname, text="Export Selected", icon="EXPORT")
        row.operator(MUTAFORMBRIDGE_OT_send_selection_to_maya.bl_idname, text="Export Selected Collection", icon="OUTLINER_COLLECTION")

        layout.separator()
        advanced = layout.row(align=True)
        advanced.prop(
            props,
            "show_advanced",
            icon="DISCLOSURE_TRI_DOWN" if props.show_advanced else "DISCLOSURE_TRI_RIGHT",
            emboss=False,
            text="",
        )
        advanced.label(text="Convert Scene", icon="TOOL_SETTINGS")
        if props.show_advanced:
            box = layout.box()
            box.prop(props, "export_creases")
            box.prop(props, "unpack_scope", text="Convert Scope")
            box.prop(props, "unpack_bake")
            op = box.operator(MUTAFORMBRIDGE_OT_convert_from_maya.bl_idname, text="Convert In Blender Style", icon="OUTLINER")
            op.scope = props.unpack_scope
            op.bake_transforms = props.unpack_bake
            box.prop(props, "pack_scope", text="Send Scope")
            op = box.operator(MUTAFORMBRIDGE_OT_convert_to_maya.bl_idname, text="Convert In Maya Style", icon="EMPTY_AXIS")
            op.scope = props.pack_scope


TOOL = MayaBridgeTool()

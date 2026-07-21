# SPDX-License-Identifier: GPL-3.0-or-later
"""Mutaform Bridge for Blender."""

import importlib
import os

import bpy

from .tools import TOOL_MODULES

BRIDGE_VERSION = "1.1.1"
BRIDGE_VERSION_LABEL = f"ver {BRIDGE_VERSION}"


def _load_tools():
    loaded = []
    for name in TOOL_MODULES:
        mod = importlib.import_module(f"{__name__}.tools.{name}")
        importlib.reload(mod)
        tool = getattr(mod, "TOOL", None)
        if tool is not None:
            loaded.append(tool)
    return loaded


TOOLS = _load_tools()


def _build_props_group():
    annotations = {
        "exchange_dir": bpy.props.StringProperty(
            name="Exchange Folder",
            subtype="DIR_PATH",
            default=os.path.join(os.path.expanduser("~"), "Documents", "MutaformBridge"),
        ),
        "exchange_name": bpy.props.StringProperty(
            name="FBX Name",
            default="mutaform_bridge.fbx",
        ),
        "last_report": bpy.props.StringProperty(
            name="Last Report",
            default="Ready.",
        ),
        "show_settings": bpy.props.BoolProperty(
            name="Settings",
            default=False,
        ),
    }
    for tool in TOOLS:
        annotations[f"expand_{tool.idname}"] = bpy.props.BoolProperty(
            name=tool.label,
            default=(tool is TOOLS[0]),
        )
        for pname, prop in getattr(tool, "scene_props", {}).items():
            annotations[pname] = prop
    return type("MutaformBridgeProps", (bpy.types.PropertyGroup,), {"__annotations__": annotations})


MutaformBridgeProps = _build_props_group()


class MUTAFORMBRIDGE_PT_panel(bpy.types.Panel):
    bl_label = "QC Bridge Maya-Blender by Mutaform"
    bl_idname = "MUTAFORMBRIDGE_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "QC Maya Bridge"

    def draw(self, context):
        layout = self.layout
        props = context.scene.mutaform_bridge

        version_row = layout.row()
        version_row.alignment = "RIGHT"
        version_row.label(text=BRIDGE_VERSION_LABEL)
        layout.label(text=props.last_report, icon="INFO")
        layout.separator()

        for tool in TOOLS:
            tool.draw(layout.column(), context)

        layout.separator()
        settings = layout.row(align=True)
        settings.prop(
            props,
            "show_settings",
            icon="DISCLOSURE_TRI_DOWN" if props.show_settings else "DISCLOSURE_TRI_RIGHT",
            emboss=False,
            text="",
        )
        settings.label(text="Settings", icon="PREFERENCES")
        if props.show_settings:
            box = layout.box()
            box.prop(props, "exchange_dir")
            box.prop(props, "exchange_name")


def register():
    bpy.utils.register_class(MutaformBridgeProps)
    for tool in TOOLS:
        for cls in tool.classes:
            bpy.utils.register_class(cls)
        tool.register()
    bpy.utils.register_class(MUTAFORMBRIDGE_PT_panel)
    bpy.types.Scene.mutaform_bridge = bpy.props.PointerProperty(type=MutaformBridgeProps)


def unregister():
    del bpy.types.Scene.mutaform_bridge
    bpy.utils.unregister_class(MUTAFORMBRIDGE_PT_panel)
    for tool in reversed(TOOLS):
        tool.unregister()
        for cls in reversed(tool.classes):
            bpy.utils.unregister_class(cls)
    bpy.utils.unregister_class(MutaformBridgeProps)

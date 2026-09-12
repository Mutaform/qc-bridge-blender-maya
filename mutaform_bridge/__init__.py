# SPDX-License-Identifier: GPL-3.0-or-later
"""Mutaform Bridge for Blender.

The bridge lives in the 3D Viewport header: a Maya icon right after the
transform controls opens a popover with the tools, the way the Viewport
Shading popover does. Nothing is drawn in the N-panel any more.
"""

import importlib
import os

import bpy
import bpy.utils.previews

from .tools import TOOL_MODULES

BRIDGE_VERSION = "1.2.0"
BRIDGE_VERSION_LABEL = f"ver {BRIDGE_VERSION}"
BRIDGE_TITLE = "QC Bridge Maya-Blender"

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
ICON_FILES = {"maya": "maya_bridge.png"}
FALLBACK_HEADER_ICON = "OUTLINER"

# Popover width in UI units (1 unit ~ 20 px at 1.0 UI scale).
POPOVER_WIDTH_UNITS = 17
# Characters per line when wrapping the last report inside the popover.
REPORT_WRAP_CHARS = 46

_icons = None
_xform_template_original = None
_header_button_drawn = False


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
        for pname, prop in getattr(tool, "scene_props", {}).items():
            annotations[pname] = prop
    return type("MutaformBridgeProps", (bpy.types.PropertyGroup,), {"__annotations__": annotations})


MutaformBridgeProps = _build_props_group()


# ---------------------------------------------------------------------------
# Icons
# ---------------------------------------------------------------------------

def _load_icons():
    global _icons
    _unload_icons()
    _icons = bpy.utils.previews.new()
    for key, filename in ICON_FILES.items():
        path = os.path.join(ICON_DIR, filename)
        if os.path.isfile(path):
            _icons.load(key, path, "IMAGE")


def _unload_icons():
    global _icons
    if _icons is not None:
        bpy.utils.previews.remove(_icons)
        _icons = None


def _icon_id(key):
    if _icons is not None and key in _icons:
        return _icons[key].icon_id
    return 0


# ---------------------------------------------------------------------------
# Popover content
# ---------------------------------------------------------------------------

def _wrap_text(text, width):
    """Split text into lines no longer than `width` characters, on spaces."""
    lines = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


class MUTAFORMBRIDGE_PT_popover(bpy.types.Panel):
    """Popover body opened from the Maya icon in the 3D Viewport header."""

    bl_label = BRIDGE_TITLE
    bl_idname = "MUTAFORMBRIDGE_PT_popover"
    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_options = {"HIDE_HEADER"}
    bl_ui_units_x = POPOVER_WIDTH_UNITS

    def draw(self, context):
        layout = self.layout
        props = context.scene.mutaform_bridge

        title = layout.row()
        title.label(text=BRIDGE_TITLE, icon_value=_icon_id("maya"))
        version = title.row()
        version.alignment = "RIGHT"
        version.label(text=BRIDGE_VERSION_LABEL)

        report = layout.column(align=True)
        for index, line in enumerate(_wrap_text(props.last_report, REPORT_WRAP_CHARS)):
            report.label(text=line, icon="INFO" if index == 0 else "BLANK1")
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


# ---------------------------------------------------------------------------
# Header button
# ---------------------------------------------------------------------------

def _draw_header_button(layout):
    global _header_button_drawn
    row = layout.row(align=True)
    icon_id = _icon_id("maya")
    if icon_id:
        row.popover(panel=MUTAFORMBRIDGE_PT_popover.bl_idname, text="", icon_value=icon_id)
    else:
        row.popover(panel=MUTAFORMBRIDGE_PT_popover.bl_idname, text="", icon=FALLBACK_HEADER_ICON)
    _header_button_drawn = True


def _header_draw_begin(self, context):
    """Runs before VIEW3D_HT_header.draw: reset the per-draw marker."""
    global _header_button_drawn
    _header_button_drawn = False


def _header_draw_end(self, context):
    """Runs after VIEW3D_HT_header.draw: draw the button if no earlier hook did."""
    if not _header_button_drawn:
        _draw_header_button(self.layout)


def _xform_template_wrapped(layout, context):
    """VIEW3D_HT_header.draw_xform_template plus the bridge button right after it."""
    _xform_template_original(layout, context)
    _draw_header_button(layout)


def _install_header_hooks():
    global _xform_template_original
    header = bpy.types.VIEW3D_HT_header
    header.prepend(_header_draw_begin)
    header.append(_header_draw_end)
    original = getattr(header, "draw_xform_template", None)
    if callable(original) and _xform_template_original is None:
        _xform_template_original = original
        header.draw_xform_template = staticmethod(_xform_template_wrapped)


def _remove_header_hooks():
    global _xform_template_original
    header = bpy.types.VIEW3D_HT_header
    header.remove(_header_draw_begin)
    header.remove(_header_draw_end)
    if _xform_template_original is not None:
        current = getattr(header, "draw_xform_template", None)
        if current is _xform_template_wrapped:
            header.draw_xform_template = staticmethod(_xform_template_original)
        _xform_template_original = None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register():
    _load_icons()
    bpy.utils.register_class(MutaformBridgeProps)
    for tool in TOOLS:
        for cls in tool.classes:
            bpy.utils.register_class(cls)
        tool.register()
    bpy.utils.register_class(MUTAFORMBRIDGE_PT_popover)
    bpy.types.Scene.mutaform_bridge = bpy.props.PointerProperty(type=MutaformBridgeProps)
    _install_header_hooks()


def unregister():
    _remove_header_hooks()
    del bpy.types.Scene.mutaform_bridge
    bpy.utils.unregister_class(MUTAFORMBRIDGE_PT_popover)
    for tool in reversed(TOOLS):
        tool.unregister()
        for cls in reversed(tool.classes):
            bpy.utils.unregister_class(cls)
    bpy.utils.unregister_class(MutaformBridgeProps)
    _unload_icons()

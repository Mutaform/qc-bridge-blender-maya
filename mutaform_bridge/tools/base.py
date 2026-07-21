# SPDX-License-Identifier: GPL-3.0-or-later
# QC Utilities — Mutaform Studio
"""
Base contract for a QC Utilities tool module.

Adding a new tool = drop a module into `tools/`, subclass `QCTool`,
and expose a module-level `TOOL = MyTool()`. The core discovers it,
registers its operators, and draws its collapsible panel section.

A tool module must define:
    idname   : str   unique, snake_case (used for the expand toggle prop)
    label    : str   shown in the panel header
    classes  : list  bpy classes (Operators/PropertyGroups) to register
    draw(self, layout, context)  : draw the tool's body

Optional:
    icon     : str   Blender icon enum for the header (default 'TOOL_SETTINGS')
    register(self)   / unregister(self)  : extra setup/teardown hooks
"""


class QCTool:
    idname = "tool"
    label = "Tool"
    icon = "TOOL_SETTINGS"
    classes = ()

    def draw(self, layout, context):
        layout.label(text="Not implemented.")

    # Optional lifecycle hooks — override if a tool needs extra setup.
    def register(self):
        pass

    def unregister(self):
        pass

# SPDX-License-Identifier: GPL-3.0-or-later
# QC Utilities — Mutaform Studio
"""
Tool registry.

To add a new tool: create a module in this package exposing a module-level
`TOOL = YourTool()` (subclass of tools.base.QCTool), then add its module name
to `TOOL_MODULES` below. The core handles the rest — registration, the
collapsible panel section, and teardown.
"""

# Order here = order of sections in the N-panel.
TOOL_MODULES = (
    "maya_bridge",
)

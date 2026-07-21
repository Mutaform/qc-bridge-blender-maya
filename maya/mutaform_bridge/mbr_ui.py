# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya UI for Mutaform Bridge."""

from __future__ import annotations

from typing import Any

import maya.cmds as cmds

import mbr_core as core
import mbr_io
from mbr_core import (
    DEFAULT_EXCHANGE_DIR,
    DEFAULT_EXCHANGE_NAME,
    _set_report,
    _short,
)

WINDOW_TITLE = "QC Bridge Maya-Blender by Mutaform"


def _selected_roots() -> list[str]:
    return cmds.ls(selection=True, long=True) or []


def show_ui() -> None:
    """Open a small Maya window for the bridge."""
    window = "mutaformBridgeWindow"
    if cmds.window(window, exists=True):
        cmds.deleteUI(window)
    if cmds.windowPref(window, exists=True):
        cmds.windowPref(window, remove=True)

    cmds.window(window, title=WINDOW_TITLE, sizeable=True, widthHeight=(520, 430))
    cmds.scrollLayout(childResizable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=8, columnAttach=("both", 10))

    cmds.rowLayout(numberOfColumns=1, adjustableColumn=1)
    cmds.text(label=core.BRIDGE_VERSION_LABEL, align="right")
    cmds.setParent("..")

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(245, 245), adjustableColumn=2)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.text(label="Last Report", align="left", font="boldLabelFont")
    last_report = cmds.text(label=core.LAST_REPORT, align="left")
    cmds.setParent("..")
    cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
    cmds.text(label="Selected", align="left", font="boldLabelFont")
    root_field = cmds.textField(editable=False, text="")
    cmds.setParent("..")
    cmds.setParent("..")
    status = cmds.text(label="", align="left")
    cmds.separator(style="in")

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(438, 42), adjustableColumn=1, columnAttach=[(1, "both", 0), (2, "both", 0)])
    cmds.button(label="Import From Blender", height=36, command=lambda *_args: import_clicked())
    cmds.button(label="FBX", height=36, command=lambda *_args: import_fbx_clicked(), annotation="Import any FBX")
    cmds.setParent("..")
    cmds.button(label="Export To Blender", height=34, command=lambda *_args: export_clicked())

    cmds.frameLayout(
        label="Advanced",
        collapsable=True,
        collapse=True,
        marginWidth=8,
        marginHeight=6,
    )
    cmds.rowColumnLayout(
        numberOfColumns=2,
        columnWidth=[(1, 230), (2, 230)],
        columnSpacing=[(1, 8), (2, 8)],
        rowSpacing=[(1, 4), (2, 4)],
    )
    clean_names_box = cmds.checkBox(label="Clean FBX suffix names", value=True)
    unlock_box = cmds.checkBox(label="Unlock transforms", value=True)
    clean_history_box = cmds.checkBox(label="Clean geometry history", value=True)
    rebuild_materials_box = cmds.checkBox(label="Rebuild Blinn materials", value=True)
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.frameLayout(
        label="Settings",
        collapsable=True,
        collapse=True,
        marginWidth=8,
        marginHeight=6,
    )
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6)
    exchange_dir = cmds.textFieldGrp(label="Exchange", text=DEFAULT_EXCHANGE_DIR)
    exchange_name = cmds.textFieldGrp(label="FBX", text=DEFAULT_EXCHANGE_NAME)
    cmds.setParent("..")
    cmds.setParent("..")

    def _path_options() -> dict[str, str]:
        return {
            "folder": cmds.textFieldGrp(exchange_dir, query=True, text=True),
            "filename": cmds.textFieldGrp(exchange_name, query=True, text=True),
        }

    def _current_root() -> str | None:
        selection = cmds.ls(selection=True, long=True, type="transform") or []
        return selection[0] if selection else None

    def _refresh_selection(*_args: Any) -> None:
        root = _current_root()
        cmds.textField(root_field, edit=True, text=_short(root) if root else "")
        if root:
            cmds.text(status, edit=True, label="")
        else:
            cmds.text(status, edit=True, label="No transform selected.")
        cmds.text(last_report, edit=True, label=core.LAST_REPORT)

    def import_clicked(*_args: Any) -> None:
        try:
            result = mbr_io.import_from_blender(
                **_path_options(),
                rebuild=False,
                clean_names=cmds.checkBox(clean_names_box, query=True, value=True),
                unlock_transform_attrs=cmds.checkBox(unlock_box, query=True, value=True),
                normalize_materials=cmds.checkBox(rebuild_materials_box, query=True, value=True),
                clean_history=cmds.checkBox(clean_history_box, query=True, value=True),
            )
            converted = result["convert"]["converted"] if result.get("convert") else 0
            message = f"Imported {result['new_transform_count']} transforms, converted {converted} groups."
            _set_report(message)
            cmds.text(status, edit=True, label=message)
            cmds.text(last_report, edit=True, label=core.LAST_REPORT)
            cmds.inViewMessage(amg=f"{WINDOW_TITLE}: {message}", pos="midCenter", fade=True)
        except Exception as exc:
            _set_report(f"Import failed: {exc}")
            cmds.warning(str(exc))
            cmds.text(status, edit=True, label=str(exc))
            cmds.text(last_report, edit=True, label=core.LAST_REPORT)

    def import_fbx_clicked(*_args: Any) -> None:
        try:
            paths = cmds.fileDialog2(
                caption="Import FBX",
                fileMode=1,
                fileFilter="FBX (*.fbx)",
            )
            if not paths:
                return
            result = mbr_io.import_fbx_file(
                paths[0],
                rebuild=False,
                clean_names=cmds.checkBox(clean_names_box, query=True, value=True),
                unlock_transform_attrs=cmds.checkBox(unlock_box, query=True, value=True),
                normalize_materials=cmds.checkBox(rebuild_materials_box, query=True, value=True),
                clean_history=cmds.checkBox(clean_history_box, query=True, value=True),
            )
            converted = result["convert"]["converted"] if result.get("convert") else 0
            message = f"Imported FBX: {result['new_transform_count']} transforms, converted {converted} groups."
            _set_report(message)
            cmds.text(status, edit=True, label=message)
            cmds.text(last_report, edit=True, label=core.LAST_REPORT)
            cmds.inViewMessage(amg=f"{WINDOW_TITLE}: {message}", pos="midCenter", fade=True)
        except Exception as exc:
            _set_report(f"Import FBX failed: {exc}")
            cmds.warning(str(exc))
            cmds.text(status, edit=True, label=str(exc))
            cmds.text(last_report, edit=True, label=core.LAST_REPORT)

    def export_clicked(*_args: Any) -> None:
        try:
            result = mbr_io.export_selected_to_blender(**_path_options())
            message = f"Exported FBX: {result['size']} bytes."
            _set_report(message)
            cmds.text(status, edit=True, label=message)
            cmds.text(last_report, edit=True, label=core.LAST_REPORT)
            cmds.inViewMessage(amg=f"{WINDOW_TITLE}: {message}", pos="midCenter", fade=True)
        except Exception as exc:
            _set_report(f"Export failed: {exc}")
            cmds.warning(str(exc))
            cmds.text(status, edit=True, label=str(exc))
            cmds.text(last_report, edit=True, label=core.LAST_REPORT)

    _refresh_selection()
    cmds.scriptJob(event=("SelectionChanged", _refresh_selection), parent=window)
    cmds.showWindow(window)



"""Install Mutaform Bridge shelf and menu entries for the current Maya user."""

from __future__ import annotations

import os

import maya.cmds as cmds
import maya.mel as mel


TOOL_DIR = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
TARGET_SHELF_LABEL = "Poly Modeling"
TARGET_SHELF_CANDIDATES = ("Polygons", "Poly Modeling", "PolyModeling")
BUTTON_LABEL = "QC Bridge Maya-Blender by Mutaform"
LEGACY_BUTTON_LABELS = ("Mutaform Bridge", "QC Bridge Maya-Blender by Mutaform")
LEGACY_SHELF_NAME = "Mutaform"
MENU_NAME = "mutaformBridgeMenu"
BUTTON_ICON = os.path.join(TOOL_DIR, "icons", "qc_maya_bridge_shelf.png").replace("\\", "/")


def _target_shelf() -> str:
    for shelf in TARGET_SHELF_CANDIDATES:
        if cmds.shelfLayout(shelf, exists=True):
            return shelf
    try:
        top_shelf = mel.eval("$tmp=$gShelfTopLevel")
        selected = cmds.tabLayout(top_shelf, query=True, selectTab=True)
        if selected and cmds.shelfLayout(selected, exists=True):
            return selected
    except Exception:
        pass
    raise RuntimeError(f"Could not find the {TARGET_SHELF_LABEL} shelf or an active Maya shelf.")


def install() -> str:
    shelf = _target_shelf()

    command = (
        "import sys\n"
        f"path = r'{TOOL_DIR}'\n"
        "if path not in sys.path:\n"
        "    sys.path.append(path)\n"
        "import importlib\n"
        "import mutaform_bridge\n"
        "mutaform_bridge = importlib.reload(mutaform_bridge)\n"
        "mutaform_bridge.show_ui()\n"
    )

    for existing_shelf in cmds.lsUI(type="shelfLayout") or []:
        for child in cmds.shelfLayout(existing_shelf, query=True, childArray=True) or []:
            try:
                if cmds.shelfButton(child, query=True, label=True) in LEGACY_BUTTON_LABELS:
                    cmds.deleteUI(child)
            except Exception:
                pass

    if cmds.shelfLayout(LEGACY_SHELF_NAME, exists=True):
        children = cmds.shelfLayout(LEGACY_SHELF_NAME, query=True, childArray=True) or []
        if not children:
            cmds.deleteUI(LEGACY_SHELF_NAME)

    cmds.shelfButton(
        parent=shelf,
        label=BUTTON_LABEL,
        annotation="Open QC Bridge Maya-Blender by Mutaform",
        image1=BUTTON_ICON,
        style="iconOnly",
        command=command,
        sourceType="python",
    )
    if cmds.menu(MENU_NAME, exists=True):
        cmds.deleteUI(MENU_NAME)
    main_window = mel.eval("$tmp=$gMainWindow")
    menu = cmds.menu(MENU_NAME, label="Mutaform", parent=main_window, tearOff=True)
    cmds.menuItem(label=BUTTON_LABEL, parent=menu, command=command, sourceType="python")
    try:
        mel.eval("saveAllShelves $gShelfTopLevel")
    except Exception:
        pass
    return shelf


if __name__ == "__main__":
    print("Installed shelf:", install())

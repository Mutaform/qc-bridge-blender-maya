"""QC Bridge Maya-Blender - installer.

Drag this file into a Maya viewport to install. That writes a module file
pointing back at wherever this folder sits, adds a QC Bridge button to the
Mutaform shelf, retires the 1.1.x copy if one is found, and opens the panel.

It can also be run from the script editor:

    import sys
    sys.path.insert(0, r"C:\\path\\to\\mutaform_bridge_maya\\install")
    import install
    install.install()

Nothing is copied anywhere. The module file is a pointer, so the built-in
updater only has to replace one folder - no reinstall, no stale second copy
to get confused with. This is the installer QC Bake for Maya uses, with the
names changed.
"""

import os
import re
import shutil
import sys

import maya.cmds as cmds
import maya.mel as mel

MODULE_NAME = "mutaform_bridge"
SHELF_NAME = "Mutaform"
BUTTON_LABEL = "QC Bridge"
WORKSPACE_CONTROL = "MutaformBridgePanelWorkspaceControl"
LEGACY_WINDOW = "mutaformBridgeWindow"

# Where the package lives, for the panel's uiScript on a cold start: Maya
# rebuilds a docked panel before anything has put the folder on sys.path.
ROOT_OPTIONVAR = "mutaformBridge_install_root"

# What the 1.1.x install left behind: a button under either of these labels on
# whatever shelf it was put on, a menu in the main window, and the modules
# unpacked straight into Maya's scripts folder.
LEGACY_BUTTON_LABELS = ("Mutaform Bridge", "QC Bridge Maya-Blender by Mutaform")
LEGACY_MENU = "mutaformBridgeMenu"
LEGACY_MODULES = ("mbr_core", "mbr_io", "mbr_materials", "mbr_scene",
                  "mbr_locked_normals", "mbr_ui", "install_shelf_button")

# The shelf icon lives inside the package rather than beside it so that it
# travels - both into the release zip and, more importantly, through an
# update, which swaps the package folder and nothing else.
SHELF_ICON = os.path.join(MODULE_NAME, "icons", "qc_maya_bridge_shelf.png")

# Used when the bundled icon cannot be found, so a broken path never leaves
# the button blank.
FALLBACK_ICON = ":/doubleHorizArrow.png"

COMMAND = """import sys

MUTAFORM_BRIDGE_ROOT = r"{root}"
if MUTAFORM_BRIDGE_ROOT not in sys.path:
    sys.path.insert(0, MUTAFORM_BRIDGE_ROOT)

import mutaform_bridge
mutaform_bridge.show()
"""


def repo_root():
    """Return the install root - the folder holding mutaform_bridge/."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def shelf_icon(root=None):
    """Return the icon path for the shelf button.

    Falls back to a Maya resource rather than an empty button if the bundled
    file is missing - a shelf button with no image is not obviously broken,
    it just quietly becomes impossible to find among thirty others.
    """
    root = root or repo_root()
    path = os.path.join(root, SHELF_ICON)
    return path if os.path.isfile(path) else FALLBACK_ICON


def modules_dir():
    """Return this Maya version's user modules folder, creating it if needed.

    On a machine whose Documents folder is redirected to OneDrive - and with a
    localised folder name at that - this path is neither ASCII nor where the
    documentation says it is, so it is always asked of Maya rather than
    assembled by hand.
    """
    path = os.path.join(cmds.internalVar(userAppDir=True),
                        cmds.about(version=True), "modules")
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def module_file():
    return os.path.join(modules_dir(), MODULE_NAME + ".mod")


def write_module(root=None):
    """Write the .mod file that puts this folder on Maya's script path."""
    root = root or repo_root()
    from mutaform_bridge import VERSION_STRING  # noqa: E402 - needs the path first

    # "scripts: ." adds the module root itself, which is where the package
    # lives - verified against Maya 2025 rather than assumed.
    body = "+ {name} {version} {root}\nscripts: .\n".format(
        name=MODULE_NAME, version=VERSION_STRING, root=root.replace("\\", "/"))

    path = module_file()
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)
    return path


def ensure_shelf():
    """Return the Mutaform shelf, creating it if this is the first tool on it."""
    top = mel.eval("$tmp = $gShelfTopLevel")
    if cmds.shelfLayout(SHELF_NAME, exists=True):
        return SHELF_NAME
    mel.eval('addNewShelfTab "%s";' % SHELF_NAME)
    cmds.tabLayout(top, edit=True, selectTab=SHELF_NAME)
    return SHELF_NAME


def _is_legacy_copy(folder):
    """True for a 1.1.x install: the modules lie in the folder, no package."""
    return (os.path.isdir(folder)
            and os.path.isfile(os.path.join(folder, "mbr_core.py"))
            and not os.path.isfile(os.path.join(folder, "__init__.py")))


def remove_legacy():
    """Retire a 1.1.x install: its buttons, its menu, its copy of the code.

    Two copies of the tool on the path are worse than none - which one wins
    depends on path order, and an artist ends up updating a tool while still
    running the old code. The old shelf button carried the path to its copy
    in its own command, so that is where the copy is looked for, plus the
    scripts folders it was documented to live in.
    """
    removed = []
    candidates = set()

    for shelf in cmds.lsUI(type="shelfLayout") or []:
        for child in cmds.shelfLayout(shelf, query=True, childArray=True) or []:
            if not cmds.shelfButton(child, query=True, exists=True):
                continue
            label = cmds.shelfButton(child, query=True, label=True)
            if label not in LEGACY_BUTTON_LABELS:
                continue
            command = cmds.shelfButton(child, query=True, command=True) or ""
            match = re.search(r"path = r'([^']+)'", command)
            if match:
                candidates.add(match.group(1))
            cmds.deleteUI(child)
            removed.append("shelf button '%s' on %s" % (label, shelf))

    if cmds.menu(LEGACY_MENU, exists=True):
        cmds.deleteUI(LEGACY_MENU)
        removed.append("menu " + LEGACY_MENU)

    candidates.add(os.path.join(cmds.internalVar(userScriptDir=True), MODULE_NAME))
    candidates.add(os.path.join(os.path.expanduser("~"), "Documents", "maya",
                                cmds.about(version=True), "scripts", MODULE_NAME))
    for folder in sorted(candidates):
        folder = os.path.normpath(folder)
        if not _is_legacy_copy(folder):
            continue
        try:
            shutil.rmtree(folder)
            removed.append("folder " + folder)
        except OSError as exc:
            cmds.warning("Could not remove the old copy at %s: %s" % (folder, exc))

    # Forget the old modules loaded in this session, or the package would
    # import next to them and the shelf button would keep running old code
    # until Maya restarts.
    for name in [n for n in list(sys.modules) if n in LEGACY_MODULES]:
        del sys.modules[name]
    old = sys.modules.get(MODULE_NAME)
    if old is not None and not hasattr(old, "__path__"):
        del sys.modules[MODULE_NAME]
    sys.path[:] = [p for p in sys.path
                   if os.path.basename(os.path.normpath(p)) != MODULE_NAME]
    return removed


def add_shelf_button(root=None):
    """Put a QC Bridge button on the Mutaform shelf, replacing any older one."""
    root = root or repo_root()
    shelf = ensure_shelf()

    for child in cmds.shelfLayout(shelf, query=True, childArray=True) or []:
        if cmds.control(child, query=True, exists=True) \
                and cmds.shelfButton(child, query=True, exists=True) \
                and cmds.shelfButton(child, query=True, label=True) == BUTTON_LABEL:
            cmds.deleteUI(child)

    icon = shelf_icon(root)

    # No imageOverlayLabel: a word stamped across a 32-pixel icon obscures the
    # very thing that makes it findable. The tooltip carries the name.
    return cmds.shelfButton(
        parent=shelf,
        label=BUTTON_LABEL,
        annotation="QC Bridge Maya-Blender - exchange scenes with Blender through FBX",
        image=icon,
        image1=icon,
        sourceType="python",
        command=COMMAND.format(root=root),
    )


def install():
    """Write the module, add the shelf button, retire 1.1.x, open the panel."""
    root = repo_root()
    if root not in sys.path:
        sys.path.insert(0, root)

    legacy = remove_legacy()
    path = write_module(root)
    cmds.optionVar(stringValue=(ROOT_OPTIONVAR, root.replace("\\", "/")))
    add_shelf_button(root)

    # Save the shelf now, or the button is lost if Maya exits uncleanly.
    mel.eval('saveAllShelves $gShelfTopLevel;')

    import mutaform_bridge
    mutaform_bridge.show()

    print("QC Bridge %s installed.\n  module: %s\n  shelf:  %s"
          % (mutaform_bridge.VERSION_STRING, path, SHELF_NAME))
    for item in legacy:
        print("  retired: " + item)
    return path


def uninstall():
    """Remove the module file, the shelf button and the panel. The folder is left."""
    removed = []

    path = module_file()
    if os.path.isfile(path):
        os.remove(path)
        removed.append(path)

    if cmds.shelfLayout(SHELF_NAME, exists=True):
        for child in cmds.shelfLayout(SHELF_NAME, query=True, childArray=True) or []:
            if cmds.control(child, query=True, exists=True) \
                    and cmds.shelfButton(child, query=True, exists=True) \
                    and cmds.shelfButton(child, query=True, label=True) == BUTTON_LABEL:
                cmds.deleteUI(child)
                removed.append("shelf button")
        mel.eval('saveAllShelves $gShelfTopLevel;')

    if cmds.workspaceControl(WORKSPACE_CONTROL, query=True, exists=True):
        cmds.deleteUI(WORKSPACE_CONTROL)
        removed.append(WORKSPACE_CONTROL)
    if cmds.window(LEGACY_WINDOW, exists=True):
        cmds.deleteUI(LEGACY_WINDOW)
        removed.append(LEGACY_WINDOW)
    if cmds.optionVar(exists=ROOT_OPTIONVAR):
        cmds.optionVar(remove=ROOT_OPTIONVAR)

    print("QC Bridge uninstalled: %s" % (", ".join(removed) or "nothing to remove"))
    return removed


def onMayaDroppedPythonFile(*args):
    """Maya calls this when the file is dragged into a viewport."""
    install()

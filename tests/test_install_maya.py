# QC Bridge Maya-Blender - first-install test
# -------------------------------------------
# Rehearses what a new artist does: unzip the published archive somewhere it
# has never been, and drop install/install.py into a Maya viewport. Nothing in
# here reaches back into the development repository, which is the point - if
# the release archive is missing a file, this is where it shows.
#
#     import importlib.util
#     spec = importlib.util.spec_from_file_location(
#         "mutaform_bridge_install_test",
#         r"D:\path\to\qc_mutaform_bridge\Git\tests\test_install_maya.py")
#     m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
#     print(m.run())
#
# Touches the shelf and the module file, never the scene: it uninstalls the
# bridge, installs a copy from the archive, then puts the development install
# (the repository's maya/ folder) back.

import glob
import os
import shutil
import sys
import tempfile
import traceback
import zipfile

import maya.cmds as cmds

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEV_ROOT = os.path.join(REPO, "maya")

RESULTS = []


def check(label, got, want):
    RESULTS.append((got == want, label, got, want))


def _module_file():
    return os.path.join(cmds.internalVar(userAppDir=True),
                        cmds.about(version=True), "modules",
                        "mutaform_bridge.mod")


def _find_archives():
    """Newest-last list of built Maya archives, wherever the build put them."""
    found = []
    for base in (REPO, os.path.join(os.path.dirname(REPO), "Dev")):
        found.extend(glob.glob(os.path.join(base, "dist", "mutaform_bridge_maya*.zip")))
    return sorted(found, key=os.path.getmtime)


def _our_buttons():
    if not cmds.shelfLayout("Mutaform", exists=True):
        return []
    buttons = []
    for child in cmds.shelfLayout("Mutaform", query=True, childArray=True) or []:
        if cmds.shelfButton(child, query=True, exists=True) \
                and cmds.shelfButton(child, query=True, label=True) == "QC Bridge":
            buttons.append(child)
    return buttons


def _forget_everything():
    """Leave this Maya with no trace of the bridge loaded or installed.

    Only our own button is removed from the Mutaform shelf: other studio
    tools live there too.
    """
    if "mutaform_bridge.ui.panel" in sys.modules:
        try:
            sys.modules["mutaform_bridge.ui.panel"].close()
        except Exception:
            pass
    if cmds.workspaceControl("MutaformBridgePanelWorkspaceControl", query=True, exists=True):
        cmds.deleteUI("MutaformBridgePanelWorkspaceControl")
    for name in [n for n in list(sys.modules)
                 if n == "mutaform_bridge" or n.startswith("mutaform_bridge.")
                 or n.startswith("mbr_") or n == "install"]:
        del sys.modules[name]
    sys.path[:] = [p for p in sys.path
                   if "qc_mutaform_bridge" not in p and "mutaform_bridge_fresh" not in p]

    path = _module_file()
    if os.path.isfile(path):
        os.remove(path)
    for child in _our_buttons():
        cmds.deleteUI(child)


def run():
    """Install from the newest dist archive into a fresh folder, then restore."""
    del RESULTS[:]
    notes = []
    fresh = None

    try:
        _forget_everything()

        archives = _find_archives()
        check("a release archive exists", bool(archives), True)
        if not archives:
            return _report(notes)
        archive = archives[-1]
        notes.append("archive: %s" % os.path.basename(archive))

        fresh = tempfile.mkdtemp(prefix="mutaform_bridge_fresh_")
        with zipfile.ZipFile(archive) as handle:
            handle.extractall(fresh)

        tops = [os.path.join(fresh, name) for name in os.listdir(fresh)]
        tool_dir = tops[0] if len(tops) == 1 and os.path.isdir(tops[0]) else fresh
        notes.append("unpacked to: %s" % tool_dir)

        installer_py = os.path.join(tool_dir, "install", "install.py")
        check("install.py is where the README says it is",
              os.path.isfile(installer_py), True)

        sys.path.insert(0, os.path.dirname(installer_py))
        import install as installer

        check("the installer takes its own folder as the root",
              installer.repo_root(), tool_dir)

        # The real drag-into-the-viewport entry point, not install() directly.
        installer.onMayaDroppedPythonFile()
        notes.append("ran onMayaDroppedPythonFile()")

        path = _module_file()
        check("a module file was written", os.path.isfile(path), True)
        if os.path.isfile(path):
            body = open(path, encoding="utf-8").read()
            notes.append("module: %r" % body)
            check("pointing at the unpacked folder",
                  tool_dir.replace("\\", "/") in body, True)

        import mutaform_bridge
        check("the package imports", bool(mutaform_bridge.VERSION_STRING), True)
        check("out of the new folder, not the repository",
              os.path.dirname(os.path.dirname(mutaform_bridge.__file__)), tool_dir)
        notes.append("version: %s" % mutaform_bridge.VERSION_STRING)

        buttons = _our_buttons()
        check("exactly one shelf button", len(buttons), 1)
        icon = (cmds.shelfButton(buttons[0], query=True, image1=True)
                if buttons else "")
        notes.append("icon: %s" % icon)
        check("wearing the bundled icon, not a Maya fallback",
              icon.endswith("qc_maya_bridge_shelf.png"), True)
        check("and that file really shipped", os.path.isfile(icon), True)

        check("the panel opened",
              cmds.workspaceControl("MutaformBridgePanelWorkspaceControl",
                                    query=True, exists=True), True)
        from mutaform_bridge.ui import panel as panel_mod
        check("subscriptions armed", len(panel_mod._running_jobs()), 1)
        check("the uiScript knows the install root",
              cmds.optionVar(query="mutaformBridge_install_root"),
              tool_dir.replace("\\", "/"))

        # Loading is not the same as working: a read-only pass over the scene.
        from mutaform_bridge import mbr_scene
        report = mbr_scene.check_scene()
        check("check_scene runs on a fresh install", isinstance(report, dict), True)
    except Exception:
        notes.append(traceback.format_exc())
    finally:
        try:
            _forget_everything()
            sys.path.insert(0, os.path.join(DEV_ROOT, "install"))
            import install as dev_installer
            dev_installer.install()
            import mutaform_bridge as restored
            notes.append("restored the development install: %s from %s"
                         % (restored.VERSION_STRING,
                            os.path.dirname(os.path.dirname(restored.__file__))))
        except Exception:
            notes.append("RESTORE FAILED:\n" + traceback.format_exc())
        if fresh:
            shutil.rmtree(fresh, ignore_errors=True)

    return _report(notes)


def _report(notes):
    failures = [r for r in RESULTS if not r[0]]
    lines = ["%d checks, %d failed" % (len(RESULTS), len(failures))]
    for _, label, got, want in failures:
        lines.append("  FAIL %s\n       got:  %r\n       want: %r"
                     % (label, got, want))
    lines.append("")
    lines.extend(notes)
    return "\n".join(lines)

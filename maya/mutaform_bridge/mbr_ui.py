# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya window for QC Bridge Maya-Blender.

The update banner, the background check and the install-with-rollback flow
are the ones QC Bake for Maya uses, carried over as they are. The one
difference is delivery: QC Bake is a Qt panel and gets the worker thread's
answer through a Qt signal; this window is built with maya.cmds, so the
answer comes back through maya.utils.executeDeferred, which likewise lands on
the main thread.
"""

from __future__ import annotations

import importlib
import sys
import threading
import time
import traceback
from typing import Any

import maya.cmds as cmds
import maya.utils

from . import BRIDGE_VERSION_LABEL, VERSION_STRING, prefs, updater
from . import mbr_core as core
from . import mbr_io, mbr_locked_normals, mbr_scene
from .mbr_core import _set_report, _short

WINDOW = "mutaformBridgeWindow"
WINDOW_TITLE = "QC Bridge Maya-Blender by Mutaform"
TOOL_NAME = "QC Bridge"

# The window the module is currently serving, if any.
_WINDOW = None


def _selected_roots() -> list[str]:
    selection = cmds.ls(selection=True, long=True, flatten=True) or []
    roots: list[str] = []
    seen: set[str] = set()
    for item in selection:
        node = item.split(".", 1)[0]
        if not cmds.objExists(node):
            continue
        if cmds.nodeType(node) == "transform":
            transform = node
        else:
            parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
            transform = parents[0] if parents else node
        if transform not in seen:
            roots.append(transform)
            seen.add(transform)
    return roots


def _process_events() -> None:
    """Let the UI repaint before a blocking download starts."""
    try:
        from PySide6 import QtWidgets
    except ImportError:
        try:
            from PySide2 import QtWidgets  # type: ignore[no-redef]
        except ImportError:
            return
    app = QtWidgets.QApplication.instance()
    if app is not None:
        app.processEvents()


class UpdateCheck(object):
    """Fetches the update manifest off the main thread.

    The check must never be able to stall Maya. A studio proxy that black-holes
    the request would otherwise freeze the whole application for the length of
    the timeout, every time the window opened - so the request runs on a plain
    worker thread that touches nothing but urllib, and the answer is handed to
    maya.utils.executeDeferred, which runs it on the main thread. No maya.cmds
    is called from the thread, because none of it is thread-safe.
    """

    def __init__(self, url, callback):
        self._url = url
        self._callback = callback
        self._thread = None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            manifest, error = updater.check(self._url)
        except Exception as exc:                 # never kill the worker
            manifest, error = None, "Update check failed: %s" % exc
        maya.utils.executeDeferred(self._callback, manifest, error)


class BridgeWindow(object):
    """The bridge window: import/export, cleanup tools, settings, updates."""

    def __init__(self):
        self.settings = prefs.load()
        self._pending_update = None
        self._update_check = None
        self._announce_update = False
        self._build()

    # -- building --------------------------------------------------------------
    def _build(self):
        if cmds.window(WINDOW, exists=True):
            cmds.deleteUI(WINDOW)
        if cmds.windowPref(WINDOW, exists=True):
            cmds.windowPref(WINDOW, remove=True)

        cmds.window(WINDOW, title=WINDOW_TITLE, sizeable=True, widthHeight=(520, 480))
        cmds.scrollLayout(childResizable=True)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=8, columnAttach=("both", 10))

        cmds.rowLayout(numberOfColumns=1, adjustableColumn=1)
        cmds.text(label=BRIDGE_VERSION_LABEL, align="right")
        cmds.setParent("..")

        self._build_update_banner()

        cmds.rowLayout(numberOfColumns=2, columnWidth2=(245, 245), adjustableColumn=2)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
        cmds.text(label="Last Report", align="left", font="boldLabelFont")
        self.last_report = cmds.text(label=core.LAST_REPORT, align="left", wordWrap=True)
        cmds.setParent("..")
        cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
        cmds.text(label="Selected", align="left", font="boldLabelFont")
        self.root_field = cmds.textField(editable=False, text="")
        cmds.setParent("..")
        cmds.setParent("..")
        self.status = cmds.text(label="", align="left", wordWrap=True)
        cmds.separator(style="in")

        cmds.rowLayout(numberOfColumns=2, columnWidth2=(438, 42), adjustableColumn=1,
                       columnAttach=[(1, "both", 0), (2, "both", 0)])
        cmds.button(label="Import From Blender", height=36, command=lambda *_args: self.import_clicked())
        cmds.button(label="FBX", height=36, command=lambda *_args: self.import_fbx_clicked(),
                    annotation="Import any FBX")
        cmds.setParent("..")
        cmds.button(label="Export To Blender", height=34, command=lambda *_args: self.export_clicked())

        cmds.frameLayout(label="Advanced", collapsable=True, collapse=True, marginWidth=8, marginHeight=6)
        cmds.rowColumnLayout(
            numberOfColumns=2,
            columnWidth=[(1, 230), (2, 230)],
            columnSpacing=[(1, 8), (2, 8)],
            rowSpacing=[(1, 4), (2, 4)],
        )
        self.clean_names_box = cmds.checkBox(label="Clean FBX suffix names", value=True)
        self.unlock_box = cmds.checkBox(label="Unlock transforms", value=True)
        self.clean_history_box = cmds.checkBox(label="Clean geometry history", value=True)
        self.rebuild_materials_box = cmds.checkBox(label="Rebuild Blinn materials", value=True)
        cmds.setParent("..")
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(230, 230), adjustableColumn=2,
                       columnAttach=[(1, "both", 0), (2, "both", 0)])
        cmds.button(label="Find Random Sharp", height=28, command=lambda *_args: self.find_random_sharp_clicked())
        cmds.button(label="Fix Random Sharp", height=28, command=lambda *_args: self.fix_random_sharp_clicked())
        cmds.setParent("..")
        cmds.setParent("..")

        cmds.frameLayout(label="Settings", collapsable=True, collapse=True, marginWidth=8, marginHeight=6)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=6)
        # Remembered between sessions: these are optionVars, see prefs.py.
        self.exchange_dir = cmds.textFieldGrp(
            label="Exchange", text=self.settings.exchange_dir,
            changeCommand=lambda value: setattr(self.settings, "exchange_dir", value))
        self.exchange_name = cmds.textFieldGrp(
            label="FBX", text=self.settings.exchange_name,
            changeCommand=lambda value: setattr(self.settings, "exchange_name", value))
        cmds.separator(style="in")
        cmds.text(label="Updates", align="left", font="boldLabelFont")
        self.auto_check_box = cmds.checkBox(
            label="Check on Open",
            value=self.settings.update_auto_check,
            annotation="Maya has no add-on repository of its own, so QC Bridge asks a\n"
                       "manifest we publish whether a newer release exists.\n"
                       "It only ever tells you - it never installs on its own.\n"
                       "\n"
                       "Checked every time the window is opened, in the background.",
            changeCommand=lambda value: setattr(self.settings, "update_auto_check", bool(value)))
        cmds.button(label="Check for Updates Now", command=lambda *_args: self.check_for_updates(announce=True))
        cmds.setParent("..")
        cmds.setParent("..")

        cmds.rowLayout(numberOfColumns=1, columnAttach=(1, "left", 0))
        cmds.button(
            label="Unlock\nNormals",
            width=66,
            height=50,
            command=lambda *_args: self.locked_normals_clicked(),
            annotation="Convert locked imported normals to Maya soft and hard edges",
        )
        cmds.setParent("..")

        self._refresh_selection()
        cmds.scriptJob(event=("SelectionChanged", self._refresh_selection), parent=WINDOW)
        cmds.showWindow(WINDOW)

    def _build_update_banner(self):
        """A strip that appears only when a newer release has been published.

        Deliberately not a popup. An update is news, not an interruption - it
        waits at the top of the window until the artist has a moment, and until
        then the tool behaves exactly as it did.
        """
        self.update_banner = cmds.frameLayout(
            labelVisible=False, borderVisible=False, marginWidth=8, marginHeight=6,
            backgroundColor=(0.17, 0.23, 0.29), visible=False)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
        self.update_label = cmds.text(label="", align="left", wordWrap=True)

        # Opposite corners, with the whole width between them. Side by side,
        # the two are one slip apart - and they do very different things: one
        # replaces the running tool, the other silently hides the offer.
        cmds.rowLayout(numberOfColumns=3, adjustableColumn=2,
                       columnAttach=[(1, "left", 0), (2, "both", 0), (3, "right", 0)])
        self.btn_skip_update = cmds.button(
            label="Skip", width=72, height=26,
            annotation="Stop offering this particular version. A later one will still be announced.",
            command=lambda *_args: self._on_skip_update())
        cmds.text(label="")
        self.btn_update = cmds.button(
            label="Install", width=96, height=26, backgroundColor=(0.24, 0.42, 0.55),
            annotation="Download the new version, replace this one and reload.\n"
                       "The current version is kept until the new one has loaded.",
            command=lambda *_args: self._on_install_update())
        cmds.setParent("..")
        cmds.setParent("..")
        cmds.setParent("..")

    # -- status ----------------------------------------------------------------
    def _alive(self) -> bool:
        return _WINDOW is self and cmds.window(WINDOW, exists=True)

    def show_message(self, kind: str, text: str) -> None:
        if cmds.text(self.status, exists=True):
            prefix = {"WARNING": "Warning: ", "ERROR": "Error: "}.get(kind, "")
            cmds.text(self.status, edit=True, label=prefix + text)
        if kind in ("WARNING", "ERROR"):
            cmds.warning(text)

    def clear_message(self) -> None:
        if cmds.text(self.status, exists=True):
            cmds.text(self.status, edit=True, label="")

    def _show_report(self) -> None:
        if cmds.text(self.last_report, exists=True):
            cmds.text(self.last_report, edit=True, label=core.LAST_REPORT)

    def _path_options(self) -> dict[str, str]:
        return {
            "folder": cmds.textFieldGrp(self.exchange_dir, query=True, text=True),
            "filename": cmds.textFieldGrp(self.exchange_name, query=True, text=True),
        }

    def _current_root(self) -> str | None:
        selection = cmds.ls(selection=True, long=True, type="transform") or []
        return selection[0] if selection else None

    def _refresh_selection(self, *_args: Any) -> None:
        if not cmds.textField(self.root_field, exists=True):
            return
        root = self._current_root()
        cmds.textField(self.root_field, edit=True, text=_short(root) if root else "")
        cmds.text(self.status, edit=True, label="" if root else "No transform selected.")
        self._show_report()

    def _finished(self, message: str) -> None:
        """Show a short message in the status line and the full report above it."""
        self.show_message("INFO", message)
        self._show_report()
        cmds.inViewMessage(amg=f"{WINDOW_TITLE}: {message}", pos="midCenter", fade=True)

    def _failed(self, what: str, exc: Exception) -> None:
        traceback.print_exc()
        _set_report(f"{what} failed: {exc}")
        self.show_message("ERROR", str(exc))
        self._show_report()

    # -- actions ---------------------------------------------------------------
    def _import_options(self) -> dict[str, Any]:
        return {
            "rebuild": False,
            "clean_names": cmds.checkBox(self.clean_names_box, query=True, value=True),
            "unlock_transform_attrs": cmds.checkBox(self.unlock_box, query=True, value=True),
            "normalize_materials": cmds.checkBox(self.rebuild_materials_box, query=True, value=True),
            "clean_history": cmds.checkBox(self.clean_history_box, query=True, value=True),
        }

    def import_clicked(self) -> None:
        try:
            result = mbr_io.import_from_blender(**self._path_options(), **self._import_options())
            converted = result["convert"]["converted"] if result.get("convert") else 0
            self._finished(f"Imported {result['new_transform_count']} transforms, converted {converted} groups.")
        except Exception as exc:
            self._failed("Import", exc)

    def import_fbx_clicked(self) -> None:
        try:
            paths = cmds.fileDialog2(caption="Import FBX", fileMode=1, fileFilter="FBX (*.fbx)")
            if not paths:
                return
            result = mbr_io.import_fbx_file(paths[0], **self._import_options())
            converted = result["convert"]["converted"] if result.get("convert") else 0
            self._finished(f"Imported FBX: {result['new_transform_count']} transforms, converted {converted} groups.")
        except Exception as exc:
            self._failed("Import FBX", exc)

    def export_clicked(self) -> None:
        try:
            result = mbr_io.export_selected_to_blender(**self._path_options())
            self._finished(f"Exported FBX: {result['size']} bytes.")
        except Exception as exc:
            self._failed("Export", exc)

    def _advanced_roots(self) -> list[str] | None:
        return _selected_roots() or None

    def find_random_sharp_clicked(self) -> None:
        try:
            result = mbr_scene.find_random_sharp_edges(roots=self._advanced_roots(), select_edges=True)
            self._finished(f"Random Sharp: {result['edges']} edge(s) found.")
        except Exception as exc:
            self._failed("Find Random Sharp", exc)

    def fix_random_sharp_clicked(self) -> None:
        try:
            result = mbr_scene.fix_random_sharp_edges(roots=self._advanced_roots(), select_edges=True)
            self._finished(f"Random Sharp fixed: {result['fixed']} edge(s), {result['failed']} failed.")
        except Exception as exc:
            self._failed("Fix Random Sharp", exc)

    def locked_normals_clicked(self) -> None:
        try:
            processed = mbr_locked_normals.convert_selected()
            message = f"Locked normals converted: {processed} mesh(es)."
            _set_report(message)
            self._finished(message)
        except Exception as exc:
            self._failed("Locked normals", exc)

    # -- updates ---------------------------------------------------------------
    def check_on_open(self):
        """Check every time the tool is opened. No clock, no conditions.

        Opening the bridge from the shelf is a deliberate act, and the moment
        an artist is most willing to be told the tool is out of date. Anything
        clever here - a timestamp, a rate limit - eventually produces the one
        behaviour that matters: a tool that knows it is out of date and says
        nothing. That happened to QC Bake, twice, and it is not worth the
        saved request.

        Honoured only when "Check on Open" is on: an artist who turned it off
        meant it.
        """
        if not self.settings.update_auto_check:
            return
        self.check_for_updates(announce=False)

    def check_for_updates(self, announce=True):
        """Start a check. `announce` reports "you are up to date" as well.

        Silent when it runs on its own: nobody wants "no update available" in
        the status line every time they open the tool. A check the artist
        asked for says so either way, because a button that does nothing
        visible reads as broken.
        """
        if self._update_check is not None:
            return
        url = self.settings.update_url
        self._announce_update = announce
        if announce:
            self.show_message("INFO", "Checking for updates...")

        self._update_check = UpdateCheck(url, self._on_update_checked)
        self._update_check.start()

    def _on_update_checked(self, manifest, error):
        """Back on the main thread with the manifest, or a reason there isn't."""
        self._update_check = None
        if not self._alive():
            return

        if error:
            # A failed check is not the artist's problem unless they asked.
            if self._announce_update:
                self.show_message("WARNING", error)
            return

        self.settings.update_last_check = time.time()
        # Recorded together, so "checked recently" can be told from "checked
        # recently, by a different version of the tool".
        self.settings.update_last_version = VERSION_STRING
        remote = manifest.get("version", "")

        if not updater.is_newer(remote, VERSION_STRING):
            if self._announce_update:
                self.show_message("INFO", "%s %s is the latest version." % (TOOL_NAME, VERSION_STRING))
            return

        if remote == self.settings.update_skip_version:
            return

        self._pending_update = manifest
        notes = manifest.get("notes") or ""
        cmds.text(self.update_label, edit=True,
                  label="%s %s is available (you have %s).%s"
                        % (TOOL_NAME, remote, VERSION_STRING, ("\n" + notes) if notes else ""))
        cmds.button(self.btn_update, edit=True, enable=True)
        cmds.frameLayout(self.update_banner, edit=True, visible=True)
        # The banner is now carrying the news, so the status line should stop
        # saying "Checking for updates..." - left there it reads as a check
        # that never finished.
        if self._announce_update:
            self.clear_message()

    def _on_skip_update(self):
        if self._pending_update:
            self.settings.update_skip_version = self._pending_update.get("version", "")
        self._pending_update = None
        cmds.frameLayout(self.update_banner, edit=True, visible=False)

    def _on_install_update(self):
        """Fetch, verify, swap and reload. Never silent about what happened."""
        manifest = self._pending_update
        if not manifest:
            return

        cmds.button(self.btn_update, edit=True, enable=False)
        self.show_message("INFO", "Downloading %s %s..." % (TOOL_NAME, manifest.get("version")))
        _process_events()

        install_dir = updater.install_dir_for(updater.__file__)
        try:
            backup, error = updater.perform_update(manifest, install_dir)
        except Exception as exc:
            traceback.print_exc()
            backup, error = None, "Update failed: %s" % exc

        if error:
            cmds.button(self.btn_update, edit=True, enable=True)
            self.show_message("ERROR", error)
            return

        # The swap is done. Reloading has to happen after this handler has
        # returned, because it destroys the very window the handler is running
        # from - and the backup is kept until the new version has actually
        # imported, so a broken release cannot take the tool out of the studio.
        maya.utils.executeDeferred(_finish_update, backup, install_dir, manifest.get("version", ""))


# -----------------------------------------------------------------------------
# Module entry points
# -----------------------------------------------------------------------------
def show_ui():
    """Open the bridge window and check for updates."""
    global _WINDOW
    _WINDOW = BridgeWindow()
    _WINDOW.check_on_open()
    return _WINDOW


def close():
    """Close the window. Its scriptJob is parented to it and goes with it."""
    global _WINDOW
    _WINDOW = None
    if cmds.window(WINDOW, exists=True):
        cmds.deleteUI(WINDOW)


def reload_package():
    """Drop the package and bring it back at whatever version is on disk."""
    close()
    package = updater.PACKAGE_NAME
    for name in [n for n in list(sys.modules) if n == package or n.startswith(package + ".")]:
        del sys.modules[name]

    module = importlib.import_module(package)
    return module.show()


def _finish_update(backup, install_dir, version):
    """Reload after a swap, and put the old version back if it will not load.

    An update that installs but cannot import would otherwise leave the artist
    with no tool and no obvious way back, which is the one failure an updater
    absolutely must not have.
    """
    try:
        window = reload_package()
    except Exception:
        traceback.print_exc()
        restored = updater.rollback(backup, install_dir)
        try:
            window = reload_package()
        except Exception:
            traceback.print_exc()
            cmds.warning(
                "%s %s failed to load and the previous version could not be "
                "restored automatically. Reinstall from install/install.py."
                % (TOOL_NAME, version))
            return None
        if window is not None and restored:
            window.show_message(
                "ERROR",
                "%s %s failed to load, so the previous version was put back. "
                "The traceback is in the Script Editor." % (TOOL_NAME, version))
        return window

    updater.discard_backup(backup)
    if window is not None:
        window.show_message("INFO", "Updated to %s %s." % (TOOL_NAME, version))
    return window

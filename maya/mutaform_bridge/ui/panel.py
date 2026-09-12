# SPDX-License-Identifier: GPL-3.0-or-later
"""The QC Bridge panel: a dockable PySide6 widget in the studio's Maya style.

Same vocabulary as QC Bake and QC Validator for Maya - a bold title with the
version, one primary button, a coloured status strip, collapsible sections
with a rule underneath, an icon on every row - so an artist moving between
the three tools finds the controls where they expect them.

Qt draws once and waits, so state is pushed by scriptJobs, and the rules the
QC Bake port paid for are followed here and are not negotiable:

* never bind a scriptJob to a bound method of the widget - bind a
  module-level function that looks up the current panel;
* never keep our own list of job ids - read them back from Maya by name;
* catch everything inside a callback: Maya disables a scriptJob whose
  callback raised;
* install jobs only after the panel is reachable;
* ``show()`` doubles as the workspaceControl's ``uiScript``: it must be
  idempotent, and it must never delete the control that called it.

The update banner, the background check and the install-with-rollback flow
are QC Bake's, carried over as they are.
"""

import importlib
import sys
import threading
import time
import traceback
import weakref

import maya.OpenMayaUI as omui
import maya.cmds as cmds
from PySide6 import QtCore, QtWidgets
from shiboken6 import isValid, wrapInstance

from .. import VERSION_STRING, icons, prefs, updater
from .. import mbr_core as core
from .. import mbr_io, mbr_locked_normals, mbr_scene
from ..mbr_core import _short
from . import widgets

OBJECT_NAME = "MutaformBridgePanel"
WORKSPACE_CONTROL = OBJECT_NAME + "WorkspaceControl"
TITLE = "QC Bridge"
TOOL_NAME = "QC Bridge"

# Where the installed package lives, so the dock can be rebuilt on a cold
# start. Written by the installer and refreshed on every show().
ROOT_OPTIONVAR = prefs.OPTIONVAR_PREFIX + "install_root"

# What Maya runs to rebuild the panel when it restores a docked layout.
#
# Maya restores the control before anything has put the install folder on
# sys.path, so the script has to do that itself - and a failed uiScript
# leaves the control there, EMPTY, with no error anywhere the artist will
# see. The folder is read from an optionVar rather than written into the
# script: Maya stores the script wrapped in MEL, so a Windows path with its
# backslashes (or a OneDrive folder with a Cyrillic name) inside it is a
# broken line. One line, and not one double quote in it, for the same reason.
UI_SCRIPT = (
    "import sys, maya.cmds as cmds; "
    "root = cmds.optionVar(query='%(var)s') if cmds.optionVar(exists='%(var)s') else ''; "
    "root and root not in sys.path and sys.path.insert(0, root); "
    "import mutaform_bridge; mutaform_bridge.show()"
) % {"var": ROOT_OPTIONVAR}

JOB_MARKERS = ("mutaformbridge_scriptjob_selection",)

_PANEL = None
_BUILDING = False


# ---------------------------------------------------------------------------
# scriptJob plumbing - module level on purpose, see the module docstring
# ---------------------------------------------------------------------------
def _dispatch(method_name):
    panel = _PANEL
    if panel is None or not isValid(panel):
        return
    try:
        getattr(panel, method_name)()
    except Exception:
        traceback.print_exc()


def mutaformbridge_scriptjob_selection():
    _dispatch("refresh_selection")


def _running_jobs():
    found = []
    for entry in cmds.scriptJob(listJobs=True) or []:
        if any(marker in entry for marker in JOB_MARKERS):
            try:
                found.append(int(entry.split(":", 1)[0]))
            except ValueError:
                continue
    return found


def _install_jobs():
    if _running_jobs():
        return
    cmds.scriptJob(event=["SelectionChanged", mutaformbridge_scriptjob_selection],
                   killWithScene=False)


def _remove_jobs():
    for job in _running_jobs():
        if cmds.scriptJob(exists=job):
            cmds.scriptJob(kill=job, force=True)


# ---------------------------------------------------------------------------
# Update check, off the main thread
# ---------------------------------------------------------------------------
class UpdateCheck(QtCore.QObject):
    """Fetches the update manifest off the main thread.

    The check must never be able to stall Maya. A studio proxy that black-holes
    the request would otherwise freeze the whole application for the length of
    the timeout, every time the panel opened - so the request runs on a plain
    worker thread that touches nothing but urllib, and the answer comes back
    through a Qt signal, which Qt delivers on the main thread. No maya.cmds is
    called from the thread, because none of it is thread-safe.
    """

    finished = QtCore.Signal(object, object)   # manifest, error

    def __init__(self, url, parent=None):
        super(UpdateCheck, self).__init__(parent)
        self._url = url
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
        self.finished.emit(manifest, error)


# ---------------------------------------------------------------------------
# The panel
# ---------------------------------------------------------------------------
class BridgePanel(QtWidgets.QWidget):
    """One panel, ever. See ``_sweep_orphans``."""

    _instances = weakref.WeakSet()

    def __init__(self, parent=None):
        super(BridgePanel, self).__init__(parent)
        BridgePanel._instances.add(self)
        self.setObjectName(OBJECT_NAME)
        self.setWindowTitle(TITLE)
        self.setMinimumWidth(300)

        self.settings = prefs.load()
        self._pending_update = None
        self._update_check = None
        self._announce_update = False
        self._ready = False

        self._build()
        self._apply_tones()
        self._ready = True
        self.refresh_selection()
        self.show_report()

    # -- small builders --------------------------------------------------------
    def _rule(self):
        rule = QtWidgets.QFrame()
        rule.setFrameShape(QtWidgets.QFrame.HLine)
        rule.setFrameShadow(QtWidgets.QFrame.Sunken)
        return rule

    def _add_section(self, layout, key, title, icon, default_open):
        section = widgets.Section(title, icon, prefs.ui_flag(key, default_open))
        section.toggled.connect(lambda state, name=key: prefs.set_ui_flag(name, state))
        # Folding changes the panel's height, and the floating window follows.
        section.toggled.connect(lambda _state: self._rebalance())
        layout.addWidget(section)
        return section

    def _say(self, message, level="info"):
        """Put a message in the status strip and let the window follow its height."""
        self.status.show_message(message, level)
        self._rebalance()

    # -- window height ---------------------------------------------------------
    def _rebalance(self):
        """Keep a floating window the height of what is in it.

        Every section here is fixed-height, so there is nothing to hand spare
        height to: the tail stretch takes it, and the window is shrunk or
        grown to match. Now and next turn, and _fit_window keeps chasing from
        there until the height lands - measuring immediately can read a
        layout whose hide event has not been delivered yet.
        """
        if not getattr(self, "_ready", False):
            return
        self.updateGeometry()
        self._fit_passes = 0
        self._fit_window()
        QtCore.QTimer.singleShot(0, self._fit_window)

    def _room_below(self, window):
        """How tall this window can be without running off the screen."""
        screen = window.screen()
        if screen is None:
            return 1 << 20
        available = screen.availableGeometry()
        return max(200, available.bottom() - window.y())

    def _fit_window(self, retry=True):
        """Fit a floating window to the height the panel actually needs.

        The rule is simply: the window is the height of what is in it. Fold a
        section and it shrinks, unfold it and it grows back. Only a floating
        window is touched - a docked control's height belongs to the artist's
        layout. The layout is activated before sizeHint is read, and the fit
        repeats across event-loop turns until it lands, bounded at four so a
        window that will not shrink cannot spin.
        """
        try:
            if not cmds.workspaceControl(WORKSPACE_CONTROL, query=True, exists=True):
                return
            if not cmds.workspaceControl(WORKSPACE_CONTROL, query=True, floating=True):
                return
        except RuntimeError:
            return
        if not isValid(self):
            return
        window = self.window()
        if window is None or not isValid(window):
            return
        layout = self.layout()
        if layout is not None:
            layout.activate()
        chrome = window.height() - self.height()
        # Measured for the width the panel actually has, not from sizeHint:
        # a word-wrapped label reports a hint for a typical width, which on a
        # wider window counts lines that are not there and leaves a blank band
        # under the last section.
        if layout is not None and layout.hasHeightForWidth():
            content = layout.heightForWidth(self.width())
        else:
            content = self.sizeHint().height()
        target = max(content, self.minimumSizeHint().height()) + chrome
        target = min(target, self._room_below(window))
        if abs(window.height() - target) <= 2:
            self._fit_passes = 0
            return
        window.resize(window.width(), target)
        if not retry:
            return
        self._fit_passes = getattr(self, "_fit_passes", 0) + 1
        if self._fit_passes <= 4:
            QtCore.QTimer.singleShot(0, self._fit_window)
        else:
            self._fit_passes = 0

    # -- construction ----------------------------------------------------------
    def _build(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(6)
        badge = QtWidgets.QLabel()
        badge.setPixmap(widgets.make_icon(icons.ICON_BADGE)
                        .pixmap(widgets.ICON_SIZE, widgets.ICON_SIZE))
        header.addWidget(badge)
        title = QtWidgets.QLabel("QC Bridge by Mutaform Studio")
        title.setStyleSheet("QLabel { font-weight: bold; }")
        header.addWidget(title)
        header.addStretch(1)
        version = QtWidgets.QLabel("ver %s" % VERSION_STRING)
        version.setStyleSheet(widgets.HINT_STYLE)
        header.addWidget(version)
        outer.addLayout(header)
        outer.addWidget(self._rule())

        self.update_banner = self._build_update_banner()
        outer.addWidget(self.update_banner)

        # The one thing the artist came here to press, with the any-FBX
        # variant beside it rather than buried in a section.
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(4)
        self.btn_import = QtWidgets.QPushButton("  Import From Blender")
        self.btn_import.setIcon(widgets.make_icon(icons.ICON_IMPORT))
        self.btn_import.setMinimumHeight(34)
        self.btn_import.setStyleSheet(widgets.PRIMARY_BUTTON_STYLE)
        self.btn_import.setToolTip(
            "Import the exchange FBX written by the Blender side, then run the\n"
            "cleanup: empties to groups, names, transforms, history, materials.")
        self.btn_import.clicked.connect(lambda: self._run(self.import_from_blender))
        row.addWidget(self.btn_import, 1)

        self.btn_import_fbx = QtWidgets.QPushButton("FBX")
        self.btn_import_fbx.setMinimumHeight(34)
        self.btn_import_fbx.setFixedWidth(52)
        self.btn_import_fbx.setToolTip("Import any FBX file with the same cleanup.")
        self.btn_import_fbx.clicked.connect(lambda: self._run(self.import_fbx))
        row.addWidget(self.btn_import_fbx, 0)
        outer.addLayout(row)

        self.btn_export = QtWidgets.QPushButton("  Export To Blender")
        self.btn_export.setIcon(widgets.make_icon(icons.ICON_EXPORT))
        self.btn_export.setMinimumHeight(28)
        self.btn_export.setToolTip(
            "Export the selected roots to the exchange FBX for the Blender side.")
        self.btn_export.clicked.connect(lambda: self._run(self.export_to_blender))
        outer.addWidget(self.btn_export)

        # A greyed-out button is an answer with the reason left out. This line
        # always says what the tool can see.
        self.selection_hint = widgets.hint("")
        outer.addWidget(self.selection_hint)

        self.status = widgets.StatusBar()
        outer.addWidget(self.status)

        # Everything above this point is furniture: it has one correct height
        # and must never grow, or spare height lands as gaps between it.
        for fixed in (badge, title, version, self.btn_import,
                      self.btn_import_fbx, self.btn_export):
            fixed.setSizePolicy(fixed.sizePolicy().horizontalPolicy(),
                                QtWidgets.QSizePolicy.Fixed)
        for wrapping in (self.selection_hint, self.status, self.update_banner):
            wrapping.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                   QtWidgets.QSizePolicy.Maximum)

        self.sec_import = self._add_section(
            outer, "import_options", "Import Options", icons.ICON_IMPORT_OPTIONS, False)
        self._build_import_options(self.sec_import)

        self.sec_tools = self._add_section(
            outer, "tools", "Tools", icons.ICON_TOOLS, False)
        self._build_tools(self.sec_tools)

        self.sec_settings = self._add_section(
            outer, "settings", "Settings", icons.ICON_SETTINGS, False)
        self._build_settings(self.sec_settings)

        outer.addStretch(1)

    def _build_update_banner(self):
        """A quiet strip that appears only when a newer build is published.

        Skip and Install sit apart on purpose: one mis-click between "not
        now" and "replace the tool" is one too many.
        """
        banner = QtWidgets.QWidget()
        banner.setStyleSheet(
            "QWidget { background-color: #2b3a4a; border-radius: 3px; }")
        layout = QtWidgets.QHBoxLayout(banner)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)
        self.update_label = QtWidgets.QLabel("")
        self.update_label.setWordWrap(True)
        self.update_label.setStyleSheet("QLabel { color: #a9cbe8; }")
        layout.addWidget(self.update_label, 1)

        self.btn_skip_update = QtWidgets.QPushButton("Skip")
        self.btn_skip_update.setStyleSheet(
            "QPushButton { background-color: transparent; color: #9fb4c6;"
            " border: 1px solid #4a5f70; border-radius: 3px; padding: 3px 10px; }"
            "QPushButton:hover { color: #cfe0ee; border-color: #6d8397; }")
        self.btn_skip_update.setToolTip(
            "Stop offering this particular version. A later one will still "
            "be announced.")
        self.btn_skip_update.clicked.connect(self._on_skip_update)
        layout.addWidget(self.btn_skip_update)

        layout.addSpacing(12)
        self.btn_update = QtWidgets.QPushButton("Install")
        self.btn_update.setStyleSheet(
            "QPushButton { background-color: #3d6a8c; color: #f0f6fb;"
            " border: 1px solid #5a89ad; border-radius: 3px;"
            " font-weight: bold; padding: 3px 12px; }"
            "QPushButton:hover { background-color: #4a7da3; }"
            "QPushButton:disabled { background-color: #3a4650; color: #7f8b95; }")
        self.btn_update.setToolTip(
            "Download the new version, replace this one and reload.\n"
            "The current version is kept until the new one has loaded.")
        self.btn_update.clicked.connect(self._on_install_update)
        layout.addWidget(self.btn_update)

        banner.setVisible(False)
        return banner

    def _build_import_options(self, section):
        self.option_boxes = {}
        for name, label, icon, tooltip in (
                ("import_clean_names", "Clean FBX suffix names", icons.ICON_CLEAN_NAMES,
                 "Strip the FBXASC046### suffixes that Blender's .001 names\n"
                 "arrive with, on nodes, shapes and materials."),
                ("import_unlock_transforms", "Unlock transforms", icons.ICON_UNLOCK,
                 "Unlock translate, rotate, scale and visibility on the\n"
                 "imported transforms."),
                ("import_clean_history", "Clean geometry history", icons.ICON_HISTORY,
                 "Delete construction history on the imported meshes."),
                ("import_rebuild_materials", "Rebuild Blinn materials", icons.ICON_MATERIALS,
                 "Replace the imported shaders with clean Blinns that keep the\n"
                 "diffuse, normal and opacity textures."),
        ):
            box = widgets.IconCheckBox(label, icon, tooltip)
            box.setChecked(getattr(self.settings, name))
            box.toggled.connect(lambda value, n=name: setattr(self.settings, n, value))
            section.add_widget(box)
            self.option_boxes[name] = box

    def _build_tools(self, section):
        section.add_widget(widgets.heading("Random Sharp"))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(4)
        self.btn_find_sharp = QtWidgets.QPushButton("  Find")
        self.btn_find_sharp.setIcon(widgets.make_icon(icons.ICON_FIND))
        self.btn_find_sharp.setMinimumHeight(28)
        self.btn_find_sharp.setToolTip(
            "Select hard edges that are not UV borders - the edges Blender's\n"
            "Random Sharp check reports.")
        self.btn_find_sharp.clicked.connect(lambda: self._run(self.find_random_sharp))
        self.btn_fix_sharp = QtWidgets.QPushButton("  Fix")
        self.btn_fix_sharp.setIcon(widgets.make_icon(icons.ICON_FIX))
        self.btn_fix_sharp.setMinimumHeight(28)
        self.btn_fix_sharp.setToolTip("Soften those edges.")
        self.btn_fix_sharp.clicked.connect(lambda: self._run(self.fix_random_sharp))
        row.addWidget(self.btn_find_sharp, 1)
        row.addWidget(self.btn_fix_sharp, 1)
        section.add_layout(row)
        section.add_widget(widgets.hint(
            "Works on the selection, or on the whole scene when nothing is selected."))

        section.body().addSpacing(6)
        section.add_widget(widgets.heading("Normals"))
        self.btn_normals = QtWidgets.QPushButton("  Unlock Normals")
        self.btn_normals.setIcon(widgets.make_icon(icons.ICON_NORMALS))
        self.btn_normals.setMinimumHeight(28)
        self.btn_normals.setToolTip(
            "Convert locked imported normals to Maya soft and hard edges.")
        self.btn_normals.clicked.connect(lambda: self._run(self.unlock_normals))
        section.add_widget(self.btn_normals)
        section.add_widget(widgets.hint(
            "For meshes that arrived with locked normals: the split is kept "
            "as hard edges and the normals are unlocked."))

    def _build_settings(self, section):
        section.add_widget(widgets.heading("Exchange"))

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)
        label = QtWidgets.QLabel("Folder")
        label.setStyleSheet(widgets.HINT_STYLE)
        label.setMinimumWidth(48)
        row.addWidget(label)
        self.field_dir = QtWidgets.QLineEdit(self.settings.exchange_dir)
        self.field_dir.setToolTip("The folder both sides exchange the FBX through.")
        self.field_dir.editingFinished.connect(
            lambda: setattr(self.settings, "exchange_dir", self.field_dir.text()))
        row.addWidget(self.field_dir, 1)
        browse = QtWidgets.QToolButton()
        browse.setIcon(widgets.make_icon(icons.ICON_BROWSE))
        browse.setToolTip("Pick the exchange folder.")
        browse.clicked.connect(lambda: self._run(self.browse_exchange_dir))
        row.addWidget(browse)
        section.add_layout(row)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)
        label = QtWidgets.QLabel("FBX")
        label.setStyleSheet(widgets.HINT_STYLE)
        label.setMinimumWidth(48)
        row.addWidget(label)
        self.field_name = QtWidgets.QLineEdit(self.settings.exchange_name)
        self.field_name.setToolTip("File name of the exchange FBX. Must match the Blender side.")
        self.field_name.editingFinished.connect(
            lambda: setattr(self.settings, "exchange_name", self.field_name.text()))
        row.addWidget(self.field_name, 1)
        section.add_layout(row)

        section.body().addSpacing(6)
        section.add_widget(widgets.heading("Updates"))
        self.chk_auto_check = widgets.IconCheckBox(
            "Check on Open", icons.ICON_UPDATE,
            "Maya has no add-on repository of its own, so QC Bridge asks a\n"
            "manifest we publish whether a newer release exists.\n"
            "It only ever tells you - it never installs on its own.\n"
            "\n"
            "Checked every time the panel is opened, in the background.")
        self.chk_auto_check.setChecked(self.settings.update_auto_check)
        self.chk_auto_check.toggled.connect(
            lambda value: setattr(self.settings, "update_auto_check", value))
        section.add_widget(self.chk_auto_check)

        check_now = QtWidgets.QPushButton("Check for Updates Now")
        check_now.clicked.connect(lambda: self.check_for_updates(announce=True))
        section.add_widget(check_now)

    def _apply_tones(self):
        """Lift what you press, sink what you read - in one pass."""
        self.setStyleSheet(widgets.FIELD_STYLE)
        for button in self.findChildren(QtWidgets.QPushButton):
            if button is self.btn_import:
                continue                       # the one primary control
            if not button.styleSheet():
                button.setStyleSheet(widgets.CHECKED_BUTTON_STYLE)

    # -- state -----------------------------------------------------------------
    def show_report(self, level="info"):
        """Put the bridge's last report into the status strip."""
        self._say(core.LAST_REPORT, level)

    def refresh_selection(self):
        """Cheap update: only what depends on the current selection."""
        if not getattr(self, "_ready", False):
            return
        try:
            roots = cmds.ls(selection=True, long=True, type="transform") or []
            if not roots:
                self.selection_hint.setText(
                    "Nothing selected. Export takes the selected roots; "
                    "the tools fall back to the whole scene.")
            elif len(roots) == 1:
                self.selection_hint.setText("Selected: %s" % _short(roots[0]))
            else:
                self.selection_hint.setText(
                    "Selected: %s and %d more" % (_short(roots[0]), len(roots) - 1))
        except RuntimeError:
            pass

    def _path_options(self):
        return {"folder": self.field_dir.text(), "filename": self.field_name.text()}

    def _import_options(self):
        return {
            "rebuild": False,
            "clean_names": self.option_boxes["import_clean_names"].isChecked(),
            "unlock_transform_attrs": self.option_boxes["import_unlock_transforms"].isChecked(),
            "normalize_materials": self.option_boxes["import_rebuild_materials"].isChecked(),
            "clean_history": self.option_boxes["import_clean_history"].isChecked(),
        }

    # -- actions ---------------------------------------------------------------
    def _run(self, function):
        """Run an action and report it, whatever happens.

        A Qt slot that raises does not reach the user: PySide prints the
        traceback and returns as if nothing happened. Every button goes
        through here, so an escaping exception lands in the status strip.
        """
        try:
            message = function()
        except Exception as exc:
            traceback.print_exc()
            self._say(
                "%s: %s  (full traceback in the Script Editor)"
                % (type(exc).__name__, exc), "error")
            return None
        if message:
            # The strip carries the bridge's own detailed report; the short
            # line goes to the viewport, where the artist is looking.
            self.show_report("clean")
            cmds.inViewMessage(amg="%s: %s" % (TOOL_NAME, message), pos="midCenter", fade=True)
        return message

    def import_from_blender(self):
        result = mbr_io.import_from_blender(**self._path_options(), **self._import_options())
        converted = result["convert"]["converted"] if result.get("convert") else 0
        return "Imported %d transforms, converted %d groups." % (
            result["new_transform_count"], converted)

    def import_fbx(self):
        paths = cmds.fileDialog2(caption="Import FBX", fileMode=1, fileFilter="FBX (*.fbx)")
        if not paths:
            return None
        result = mbr_io.import_fbx_file(paths[0], **self._import_options())
        converted = result["convert"]["converted"] if result.get("convert") else 0
        return "Imported FBX: %d transforms, converted %d groups." % (
            result["new_transform_count"], converted)

    def export_to_blender(self):
        result = mbr_io.export_selected_to_blender(**self._path_options())
        return "Exported FBX: %d bytes." % result["size"]

    def _tool_roots(self):
        roots = cmds.ls(selection=True, long=True, type="transform") or []
        return roots or None

    def find_random_sharp(self):
        result = mbr_scene.find_random_sharp_edges(roots=self._tool_roots(), select_edges=True)
        return "Random Sharp: %d edge(s) found." % result["edges"]

    def fix_random_sharp(self):
        result = mbr_scene.fix_random_sharp_edges(roots=self._tool_roots(), select_edges=True)
        return "Random Sharp fixed: %d edge(s), %d failed." % (result["fixed"], result["failed"])

    def unlock_normals(self):
        processed = mbr_locked_normals.convert_selected()
        message = "Locked normals converted: %d mesh(es)." % processed
        core._set_report(message)
        return message

    def browse_exchange_dir(self):
        start = self.field_dir.text() or self.settings.exchange_dir
        picked = cmds.fileDialog2(caption="Exchange Folder", fileMode=3,
                                  startingDirectory=start)
        if not picked:
            return None
        self.field_dir.setText(picked[0])
        self.settings.exchange_dir = picked[0]
        return None

    # -- updates ---------------------------------------------------------------
    def check_on_open(self):
        """Check every time the tool is opened. No clock, no conditions.

        Opening the panel from the shelf is a deliberate act, and the moment
        an artist is most willing to be told the tool is out of date.
        Anything clever here - a timestamp, a rate limit - eventually produces
        the one behaviour that matters: a tool that knows it is out of date
        and says nothing. That happened to QC Bake, twice.

        Honoured only when "Check on Open" is on: an artist who turned it off
        meant it.
        """
        if not self.settings.update_auto_check:
            return
        self.check_for_updates(announce=False)

    def check_for_updates(self, announce=True):
        """Start a check. `announce` reports "you are up to date" as well."""
        if self._update_check is not None:
            return
        url = self.settings.update_url
        self._announce_update = announce
        if announce:
            self._say("Checking for updates...", "busy")

        self._update_check = UpdateCheck(url, self)
        self._update_check.finished.connect(self._on_update_checked)
        self._update_check.start()

    def _on_update_checked(self, manifest, error):
        """Back on the main thread with the manifest, or a reason there isn't."""
        self._update_check = None
        if not getattr(self, "_ready", False) or not isValid(self):
            return

        if error:
            # A failed check is not the artist's problem unless they asked.
            if self._announce_update:
                self._say(error, "issues")
            return

        self.settings.update_last_check = time.time()
        self.settings.update_last_version = VERSION_STRING
        remote = manifest.get("version", "")

        if not updater.is_newer(remote, VERSION_STRING):
            if self._announce_update:
                self._say("%s %s is the latest version." % (TOOL_NAME, VERSION_STRING), "clean")
            return

        if remote == self.settings.update_skip_version:
            return

        self._pending_update = manifest
        notes = manifest.get("notes") or ""
        self.update_label.setText(
            "%s %s is available (you have %s).%s"
            % (TOOL_NAME, remote, VERSION_STRING, ("\n" + notes) if notes else ""))
        self.btn_update.setEnabled(True)
        self.update_banner.setVisible(True)
        if self._announce_update:
            self.show_report()
        self._rebalance()

    def _on_skip_update(self):
        if self._pending_update:
            self.settings.update_skip_version = self._pending_update.get("version", "")
        self._pending_update = None
        self.update_banner.setVisible(False)
        self._rebalance()

    def _on_install_update(self):
        """Fetch, verify, swap and reload. Never silent about what happened."""
        manifest = self._pending_update
        if not manifest:
            return

        self.btn_update.setEnabled(False)
        self._say("Downloading %s %s..." % (TOOL_NAME, manifest.get("version")), "busy")
        QtWidgets.QApplication.processEvents()

        install_dir = updater.install_dir_for(updater.__file__)
        try:
            backup, error = updater.perform_update(manifest, install_dir)
        except Exception as exc:
            traceback.print_exc()
            backup, error = None, "Update failed: %s" % exc

        if error:
            self.btn_update.setEnabled(True)
            self._say(error, "error")
            return

        # The swap is done. Reloading has to happen after this handler has
        # returned, because it destroys the very widget the handler is running
        # on - and the backup is kept until the new version has actually
        # imported, so a broken release cannot take the tool out of the studio.
        QtCore.QTimer.singleShot(
            0, lambda: _finish_update(backup, install_dir, manifest.get("version", "")))

    # -- lifecycle -------------------------------------------------------------
    def showEvent(self, event):
        """Re-arm the subscriptions, and fit the window the first time.

        The fit cannot happen at the end of construction: Maya has not created
        the workspaceControl's window yet, so there is nothing to measure -
        and the panel would open at whatever height Maya chose, with a field
        of empty panel underneath. Only on the first show; after that the
        artist's own resizes are theirs to keep, folds being the only thing
        that overrules them.
        """
        super(BridgePanel, self).showEvent(event)
        _install_jobs()          # self-heal: a dock restore can lose them
        self.refresh_selection()
        if not getattr(self, "_first_show_done", False):
            self._first_show_done = True
            QtCore.QTimer.singleShot(0, self._rebalance)

    def closeEvent(self, event):
        global _PANEL
        if _PANEL is self:
            _remove_jobs()
            _PANEL = None
        super(BridgePanel, self).closeEvent(event)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def _destroy(widget):
    """``hide()`` first, or the widget is briefly a top-level window and
    flashes on screen before it goes."""
    try:
        widget.hide()
        widget.setParent(None)
        widget.deleteLater()
    except RuntimeError:
        pass


def _sweep_orphans(keep, parent=None):
    """Destroy every panel but ``keep``.

    Two passes. The class registry only knows panels built by this generation
    of the module: reloading gives the class a clean registry while the
    previous panel is still sitting in the workspaceControl's layout. So the
    registry is swept first, and then the control itself is asked what it
    actually contains.
    """
    for panel in list(BridgePanel._instances):
        if panel is not keep and isValid(panel):
            _destroy(panel)

    if parent is None:
        pointer = omui.MQtUtil.findControl(WORKSPACE_CONTROL)
        parent = wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None
    if parent is None:
        return
    for child in parent.findChildren(QtWidgets.QWidget, OBJECT_NAME):
        if child is not keep and isValid(child):
            _destroy(child)


def close():
    """Take the panel and its subscriptions down. Call before reloading."""
    global _PANEL
    _remove_jobs()
    if _PANEL is not None and isValid(_PANEL):
        _destroy(_PANEL)
    _PANEL = None
    if cmds.workspaceControl(WORKSPACE_CONTROL, query=True, exists=True):
        cmds.deleteUI(WORKSPACE_CONTROL)


def _remember_root():
    """Record where the package lives, for the uiScript on a cold start.

    Refreshed on every show() rather than only at install, so a folder the
    artist moved heals itself the next time the panel is opened from the
    shelf button (whose command carries the new path).
    """
    root = updater.install_dir_for(updater.__file__).replace("\\", "/")
    cmds.optionVar(stringValue=(ROOT_OPTIONVAR, root))


def _assert_ui_script():
    """Keep the workspaceControl's stored uiScript current.

    Maya saves the uiScript into its preferences along with the docked layout
    and replays THAT on the next start - not whatever the installed code
    says. Re-asserted on every show, unconditionally: querying it answers
    None in Maya 2025 even when one is stored.
    """
    if not cmds.workspaceControl(WORKSPACE_CONTROL, query=True, exists=True):
        return
    try:
        cmds.workspaceControl(WORKSPACE_CONTROL, edit=True, uiScript=UI_SCRIPT)
    except RuntimeError:
        pass


def show():
    """Open or raise the panel. Also Maya's ``uiScript``, so idempotent.

    * ``show()`` must never delete the workspaceControl: Maya calls this
      while restoring the dock, so deleting the control deletes the very
      thing that is calling us, which re-runs the uiScript - an infinite
      loop that wedges Maya's main thread. Removal belongs in ``close()``.
    * the re-entrancy guard: creating the control fires the uiScript
      immediately, before ``_PANEL`` has been assigned.
    """
    global _PANEL, _BUILDING

    if not _BUILDING:
        _remember_root()
        _assert_ui_script()

    if _PANEL is not None and isValid(_PANEL):
        _sweep_orphans(_PANEL)
        if cmds.workspaceControl(WORKSPACE_CONTROL, query=True, exists=True):
            cmds.workspaceControl(WORKSPACE_CONTROL, edit=True,
                                  restore=True, visible=True)
        _install_jobs()
        _PANEL.check_on_open()
        return _PANEL

    if _BUILDING:
        return None

    _BUILDING = True
    try:
        if not cmds.workspaceControl(WORKSPACE_CONTROL, query=True, exists=True):
            cmds.workspaceControl(
                WORKSPACE_CONTROL, label=TITLE,
                retain=False, floating=True, initialWidth=340,
                uiScript=UI_SCRIPT)
        pointer = omui.MQtUtil.findControl(WORKSPACE_CONTROL)
        parent = wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None

        # Clear out any panel left by a previous generation of this module
        # BEFORE adding ours, so the control never holds two at once.
        _sweep_orphans(None, parent)
        _PANEL = BridgePanel(parent)
        if parent is not None and parent.layout() is not None:
            parent.layout().addWidget(_PANEL)
        _sweep_orphans(_PANEL, parent)
    finally:
        _BUILDING = False

    _install_jobs()              # only now: the panel is reachable
    _PANEL.check_on_open()
    return _PANEL


def reload_package():
    """Drop the package and bring it back at whatever version is on disk.

    Only possible because close() genuinely lets go - the subscriptions and
    the widget both.
    """
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
        panel = reload_package()
    except Exception:
        traceback.print_exc()
        restored = updater.rollback(backup, install_dir)
        try:
            panel = reload_package()
        except Exception:
            traceback.print_exc()
            cmds.warning(
                "%s %s failed to load and the previous version could not be "
                "restored automatically. Reinstall from install/install.py."
                % (TOOL_NAME, version))
            return None
        if panel is not None and restored:
            panel.status.show_message(
                "%s %s failed to load, so the previous version was put back. "
                "The traceback is in the Script Editor." % (TOOL_NAME, version), "error")
        return panel

    updater.discard_backup(backup)
    if panel is not None:
        panel.status.show_message("Updated to %s %s." % (TOOL_NAME, version), "clean")
    return panel

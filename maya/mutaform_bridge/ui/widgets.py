# SPDX-License-Identifier: GPL-3.0-or-later
"""Reusable widgets the panel is built from.

Blender hands an addon collapsible sub-panels, property rows and a report line
for free. Qt hands over none of that, so the pieces are built once here and the
panel module stays about layout rather than plumbing.

The visual vocabulary is the one QC Bake and QC Validator for Maya settled
on: Blender's structure, but with enough contrast that a Maya panel does not
read as one grey block. Three devices do most of that work - a rule under
every section, a bold heading inside it, and secondary text in grey - and
they are worth keeping consistent across the studio's tools.
"""

from PySide6 import QtCore, QtGui, QtWidgets

from .. import icons

ICON_SIZE = 16

# Depth, in three tones.
#
# Maya's panel palette is nearly flat, so a control that only differs from the
# background by a hairline border disappears into it - a row of buttons reads
# as a row of labels. The fix is the one Maya's own UI uses: lift the things
# you press, sink the things you read.
SURFACE_RAISED = "#4d4d4d"      # buttons: above the panel
SURFACE_RAISED_HOVER = "#5a5a5a"
SURFACE_SUNKEN = "#2b2b2b"      # lists and detail boxes: below it
BORDER = "#5e5e5e"
BORDER_SUNKEN = "#404040"
ACCENT = "#4c7a99"              # the one colour that means "on"
ACCENT_HOVER = "#588aad"
ACCENT_BORDER = "#6ea3c4"

# Maya renders a checked QPushButton almost identically to an unchecked one,
# so both states are painted in explicitly.
CHECKED_BUTTON_STYLE = """
QPushButton {
    background-color: %(raised)s;
    border: 1px solid %(border)s;
    border-radius: 3px;
    padding: 4px 8px;
}
QPushButton:hover { background-color: %(raised_hover)s; }
QPushButton:pressed { background-color: %(sunken)s; }
QPushButton:checked {
    background-color: %(accent)s;
    color: #ffffff;
    border: 1px solid %(accent_border)s;
}
QPushButton:checked:hover { background-color: %(accent_hover)s; }
QPushButton:disabled { background-color: #3d3d3d; color: #7d7d7d;
                       border-color: #464646; }
""" % {"raised": SURFACE_RAISED, "raised_hover": SURFACE_RAISED_HOVER,
       "sunken": SURFACE_SUNKEN, "border": BORDER, "accent": ACCENT,
       "accent_hover": ACCENT_HOVER, "accent_border": ACCENT_BORDER}

# Fields the artist types into read as sunken too, so they are visibly
# editable rather than another slab of panel.
FIELD_STYLE = """
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background-color: %(sunken)s;
    border: 1px solid %(border)s;
    border-radius: 3px;
    padding: 2px 4px;
}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {
    border-color: %(hover)s;
}
QToolButton { background-color: %(raised)s; border: 1px solid %(border)s;
              border-radius: 2px; }
QToolButton:hover { background-color: %(raised_hover)s; }
QToolButton:pressed { background-color: %(sunken)s; }
""" % {"sunken": SURFACE_SUNKEN, "border": BORDER_SUNKEN, "hover": BORDER,
       "raised": SURFACE_RAISED, "raised_hover": SURFACE_RAISED_HOVER}

# Setting ANY stylesheet property on a QPushButton drops Maya's native
# background and border with it, so a button styled only for weight renders as
# bare text and stops looking like a button at all. A style that touches a
# button must therefore draw the whole thing.
PRIMARY_BUTTON_STYLE = """
QPushButton {
    background-color: #4c7a99;
    color: #ffffff;
    border: 1px solid #6ea3c4;
    border-radius: 3px;
    font-weight: bold;
    padding: 6px;
}
QPushButton:hover { background-color: #588aad; }
QPushButton:pressed { background-color: #3f6884; }
QPushButton:disabled {
    background-color: #3a4650;
    color: #7f8b95;
    border-color: #46525c;
}
"""

HINT_STYLE = "QLabel { color: #8f8f8f; }"
HEADING_STYLE = "QLabel { font-weight: bold; color: #d0d0d0; }"


def make_icon(name):
    """A QIcon for one of Maya's built-in resources, scaled to fit.

    Maya's resource set mixes 17x14 and 240x240 art, so leaving icons at their
    native size produces a visibly ragged column of buttons.
    """
    pixmap = QtGui.QPixmap(icons.path(name))
    if pixmap.isNull():
        return QtGui.QIcon()
    if pixmap.width() != ICON_SIZE or pixmap.height() != ICON_SIZE:
        pixmap = pixmap.scaled(ICON_SIZE, ICON_SIZE, QtCore.Qt.KeepAspectRatio,
                               QtCore.Qt.SmoothTransformation)
    return QtGui.QIcon(pixmap)


def blank_icon():
    """A transparent icon of the standard size, so a row never twitches."""
    pixmap = QtGui.QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(QtCore.Qt.transparent)
    return QtGui.QIcon(pixmap)


def heading(text):
    label = QtWidgets.QLabel(text)
    label.setStyleSheet(HEADING_STYLE)
    return label


def hint(text):
    label = QtWidgets.QLabel(text)
    label.setStyleSheet(HINT_STYLE)
    label.setWordWrap(True)
    return label


class Section(QtWidgets.QWidget):
    """A collapsible section with a disclosure arrow, icon and title.

    Stands in for a Blender sub-panel. The rule underneath is what stops a
    stack of these reading as one undifferentiated block - without it the
    panel is Blender-shaped but unnavigable.
    """

    toggled = QtCore.Signal(bool)

    def __init__(self, title, icon_name=None, expanded=True, nested=False,
                 parent=None):
        super(Section, self).__init__(parent)

        self._button = QtWidgets.QToolButton(self)
        self._button.setStyleSheet(
            "QToolButton { border: none; font-weight: bold; padding: 3px 2px;"
            " background-color: #444444; border-radius: 2px; }"
            "QToolButton:hover { background-color: #4f4f4f; color: #ffffff; }")
        self._button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._button.setArrowType(QtCore.Qt.DownArrow if expanded
                                  else QtCore.Qt.RightArrow)
        self._button.setText("  " + title)
        self._button.setCheckable(True)
        self._button.setChecked(expanded)
        self._button.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                   QtWidgets.QSizePolicy.Fixed)
        self._button.clicked.connect(self._on_clicked)

        icon_label = QtWidgets.QLabel(self)
        if icon_name:
            icon_label.setPixmap(make_icon(icon_name).pixmap(ICON_SIZE, ICON_SIZE))

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)
        header.addWidget(self._button, 1)
        header.addWidget(icon_label, 0)

        self._body = QtWidgets.QWidget(self)
        self._body_layout = QtWidgets.QVBoxLayout(self._body)
        # Symmetric: a larger left inset than right makes everything inside a
        # section sit off-centre, and a ragged right edge is the first thing
        # the eye catches. A nested section adds no inset of its own.
        inset = 0 if nested else 10
        self._body_layout.setContentsMargins(inset, 4, inset, 6)
        self._body_layout.setSpacing(4)
        self._body.setVisible(expanded)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addLayout(header)
        outer.addWidget(self._body)

        rule = QtWidgets.QFrame(self)
        rule.setFrameShape(QtWidgets.QFrame.HLine)
        rule.setFrameShadow(QtWidgets.QFrame.Sunken)
        outer.addWidget(rule)
        self._apply()

    def body(self):
        return self._body_layout

    def add_widget(self, widget, stretch=0):
        self._body_layout.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout):
        self._body_layout.addLayout(layout)
        return layout

    def is_expanded(self):
        return self._button.isChecked()

    def set_expanded(self, expanded):
        self._button.setChecked(expanded)
        self._apply()

    def _on_clicked(self):
        self._apply()
        self.toggled.emit(self._button.isChecked())

    def wants_height(self):
        """True when something inside this section could use extra height."""
        if not self._button.isChecked():
            return False
        growing = (QtWidgets.QSizePolicy.Expanding,
                   QtWidgets.QSizePolicy.MinimumExpanding)
        for index in range(self._body_layout.count()):
            item = self._body_layout.itemAt(index)
            widget = item.widget()
            if isinstance(widget, Section):
                if widget.wants_height():
                    return True
                continue
            if self._body_layout.stretch(index) > 0:
                return True
            if widget is None:
                continue
            if widget.isVisible() and \
                    widget.sizePolicy().verticalPolicy() in growing:
                return True
        return False

    def _apply(self):
        expanded = self._button.isChecked()
        self._button.setArrowType(QtCore.Qt.DownArrow if expanded
                                  else QtCore.Qt.RightArrow)
        self._body.setVisible(expanded)
        # A collapsed section must not count as stretchable, or the space it
        # gave up is handed back to it as blank panel.
        wants = self.wants_height()
        vertical = (QtWidgets.QSizePolicy.Expanding if wants
                    else QtWidgets.QSizePolicy.Maximum)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, vertical)
        self._body.setSizePolicy(QtWidgets.QSizePolicy.Preferred, vertical)
        self.updateGeometry()


class IconCheckBox(QtWidgets.QWidget):
    """A checkbox with an icon between the box and its label.

    Mirrors the Blender panel's option rows, which put a small icon beside
    every toggle so a list can be scanned by shape rather than by reading
    every label. The whole row is clickable, not just the 13-pixel box.
    """

    toggled = QtCore.Signal(bool)

    def __init__(self, label, icon_name=None, tooltip="", parent=None):
        super(IconCheckBox, self).__init__(parent)

        self._box = QtWidgets.QCheckBox(self)
        self._box.toggled.connect(self.toggled.emit)

        icon_label = QtWidgets.QLabel(self)
        if icon_name:
            icon_label.setPixmap(make_icon(icon_name).pixmap(ICON_SIZE, ICON_SIZE))

        self._text = QtWidgets.QLabel(label, self)

        for widget in (icon_label, self._text):
            widget.setCursor(QtCore.Qt.PointingHandCursor)
            widget.mousePressEvent = self._forward_click

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(self._box, 0)
        layout.addWidget(icon_label, 0)
        layout.addWidget(self._text, 0)
        layout.addStretch(1)
        if tooltip:
            self.setToolTip(tooltip)

    def _forward_click(self, _event):
        self._box.toggle()

    def isChecked(self):
        return self._box.isChecked()

    def setChecked(self, value):
        blocked = self._box.blockSignals(True)
        self._box.setChecked(bool(value))
        self._box.blockSignals(blocked)


class StatusBar(QtWidgets.QLabel):
    """The panel's report line.

    A coloured strip rather than a line of text: an artist who has just run
    an import needs to know the outcome at a glance, and grey-on-grey does
    not carry that. Hidden entirely when there is nothing to say.
    """

    COLOURS = {
        "info": ("#2f3a44", "#b9cddc"),
        "busy": ("#3d3626", "#e0c274"),
        "clean": ("#2c3b2c", "#9fd39f"),
        "issues": ("#3d3327", "#e8bf87"),
        "error": ("#3d2727", "#e59191"),
    }

    def __init__(self, parent=None):
        super(StatusBar, self).__init__(parent)
        self.setWordWrap(True)
        self.setMargin(6)
        self.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.clear_message()

    def clear_message(self):
        self.setText("")
        self.setStyleSheet("")
        self.setVisible(False)

    def show_message(self, message, level="info"):
        background, foreground = self.COLOURS.get(level, self.COLOURS["info"])
        self.setStyleSheet(
            "QLabel { background-color: %s; color: %s; border-radius: 3px; }"
            % (background, foreground))
        self.setText(message)
        self.setToolTip(message)
        self.setVisible(True)

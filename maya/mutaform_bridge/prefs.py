# SPDX-License-Identifier: GPL-3.0-or-later
# QC Bridge Maya-Blender - settings
# ---------------------------------
# Settings live in Maya optionVars, so they belong to the artist and survive
# closing the window, closing Maya and reinstalling the tool. The Blender half
# keeps its copy of the exchange folder in the scene; on the Maya side there is
# no scene worth attaching them to, and having to retype the exchange folder
# every time the window opens was exactly the kind of small friction the tool
# should not have.
#
# Settings are read and written through plain attribute access:
#
#     settings = prefs.load()
#     folder = settings.exchange_dir
#     settings.update_auto_check = False

import maya.cmds as cmds

from .mbr_core import DEFAULT_EXCHANGE_DIR, DEFAULT_EXCHANGE_NAME

OPTIONVAR_PREFIX = "mutaformBridge_"


class _Field(object):
    """One setting: its default, and how it survives a round trip to Maya."""

    def __init__(self, name, default, kind):
        self.name = name
        self.default = default
        self.kind = kind
        self.var = OPTIONVAR_PREFIX + name

    def read(self):
        if not cmds.optionVar(exists=self.var):
            return self.default
        raw = cmds.optionVar(query=self.var)
        try:
            if self.kind is bool:
                return bool(int(raw))
            return self.kind(raw)
        except (TypeError, ValueError):
            return self.default

    def write(self, value):
        if self.kind is bool:
            cmds.optionVar(intValue=(self.var, int(bool(value))))
        elif self.kind is float:
            cmds.optionVar(floatValue=(self.var, float(value)))
        elif self.kind is int:
            cmds.optionVar(intValue=(self.var, int(value)))
        else:
            cmds.optionVar(stringValue=(self.var, str(value)))


FIELDS = [
    # Where the exchange FBX lives. Must match the Blender side.
    _Field("exchange_dir", DEFAULT_EXCHANGE_DIR, str),
    _Field("exchange_name", DEFAULT_EXCHANGE_NAME, str),

    # Updates. Maya has no add-on repository of its own, so the tool checks a
    # manifest we publish and tells the artist - it never installs on its own.
    _Field("update_url",
           "https://mutaform.github.io/qc-bridge-blender-maya/version.json", str),
    _Field("update_auto_check", True, bool),
    # Epoch seconds of the last successful check.
    _Field("update_last_check", 0.0, float),
    # Which version was running at that check. These settings are Maya
    # optionVars: they belong to the artist and outlive any install, so a
    # freshly installed copy would otherwise inherit the previous one's
    # timestamp and stay silent about being out of date - exactly the moment
    # it most needs to speak up.
    _Field("update_last_version", "", str),
    # A version the artist chose to pass over; they are not asked about it
    # again, but a later one still surfaces.
    _Field("update_skip_version", "", str),
]

_BY_NAME = {f.name: f for f in FIELDS}


class Settings(object):
    """Live view onto the optionVars: every read and write hits Maya."""

    __slots__ = ()

    def __getattr__(self, name):
        field = _BY_NAME.get(name)
        if field is None:
            raise AttributeError(name)
        return field.read()

    def __setattr__(self, name, value):
        field = _BY_NAME.get(name)
        if field is None:
            raise AttributeError(name)
        field.write(value)

    def as_dict(self):
        return {f.name: f.read() for f in FIELDS}

    def reset(self):
        """Drop every stored value, returning the tool to its defaults."""
        for field in FIELDS:
            if cmds.optionVar(exists=field.var):
                cmds.optionVar(remove=field.var)


_INSTANCE = Settings()


def load():
    """Return the shared settings object."""
    return _INSTANCE

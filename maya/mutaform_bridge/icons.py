# SPDX-License-Identifier: GPL-3.0-or-later
"""Every icon the panel uses, in one place.

The panel refers to the semantic names here rather than to resource paths, so
restyling the tool is a one-file change - the same arrangement QC Bake and
QC Validator for Maya use.

These are Maya's own built-in resources, reached through the ``:/`` prefix.
Every name below is one the other two tools already confirmed to load as a
non-null pixmap in Maya 2025. That check is not optional: a missing resource
does not raise, it silently draws an empty square.
"""

RESOURCE_PREFIX = ":/"

# Header
ICON_BADGE = "doubleHorizArrow.png"

# Primary actions
ICON_IMPORT = "fileOpen.png"
ICON_EXPORT = "reloadReference.png"

# Import Options section and its rows
ICON_IMPORT_OPTIONS = "polyCleanup.png"
ICON_CLEAN_NAMES = "quickRename.png"
ICON_UNLOCK = "out_transform.png"
ICON_HISTORY = "smallTrash.png"
ICON_MATERIALS = "out_lambert.png"

# Tools section
ICON_TOOLS = "polyRemesh.png"
ICON_FIND = "search.png"
ICON_FIX = "polySmooth.png"
ICON_NORMALS = "polyMesh.png"

# Settings section
ICON_SETTINGS = "advancedSettings.png"
ICON_BROWSE = "fileOpen.png"
ICON_UPDATE = "polyRandomizeShell.png"


def path(name):
    """Full resource path for a name from this module."""
    return RESOURCE_PREFIX + name if name else ""

# SPDX-License-Identifier: GPL-3.0-or-later
# QC Bridge Maya-Blender - Maya side
# ==================================
# Exchanges scenes with the Blender half of the bridge through an FBX in a
# shared folder, then runs the Maya cleanup automatically: Blender empties
# become groups, FBX name suffixes are stripped, transforms are unlocked,
# materials are rebuilt as clean Blinns with their textures.
#
# The package is laid out so the pieces stay small:
#
#   mbr_core            hierarchy helpers, name cleanup, pivots, FBX options
#   mbr_io              import from / export to the exchange FBX
#   mbr_materials       Blinn rebuild and the texture sidecar
#   mbr_scene           history, locks, Random Sharp checks
#   mbr_locked_normals  locked normals -> Maya soft/hard edges
#   prefs               settings, persisted in Maya optionVars
#   updater             the update mechanism, testable without Maya
#   mbr_ui              the window
#
# The installer (install/install.py) and the updater rely on this file
# carrying VERSION as the first thing named VERSION: the release build reads
# it from here, and so does an update before deciding whether to trust an
# archive.

VERSION = (1, 2, 0)
VERSION_STRING = ".".join(str(part) for part in VERSION)

BRIDGE_VERSION = VERSION_STRING
BRIDGE_VERSION_LABEL = "ver %s" % VERSION_STRING


def show():
    """Open the bridge window. The single public entry point."""
    from . import mbr_ui
    return mbr_ui.show_ui()


# The name the previous shelf button called.
show_ui = show


# The old flat layout exposed the working functions on the entry module
# (mutaform_bridge.import_from_blender() and so on). They stay reachable here,
# resolved lazily so importing the package does not load Maya modules until
# something actually needs them.
_EXPORTS = {
    "mbr_core": (
        "DEFAULT_EXCHANGE_DIR", "DEFAULT_EXCHANGE_NAME", "analyze_roots",
        "clean_blender_fbx_suffixes", "convert_empties_to_groups",
        "exchange_path", "find_empty_candidates", "is_empty_candidate",
        "iter_transforms_under",
    ),
    "mbr_io": (
        "export_scene_to_blender", "export_selected_to_blender",
        "import_fbx_file", "import_from_blender",
    ),
    "mbr_materials": ("normalize_materials_to_blinn",),
    "mbr_scene": (
        "check_scene", "clean_geometry_history", "find_random_sharp_edges",
        "fix_random_sharp_edges", "unlock_transforms",
    ),
}


def __getattr__(name):
    import importlib

    for module_name, names in _EXPORTS.items():
        if name in names:
            module = importlib.import_module("." + module_name, __name__)
            return getattr(module, name)
    if name == "LAST_REPORT":
        from . import mbr_core
        return mbr_core.LAST_REPORT
    raise AttributeError("module %r has no attribute %r" % (__name__, name))

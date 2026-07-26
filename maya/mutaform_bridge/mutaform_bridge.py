# SPDX-License-Identifier: GPL-3.0-or-later
# Mutaform Bridge - Mutaform Studio
"""Public Maya entry point for Mutaform Bridge.

This file intentionally stays small. Implementation lives in mbr_core,
mbr_materials, mbr_io, and mbr_ui so day-to-day maintenance does not require
loading one large script.
"""

from __future__ import annotations

from mbr_core import (
    BRIDGE_VERSION,
    BRIDGE_VERSION_LABEL,
    DEFAULT_EXCHANGE_DIR,
    DEFAULT_EXCHANGE_NAME,
    LAST_REPORT,
    analyze_roots,
    clean_blender_fbx_suffixes,
    convert_empties_to_groups,
    exchange_path,
    find_empty_candidates,
    is_empty_candidate,
    iter_transforms_under,
)
from mbr_io import export_scene_to_blender, export_selected_to_blender, import_fbx_file, import_from_blender
from mbr_materials import normalize_materials_to_blinn
from mbr_scene import (
    check_scene,
    clean_geometry_history,
    find_random_sharp_edges,
    fix_random_sharp_edges,
    unlock_transforms,
)
from mbr_ui import show_ui

__all__ = [
    "BRIDGE_VERSION",
    "BRIDGE_VERSION_LABEL",
    "DEFAULT_EXCHANGE_DIR",
    "DEFAULT_EXCHANGE_NAME",
    "LAST_REPORT",
    "analyze_roots",
    "check_scene",
    "clean_blender_fbx_suffixes",
    "clean_geometry_history",
    "convert_empties_to_groups",
    "exchange_path",
    "export_scene_to_blender",
    "export_selected_to_blender",
    "find_empty_candidates",
    "find_random_sharp_edges",
    "fix_random_sharp_edges",
    "import_fbx_file",
    "import_from_blender",
    "is_empty_candidate",
    "iter_transforms_under",
    "normalize_materials_to_blinn",
    "show_ui",
    "unlock_transforms",
]

if __name__ == "__main__":
    show_ui()

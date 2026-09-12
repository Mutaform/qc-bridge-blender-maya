# Changelog

## 1.3.0

Maya: the bridge is now a dockable panel in the same style as QC Bake and
QC Validator for Maya. Blender: no changes.

**Maya.** The `maya.cmds` window is replaced by a PySide6 panel that docks
like the other two studio tools and shares their look: a bold title with the
version, one primary Import button with the any-FBX variant beside it, a
coloured status strip carrying the bridge's report, and three collapsible
sections - Import Options, Tools (Random Sharp, Unlock Normals) and Settings
(exchange folder with a browse button, FBX name, updates). Import options and
folded sections are remembered between sessions. The panel restores itself
when Maya starts with it docked; the update banner and the install flow are
unchanged.

## 1.2.0

Maya: drag-and-drop installer and a built-in update check with one-click
install. Blender: the bridge moved from the N-panel to a Maya icon in the 3D
Viewport header.

**Blender.** The N-panel tab is gone. A Maya icon sits in the 3D Viewport
header right after the Proportional Editing controls and opens a popover with
the same items: Import From Maya, Export Selected, Export Selected Collection,
Convert Scene, Settings. The last report wraps instead of being clipped. The
manifest declares the `files` permission it always needed.

**Maya.** The Maya half is now a package installed the way QC Bake for Maya
is: unzip anywhere permanent, drag `install/install.py` into a viewport. The
installer writes a module file pointing at the unpacked folder, puts a
QC Bridge button on the Mutaform shelf, removes the old copy from the scripts
folder and the old shelf buttons, and opens the window. The window checks a
published manifest every time it opens and, when a newer release exists,
offers to install it: download, sha256 check, swap of the package folder,
reload without restarting Maya, with the previous version kept until the new
one has loaded. Exchange folder and FBX name are remembered between sessions.

**Build.** One script builds both archives, checks that the version agrees in
the Blender manifest, the Blender package and the Maya package, and writes
the update manifest beside the archives. Archives are written with forward
slashes so they unpack anywhere.

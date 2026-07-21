# QC Bridge Blender-Maya

QC Bridge Maya-Blender by Mutaform is a two-part pipeline tool:

- Blender extension: `mutaform_bridge/`
- Maya companion files: `maya/mutaform_bridge/`

## Blender Install

Add the extension repository URL in Blender:

```text
https://mutaform.github.io/qc-bridge-blender-maya/index.json
```

Then sync repositories and install `QC Bridge Maya-Blender by Mutaform`.

## Maya Install

Download the current Maya archive:

[mutaform_bridge_maya_v1.zip](https://mutaform.github.io/qc-bridge-blender-maya/mutaform_bridge_maya_v1.zip)

1. Close Maya.
2. Extract `mutaform_bridge_maya_v1.zip`.
3. Inside the archive there is a folder named `mutaform_bridge`.
4. Copy that folder to your Maya scripts folder:

```text
C:\Users\YOUR_WINDOWS_USER\Documents\maya\2025\scripts\
```

The final folder should look like this:

```text
C:\Users\YOUR_WINDOWS_USER\Documents\maya\2025\scripts\mutaform_bridge\
```

5. Start Maya.
6. Open Script Editor:

```text
Windows > General Editors > Script Editor
```

7. Go to the Python tab.
8. Paste this code, replacing `YOUR_WINDOWS_USER` with your Windows user name:

```python
import sys

path = r"C:\Users\YOUR_WINDOWS_USER\Documents\maya\2025\scripts\mutaform_bridge"
if path not in sys.path:
    sys.path.append(path)

import install_shelf_button
install_shelf_button.install()
```

For example:

```python
import sys

path = r"C:\Users\denis\Documents\maya\2025\scripts\mutaform_bridge"
if path not in sys.path:
    sys.path.append(path)

import install_shelf_button
install_shelf_button.install()
```

9. Press `Ctrl + Enter`.

After that, the `QC Bridge` button appears on the `Poly Modeling` shelf. It uses the Mutaform logo and opens the addon window.

## Build Blender Release ZIP

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File tools/build_release.ps1
```

The release archive will be written to:

```text
dist/mutaform_bridge_blender.zip
```

## Repository Layout

```text
mutaform_bridge/       Blender extension source
maya/mutaform_bridge/  Maya companion source
downloads/             Downloadable Maya archive
tools/                 Release build scripts
```

## License

This project is licensed under GPL-3.0-or-later, matching the Blender Extension manifest.

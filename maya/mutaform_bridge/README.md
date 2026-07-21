# Mutaform Bridge for Maya

Maya-side companion for the Blender Mutaform Bridge add-on.

Use `install_shelf_button.py` once to add the Mutaform shelf button and the
Mutaform menu. The main tool is:

```python
import mutaform_bridge
mutaform_bridge.show_ui()
```

The first version exchanges FBX files through a shared folder, then runs the
Maya cleanup step automatically: locator empties become groups, Blender FBX
suffixes are cleaned, and transforms can be unlocked.

# Content tools

Start both services and open Content Studio:

```bat
launchers\editor\workbench.bat <pack>
```

```sh
sh launchers/editor/workbench.sh <pack>
```

Use `cc0-starter` for the bundled examples, or the name of an existing private pack export.
Without an argument, `SPRITEMOTION_FIT_PACK` takes precedence; otherwise the bundled starter
is preferred, or the sole existing export. A missing starter export is prepared automatically
from the bundled assets and your supplied UO model. Private packs still require their own export. It reuses matching services and refuses a port occupied by another pack
or application. Ctrl+C stops only services it started; finish saves/renders first.

Content Studio and Fit Lab have **Open Fit Lab** / **Open Content Studio** links in their
headers. These open another tab so unsaved work in the current tool remains available.
The links use the standard local ports, 8772 and 8774; start both with the workbench launcher.

Individual Windows launchers: `content-studio.bat`, `fit-lab.bat <pack>`.
Linux/macOS equivalents:

```sh
sh launchers/editor/content-studio.sh
sh launchers/editor/fit-lab.sh <pack>
```

The shell launchers use `.venvs/spritemotion/bin/python`, then `python3`.
Set `SPRITEMOTION_PYTHON` to override. Install the repository's Python dependencies first;
UO builds also require Blender and the supplied canonical model. The Linux scripts can be
run with `sh` without changing executable permissions.

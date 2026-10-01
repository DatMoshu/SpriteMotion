# Godot (third-party runtime)

The Sprite Pose Editor (`tools/sprite-pose-editor/`) is a Godot project.
This folder holds the Godot executable the launchers use. **The executables
are gitignored and are not distributed with SpriteMotion.**

| | |
|---|---|
| Version | Godot 4.7 stable, official build (`v4.7.stable.official.5b4e0cb0f`), Windows x86-64 |
| Files | `Godot_v4.7-stable_win64.exe` (editor/runtime), `Godot_v4.7-stable_win64_console.exe` (console wrapper for headless runs) |
| Origin | <https://godotengine.org/download/archive/4.7-stable/>, the standard (non-.NET) build |
| License | MIT, see <https://godotengine.org/license/> |

## Install

`launchers\pipeline\0-setup.bat` does this for you. To run it on its own:

```sh
python tools/godot/fetch.py
```

`fetch.py` downloads the official 4.7-stable zip for your platform (Windows,
Linux x86-64 or macOS) from the Godot GitHub release, checks it against the
SHA-512 pinned in the script, and extracts it here. If the executable is
already present, it does nothing. It uses the standard library only.

To use a Godot you already have, set `SPRITEMOTION_GODOT` (and
`SPRITEMOTION_GODOT_CONSOLE` for tests) in `launchers/_shared/config.bat` or as
environment variables. Setup then skips the download.

On Linux and macOS, run the editor with your own Godot 4.7:

```sh
godot --path tools/sprite-pose-editor -- --dataset=<dataset folder>
```

Other Godot 4.x versions may work but are not tested. The project uses no
.NET or GDExtension code.

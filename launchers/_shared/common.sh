# Shared logic of the .sh launchers (twin of common.bat). Source it; do not run it:
#   . "$(dirname "${BASH_SOURCE[0]}")/../_shared/common.sh"
# Settings resolve: environment variable > config.local.sh > config.sh. Needs bash 3.2 or newer.

SM_ROOT=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
_sm_here="$SM_ROOT/launchers/_shared"
_sm_keys="SPRITEMOTION_UO_SOURCE SPRITEMOTION_DATASET SPRITEMOTION_GODOT SPRITEMOTION_GODOT_CONSOLE SPRITEMOTION_BLENDER SPRITEMOTION_BLEND SPRITEMOTION_ARMATURE SPRITEMOTION_MAPPING SPRITEMOTION_FRAME_START SPRITEMOTION_FRAME_STEP SPRITEMOTION_PYTHON"

# Remember what the environment already says (a blank value counts as unset, like in common.bat).
_sm_env=""
for _k in $_sm_keys; do
    eval "_v=\${$_k:-}"
    if [ -n "$_v" ]; then _sm_env="$_sm_env $_k"; eval "_sm_saved_$_k=\$_v"; fi
done
[ -f "$_sm_here/config.sh" ] && . "$_sm_here/config.sh"
[ -f "$_sm_here/config.local.sh" ] && . "$_sm_here/config.local.sh"
for _k in $_sm_env; do eval "$_k=\$_sm_saved_$_k"; done

sm_find_venv_python() {
    local c
    for c in "$SM_ROOT/.venvs/spritemotion/bin/python" "$SM_ROOT/.venvs/spritemotion/Scripts/python.exe"; do
        if [ -x "$c" ]; then printf '%s\n' "$c"; return 0; fi
    done
    return 1
}
SM_VENV_PYTHON=$(sm_find_venv_python || true)
if [ -z "${SPRITEMOTION_PYTHON:-}" ]; then
    if [ -n "$SM_VENV_PYTHON" ]; then SPRITEMOTION_PYTHON=$SM_VENV_PYTHON
    else SPRITEMOTION_PYTHON=$(command -v python3 || command -v python || true); fi
fi

if [ -z "${SPRITEMOTION_GODOT:-}" ]; then
    for _c in "$SM_ROOT/tools/godot/Godot_v4.7-stable_win64.exe" "$SM_ROOT/tools/godot/Godot_v4.7-stable_linux.x86_64" \
              "$SM_ROOT/tools/godot/Godot.app/Contents/MacOS/Godot"; do
        if [ -x "$_c" ]; then SPRITEMOTION_GODOT=$_c; break; fi
    done
fi
if [ -z "${SPRITEMOTION_GODOT_CONSOLE:-}" ]; then
    if [ -x "$SM_ROOT/tools/godot/Godot_v4.7-stable_win64_console.exe" ]; then
        SPRITEMOTION_GODOT_CONSOLE="$SM_ROOT/tools/godot/Godot_v4.7-stable_win64_console.exe"
    else SPRITEMOTION_GODOT_CONSOLE=${SPRITEMOTION_GODOT:-}; fi
fi
if [ -z "${SPRITEMOTION_BLENDER:-}" ]; then
    SPRITEMOTION_BLENDER=$(command -v blender || true)
    if [ -z "$SPRITEMOTION_BLENDER" ] && [ -x /Applications/Blender.app/Contents/MacOS/Blender ]; then
        SPRITEMOTION_BLENDER=/Applications/Blender.app/Contents/MacOS/Blender
    fi
    if [ -z "$SPRITEMOTION_BLENDER" ] && [ -n "${ProgramFiles:-}" ]; then
        for _c in "$ProgramFiles"/Blender\ Foundation/Blender\ */blender.exe; do
            if [ -x "$_c" ]; then SPRITEMOTION_BLENDER=$_c; fi
        done
    fi
fi

SM_EDITOR="$SM_ROOT/tools/sprite-pose-editor"
SM_BLENDER_TOOLS="$SM_ROOT/tools/blender"
SM_CLI=("$SPRITEMOTION_PYTHON" -m spritemotion)
# --factory-startup keeps your own Blender add-ons out of headless runs.
SM_BLENDER_ARGS=(-b --factory-startup)
SM_ARMATURE_ARG=()
if [ -n "${SPRITEMOTION_ARMATURE:-}" ]; then SM_ARMATURE_ARG=(--armature "$SPRITEMOTION_ARMATURE"); fi
export SPRITEMOTION_UO_SOURCE SPRITEMOTION_DATASET SPRITEMOTION_GODOT SPRITEMOTION_GODOT_CONSOLE SPRITEMOTION_BLENDER \
       SPRITEMOTION_BLEND SPRITEMOTION_ARMATURE SPRITEMOTION_MAPPING SPRITEMOTION_FRAME_START SPRITEMOTION_FRAME_STEP \
       SPRITEMOTION_PYTHON
unset _k _v _c _sm_env _sm_keys _sm_here

# sm_need_python: stop unless a Python interpreter was found.
sm_need_python() {
    if [ -z "${SPRITEMOTION_PYTHON:-}" ] || ! command -v "$SPRITEMOTION_PYTHON" >/dev/null 2>&1; then
        echo "[SpriteMotion] No Python found at '${SPRITEMOTION_PYTHON:-}'." >&2
        echo "               Run launchers/pipeline/0-setup.sh first, or set SPRITEMOTION_PYTHON." >&2
        exit 1
    fi
}
# sm_require VARIABLE "what it is": stop unless the setting is non-empty.
sm_require() {
    local value
    eval "value=\${$1:-}"
    if [ -z "$value" ]; then
        echo "[SpriteMotion] $1 is not set: $2" >&2
        echo "               Set it in launchers/_shared/config.local.sh or as an environment variable." >&2
        exit 1
    fi
}
# sm_open PATH: open a file in the default viewer (a GUI window; returns at once).
sm_open() {
    if command -v xdg-open >/dev/null 2>&1; then nohup xdg-open "$1" >/dev/null 2>&1 &
    elif command -v open >/dev/null 2>&1; then open "$1"
    elif command -v cygstart >/dev/null 2>&1; then cygstart "$1"
    elif command -v start >/dev/null 2>&1; then start "" "$1"
    else echo "Open this file: $1"; fi
}

cd "$SM_ROOT"

#!/usr/bin/env bash
# Run the shared CLI on Linux, Termux, macOS, Git Bash, or WSL.
script_path=${BASH_SOURCE[0]}
case "$script_path" in
    */*) project_dir=${script_path%/*} ;;
    *) project_dir=. ;;
esac
project_dir=$(CDPATH= cd -- "$project_dir" && pwd -P) || exit 1

supports_python() {
    "$@" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
}

# This variable accepts one executable name or path, including paths with spaces.
if [[ -n "${GETIT_UNLOCK_PYTHON:-}" ]]; then
    if ! supports_python "$GETIT_UNLOCK_PYTHON"; then
        printf '%s\n' 'Error: GETIT_UNLOCK_PYTHON must point to a working Python 3.11+ executable.' >&2
        exit 1
    fi
    python_command=("$GETIT_UNLOCK_PYTHON")
else
    python_command=()
    for candidate in "$project_dir/.venv/bin/python" "$project_dir/.venv/Scripts/python.exe" python3 python; do
        if supports_python "$candidate"; then
            python_command=("$candidate")
            break
        fi
    done
    if [[ ${#python_command[@]} -eq 0 ]] && supports_python py -3; then
        python_command=(py -3)
    fi
    if [[ ${#python_command[@]} -eq 0 ]]; then
        printf '%s\n' \
            'Error: Python 3.11 or newer is required by the Bash launcher.' \
            'Install Python using your package manager (Termux: pkg install python).' \
            'For a custom installation, set GETIT_UNLOCK_PYTHON to its executable path.' >&2
        exit 1
    fi
fi

# Keep the caller's working directory for .env and saved state, as main.py does.
exec "${python_command[@]}" "$project_dir/main.py" "$@"

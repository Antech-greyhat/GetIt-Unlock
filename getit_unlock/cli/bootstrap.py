"""Report missing runtime requirements without importing terminal libraries."""
import importlib.util
import os
import shlex
import sys
from pathlib import Path

from .. import PROJECT_NAME, __version__
from .brand import DISCLAIMER, PROFILE_URL

DEPENDENCIES = ("rich",)


def missing_dependencies():
    return [name for name in DEPENDENCIES if importlib.util.find_spec(name) is None]


def launch(argv=None):
    if sys.version_info < (3, 11):
        print("Error: GetIt-Unlock requires Python 3.11 or newer. Select a compatible interpreter.", file=sys.stderr)
        return 1
    missing = missing_dependencies()
    if missing:
        project = Path(__file__).resolve().parents[2]
        print(f"{PROJECT_NAME} {__version__}\nDeveloper: {PROFILE_URL}", file=sys.stderr)
        print(DISCLAIMER, file=sys.stderr)
        print("\nStartup requirements need attention:", file=sys.stderr)
        print("  Missing Python packages: " + ", ".join(missing), file=sys.stderr)
        print("  Install into the same Python used by this launcher:", file=sys.stderr)
        if os.name == "nt":
            executable = "'" + sys.executable.replace("'", "''") + "'"
            path = "'" + str(project / "requirements.txt").replace("'", "''") + "'"
            packages = f"-r {path}" if (project / "requirements.txt").exists() else "'rich>=14.0,<16'"
            command = f"& {executable} -m pip install --no-cache-dir {packages}"
        else:
            packages = (f"-r {shlex.quote(str(project / 'requirements.txt'))}" if (project / "requirements.txt").exists()
                        else "'rich>=14.0,<16'")
            command = f"{shlex.quote(sys.executable)} -m pip install --no-cache-dir {packages}"
        print("\n  " + command, file=sys.stderr)
        print("\n  Linux: use a project virtual environment if system Python is externally managed.", file=sys.stderr)
        print("  Termux: pkg install python python-pip, then run the pip command above.", file=sys.stderr)
        print("  Restart the launcher after installation. See README.md for OS setup.", file=sys.stderr)
        return 1
    from .commands import main
    return main(argv)

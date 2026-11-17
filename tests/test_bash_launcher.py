"""Offline integration checks for the Bash entry point."""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from getit_unlock.core.state import StateStore


PROJECT = Path(__file__).resolve().parents[1]


def find_bash():
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            candidate = Path(git).parent.parent / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
    return shutil.which("bash")


BASH = find_bash()


@unittest.skipUnless(BASH, "Bash is not installed")
class BashLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.project = self.directory / "project with spaces"
        self.project.mkdir()
        self.script = self.project / "main.sh"
        shutil.copyfile(PROJECT / "main.sh", self.script)
        # A small subprocess target lets us observe argument, cwd, and exit handling.
        (self.project / "main.py").write_text(
            "import json, os, sys\n"
            "print(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd()}))\n"
            "raise SystemExit(37)\n",
            encoding="utf-8",
        )
        self.environment = os.environ.copy()
        for key in ("GITHUB_TOKEN", "GH_TOKEN", "HELPER_TOKEN", "TARGET_REPO", "GETIT_UNLOCK_PYTHON"):
            self.environment.pop(key, None)
        self.python = Path(sys.executable).as_posix()

    def invoke(self, *args, script=None, environment=None):
        return subprocess.run(
            [BASH, "--noprofile", "--norc", (script or self.script).as_posix(), *args],
            cwd=self.directory,
            env=self.environment if environment is None else environment,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def executable(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8", newline="\n")
        path.chmod(0o755)
        return path.as_posix()

    def test_source_launcher_returns_same_catalog_as_python(self):
        result = self.invoke("list", "--json", script=PROJECT / "main.sh")
        direct = subprocess.run(
            [sys.executable, str(PROJECT / "main.py"), "list", "--json"],
            cwd=self.directory, env=self.environment, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(direct.returncode, 0, direct.stderr)
        self.assertEqual(json.loads(result.stdout), json.loads(direct.stdout))

    def test_spaces_arguments_and_child_exit_code_are_preserved(self):
        interpreter = self.executable(
            self.directory / "custom python with spaces",
            f'exec {shlex.quote(self.python)} "$@"\n',
        )
        self.environment["GETIT_UNLOCK_PYTHON"] = interpreter
        args = ("--env-file", "settings with spaces/.env", "--pr-title", "Keep {repo} progress together", "")
        result = self.invoke(*args)
        self.assertEqual(result.returncode, 37, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"args": list(args), "cwd": str(self.directory)})

    def test_reads_configuration_and_saved_state_from_callers_directory(self):
        (self.directory / ".env").write_text("TARGET_REPO=alice/lab\n", encoding="utf-8")
        with StateStore(self.directory / ".achievement-state" / "progress.sqlite3") as store:
            store.finish(store.start("alice", "alice/lab", "quickdraw"))
            store.finish(store.start("alice", "alice/other", "quickdraw"))
        self.environment["GETIT_UNLOCK_PYTHON"] = self.python
        result = self.invoke("status", "--json", script=PROJECT / "main.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)["summary"]
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["repo"], "alice/lab")
        self.assertEqual(summary[0]["count"], 1)

    def test_rejects_unavailable_explicit_interpreter_without_fallback(self):
        self.environment["GETIT_UNLOCK_PYTHON"] = "getit-unlock-missing-python"
        result = self.invoke("list")
        self.assertEqual(result.returncode, 1)
        self.assertIn("GETIT_UNLOCK_PYTHON", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_old_explicit_python_is_rejected(self):
        self.environment["GETIT_UNLOCK_PYTHON"] = self.executable(
            self.directory / "old-python", "exit 1\n",
        )
        result = self.invoke("list")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Python 3.11+", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_missing_python_reports_installation_hint(self):
        empty_path = self.directory / "empty-path"
        empty_path.mkdir()
        self.environment["PATH"] = empty_path.as_posix()
        result = self.invoke("list")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Python 3.11 or newer", result.stderr)
        self.assertIn("pkg install python", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_project_virtual_environment_is_used_without_activation(self):
        self.executable(
            self.project / ".venv" / "bin" / "python",
            'if [[ "$1" == "-c" ]]; then exit 0; fi\nexit 42\n',
        )
        result = self.invoke("list")
        self.assertEqual(result.returncode, 42, result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()

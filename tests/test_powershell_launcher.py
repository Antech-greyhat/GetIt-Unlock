"""PowerShell integration: arguments, interpreter selection, and exit codes."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


@unittest.skipUnless(POWERSHELL, "PowerShell is not installed")
class PowerShellLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.project = self.directory / "project with spaces"
        self.project.mkdir()
        self.script = self.project / "main.ps1"
        shutil.copyfile(PROJECT / "main.ps1", self.script)
        (self.project / "main.py").write_text(
            "import json, os, sys\n"
            "print(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd()}))\n"
            "raise SystemExit(37)\n", encoding="utf-8",
        )
        self.environment = os.environ.copy()
        for key in ("GITHUB_TOKEN", "GH_TOKEN", "HELPER_TOKEN", "TARGET_REPO", "GETIT_UNLOCK_PYTHON"):
            self.environment.pop(key, None)
        self.environment["PYTHONDONTWRITEBYTECODE"] = "1"
        # PowerShell may create startup telemetry/cache files; keep them in the temporary test directory.
        self.environment["XDG_CACHE_HOME"] = str(self.directory / "cache")
        self.environment["GETIT_UNLOCK_PYTHON"] = sys.executable

    def invoke(self, *args, script=None):
        return subprocess.run(
            [POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(script or self.script), *args],
            cwd=self.directory, env=self.environment, capture_output=True, text=True, timeout=30,
        )

    def test_spaces_arguments_caller_directory_and_exit_code(self):
        args = ("--env-file", "settings with spaces/.env", "--pr-title", "Keep {repo} progress $together", "--plain")
        result = self.invoke(*args)
        self.assertEqual(result.returncode, 37, result.stderr)
        observed = json.loads(result.stdout)
        self.assertEqual(observed["args"], list(args))
        # Windows may expand the runner's short path (RUNNER~1) to runneradmin.
        self.assertTrue(self.directory.samefile(observed["cwd"]))

    def test_source_catalog_matches_python(self):
        result = self.invoke("list", "--json", script=PROJECT / "main.ps1")
        direct = subprocess.run([sys.executable, "-B", str(PROJECT / "main.py"), "list", "--json"],
                                cwd=self.directory, env=self.environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), json.loads(direct.stdout))

    def test_invalid_override_is_rejected_without_fallback(self):
        self.environment["GETIT_UNLOCK_PYTHON"] = "getit-unlock-missing-python"
        result = self.invoke("list")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("GETIT_UNLOCK_PYTHON", result.stderr)

    def test_reads_configuration_from_callers_directory(self):
        (self.directory / ".env").write_text("TARGET_REPO=alice/lab\n", encoding="utf-8")
        result = self.invoke("requirements", "--json", script=PROJECT / "main.ps1")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)
        self.assertEqual(next(row["detail"] for row in rows if row["requirement"] == "Target repository"), "alice/lab")
        self.assertFalse((self.directory / ".achievement-state").exists())


if __name__ == "__main__":
    unittest.main()

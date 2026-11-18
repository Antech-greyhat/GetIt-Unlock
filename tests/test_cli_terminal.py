"""Offline checks for startup, real menu keys, and complete session shutdown."""
import io
import json
import os
import signal
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.data_structures import Size

from getit_unlock.cli import bootstrap
from getit_unlock.cli.brand import FAREWELL, FORK_URL, PROFILE_URL, REPOSITORY_URL
from getit_unlock.cli.commands import Terminated, main
from getit_unlock.cli.preflight import startup_checks
from getit_unlock.cli.ui import Choice, Console, UI_OPTIONS, UIOptions
from getit_unlock.core.config import Config


class SmallScreen(DummyOutput):
    def __init__(self, columns=40):
        self.columns = columns

    def get_size(self):
        return Size(rows=12, columns=self.columns)


class KeyboardTests(unittest.TestCase):
    def test_scrolling_keeps_selected_description_and_exit_hint_visible(self):
        description = "A description wrapping across a small mobile screen"
        choices = [Choice(str(i), f"Choice {i}", description) for i in range(1, 10)]
        for columns in (20, 40, 80):
            with self.subTest(columns=columns), create_pipe_input() as keyboard:
                pages = []

                def inspect_screen(app):
                    if len(pages) >= 2:
                        return
                    screen = app.renderer.last_rendered_screen
                    pages.append("\n".join(
                        "".join(screen.data_buffer[row][col].char for col in range(columns)).rstrip()
                        for row in range(screen.height)
                    ))
                    keyboard.send_text("\x1b[A" if len(pages) == 1 else "\r")

                app = Console().menu_application(choices, input=keyboard, output=SmallScreen(columns))
                app.after_render += inspect_screen
                self.assertEqual(app.run(), "9")
                self.assertEqual(len(pages), 2)
                self.assertIn(">  9  Choice 9", pages[1])
                compact = "".join(pages[1].split())
                self.assertIn("".join(description.split()), compact)
                self.assertIn("Ctrl+Cexit", compact)
                self.assertLessEqual(len(pages[1].splitlines()), 12)

    def test_number_back_and_wrapped_arrow_navigation(self):
        choices = [Choice(str(i), f"Choice {i}", "A description wrapping across a small mobile screen") for i in range(1, 10)]
        for keys, expected in (("9", "9"), ("0", "back"), ("q", "back"),
                               ("\x1b[A\r", "9"), ("jj\r", "3"), ("\t\r", "2")):
            with self.subTest(keys=repr(keys)), create_pipe_input() as keyboard:
                keyboard.send_text(keys)
                app = Console().menu_application(choices, input=keyboard, output=SmallScreen())
                self.assertEqual(app.run(), expected)

    def test_eof_shortcuts_exit_prompt(self):
        for keys in ("\x04", "\x1a"):
            with self.subTest(keys=repr(keys)), create_pipe_input() as keyboard:
                keyboard.send_text(keys)
                app = Console().menu_application([Choice("a", "One")], input=keyboard, output=DummyOutput())
                with self.assertRaises(EOFError):
                    app.run()


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.args = ["--env-file", str(self.path / ".env"), "--state-dir", str(self.path / "state")]

    def invoke(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(self.args + list(args))
        return code, output.getvalue(), errors.getvalue()

    def test_missing_configuration_is_outlined_before_menu_and_can_exit(self):
        with patch.dict(os.environ, {}, clear=True), patch("sys.stdin.isatty", return_value=True), patch.object(
            Console, "choose", return_value="back"
        ), patch("getit_unlock.cli.commands.make_runner", side_effect=AssertionError("No network at startup")):
            code, output, _ = self.invoke()
        self.assertEqual(code, 0)
        self.assertIn("NEEDS SETUP", output)
        self.assertIn("HELPER", output.upper())
        self.assertEqual(output.count(FAREWELL), 1)
        self.assertTrue(output.rstrip().endswith(FAREWELL))
        for url in (PROFILE_URL, REPOSITORY_URL, FORK_URL):
            self.assertIn(url, output)
        self.assertFalse((self.path / "state").exists())
        self.assertFalse((self.path / ".env").exists())

    def test_nested_interrupt_exits_whole_session_with_one_farewell(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "secret-token", "TARGET_REPO": "alice/lab"}, clear=True), patch(
            "sys.stdin.isatty", return_value=True
        ), patch.object(Console, "choose", return_value="status"), patch(
            "getit_unlock.cli.commands.show_status", side_effect=KeyboardInterrupt
        ):
            code, output, errors = self.invoke()
        self.assertEqual(code, 130)
        self.assertEqual(output.count(FAREWELL), 1)
        self.assertIn("status --history", errors)
        self.assertNotIn("secret-token", output + errors)

    def test_termination_restores_signal_handler(self):
        before = signal.getsignal(signal.SIGTERM)
        with patch.dict(os.environ, {}, clear=True), patch("sys.stdin.isatty", return_value=True), patch(
            "getit_unlock.cli.commands.show_status", side_effect=Terminated
        ):
            code, output, _ = self.invoke("status")
        self.assertEqual(code, 143)
        self.assertIn(FAREWELL, output)
        self.assertEqual(signal.getsignal(signal.SIGTERM), before)

    def test_requirements_json_has_no_secrets_network_or_state_creation(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "primary-secret", "HELPER_TOKEN": "helper-secret"}, clear=True), patch(
            "getit_unlock.cli.commands.make_runner", side_effect=AssertionError("No network")
        ), patch("sys.stdin.isatty", return_value=True):
            code, output, _ = self.invoke("requirements", "--json")
        self.assertEqual(code, 0)
        rows = json.loads(output)
        self.assertEqual(next(row["status"] for row in rows if row["requirement"] == "Primary token"), "PRESENT")
        self.assertNotIn("primary-secret", output)
        self.assertNotIn("helper-secret", output)
        self.assertNotIn(FAREWELL, output)
        self.assertFalse((self.path / "state").exists())

    def test_plain_and_no_animation_are_scoped_to_one_invocation(self):
        options = UI_OPTIONS.get()
        with patch.dict(os.environ, {}, clear=True):
            code, output, _ = self.invoke("list", "--plain", "--no-animation")
        self.assertEqual(code, 0)
        self.assertNotIn("\x1b", output)
        self.assertEqual(UI_OPTIONS.get(), options)


class PresentationTests(unittest.TestCase):
    def test_farewell_urls_wrap_to_screen_width_and_remain_clickable(self):
        output = io.StringIO()
        with redirect_stdout(output):
            console = Console()
            console.rich.width = 40
            console.goodbye()
        value = output.getvalue()
        self.assertTrue(all(len(line) <= 40 for line in value.splitlines()))
        for url in (PROFILE_URL, REPOSITORY_URL, FORK_URL):
            self.assertIn(url, "".join(value.split()))

        output = io.StringIO()
        with patch("getit_unlock.cli.ui.enable_terminal", return_value=True), redirect_stdout(output):
            console = Console()
            console.rich.width = 40
            console.goodbye()
        for url in (PROFILE_URL, REPOSITORY_URL, FORK_URL):
            self.assertIn("\x1b]8;", output.getvalue())
            self.assertIn(";" + url + "\x1b\\", output.getvalue())

    def test_small_banner_and_literal_remote_text(self):
        output = io.StringIO()
        with redirect_stdout(output):
            console = Console()
            console.rich.width = 40
            console.masthead(disclaimer=True)
            console.panel("[red]remote\x1b[2J", ["[bold]literal\r\ntext"])
        value = output.getvalue()
        self.assertIn("GETIT", value)
        self.assertIn("UNLOCK", value)
        self.assertIn("[red]remote", value)
        self.assertNotIn("\x1b", value)

    def test_no_animation_does_not_start_live_renderer(self):
        token = UI_OPTIONS.set(UIOptions(no_animation=True))
        try:
            with patch("getit_unlock.cli.ui.enable_terminal", return_value=True), redirect_stdout(io.StringIO()):
                console = Console()
                with patch.object(console.rich, "status", side_effect=AssertionError("No animation")):
                    with console.activity("Checking") as activity:
                        activity.update("Checked")
        finally:
            UI_OPTIONS.reset(token)

    def test_missing_dependencies_are_actionable_without_importing_commands(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(bootstrap, "missing_dependencies", return_value=["rich", "prompt_toolkit"]), redirect_stdout(
            output
        ), redirect_stderr(errors):
            code = bootstrap.launch(["list", "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("pip install --no-cache-dir", errors.getvalue())
        self.assertIn("Termux", errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())

    def test_shell_configuration_does_not_require_env_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            checks = startup_checks(Config("alice/lab", "secret"), path / ".env", path / "state")
            self.assertEqual(next(status for name, status, _ in checks if name == "Primary token"), "PRESENT")
            self.assertFalse((path / "state").exists())


if __name__ == "__main__":
    unittest.main()

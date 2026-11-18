"""Offline checks for numbered menus, startup, and complete session shutdown."""
import io
import json
import os
import signal
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from rich.console import Console as RichConsole

from getit_unlock.cli import bootstrap
from getit_unlock.cli.brand import DISCLAIMER, FAREWELL, FORK_URL, PROFILE_URL, REPOSITORY_URL
from getit_unlock.cli.commands import Terminated, main
from getit_unlock.cli.preflight import configuration_warning, launch_startup, startup_checks
from getit_unlock.cli.ui import Choice, Console, UI_OPTIONS, UIOptions
from getit_unlock.core.config import Config


class NumberedMenuTests(unittest.TestCase):
    def test_numbers_leading_zeroes_default_and_back(self):
        choices = [Choice(str(i), f"Choice {i}") for i in range(1, 13)] + [Choice("back", "Exit")]
        for value, expected in (("1", "1"), ("01", "1"), ("12", "12"), ("", "2"),
                                ("0", "back"), ("00", "back"), ("q", "back"), ("back", "back")):
            with self.subTest(value=value), redirect_stdout(io.StringIO()), patch("builtins.input", return_value=value):
                self.assertEqual(Console().choose("Choose", choices, default=1), expected)

    def test_wrapping_preserves_choices_and_back_at_mobile_widths(self):
        choices = [Choice(str(i), f"Choice {i}", "A description wrapping across a small mobile screen")
                   for i in range(1, 10)] + [Choice("back", "Exit")]
        for width in (20, 40, 80):
            output = io.StringIO()
            with self.subTest(width=width), redirect_stdout(output), patch("builtins.input", return_value="09"):
                console = Console()
                console.rich.width = width
                self.assertEqual(console.choose("Choose", choices), "9")
                console.say()
            text = output.getvalue()
            self.assertTrue(all(len(line) <= width for line in text.splitlines()))
            compact = "".join(text.split())
            for number in range(1, 10):
                self.assertIn(f"[{number:02}]Choice{number}", compact)
            self.assertIn("[00]Exit", compact)

    def test_invalid_numbers_reprompt_and_back_default_is_zero(self):
        output = io.StringIO()
        with redirect_stdout(output), patch("builtins.input", side_effect=["bad", "13", "9" * 5000, ""]):
            result = Console().choose("Choose", [Choice("a", "One"), Choice("back", "Back")], default=1)
        self.assertEqual(result, "back")
        self.assertIn("Enter = 00", output.getvalue())
        self.assertEqual(output.getvalue().count("Invalid option"), 3)

    def test_interrupt_and_eof_propagate_to_session_cleanup(self):
        for error in (KeyboardInterrupt, EOFError):
            with self.subTest(error=error), redirect_stdout(io.StringIO()), patch("builtins.input", side_effect=error):
                with self.assertRaises(error):
                    Console().choose("Choose", [Choice("a", "One")])


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

    def test_startup_disappears_before_main_prompt_without_forcing_setup(self):
        output = io.StringIO()
        screens = []

        def exit_from_prompt():
            screens.append(output.getvalue().rsplit("\x1b[H", 1)[-1])
            return "00"

        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=True), patch("sys.stdin.isatty", return_value=True), patch(
            "getit_unlock.cli.ui.enable_terminal", return_value=True
        ), patch("builtins.input", side_effect=exit_from_prompt), patch(
            "getit_unlock.cli.commands.setup", side_effect=AssertionError("Do not force setup")
        ), patch("getit_unlock.cli.commands.make_runner", side_effect=AssertionError("No startup network")), redirect_stdout(output):
            self.assertEqual(main(self.args + ["--no-animation"]), 0)
        self.assertEqual(len(screens), 1)
        screen = screens[0]
        self.assertNotIn("STARTUP / local requirements", screen)
        self.assertNotIn("Checking credentials", screen)
        self.assertIn("SELECT AN OPTION", screen)
        self.assertIn("".join(DISCLAIMER.split()), "".join(screen.split()))
        self.assertLess(screen.index("[00] Exit"), screen.index("Required:"))
        self.assertLess(screen.index("Required:"), screen.index("Select an option"))
        self.assertIn("TARGET_REPO=OWNER/REPO", screen)
        self.assertFalse((self.path / ".env").exists())
        self.assertFalse((self.path / "state").exists())

    def test_warning_refreshes_after_setup_and_old_menu_is_cleared(self):
        output = io.StringIO()
        screens = []
        answers = iter(("05", "01", "", "00"))

        def answer():
            screens.append(output.getvalue().rsplit("\x1b[H", 1)[-1])
            return next(answers)

        def configure(config, env_file, workflow):
            env_file.write_text("GITHUB_TOKEN=secret-token\nTARGET_REPO=alice/lab\n", encoding="utf-8")

        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=True), patch("sys.stdin.isatty", return_value=True), patch(
            "getit_unlock.cli.ui.enable_terminal", return_value=True
        ), patch("builtins.input", side_effect=answer), patch("getit_unlock.cli.commands.setup", side_effect=configure), redirect_stdout(output):
            self.assertEqual(main(self.args + ["--no-animation"]), 0)
        self.assertIn("Required:", screens[0])
        self.assertNotIn("Required:", screens[-1])
        self.assertNotIn("ACCOUNT SETTINGS", screens[-1])
        self.assertIn("alice/lab", screens[-1])
        self.assertIn("".join(DISCLAIMER.split()), "".join(screens[-1].split()))
        self.assertNotIn("secret-token", output.getvalue())

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

        # Rich omits OSC 8 hyperlinks in legacy Windows mode. Test each renderer explicitly
        # so the host runner's console detection cannot change these expectations.
        for legacy_windows in (False, True):
            output = io.StringIO()
            with self.subTest(legacy_windows=legacy_windows):
                console = Console()
                console.rich = RichConsole(file=output, width=40, force_terminal=True,
                                           legacy_windows=legacy_windows, markup=False, highlight=False)
                console.goodbye()
                text = output.getvalue()
                if legacy_windows:
                    self.assertNotIn("\x1b]8;", text)
                else:
                    for url in (PROFILE_URL, REPOSITORY_URL, FORK_URL):
                        self.assertIn(";" + url + "\x1b\\", text)

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
        with patch.object(bootstrap, "missing_dependencies", return_value=["rich"]), redirect_stdout(
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


class StartupTests(unittest.TestCase):
    def test_checks_run_inside_their_loading_phase_with_three_seconds_total(self):
        events = []
        now = [0.0]

        class LoadingConsole:
            animate = True

            def clear(self):
                events.append("clear")

            def heading(self, title):
                events.append("heading")

            @contextmanager
            def loading(self, message):
                events.append(message)
                yield
                events.append("finished loading")

            def notice(self, text, **kwargs):
                events.append(text)

        def probe(name):
            self.assertEqual(events[-1], "Checking " + name)
            events.append("evaluated " + name)
            return "READY", "local result"

        def sleep(seconds):
            now[0] += seconds

        probes = [(name, "Checking " + name, lambda name=name: probe(name)) for name in ("first", "second", "third")]
        with patch("getit_unlock.cli.preflight.startup_probes", return_value=probes):
            launch_startup(Config(), Path("missing.env"), Path("state"), LoadingConsole(), sleep=sleep, clock=lambda: now[0])
        self.assertEqual(events[:2], ["clear", "heading"])
        for previous, following in (("first", "second"), ("second", "third")):
            self.assertLess(events.index(previous + " : READY"), events.index("Checking " + following))
        self.assertAlmostEqual(now[0], 3.0)

    def test_static_launch_has_no_delay_and_optional_helper_does_not_warn(self):
        config = Config("alice/lab", "primary-secret")
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()), patch.dict(os.environ, {}, clear=True):
            path = Path(directory)
            console = Console()
            console.animate = False
            launch_startup(config, path / ".env", path / "state", console,
                           sleep=lambda seconds: self.fail("Static output must not wait"))
            self.assertEqual(configuration_warning(config), "")
            self.assertFalse((path / "state").exists())

    def test_invalid_settings_warn_without_printing_credentials(self):
        config = Config("invalid", "primary secret", "helper secret")
        warning = configuration_warning(config)
        self.assertIn("GITHUB_TOKEN without whitespace", warning)
        self.assertIn("TARGET_REPO=OWNER/REPO", warning)
        self.assertIn("HELPER_TOKEN without whitespace", warning)
        self.assertNotIn(config.token, warning)
        self.assertNotIn(config.helper_token, warning)


if __name__ == "__main__":
    unittest.main()

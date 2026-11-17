import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from getit_unlock.cli.commands import main, run_wizard
from getit_unlock.cli.onboarding import ensure_credentials, helper_credentials
from getit_unlock.cli.ui import Console
from getit_unlock.core.catalog import target_for
from getit_unlock.core.config import Config
from getit_unlock.core.state import StateStore
from getit_unlock.github.api import GitHubError
from getit_unlock.github.badges import check_badges
from getit_unlock.workflows.runner import WorkflowRunner
from tests.test_interactive_badges import profile
from tests.test_workflows import FakeGitHub, REPO


class StarGitHub(FakeGitHub):
    def __init__(self, login="alice", user_id=1):
        super().__init__(login, user_id)
        self.repo.update(stargazers_count=15, private=False)
        self.starred = False
        self.star_error = None
        self.read_error = None
        self.verify_error = None

    def request(self, method, path, payload=None):
        if path != "/user/starred/alice/lab":
            if path == REPO and self.read_error:
                raise self.read_error
            return super().request(method, path, payload)
        self.calls.append((method, path, payload))
        if method == "GET":
            if self.starred:
                if self.verify_error:
                    raise self.verify_error
                return {}
            raise GitHubError("Not starred", 404)
        if method == "PUT":
            if self.star_error:
                raise self.star_error
            if not self.starred:
                self.repo["stargazers_count"] += 1
                self.starred = True
            return {}
        raise AssertionError(f"Unexpected star request: {method}")


class StarstruckWorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = StateStore(Path(temporary.name) / "progress.sqlite3")
        self.addCleanup(self.store.close)
        self.config = Config("alice/lab", "primary-secret", "helper-secret")
        self.primary = StarGitHub()
        self.helper = StarGitHub("bob", 2)
        self.helper.repo = self.primary.repo
        self.now = 0
        self.sleeps = []
        self.runner = WorkflowRunner(self.config, self.primary, self.helper,
                                     sleep=self.sleep, clock=lambda: self.now)

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def test_tiers_match_received_star_thresholds(self):
        self.assertEqual([target_for("starstruck", tier) for tier in
                          ("base", "bronze", "silver", "gold")], [16, 128, 512, 4096])

    def test_read_only_tracking_saves_observations_without_contribution_successes(self):
        self.primary.repo.update(permissions={}, default_branch=None, has_issues=False)
        self.runner.preflight("starstruck")
        result = self.runner.run_one("starstruck", self.store)
        self.assertEqual((result["stars"], result["remaining"], result["target_met"]), (15, 1, False))
        self.assertEqual(self.store.count("alice", "alice/lab", "starstruck"), 0)
        record = self.store.history()[0]
        self.assertEqual(record["status"], "observed")
        self.assertEqual(record["detail"]["stars"], 15)
        self.assertTrue(all(method == "GET" for method, _, _ in self.primary.calls))
        self.assertEqual(self.helper.calls, [])

    def test_live_stars_can_decrease_and_are_not_accumulated_across_runs(self):
        self.runner.preflight("starstruck")
        self.primary.repo["stargazers_count"] = 128
        first = self.runner.run_one("starstruck", self.store, star_tier="bronze")
        self.primary.repo["stargazers_count"] = 127
        second = self.runner.run_one("starstruck", self.store, star_tier="bronze")
        self.assertTrue(first["target_met"])
        self.assertEqual((second["stars"], second["remaining"], second["target_met"]), (127, 1, False))

    def test_helper_star_is_verified_and_not_repeated(self):
        self.runner.preflight("starstruck", star_with_helper=True)
        first = self.runner.run_one("starstruck", self.store, star_with_helper=True)
        second = self.runner.run_one("starstruck", self.store, star_with_helper=True)
        self.assertEqual(first["helper_star"], "added")
        self.assertEqual(second["helper_star"], "already_starred")
        self.assertEqual(second["stars"], 16)
        self.assertTrue(second["target_met"])
        self.assertEqual(sum(method == "PUT" for method, _, _ in self.helper.calls), 1)
        self.assertFalse(any(method != "GET" for method, _, _ in self.primary.calls))
        self.assertFalse(any(path == REPO for _, path, _ in self.helper.calls))

    def test_same_account_and_private_or_foreign_repository_are_rejected(self):
        self.helper.user = self.primary.user
        with self.assertRaisesRegex(ValueError, "different"):
            self.runner.preflight("starstruck", star_with_helper=True)
        self.primary.repo["private"] = True
        with self.assertRaisesRegex(ValueError, "public"):
            self.runner.preflight("starstruck")
        self.primary.repo["private"] = False
        self.primary.repo["owner"]["login"] = "someone-else"
        with self.assertRaisesRegex(ValueError, "owned"):
            self.runner.preflight("starstruck")

    def test_missing_helper_is_rejected_before_starring(self):
        runner = WorkflowRunner(self.config, self.primary)
        with self.assertRaisesRegex(ValueError, "helper client"):
            runner.preflight("starstruck", star_with_helper=True)
        self.runner.preflight("starstruck")
        with self.assertRaisesRegex(ValueError, "Verify a different helper"):
            self.runner.run_one("starstruck", self.store, star_with_helper=True)
        self.assertEqual(self.store.history(), [])

    def test_ambiguous_star_write_is_recorded_and_not_replayed(self):
        self.runner.preflight("starstruck", star_with_helper=True)
        self.helper.star_error = GitHubError("helper-secret: outcome uncertain", 502)
        with self.assertRaises(GitHubError):
            self.runner.run_one("starstruck", self.store, star_with_helper=True)
        record = self.store.history()[0]
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["detail"]["stage"], "starring_repository")
        self.assertNotIn("helper-secret", json.dumps(record))
        self.assertEqual(sum(method == "PUT" for method, _, _ in self.helper.calls), 1)

    def test_failed_readback_does_not_report_verified_star(self):
        self.runner.preflight("starstruck", star_with_helper=True)
        self.helper.verify_error = GitHubError("Not accessible", 403)
        with self.assertRaises(GitHubError):
            self.runner.run_one("starstruck", self.store, star_with_helper=True)
        self.assertEqual(self.store.history()[0]["status"], "failed")
        self.assertNotIn("helper_star", self.store.history()[0]["detail"])

    def test_polling_stops_when_target_is_met(self):
        def arrive(seconds):
            self.sleep(seconds)
            self.primary.repo["stargazers_count"] = 16
        self.runner.sleep = arrive
        self.runner.preflight("starstruck")
        result = self.runner.run_one("starstruck", self.store, star_wait=120)
        self.assertTrue(result["target_met"])
        self.assertEqual(self.sleeps, [15])
        self.assertEqual(len(self.store.history()), 1)

    def test_polling_timeout_saves_remaining_stars(self):
        self.runner.preflight("starstruck")
        result = self.runner.run_one("starstruck", self.store, star_wait=20)
        self.assertFalse(result["target_met"])
        self.assertEqual(self.sleeps, [15, 5])
        self.assertEqual(self.store.history()[0]["status"], "observed")

    def test_invalid_star_counts_and_api_failures_do_not_become_success(self):
        for value in (None, True, -1, "16"):
            self.primary.repo["stargazers_count"] = value
            with self.subTest(value=value), self.assertRaisesRegex(GitHubError, "star count"):
                self.runner.preflight("starstruck")
        self.primary.repo["stargazers_count"] = 15
        self.runner.preflight("starstruck")
        self.primary.read_error = GitHubError("Rate limited", 429)
        with self.assertRaises(GitHubError):
            self.runner.run_one("starstruck", self.store)
        self.assertEqual(self.store.history()[0]["status"], "failed")


class StarstruckCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)
        environment = patch.dict("os.environ", {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.primary = StarGitHub()
        self.helper = StarGitHub("bob", 2)
        self.helper.repo = self.primary.repo
        self.badge_result = {"account": "alice", "profile_url": "https://github.com/alice?tab=achievements",
                             "badges": {"starstruck": "not_visible"}, "note": "Not visible yet."}

    def invoke(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(["--env-file", str(self.path / ".env"), "--state-dir", str(self.path / "state"),
                         "--repo", "alice/lab", *args])
        return code, output.getvalue(), errors.getvalue()

    def make_runner(self, config):
        return WorkflowRunner(config, self.primary, self.helper if config.helper_token else None)

    def test_preview_needs_no_credentials_network_or_journal(self):
        with patch("getit_unlock.cli.commands.make_runner", side_effect=AssertionError("No network")):
            code, output, errors = self.invoke("run", "starstruck", "--tier", "gold", "--star-with-helper")
        self.assertEqual(code, 0, errors)
        self.assertIn("4096", output)
        self.assertIn("verified helper", output)
        self.assertFalse((self.path / "state").exists())

    def test_live_tier_run_ignores_old_local_successes_and_keeps_checking(self):
        with StateStore(self.path / "state" / "progress.sqlite3") as store:
            for _ in range(16):
                operation = store.start("alice", "alice/lab", "starstruck")
                store.finish(operation)
        with patch.dict("os.environ", {"GITHUB_TOKEN": "primary"}), patch(
                "getit_unlock.cli.commands.make_runner", side_effect=self.make_runner), patch(
                "getit_unlock.cli.commands.check_badges", return_value=self.badge_result) as badges:
            first = self.invoke("run", "starstruck", "--tier", "base", "--execute")
            second = self.invoke("run", "starstruck", "--tier", "base", "--execute")
        self.assertEqual(first[0], 0, first[2])
        self.assertEqual(second[0], 0, second[2])
        self.assertIn("15/16 received stars", second[1])
        self.assertEqual(badges.call_count, 2)
        with StateStore(self.path / "state" / "progress.sqlite3") as store:
            self.assertEqual(sum(row["status"] == "observed" for row in store.history()), 2)

    def test_helper_execution_and_badge_skip(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "primary", "HELPER_TOKEN": "helper"}), patch(
                "getit_unlock.cli.commands.make_runner", side_effect=self.make_runner), patch(
                "getit_unlock.cli.commands.check_badges", side_effect=AssertionError("Skip badge check")):
            code, output, errors = self.invoke("run", "starstruck", "--execute", "--star-with-helper", "--skip-badge-check")
        self.assertEqual(code, 0, errors)
        self.assertIn("16/16 received stars", output)
        self.assertIn("Helper star: added", output)

    def test_invalid_options_stop_before_network_or_setup(self):
        for options in (("run", "starstruck", "--count", "16"),
                        ("run", "quickdraw", "--star-with-helper"),
                        ("run", "quickdraw", "--wait-for-stars", "30"),
                        ("run", "--star-with-helper"),
                        ("run", "starstruck", "--execute", "--star-with-helper")):
            with self.subTest(options=options), patch.dict("os.environ", {"GITHUB_TOKEN": "primary"}), patch(
                    "getit_unlock.cli.commands.make_runner", side_effect=AssertionError("No network")), patch(
                    "getit_unlock.cli.commands.run_wizard", side_effect=AssertionError("No setup")):
                code, _, _ = self.invoke(*options)
            self.assertEqual(code, 1)

    def test_doctor_reports_stars_without_helper_access_or_writes(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "primary"}), patch(
                "getit_unlock.cli.commands.make_runner", side_effect=self.make_runner):
            code, output, errors = self.invoke("doctor", "--workflow", "starstruck", "--json")
        self.assertEqual(code, 0, errors)
        self.assertEqual(json.loads(output)["stars"], 15)
        self.assertEqual(self.helper.calls, [])
        self.assertTrue(all(method == "GET" for method, _, _ in self.primary.calls))

    def test_starstruck_profile_badge_can_be_verified(self):
        result = check_badges("alice", ["starstruck"], fetch=lambda _: profile("starstruck"))
        self.assertEqual(result["badges"]["starstruck"], "visible")

    def test_helper_is_only_requested_for_explicit_starring_setup(self):
        config = Config("alice/lab", "primary")
        with patch("getpass.getpass", side_effect=AssertionError("No helper prompt")):
            self.assertEqual(helper_credentials(config, "starstruck", Console()), config)
        with patch("getpass.getpass", return_value="helper"), redirect_stdout(io.StringIO()) as output:
            updated = helper_credentials(config, "starstruck", Console(), required=True)
        self.assertEqual(updated.helper_token, "helper")
        self.assertIn("No collaborator invitation", output.getvalue())

    def test_initial_tracking_setup_does_not_require_an_optional_helper(self):
        with patch("sys.stdin.isatty", return_value=True), patch(
                "getpass.getpass", side_effect=["primary"]) as secret, patch(
                "getit_unlock.cli.onboarding.Console.choose", return_value="existing"), patch(
                "getit_unlock.cli.onboarding.Console.ask", return_value="alice/lab"), redirect_stdout(io.StringIO()):
            config = ensure_credentials(Config(), self.path / ".env", "starstruck")
        self.assertEqual(config.repo, "alice/lab")
        self.assertEqual(config.helper_token, "")
        secret.assert_called_once()

    def test_wizard_offers_star_tiers_and_helper_action_without_custom_count(self):
        self.path.joinpath(".env").write_text("TARGET_REPO=alice/lab\n", encoding="utf-8")
        with patch("sys.stdin.isatty", return_value=True), patch(
                "getit_unlock.cli.commands.Console.choose", side_effect=["starstruck", "bronze", "helper", "preview"]) as choose, \
                redirect_stdout(io.StringIO()) as output:
            code = run_wizard(self.path / ".env", self.path / "state", None)
        self.assertEqual(code, 0)
        target_choices = choose.call_args_list[1].args[1]
        self.assertFalse(any(choice.value == "custom" for choice in target_choices))
        self.assertIn("128", output.getvalue())
        self.assertIn("verified helper", output.getvalue())


if __name__ == "__main__":
    unittest.main()

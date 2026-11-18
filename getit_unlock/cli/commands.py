import argparse
import json
import math
import signal
import sqlite3
import sys
import threading
import time
from contextvars import ContextVar
from dataclasses import replace
from pathlib import Path

from .. import PROJECT_NAME, __version__
from ..github.api import GitHubClient, GitHubError, WriteLimiter
from ..core.catalog import ACHIEVEMENTS, TIERS, target_for
from ..core.config import Config
from ..core.state import RunLock, StateStore
from ..workflows.runner import WorkflowRunner
from ..github.badges import check_badges
from .onboarding import ensure_credentials, helper_credentials, save_config, setup
from .ui import Choice, Console, UIOptions, UI_OPTIONS
from .preflight import (configuration_warning, launch_startup, setup_guide,
                        show_startup, show_workflow_requirements, startup_checks)
from ..workflows.cleanup import cleanup_tracked
from ..messages.templates import (MESSAGE_FILES, MESSAGE_LABELS, PR_WORKFLOWS, PREVIEW_OPERATION,
                                 message_directory, render_messages, validate_message_templates)


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Must be at least 1.")
    return number


def interval_value(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("Must be a finite, non-negative number.")
    return number


def common_arguments(parser):
    parser.add_argument("--env-file", type=Path, default=argparse.SUPPRESS, help="Configuration file (default: .env)")
    parser.add_argument("--state-dir", type=Path, default=argparse.SUPPRESS, help="Local journal directory (default: .achievement-state)")
    parser.add_argument("--repo", default=argparse.SUPPRESS, help="Target personal repository: OWNER/REPO")
    parser.add_argument("--plain", action="store_true", default=argparse.SUPPRESS,
                        help="Use plain output without colors or screen clearing")
    parser.add_argument("--no-animation", action="store_true", default=argparse.SUPPRESS,
                        help="Disable loading animations")


def badge_wait(value):
    number = int(value)
    if not 0 <= number <= 600:
        raise argparse.ArgumentTypeError("Choose between 0 and 600 seconds.")
    return number


def build_parser():
    parser = argparse.ArgumentParser(
        prog="getit-unlock",
        description=f"{PROJECT_NAME}: GitHub achievement workflows in Python. Run without a command for the menu.",
    )
    parser.add_argument("--version", action="version", version=f"{PROJECT_NAME} {__version__}")
    common_arguments(parser)
    subs = parser.add_subparsers(dest="command")
    definitions = (
        ("list", "List achievements and community-reported tier thresholds"),
        ("setup", "Configure tokens and repository interactively"),
        ("requirements", "Show local requirements and setup guidance without network access"),
        ("doctor", "Check authentication and repository access without changing GitHub"),
        ("status", "Show the local operation journal; no network access"),
        ("verify", "Check which badges are visible on your public GitHub profile"),
        ("cleanup", "Remove leftover merged workflow branches; previews by default"),
        ("run", "Preview or execute an achievement workflow"),
        ("reset-history", "Preview or reset the default branch with a backup branch"),
    )
    commands = {}
    for name, help_text in definitions:
        sub = subs.add_parser(name, help=help_text)
        common_arguments(sub)
        commands[name] = sub
    commands["list"].add_argument("--json", action="store_true")
    commands["requirements"].add_argument("--json", action="store_true")
    commands["setup"].add_argument("--workflow", choices=ACHIEVEMENTS, help="Also configure the selected workflow's helper account")
    commands["doctor"].add_argument("--workflow", choices=ACHIEVEMENTS)
    commands["doctor"].add_argument("--json", action="store_true")
    commands["status"].add_argument("--account", help="Filter by authenticated account login")
    commands["status"].add_argument("--history", action="store_true", help="Include recent operations and resource URLs")
    commands["status"].add_argument("--limit", type=positive_int, default=25)
    commands["status"].add_argument("--json", action="store_true")
    commands["verify"].add_argument("--account", help="GitHub username; defaults to target repository owner")
    commands["verify"].add_argument("--achievement", choices=ACHIEVEMENTS)
    commands["verify"].add_argument("--wait", type=badge_wait, default=0, help="Poll public profile for up to this many seconds (max 600)")
    commands["verify"].add_argument("--json", action="store_true")
    cleanup_mode = commands["cleanup"].add_mutually_exclusive_group()
    cleanup_mode.add_argument("--execute", action="store_true", help="Delete the verified merged workflow branches")
    cleanup_mode.add_argument("--dry-run", action="store_true", help="Only preview the cleanup (default)")
    commands["cleanup"].add_argument("--json", action="store_true")
    run = commands["run"]
    run.add_argument("achievement", choices=ACHIEVEMENTS, nargs="?", help="Omit to choose interactively")
    amount = run.add_mutually_exclusive_group()
    amount.add_argument("--count", type=positive_int, help="Number of new operations (default: 1)")
    amount.add_argument("--tier", choices=TIERS, help="Reach this threshold using locally recorded successes (live received stars for Starstruck)")
    mode = run.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="Perform the displayed GitHub writes")
    mode.add_argument("--dry-run", action="store_true", help="Preview without credentials or network (the default)")
    run.add_argument("--interval", type=interval_value, default=10.0, help="Seconds between operations; API writes are also paced (default: 10)")
    run.add_argument("--coauthor-name")
    run.add_argument("--coauthor-email")
    run.add_argument("--category-id")
    for field in MESSAGE_FILES:
        run.add_argument("--" + field.replace("_", "-"),
                         help=f"{MESSAGE_LABELS[field]} template; overrides {field.upper()} in .env (PR workflows only)")
    run.add_argument("--wait-for-badge", type=badge_wait, default=0, help="After successful operations, poll for public badge visibility (max 600 seconds)")
    run.add_argument("--skip-badge-check", action="store_true", help="Only verify API operations; skip the public profile check")
    run.add_argument("--wait-for-stars", type=badge_wait, default=0,
                     help="Starstruck: poll received stars for up to this many seconds (max 600)")
    run.add_argument("--star-with-helper", action="store_true",
                     help="Starstruck: use HELPER_TOKEN to add one star if the helper has not already starred")
    reset = commands["reset-history"]
    reset.add_argument("--execute", action="store_true")
    reset.add_argument("--expected-head", help="Full SHA from a fresh reset-history preview")
    return parser


def table(headers, rows):
    Console().table(headers, rows)


def list_achievements(as_json=False):
    data = [{"id": a.slug, "name": a.name, "thresholds": a.thresholds,
             "description": a.description, "helper_required": a.helper} for a in ACHIEVEMENTS.values()]
    if as_json:
        print(json.dumps(data, indent=2))
        return
    Console().panel("THE ACHIEVEMENT COLLECTION", ["Pick a badge and a target tier from the interactive menu."])
    table(["Achievement", "Base / Bronze / Silver / Gold", "Requires"], [
        [a.slug, " / ".join(map(str, a.thresholds)),
         "Helper account" if a.helper else "Primary account"]
        for a in ACHIEVEMENTS.values()
    ])
    print("\nThresholds are community-reported. GitHub decides when and whether to award badges.")


def make_runner(config):
    limiter = WriteLimiter()
    primary = GitHubClient(config.token, limiter=limiter)
    helper = GitHubClient(config.helper_token, limiter=limiter) if config.helper_token else None
    runner = WorkflowRunner(config, primary, helper)
    primary.report = lambda message: runner.report(message)
    if helper:
        helper.report = lambda message: runner.report(message)
    return runner


def cleanup_repository(args, config, state_dir):
    path = state_dir / "progress.sqlite3"
    if not path.exists():
        print("[]" if args.json else "No recorded workflow branches to clean up.")
        return 0
    config.validate(credentials=True)
    runner = make_runner(config)
    runner.preflight()
    with RunLock(state_dir), StateStore(path) as store:
        if args.json:
            results = cleanup_tracked(runner, store, execute=args.execute)
            print(json.dumps(results, indent=2))
        else:
            with Console().activity("Checking recorded branches against GitHub") as activity:
                runner.report = activity.update
                results = cleanup_tracked(runner, store, execute=args.execute)
            if results:
                for result in results:
                    Console().say(f"{result['status'].upper()}: {result['branch']} / {result['reason']}")
            else:
                print("No recorded workflow branches to clean up.")
            if not args.execute:
                print("Preview only. Add --execute to remove branches marked READY.")
    return 1 if any(result["status"] == "error" for result in results) else 0


def show_status(args, config, state_dir):
    path = state_dir / "progress.sqlite3"
    if not path.exists():
        data = {"summary": [], "history": []}
    else:
        with StateStore(path) as store:
            data = {"summary": store.summary(account=args.account, repo=config.repo),
                    "history": store.history(account=args.account, repo=config.repo, limit=args.limit) if args.history else []}
    if args.json:
        print(json.dumps(data, indent=2))
        return
    print("Local workflow records (these are not verified GitHub badge counts).")
    if not data["summary"]:
        print("No recorded operations.")
        return
    table(["Account", "Repository", "Workflow", "Status", "Count"], [list(row.values()) for row in data["summary"]])
    for row in data["history"]:
        print(f"\n{row['id']}  {row['workflow']}  {row['status']}  {row['started_at']}")
        print(json.dumps(row["detail"], indent=2))


def show_plan(args, config):
    console = Console()
    achievement = ACHIEVEMENTS[args.achievement]
    config.validate()
    if args.achievement == "starstruck":
        tier = args.tier or "base"
        amount = f"check live received stars against {target_for('starstruck', tier)} ({tier})"
    elif args.tier:
        target = target_for(args.achievement, args.tier)
        amount = f"up to {target} total locally recorded successes ({args.tier}); account checked at execution"
    else:
        amount = f"{args.count or 1} new operation(s)"
    console.panel(f"{achievement.name.upper()} / {config.repo}", [f"Plan: {amount}"])
    for number, step in enumerate(achievement.steps, 1):
        console.say(f"  {number:02}. {step}")
    if args.achievement == "starstruck":
        console.say("Stars must come from other users; each account can contribute one star to this repository.", "muted")
        if args.star_with_helper:
            console.say("Use the verified helper to star this repository once; an existing star is kept.", "menu")
        if args.wait_for_stars:
            console.say(f"Poll received stars for up to {args.wait_for_stars} seconds.", "muted")
    if achievement.helper:
        console.say("Requires a token from a different helper account.", "gold")
    if args.achievement == "pair-extraordinaire":
        console.say("Co-author identity is resolved from the helper; GitHub must recognize both commit authors.", "muted")
    if args.achievement in PR_WORKFLOWS:
        messages = render_messages(config, args.achievement, PREVIEW_OPERATION)
        console.say(f"\nMessage files: {message_directory(config)}", "muted")
        console.say("Messages are selected automatically in file order using saved progress.", "muted")
        console.say("Message preview / first entries and sample ID; execution uses the next saved position.", "menu")
        for field, message in messages.items():
            console.say(f"  {MESSAGE_LABELS[field]}:", "menu")
            for line in config.redact(message).splitlines():
                console.say(f"    {line}")


def display_badges(result):
    console = Console()
    console.panel("GITHUB / badge visibility", [result["account"], result["profile_url"]])
    labels = {"visible": ("VISIBLE ON GITHUB", "green"), "not_visible": ("NOT VISIBLE YET", "gold"), "unknown": ("UNKNOWN", "muted")}
    for slug, status in result["badges"].items():
        label, color = labels[status]
        console.say(f"  {ACHIEVEMENTS[slug].name:<22} {label}", color)
    console.say(result["note"], "muted")


def verify_badges(args, config):
    account = args.account or (config.repo.split("/")[0] if config.repo else "")
    if not account:
        raise ValueError("Use --account YOUR_USERNAME or configure a target repository.")
    selected = [args.achievement] if args.achievement else None
    if args.json:
        result = check_badges(account, selected, wait=args.wait)
        print(json.dumps(result, indent=2))
    else:
        with Console().activity("Checking public GitHub badges") as activity:
            result = check_badges(account, selected, wait=args.wait, report=activity.update)
        display_badges(result)
    return 0 if all(status == "visible" for status in result["badges"].values()) else 3


def execute_run(args, config, state_dir):
    console = Console()
    show_plan(args, config)
    if not args.execute:
        print("\nPreview only. Add --execute to perform these operations on GitHub.")
        return
    config.validate(args.achievement, credentials=True)
    runner = make_runner(config)
    with console.activity("Checking workflow prerequisites") as activity:
        runner.report = activity.update
        info = (runner.preflight(args.achievement, star_with_helper=args.star_with_helper)
                if args.achievement == "starstruck" else runner.preflight(args.achievement))
    with RunLock(state_dir), StateStore(state_dir / "progress.sqlite3") as store:
        starstruck = args.achievement == "starstruck"
        if starstruck:
            count = 1
            print(f"\nAuthenticated as {info['account']}. {info['stars']} live received stars; checking progress.")
        else:
            completed = store.count(info["account"], config.repo, args.achievement)
            count = max(0, target_for(args.achievement, args.tier) - completed) if args.tier else (args.count or 1)
            print(f"\nAuthenticated as {info['account']}. {completed} recorded successes; {count} operation(s) to run.")
        if info.get("helper"):
            console.say(f"Helper verified: {info['helper']}", "green")
        console.progress(0, count)
        for index in range(count):
            if index:
                with console.activity(f"Next operation in {args.interval:g} seconds"):
                    time.sleep(args.interval)
            with console.activity(f"Operation {index + 1} of {count}") as activity:
                runner.report = activity.update
                result = (runner.run_one(args.achievement, store, star_tier=args.tier or "base",
                                         star_wait=args.wait_for_stars, star_with_helper=args.star_with_helper)
                          if starstruck else runner.run_one(args.achievement, store))
            if starstruck:
                console.say(f"  {result['stars']}/{result['target']} received stars ({result['tier']}); "
                            f"{result['remaining']} more needed.", "green" if result["target_met"] else "gold")
                if result["helper_star"] != "not_requested":
                    console.say("Helper star: " + result["helper_star"].replace("_", " "))
                console.say(f"  Repository: {result['url']}", "cyan")
            else:
                console.say(f"  VERIFIED  {result['url']}", "green")
            console.progress(index + 1, count)
            if result.get("warning"):
                print(result["warning"], file=sys.stderr)
            if result.get("cleanup", {}).get("rate_limited"):
                raise GitHubError("The completed operation was saved. Stopping because cleanup hit a rate limit; retry cleanup after GitHub's wait time.")
        console.say("Star progress snapshot saved; GitHub decides badge awards." if starstruck
                    else "Workflow results verified and saved.", "green")
    if not args.skip_badge_check:
        with console.activity("Checking whether GitHub displays the badge") as activity:
            result = check_badges(info["account"], [args.achievement], wait=args.wait_for_badge, report=activity.update)
        display_badges(result)
    else:
        console.say("Public badge check skipped. Run verify when you want to check your profile.", "muted")


def reset_history(args, config, state_dir):
    config.validate(credentials=True)
    runner = make_runner(config)
    info = runner.preflight("reset-history")
    head = runner.head()
    print(f"Repository: {config.repo}\nDefault branch: {info['default_branch']}\nCurrent head: {head}")
    print("This creates a backup branch, then replaces default-branch history with one commit keeping the same files.")
    print("PRs, issues, discussions, and other branches remain. Stop other writers while resetting history.")
    if not args.execute:
        print(f"\nPreview only. To reset, add --execute --expected-head {head}")
        return
    if not args.expected_head:
        raise ValueError("Reset requires --expected-head with the full SHA from a fresh preview.")
    with RunLock(state_dir), StateStore(state_dir / "progress.sqlite3") as store:
        result = runner.reset_history(args.expected_head, store)
    print(f"History reset. Backup: {result['backup_branch']}\nNew head: {result['new_sha']}")


def run_wizard(env_file, state_dir, repo=None):
    if not sys.stdin.isatty():
        raise ValueError("Choose an achievement ID for scripted runs, or open the interactive menu in a terminal.")
    console = Console()
    console.session()
    workflow = console.choose("01 / Choose a badge", [
        Choice(a.slug, a.name, "Received stars" if a.slug == "starstruck" else
               ("Helper account" if a.helper else "Solo workflow"))
        for a in ACHIEVEMENTS.values()
    ] + [Choice("back", "Back")])
    if workflow == "back":
        return 0
    achievement = ACHIEVEMENTS[workflow]
    config = Config.load(env_file, repo=repo)
    console.session()
    show_workflow_requirements(workflow, config, console)
    choices = [Choice(tier, tier.title(), f"{achievement.thresholds[index]} "
                      + ("received stars" if workflow == "starstruck" else "total recorded successes"))
               for tier, index in TIERS.items() if index < len(achievement.thresholds)]
    if workflow != "starstruck":
        choices.append(Choice("custom", "Custom count", "New operations"))
    target = console.choose("02 / Choose a level", choices + [Choice("back", "Back")])
    if target == "back":
        return 0
    amount = ["--tier", target]
    if target == "custom":
        def validate_count(value):
            if not value.isdigit() or int(value) < 1:
                raise ValueError("Enter a positive whole number.")
        amount = ["--count", console.ask("New operations", "1", validator=validate_count)]
    if workflow == "starstruck":
        console.session()
        star_action = console.choose("Starstruck automation", [
            Choice("track", "Track received stars", "Read current progress and check the badge"),
            Choice("helper", "Add a helper star and track", "A different account contributes one star"),
            Choice("back", "Back"),
        ])
        if star_action == "back":
            return 0
        if star_action == "helper":
            amount.append("--star-with-helper")
    if not config.repo:
        # A preview remains available without asking for tokens or creating a repository.
        from ..core.config import validate_repo
        config = replace(config, repo=console.ask("Repository for this plan (OWNER/REPO)",
                                                 required=True, validator=validate_repo))
    common = ["--env-file", str(env_file), "--state-dir", str(state_dir), "--repo", config.repo]
    command = common + ["run", workflow, *amount]
    preview = build_parser().parse_args(command)
    console.session()
    show_plan(preview, config)
    action = console.choose("03 / Review your plan", [
        Choice("execute", "Run this workflow", "Check received stars and badge visibility" if workflow == "starstruck"
               else "Use the predefined messages and verify the workflow"),
        Choice("preview", "Keep as preview", "No GitHub changes"),
        Choice("back", "Back"),
    ], default=1)
    if action == "execute":
        console.session()
        return main(command + ["--execute"])
    console.say("Preview only. Your plan has not been executed.", "muted")
    return 0


def interactive(env_file, state_dir, repo):
    if not sys.stdin.isatty():
        build_parser().print_help()
        return 0
    console = Console()
    config = Config.load(env_file, repo=repo)
    launch_startup(config, env_file, state_dir, console)
    common = ["--env-file", str(env_file), "--state-dir", str(state_dir)]
    if repo:
        common.extend(["--repo", repo])
    while True:
        config = Config.load(env_file, repo=repo)
        summary = []
        if (state_dir / "progress.sqlite3").exists():
            with StateStore(state_dir / "progress.sqlite3") as store:
                summary = store.summary(repo=config.repo)
        completed = sum(row["count"] for row in summary if row["status"] == "completed")
        pending = sum(row["count"] for row in summary if row["status"] not in {"completed", "observed"})
        console.banner(config.repo, completed, pending)
        choice = console.choose("MAIN MENU", [
            Choice("run", "Unlock an achievement", "Choose a badge and target tier"),
            Choice("verify", "Check GitHub badges", "Read your public profile"),
            Choice("status", "Your progress", "Completed operations and anything to inspect"),
            Choice("list", "Browse achievements", "Requirements and tiers"),
            Choice("setup", "Connect or create a repository", "Account and repository setup"),
            Choice("doctor", "Check connection", "Validate prerequisites for your chosen workflow"),
            Choice("requirements", "Requirements and advanced tools", "Setup guide and history-reset preview"),
            Choice("cleanup", "Clean up merged branches", "Preview leftover workflow branches"),
            Choice("back", "Exit"),
        ], warning=configuration_warning(config))
        if choice == "back":
            return 0
        if choice != "run":
            console.session()
        if choice == "run":
            try:
                run_wizard(env_file, state_dir, repo)
            except ValueError as exc:
                console.say(config.redact(str(exc)), "gold")
        elif choice == "status":
            main(common + ["status", "--history"])
        elif choice == "cleanup":
            if main(common + ["cleanup"]) == 0:
                action = console.choose("CLEANUP", [Choice("execute", "Remove verified merged branches"), Choice("back", "Back")])
                if action == "execute":
                    console.session()
                    main(common + ["cleanup", "--execute"])
        elif choice == "setup":
            section = console.choose("ACCOUNT SETTINGS", [
                Choice("primary", "Primary account and repository"),
                Choice("pair-extraordinaire", "Pair Extraordinaire helper", "Configure or replace its token"),
                Choice("yolo", "YOLO helper", "Collaborator token"),
                Choice("galaxy-brain", "Galaxy Brain helper", "Collaborator token"),
                Choice("starstruck", "Starstruck helper", "Optional token to contribute one star"),
                Choice("back", "Back"),
            ])
            if section != "back":
                console.session()
                main(common + ["setup"] + ([] if section == "primary" else ["--workflow", section]))
        elif choice == "doctor":
            workflow = console.choose("CHECK CONNECTION / REQUIREMENTS", [
                Choice("general", "Primary account and repository", "Read-only connection check"),
                *[Choice(a.slug, a.name, "Check this workflow's prerequisites") for a in ACHIEVEMENTS.values()],
                Choice("back", "Back"),
            ])
            if workflow == "back":
                continue
            console.session()
            main(common + ["doctor"] + ([] if workflow == "general" else ["--workflow", workflow]))
        elif choice == "requirements":
            section = console.choose("REQUIREMENTS AND ADVANCED TOOLS", [
                Choice("requirements", "Local requirements and setup guide"),
                Choice("reset-history", "Preview history reset", "Preserve files and create a backup if executed"),
                Choice("back", "Back"),
            ])
            if section == "back":
                continue
            console.session()
            main(common + [section])
        elif choice == "verify" and not config.repo:
            account = console.ask("GitHub username", required=True)
            main(common + ["verify", "--account", account])
        else:
            main(common + [choice])
        console.pause()


def _dispatch(args):
    env_file = getattr(args, "env_file", Path(".env"))
    state_dir = getattr(args, "state_dir", Path(".achievement-state"))
    repo = getattr(args, "repo", None)
    config = Config()
    try:
        if args.command is None:
            return interactive(env_file, state_dir, repo)
        if args.command == "list":
            list_achievements(args.json)
            return 0
        config = Config.load(env_file, repo=repo)
        if args.command == "setup":
            setup(config, env_file, args.workflow)
        elif args.command == "requirements":
            if args.json:
                print(json.dumps([dict(zip(("requirement", "status", "detail"), row))
                                  for row in startup_checks(config, env_file, state_dir)], indent=2))
            else:
                show_startup(config, env_file, state_dir, Console())
                setup_guide(Console())
        elif args.command == "status":
            show_status(args, config, state_dir)
        elif args.command == "verify":
            return verify_badges(args, config)
        elif args.command == "cleanup":
            return cleanup_repository(args, config, state_dir)
        elif args.command == "doctor":
            if not args.json:
                config = ensure_credentials(config, env_file, args.workflow, allow_create=False)
            config.validate(args.workflow, credentials=True)
            runner = make_runner(config)
            if args.json:
                info = runner.preflight(args.workflow)
            else:
                if args.workflow:
                    show_workflow_requirements(args.workflow, config, Console())
                with Console().activity("Checking GitHub connection and repository prerequisites") as activity:
                    runner.report = activity.update
                    info = runner.preflight(args.workflow)
            print(json.dumps(info, indent=2) if args.json else
                  f"Connected as {info['account']} to {info['repo']}. Default branch: {info['default_branch']}.")
            if not args.json:
                if args.workflow == "starstruck":
                    print(f"Received stars: {info['stars']}.")
                print("Read-only checks passed. Branch rules and exact write permissions are enforced by GitHub when executing.")
        elif args.command == "run":
            if args.achievement is None:
                if (args.execute or args.dry_run or args.count is not None or args.tier
                        or args.coauthor_name or args.coauthor_email or args.category_id
                        or args.wait_for_badge or args.skip_badge_check or args.interval != 10
                        or args.wait_for_stars or args.star_with_helper
                        or any(getattr(args, field) is not None for field in MESSAGE_FILES)):
                    raise ValueError("Specify an achievement ID when using run options; use plain run for the interactive chooser.")
                return run_wizard(env_file, state_dir, repo)
            if args.achievement == "starstruck" and args.count is not None:
                raise ValueError("Starstruck uses live received stars. Choose --tier instead of --count.")
            if args.achievement != "starstruck" and (args.wait_for_stars or args.star_with_helper):
                raise ValueError("--wait-for-stars and --star-with-helper apply only to Starstruck.")
            overrides = {key: getattr(args, arg) for key, arg in (
                ("coauthor_name", "coauthor_name"), ("coauthor_email", "coauthor_email"), ("category_id", "category_id")
            ) if getattr(args, arg) is not None}
            message_overrides = {field: getattr(args, field) for field in MESSAGE_FILES
                                 if getattr(args, field) is not None}
            if message_overrides and args.achievement not in PR_WORKFLOWS:
                raise ValueError("Custom PR messages apply to Pull Shark, Pair Extraordinaire, and YOLO.")
            overrides.update(message_overrides)
            config = replace(config, **overrides)
            if args.achievement in PR_WORKFLOWS:
                validate_message_templates(config, args.achievement)
            if args.execute:
                config = ensure_credentials(config, env_file, args.achievement)
                if args.star_with_helper:
                    if sys.stdin.isatty():
                        updated = helper_credentials(config, "starstruck", Console(), required=True)
                        if updated != config:
                            save_config(updated, env_file)
                        config = updated
                    if not config.helper_token:
                        raise ValueError("--star-with-helper requires HELPER_TOKEN for a different GitHub account.")
            execute_run(args, config, state_dir)
        elif args.command == "reset-history":
            reset_history(args, config, state_dir)
        return 0
    except (ValueError, GitHubError, OSError, sqlite3.Error) as exc:
        print("Error: " + config.redact(str(exc)), file=sys.stderr)
        return 1


_SESSION_DEPTH = ContextVar("getit_session_depth", default=0)


class Terminated(KeyboardInterrupt):
    """A termination request follows the same journal and terminal cleanup path."""


def main(argv=None):
    args = build_parser().parse_args(argv)
    depth = _SESSION_DEPTH.get()
    depth_token = _SESSION_DEPTH.set(depth + 1)
    previous_options = UI_OPTIONS.get()
    options_token = UI_OPTIONS.set(UIOptions(getattr(args, "plain", previous_options.plain),
                                            getattr(args, "no_animation", previous_options.no_animation)))
    machine_output = getattr(args, "json", False)
    human_session = (args.command is None or args.command == "setup"
                     or (args.command == "run" and args.achievement is None))
    farewell = depth == 0 and sys.stdin.isatty() and human_session and not machine_output
    previous_handler = None
    handles_signal = depth == 0 and threading.current_thread() is threading.main_thread()
    if handles_signal:
        previous_handler = signal.getsignal(signal.SIGTERM)
        def terminate(signum, frame):
            raise Terminated()
        signal.signal(signal.SIGTERM, terminate)
    try:
        return _dispatch(args)
    except (KeyboardInterrupt, EOFError) as exc:
        if depth:
            raise  # Exit the entire session, including nested workflows and prompts.
        farewell = sys.stdin.isatty() and not machine_output
        print("\nStopped. Any started operation is recorded in the local journal. Inspect status --history before retrying.",
              file=sys.stderr)
        return 143 if isinstance(exc, Terminated) else 130
    finally:
        if handles_signal:
            signal.signal(signal.SIGTERM, previous_handler)
        try:
            if farewell:
                Console().goodbye()
        finally:
            UI_OPTIONS.reset(options_token)
            _SESSION_DEPTH.reset(depth_token)

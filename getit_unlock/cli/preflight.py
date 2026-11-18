"""Local launch checks and workflow requirements; no writes or network calls."""
import os
import platform
import sys
from importlib.metadata import version

from ..core.config import validate_repo
from ..core.catalog import ACHIEVEMENTS


WORKFLOW_REQUIREMENTS = {
    "pull-shark": ("Primary account owns the target repository.",
                   "Repository has at least one commit and allows merge commits.",
                   "Token needs Contents and Pull requests read/write access. No helper needed."),
    "pair-extraordinaire": ("Primary repository has a commit and allows merge commits.",
                           "A different helper account supplies co-author identity; no invitation needed.",
                           "Primary needs Contents and Pull requests read/write; helper needs profile access."),
    "quickdraw": ("Primary account owns the target repository; Issues must be enabled.",
                  "Primary token needs Issues read/write access. No helper needed."),
    "yolo": ("Primary repository has a commit and allows merge commits.",
             "Different helper account has accepted a collaborator invitation to the target.",
             "Use a classic repo-scoped helper token. Required review rules can block this workflow."),
    "galaxy-brain": ("Enable Discussions and a Question and Answer category in the target repository.",
                     "Different helper account has accepted a collaborator invitation to the target.",
                     "Primary needs Discussions read/write; use a classic repo-scoped helper token."),
    "starstruck": ("Target is a public repository owned by the primary account.",
                   "Stars come from other users. Each account contributes at most one star.",
                   "Helper is optional; starring needs classic public_repo or account Starring read/write."),
}


def platform_name():
    if os.getenv("TERMUX_VERSION") or "com.termux" in os.getenv("PREFIX", ""):
        return "Android / Termux"
    return platform.system()


def startup_checks(config, env_file, state_dir):
    source = str(env_file) if env_file.exists() else "No .env file; shell variables can supply configuration"
    try:
        validate_repo(config.repo)
        repo_status, repo_detail = "PRESENT", config.repo
    except ValueError as exc:
        repo_status, repo_detail = "NEEDS SETUP", str(exc)
    journal = state_dir / "progress.sqlite3"
    return [
        ("Runtime", "READY", f"Python {sys.version.split()[0]} / {platform_name()}"),
        ("Terminal libraries", "READY", f"Rich {version('rich')}"),
        ("Configuration", "FOUND" if env_file.exists() else "INFO", source),
        ("Primary token", "PRESENT" if config.token else "NEEDS SETUP",
         "Hidden; checked against GitHub only when you request a connection check or execution" if config.token
         else "Set GITHUB_TOKEN (or GH_TOKEN) in .env or use guided setup"),
        ("Target repository", repo_status, repo_detail),
        ("Helper token", "PRESENT" if config.helper_token else "OPTIONAL",
         "Different account required for Pair Extraordinaire, YOLO and Galaxy Brain"),
        ("Saved progress", "FOUND" if journal.exists() else "NEW", str(journal)),
    ]


def show_startup(config, env_file, state_dir, console):
    console.heading("STARTUP / local requirements")
    for name, status, detail in startup_checks(config, env_file, state_dir):
        color = "red" if status == "NEEDS SETUP" else "green" if status in {"READY", "PRESENT", "FOUND"} else "cyan"
        console.notice(f"{name} : {status}", marker="!" if color == "red" else "+", color=color)
        console.say("     " + detail, "muted")
    console.say("Local settings only. Check connection validates GitHub access.", "muted")
    console.say("Solo: Pull Shark, Quickdraw. Helper: Pair Extraordinaire, YOLO, Galaxy Brain.", "muted")
    console.say("Starstruck tracks received stars; a helper star is optional.", "muted")


def show_workflow_requirements(workflow, config, console):
    achievement = ACHIEVEMENTS[workflow]
    lines = list(WORKFLOW_REQUIREMENTS[workflow])
    if achievement.helper:
        lines.append("Helper token: " + ("present; identity/access checked before execution." if config.helper_token
                                         else "missing; guided setup requests it before execution."))
    lines.append("Preview needs a repository name. Execution checks credentials and repository requirements first.")
    console.panel(achievement.name.upper() + " / requirements", lines, "gold")


def setup_guide(console):
    console.panel("SETUP GUIDE", [
        "1. Create a primary token for the account that owns your target repository.",
        "2. Save GITHUB_TOKEN and TARGET_REPO=OWNER/REPO in your local .env, or select guided setup.",
        "3. Add HELPER_TOKEN only for a workflow that needs a different account.",
        "4. For YOLO/Galaxy Brain, the helper accepts a collaborator invitation first.",
        "5. Run Check connection for the selected workflow before executing.",
        "Tokens stay hidden. Shell variables take precedence over the chosen .env file.",
    ])
    console.link("Create a token", "https://github.com/settings/tokens")
    console.link("Create a repository", "https://github.com/new")

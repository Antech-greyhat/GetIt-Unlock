"""Local launch checks and workflow requirements; no writes or network calls."""
import os
import platform
import sys
import time
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


def startup_probes(config, env_file, state_dir):
    """Defer each local check until its loading message is on screen."""
    def repository():
        try:
            validate_repo(config.repo)
            return "PRESENT", config.repo
        except ValueError as exc:
            return "NEEDS SETUP", str(exc)

    def token(value, field, *, required=False):
        if not value:
            return ("NEEDS SETUP", f"Set {field} in .env or use guided setup") if required else (
                "OPTIONAL", "Different account required for Pair Extraordinaire, YOLO and Galaxy Brain")
        if any(character.isspace() for character in value):
            return "NEEDS SETUP", f"Remove whitespace from {field}"
        return "PRESENT", "Hidden; identity/access checked only when requested"

    return [
        ("Runtime", "Checking Python runtime...",
         lambda: ("READY", f"Python {sys.version.split()[0]} / {platform_name()}")),
        ("Terminal libraries", "Checking terminal requirements...", lambda: ("READY", f"Rich {version('rich')}")),
        ("Configuration", "Checking local configuration...",
         lambda: ("FOUND", str(env_file)) if env_file.exists() else (
             "INFO", "No .env file; shell variables can supply configuration")),
        ("Primary token", "Checking credentials...", lambda: token(config.token, "GITHUB_TOKEN", required=True)),
        ("Target repository", "Checking target repository...", repository),
        ("Helper token", "Checking optional helper credentials...", lambda: token(config.helper_token, "HELPER_TOKEN")),
        ("Saved progress", "Checking saved progress...",
         lambda: ("FOUND" if (state_dir / "progress.sqlite3").exists() else "NEW", str(state_dir / "progress.sqlite3"))),
    ]


def startup_checks(config, env_file, state_dir):
    return [(name, *probe()) for name, _, probe in startup_probes(config, env_file, state_dir)]


def launch_startup(config, env_file, state_dir, console, *, duration=3.0, sleep=time.sleep, clock=time.monotonic):
    """A separate, timed loading screen; explicit requirements commands stay static."""
    console.clear()
    console.heading("STARTUP / local requirements")
    probes = startup_probes(config, env_file, state_dir)
    duration = duration if console.animate else 0
    started = clock()
    for index, (name, message, probe) in enumerate(probes, 1):
        with console.loading(message):
            status, _ = probe()
            remaining = started + duration * index / (len(probes) + 1) - clock()
            if remaining > 0:
                sleep(remaining)
        color = "gold" if status == "NEEDS SETUP" else "green" if status in {"READY", "PRESENT", "FOUND"} else "info"
        console.notice(f"{name} : {status}", marker="!" if color == "gold" else "+", color=color)
    console.notice("Checks complete. Opening the tool...", marker="-", color="info")
    remaining = started + duration - clock()
    if remaining > 0:
        sleep(remaining)


def configuration_warning(config):
    """Only requirements that need attention; never include token values."""
    needed = []
    if not config.token:
        needed.append("GITHUB_TOKEN (or GH_TOKEN)")
    elif any(character.isspace() for character in config.token):
        needed.append("GITHUB_TOKEN without whitespace")
    try:
        validate_repo(config.repo)
    except ValueError:
        needed.append("TARGET_REPO=OWNER/REPO")
    if config.helper_token and any(character.isspace() for character in config.helper_token):
        needed.append("HELPER_TOKEN without whitespace")
    return "Required: " + ", ".join(needed) + ". Set later via 05 / setup." if needed else ""


def show_startup(config, env_file, state_dir, console):
    console.heading("STARTUP / local requirements")
    for name, status, detail in startup_checks(config, env_file, state_dir):
        color = "gold" if status == "NEEDS SETUP" else "green" if status in {"READY", "PRESENT", "FOUND"} else "info"
        console.notice(f"{name} : {status}", marker="!" if color == "gold" else "+", color=color)
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
    console.panel(achievement.name.upper() + " / requirements", lines)


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

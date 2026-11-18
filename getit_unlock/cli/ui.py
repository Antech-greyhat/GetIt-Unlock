"""ASCII artwork, bracketed numbered menus, and accessible Rich output."""
import math
import os
import re
import sys
import time
from contextvars import ContextVar
from dataclasses import dataclass

from rich import box
from rich.console import Console as RichConsole
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
from rich.text import Text
from rich.table import Table

from .. import PROJECT_NAME, __version__
from .brand import (COMPACT_MARK, DEVELOPER, DISCLAIMER, FAREWELL, FORK_URL,
                    PROFILE_URL, REPOSITORY_URL, TINY_MARK, WORDMARK)


@dataclass(frozen=True)
class UIOptions:
    plain: bool = False
    no_animation: bool = False


UI_OPTIONS = ContextVar("getit_ui_options", default=UIOptions())


def enable_terminal():
    return sys.stdout.isatty() and os.getenv("TERM") != "dumb"


def clean(value):
    """Keep terminal control sequences out of remote/user-provided labels."""
    value = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", str(value))
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", value)


@dataclass(frozen=True)
class Choice:
    value: str
    label: str
    detail: str = ""


class Console:
    COLORS = {"cyan": "cyan", "gold": "yellow", "green": "green",
              "red": "red", "blue": "blue", "muted": "dim", "bold": "bold"}

    def __init__(self):
        options = UI_OPTIONS.get()
        self.terminal = enable_terminal() and not options.plain
        self.color = self.terminal and "NO_COLOR" not in os.environ
        self.animate = self.terminal and not options.no_animation
        self.rich = RichConsole(force_terminal=self.terminal, no_color=not self.color,
                                markup=False, highlight=False)

    @property
    def width(self):
        return max(12, min(100, self.rich.size.width - 2))

    def say(self, text="", color=None):
        self.rich.print(Text(clean(text), style=self.COLORS.get(color, "")))

    def bracket(self, label, color="red"):
        text = Text("[", style=self.COLORS[color])
        text.append(clean(label), style="white")
        text.append("]", style=self.COLORS[color])
        return text

    def notice(self, text, *, marker="+", color="green"):
        line = Text(" ")
        line.append_text(self.bracket(marker, color))
        line.append(" " + clean(text), style=self.COLORS.get(color, "cyan"))
        self.rich.print(line, overflow="fold")

    def heading(self, title):
        self.say()
        text = Text(" ")
        text.append_text(self.bracket("::"))
        text.append(" " + clean(title) + " ", style="bold yellow")
        text.append_text(self.bracket("::"))
        self.rich.print(text, overflow="fold")
        self.say()

    def clear(self):
        if self.terminal and sys.stdin.isatty():
            self.rich.clear()

    def link(self, label, url):
        text = Text(" ")
        text.append_text(self.bracket("-", "green"))
        text.append(" " + clean(label) + ": ", style="cyan")
        text.append(url, style=f"cyan link {url}")
        self.rich.print(text, overflow="fold")

    def panel(self, title, lines=(), color="cyan"):
        self.heading(title)
        for line in lines:
            self.say(" " + clean(line), color)

    def table(self, headers, rows):
        rows = [[clean(value) for value in row] for row in rows]
        if self.width < 68:
            for row in rows:
                self.panel(row[0], [f"{header}: {value}" for header, value in zip(headers[1:], row[1:])])
            return
        table = Table(box=box.SIMPLE if self.terminal else box.ASCII, width=self.width,
                      header_style="bold bright_cyan", padding=(0, 1))
        for header in headers:
            table.add_column(clean(header), overflow="fold")
        for row in rows:
            table.add_row(*(Text(value) for value in row))
        self.rich.print(table)

    def masthead(self, *, disclaimer=False):
        self.say()
        if self.width >= max(map(len, WORDMARK.splitlines())):
            mark, style = WORDMARK, "bold yellow"
        elif self.width >= max(map(len, COMPACT_MARK.splitlines())):
            mark, style = COMPACT_MARK, "bold blue"
        else:
            mark, style = TINY_MARK, "bold blue"
        self.rich.print(Text(mark.rstrip("\n"), style=style), overflow="fold")
        version = Text(" " * max(1, min(self.width, max(map(len, mark.splitlines()))) - 18))
        version.append("Version : ", style="red")
        version.append(__version__, style="yellow")
        self.rich.print(version)
        self.say()
        self.link(f"Tool created by {DEVELOPER}", PROFILE_URL)
        if mark != WORDMARK:
            self.say("     " + PROJECT_NAME.upper(), "muted")
        if disclaimer:
            self.panel("EDUCATIONAL USE", [DISCLAIMER], "gold")

    def banner(self, repo="", completed=0, pending=0, configured=False):
        self.clear()
        self.masthead()
        self.say()
        self.notice("Repository : " + (repo or "setup needed"), color="cyan")
        self.notice("Primary token : " + ("configured; check connection to verify" if configured else "missing"),
                    marker="+" if configured else "!", color="green" if configured else "red")
        self.notice(f"Completed : {completed}  /  To inspect : {pending}", color="cyan")

    def goodbye(self):
        self.clear()
        self.masthead()
        self.link("Star", REPOSITORY_URL)
        self.link("Fork", FORK_URL)
        self.say()
        self.rich.print(Text(FAREWELL, style="bold black on bright_cyan"))

    def choose(self, title, choices, *, default=0):
        if not choices or not 0 <= default < len(choices):
            raise ValueError("A menu needs choices and a valid default.")
        self.heading(title)
        numbered = [(index, choice) for index, choice in enumerate(choices, 1) if choice.value != "back"]
        back_label = next((choice.label for choice in choices if choice.value == "back"), "Back")

        def option(index, choice):
            text = Text(" ")
            text.append_text(self.bracket(f"{index:02}"))
            text.append(" " + clean(choice.label), style="yellow")
            return text

        cell_width = max((option(index, choice).cell_len for index, choice in numbered), default=1)
        columns = min(3, (self.width + 3) // (cell_width + 3)) if len(numbered) >= 6 else 1
        if columns > 1:
            menu = Table.grid(padding=(0, 3))
            for _ in range(columns):
                menu.add_column(width=cell_width)
            rows = math.ceil(len(numbered) / columns)
            for row in range(rows):
                cells = [option(*numbered[index]) if index < len(numbered) else Text("")
                         for index in (row + column * rows for column in range(columns))]
                menu.add_row(*cells)
            self.rich.print(menu)
        else:
            for index, choice in numbered:
                self.rich.print(option(index, choice), overflow="fold")
                if choice.detail:
                    self.say("      " + clean(choice.detail), "muted")
        self.say()
        self.rich.print(option(0, Choice("back", back_label)))
        default_number = default + 1 if choices[default].value != "back" else 0
        self.say(f" Enter = {default_number:02} / Ctrl+C = exit", "muted")
        selections = {str(index): choice.value for index, choice in numbered}
        selections["0"] = "back"
        while True:
            value = self.read("Select an option").strip().lower()
            if value in {"0", "00", "q", "back", "\x1b"}:
                return "back"
            if not value:
                return choices[default].value
            if value.isascii() and value.isdigit():
                selected = selections.get(value.lstrip("0") or "0")
                if selected is not None:
                    return selected
            self.notice("Invalid option. Choose a number from the menu.", marker="!", color="red")

    def read(self, label):
        prompt = Text(" ")
        prompt.append_text(self.bracket("-"))
        prompt.append(" " + clean(label) + " : ", style="green")
        self.rich.print(prompt, end="")
        return input()

    def ask(self, label, default="", *, required=False, validator=None):
        while True:
            suffix = f" [{clean(default)}]" if default else ""
            value = self.read(clean(label) + suffix).strip() or default
            if required and not value:
                self.say("This field is required.", "gold")
                continue
            if validator:
                try:
                    validator(value)
                except ValueError as exc:
                    self.say(str(exc), "gold")
                    continue
            return value

    def pause(self):
        self.say()
        self.read("Press Enter to return to the main menu")

    def activity(self, message):
        return Activity(self, message)

    def progress(self, current, total):
        progress = Progress(TextColumn("Completed"), BarColumn(bar_width=None),
                            TaskProgressColumn(), TextColumn("{task.completed:.0f}/{task.total:.0f}"),
                            console=self.rich, expand=True)
        progress.add_task("workflow", total=total, completed=current)
        self.rich.print(progress)


class Activity:
    def __init__(self, console, message):
        self.console, self.message = console, clean(message)
        self.status = None

    def update(self, message):
        self.message = clean(message)
        if self.status:
            self.status.update(Text(self.message, style="bright_cyan"))
        else:
            self.console.notice(self.message, marker="-", color="cyan")

    def __enter__(self):
        self.started = time.monotonic()
        if self.console.animate:
            self.status = self.console.rich.status(Text(self.message, style="bright_cyan"),
                                                  spinner="line", refresh_per_second=8)
            self.status.start()
        else:
            self.console.notice(self.message, marker="-", color="cyan")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.status:
            self.status.stop()
        elapsed = time.monotonic() - self.started
        self.console.notice(f"{'OK' if exc_type is None else 'STOPPED'} / {self.message} / {elapsed:.1f}s",
                            marker="+" if exc_type is None else "!", color="green" if exc_type is None else "red")

"""Rich presentation and prompt_toolkit menus, with accessible plain output."""
import math
import os
import re
import sys
import time
from contextvars import ContextVar
from dataclasses import dataclass

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, ScrollOffsets, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style
from prompt_toolkit.utils import get_cwidth
from rich import box
from rich.console import Console as RichConsole
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
from rich.text import Text
from rich.table import Table

from .. import PROJECT_NAME, __version__
from .brand import COMPACT_MARK, DEVELOPER, DISCLAIMER, FAREWELL, FORK_URL, PROFILE_URL, REPOSITORY_URL, WORDMARK


@dataclass(frozen=True)
class UIOptions:
    plain: bool = False
    no_animation: bool = False


UI_OPTIONS = ContextVar("getit_ui_options", default=UIOptions())


def enable_terminal():
    # Rich and prompt_toolkit handle Windows console modes and terminal restoration.
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
    COLORS = {"cyan": "bright_cyan", "gold": "bright_yellow", "green": "bright_green",
              "red": "bright_red", "muted": "dim", "bold": "bold"}

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

    def link(self, label, url):
        text = Text(clean(label) + ": ")
        text.append(url, style=f"bright_cyan link {url}")
        self.rich.print(text, overflow="fold")

    def panel(self, title, lines=(), color="cyan"):
        content = Text("\n".join(clean(line) for line in lines))
        self.rich.print(Panel(content, title=Text(clean(title), style="bold"),
                              border_style=self.COLORS.get(color, "cyan"),
                              box=box.ROUNDED if self.terminal else box.ASCII,
                              width=self.width, padding=(1, 2)))

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
        mark = WORDMARK if self.width >= 66 else COMPACT_MARK
        self.rich.print(Text(mark, style="bold bright_yellow"))
        self.say(f"  {PROJECT_NAME} / v{__version__} / Linux · Windows · Termux", "muted")
        self.link(f"Developer / {DEVELOPER}", PROFILE_URL)
        if disclaimer:
            self.panel("EDUCATIONAL USE", [DISCLAIMER], "gold")

    def banner(self, repo="", completed=0, pending=0, configured=False):
        self.panel("DASHBOARD", [repo or "Repository: setup needed",
                   f"Primary token: {'present; run Check connection to verify' if configured else 'missing'}",
                   f"Completed: {completed}   |   To inspect: {pending}",
                   "Preview a workflow, check its requirements, then choose whether to run it."])

    def goodbye(self):
        self.masthead()
        self.link("Star", REPOSITORY_URL)
        self.link("Fork", FORK_URL)
        self.say()
        self.rich.print(Text(FAREWELL, style="bold black on bright_cyan"))

    def choose(self, title, choices, *, default=0):
        if not choices or not 0 <= default < len(choices):
            raise ValueError("A menu needs choices and a valid default.")
        self.say()
        self.say(title, "bold")
        if not self.terminal or not sys.stdin.isatty():
            for i, choice in enumerate(choices, 1):
                self.say(f"  {i}. {choice.label}" + (f" / {choice.detail}" if choice.detail else ""))
            while True:
                value = input(f"Select [1-{len(choices)}, Enter={default + 1}, 0=back]: ").strip().lower()
                if value in {"0", "q", "back"}:
                    return "back"
                if not value:
                    return choices[default].value
                if value.isdigit() and 1 <= int(value) <= len(choices):
                    return choices[int(value) - 1].value
                self.say("Choose a number from the menu.", "gold")
        return self.menu_application(choices, default=default).run()

    def menu_application(self, choices, *, default=0, input=None, output=None):
        """Inline scrollable menu; injected streams support actual keyboard tests."""
        selected = [default]
        bindings = KeyBindings()

        @bindings.add("up")
        @bindings.add("k")
        @bindings.add("s-tab")
        def previous(event):
            selected[0] = (selected[0] - 1) % len(choices)

        @bindings.add("down")
        @bindings.add("j")
        @bindings.add("tab")
        def following(event):
            selected[0] = (selected[0] + 1) % len(choices)

        @bindings.add("home")
        def first(event):
            selected[0] = 0

        @bindings.add("end")
        def last(event):
            selected[0] = len(choices) - 1

        @bindings.add("enter")
        def accept(event):
            event.app.exit(result=choices[selected[0]].value)

        @bindings.add("escape")
        @bindings.add("q")
        @bindings.add("0")
        def back(event):
            event.app.exit(result="back")

        @bindings.add("c-c")
        def interrupt(event):
            event.app.exit(exception=KeyboardInterrupt())

        @bindings.add("c-d")
        @bindings.add("c-z")
        def eof(event):
            event.app.exit(exception=EOFError())

        for index in range(min(9, len(choices))):
            def numbered(event, index=index):
                event.app.exit(result=choices[index].value)
            bindings.add(str(index + 1))(numbered)

        def render():
            fragments = []
            for index, choice in enumerate(choices):
                active = index == selected[0]
                if active:
                    fragments.append(("[SetCursorPosition]", ""))
                style = "class:selected" if active else "class:choice"
                fragments.append((style, f" {'>' if active else ' '} {index + 1:>2}  {clean(choice.label)}\n"))
                if choice.detail:
                    fragments.append(("class:detail", f"        {clean(choice.detail)}\n"))
            return FormattedText(fragments)

        style = Style.from_dict({"selected": "bold bg:#164e63 #67e8f9", "choice": "#e2e8f0",
                                 "detail": "#94a3b8", "hint": "#fbbf24"}) if self.color else Style([])
        control = FormattedTextControl(render, focusable=True, show_cursor=False)

        def wrapped_rows(text):
            width = max(1, output.get_size().columns if output else self.rich.size.width)
            return max(1, math.ceil(get_cwidth(text) / width))

        def menu_height():
            rows = sum(wrapped_rows("       " + clean(choice.label))
                       + (wrapped_rows("        " + clean(choice.detail)) if choice.detail else 0)
                       for choice in choices)
            return Dimension(min=1, preferred=rows, max=rows)

        def detail_rows():
            detail = choices[selected[0]].detail
            return wrapped_rows("        " + clean(detail)) if detail else 0

        window = Window(control, wrap_lines=True, always_hide_cursor=True, dont_extend_height=True,
                        height=menu_height, scroll_offsets=ScrollOffsets(bottom=detail_rows))
        hint_text = " Arrows / number / Enter | 0/Esc back | Ctrl+C exit"

        def hint_height():
            rows = wrapped_rows(hint_text)
            return Dimension(min=1, preferred=rows, max=rows)

        hint = Window(FormattedTextControl(FormattedText([
            ("class:hint", hint_text)
        ])), wrap_lines=True, dont_extend_height=True,
            height=hint_height)
        return Application(layout=Layout(HSplit([window, hint]), focused_element=window), key_bindings=bindings, style=style,
                           full_screen=False, input=input, output=output,
                           erase_when_done=True, min_redraw_interval=0.05)

    def ask(self, label, default="", *, required=False, validator=None):
        while True:
            suffix = f" [{clean(default)}]" if default else ""
            value = input(f"  {clean(label)}{suffix}: ").strip() or default
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
        input("\n  Press Enter to return to your dashboard...")

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
            self.console.say("  > " + self.message, "muted")

    def __enter__(self):
        self.started = time.monotonic()
        if self.console.animate:
            self.status = self.console.rich.status(Text(self.message, style="bright_cyan"),
                                                  spinner="line", refresh_per_second=8)
            self.status.start()
        else:
            self.console.say("  > " + self.message, "muted")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.status:
            self.status.stop()
        elapsed = time.monotonic() - self.started
        self.console.say(f"  {'OK' if exc_type is None else 'STOPPED'} / {self.message} / {elapsed:.1f}s",
                         "green" if exc_type is None else "gold")

"""Command-line entry point, account setup, and terminal presentation."""

def main(argv=None):
    # Keep dependency errors readable before the terminal libraries are installed.
    from .bootstrap import launch
    return launch(argv)

__all__ = ["main"]

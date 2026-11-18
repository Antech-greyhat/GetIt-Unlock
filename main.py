"""GetIt-Unlock launcher: python main.py [command]."""
import sys

sys.dont_write_bytecode = True

from getit_unlock.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

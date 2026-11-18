"""Original terminal artwork and public project links."""

DEVELOPER = "Antech-greyhat"
PROFILE_URL = "https://github.com/Antech-greyhat"
REPOSITORY_URL = PROFILE_URL + "/GetIt-Unlock"
FORK_URL = REPOSITORY_URL + "/fork"
FAREWELL = "Thanks for using this tool, dont forget to star and fork"
DISCLAIMER = (
    "For educational purposes. Use only accounts and repositories you are authorized to use. "
    "You are responsible for your actions; the developer is not responsible for abuse or misuse."
)

# Bundled FIGlet standard/small lettering; no external artwork command is needed.
# Zphisher inspired the warm wordmark, colored brackets, and numbered menus.
WORDMARK = r"""   ____ _____ _____ ___ _____     _   _ _   _ _     ___   ____ _  __
  / ___| ____|_   _|_ _|_   _|   | | | | \ | | |   / _ \ / ___| |/ /
 | |  _|  _|   | |  | |  | |_____| | | |  \| | |  | | | | |   | ' /
 | |_| | |___  | |  | |  | |_____| |_| | |\  | |__| |_| | |___| . \
  \____|_____| |_| |___| |_|      \___/|_| \_|_____\___/ \____|_|\_\
"""

COMPACT_MARK = r"""   ___ ___ _____ ___ _____
  / __| __|_   _|_ _|_   _|
 | (_ | _|  | |  | |  | |
  \___|___| |_| |___| |_|
  _   _ _  _ _    ___   ___ _  __
 | | | | \| | |  / _ \ / __| |/ /
 | |_| | .` | |_| (_) | (__| ' <
  \___/|_|\_|____\___/ \___|_|\_\
"""

TINY_MARK = r"""    .---.
    |   '   GETIT
  .-+---+-. UNLOCK
  |   o   |
  '-------'"""

# Compact three-row lettering gives menu headings their own visual weight.
# Keep an ordinary title alongside it for copy/paste and accessible output.
MENU_LETTERS = {
    "A": (" _ ", "|_|", "| |"), "B": (" _ ", "|_)", "|_)"),
    "C": (" _", "| ", "|_"), "D": (" _ ", "| )", "|_/"),
    "E": (" _", "|_", "|_"), "F": (" _", "|_", "| "),
    "G": (" _ ", "| _", "|_|"), "H": ("   ", "|_|", "| |"),
    "I": ("___", " | ", "_|_"), "J": (" __", "  |", "|_|"),
    "K": ("  ", "|/", "|\\"), "L": ("  ", "| ", "|_"),
    "M": ("    ", "|\\/|", "|  |"), "N": ("    ", "|\\ |", "| \\|"),
    "O": (" _ ", "| |", "|_|"), "P": (" _ ", "|_|", "|  "),
    "Q": (" _ ", "| |", "|_\\"), "R": (" _ ", "|_|", "| \\"),
    "S": (" _ ", "|_ ", " _|"), "T": ("___", " | ", " | "),
    "U": ("   ", "| |", "|_|"), "V": ("   ", "| |", " \\/"),
    "W": ("     ", "|   |", "|/\\|"), "X": ("   ", "\\ /", " /\\"),
    "Y": ("   ", "\\ /", " | "), "Z": ("__ ", " / ", "/__"),
    " ": (" ", " ", " "),
}


def menu_lettering(title):
    if not title or any(letter not in MENU_LETTERS for letter in title.upper()):
        return ""
    return "\n".join(" ".join(MENU_LETTERS[letter][row].ljust(max(map(len, MENU_LETTERS[letter])))
                              for letter in title.upper()).rstrip()
                     for row in range(3))

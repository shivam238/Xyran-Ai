import atexit
import os
import re

try:
    import readline
except Exception:
    readline = None


ANSI_ESCAPE_PATTERN = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|O[@-~])")
CARET_ESCAPE_PATTERN = re.compile(r"\^\[(?:\[[0-?]*[ -/]*[@-~]|O[@-~])")
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
HISTORY_PATH = os.path.join(os.path.expanduser("~"), ".local", "state", "xyran", "history")


def _configure_readline():
    if not readline:
        return

    history_enabled = True
    try:
        os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    except OSError:
        history_enabled = False

    readline.set_history_length(200)
    readline.parse_and_bind("tab: complete")
    readline.parse_and_bind("set editing-mode emacs")

    if not history_enabled:
        return

    try:
        readline.read_history_file(HISTORY_PATH)
    except FileNotFoundError:
        pass
    except Exception:
        return

    def _save_history():
        try:
            readline.write_history_file(HISTORY_PATH)
        except Exception:
            pass

    atexit.register(_save_history)


def sanitize_terminal_input(text):
    cleaned = ANSI_ESCAPE_PATTERN.sub("", text)
    cleaned = CARET_ESCAPE_PATTERN.sub("", cleaned)
    cleaned = CONTROL_CHAR_PATTERN.sub("", cleaned)
    return cleaned.strip()


def read_user_input(prompt):
    raw_text = input(prompt)
    return sanitize_terminal_input(raw_text)


_configure_readline()

import os
import shlex
import shutil
import subprocess


def run_command(command):
    try:
        stripped_command = command.strip()
        executable_error = get_command_executable_error(stripped_command)
        if executable_error:
            return executable_error

        if stripped_command.endswith("&"):
            launch_command = stripped_command[:-1].strip()
            subprocess.Popen(
                launch_command,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ, "DISPLAY": ":0"},
            )
            return "Done."
        result = subprocess.run(
            stripped_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "DISPLAY": ":0"},
        )
        output = result.stdout.strip() + result.stderr.strip()
        return output if output else "Done."
    except subprocess.TimeoutExpired:
        return "Command timeout ho gaya."
    except Exception as error:
        return f"Error: {error}"


def get_command_executable_error(command):
    if not command:
        return None

    stripped = command.strip()
    if stripped.endswith("&"):
        stripped = stripped[:-1].strip()

    if not stripped:
        return None

    if any(token in stripped for token in ["|", "&&", "||", ";", "$(", "`", ">", "<"]):
        return None

    try:
        parts = shlex.split(stripped)
    except Exception:
        return None

    if not parts:
        return None

    executable = parts[0]
    shell_builtins = {
        "cd", "echo", "pwd", "test", "[", "alias", "export", "source",
        "set", "unset", "true", "false", "printf",
    }
    if executable in shell_builtins:
        return None

    if "/" in executable:
        if os.path.isfile(executable) and os.access(executable, os.X_OK):
            return None
        return f"Error: `{executable}` executable nahi mila."

    if shutil.which(executable):
        return None
    return f"Error: `{executable}` command nahi mila."


def command_failed(output):
    if not output:
        return False
    lowered = output.lower()
    return lowered.startswith("error:") or "command not found" in lowered


def get_xdotool_window_ids(search_term, use_class=False):
    search_flag = "--class" if use_class else "--name"
    try:
        result = subprocess.run(
            f'xdotool search {search_flag} "{search_term}"',
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, "DISPLAY": ":0"},
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except Exception:
        return []


def focus_window(window_id):
    try:
        subprocess.run(
            f"xdotool windowmap {window_id} windowactivate {window_id}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, "DISPLAY": ":0"},
        )
        return True
    except Exception:
        return False

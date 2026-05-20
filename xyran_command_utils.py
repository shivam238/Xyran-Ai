import os
import shlex
import shutil
import subprocess
import time


# Map common app executables to their .desktop file IDs for gtk-launch focus
_APP_DESKTOP_MAP = {
    "gnome-text-editor": "org.gnome.TextEditor",
    "gedit": "org.gnome.gedit",
    "nautilus": "org.gnome.Nautilus",
    "gnome-calculator": "org.gnome.Calculator",
    "gnome-terminal": "org.gnome.Terminal",
    "gnome-console": "org.gnome.Console",
    "ptyxis": "org.gnome.Ptyxis",
    "kgx": "org.gnome.Console",
    "gnome-control-center": "org.gnome.Settings",
    "firefox": "firefox",
    "google-chrome": "google-chrome",
    "brave-browser": "brave-browser",
    "code": "code",
    "eog": "org.gnome.eog",
    "evince": "org.gnome.Evince",
    "totem": "org.gnome.Totem",
    "loupe": "org.gnome.Loupe",
}


def focus_launched_app(command):
    """
    Try to bring a GUI app to foreground on Wayland using gtk-launch.
    Extracts the app executable from the command and maps it to a .desktop ID.
    """
    # Extract first executable from the command
    clean_cmd = command.strip()
    if clean_cmd.endswith("&"):
        clean_cmd = clean_cmd[:-1].strip()

    # Handle compound commands (&&, ||, ;)
    # Take the LAST command part (that's usually the GUI app)
    for sep in ["&&", "||", ";"]:
        if sep in clean_cmd:
            clean_cmd = clean_cmd.split(sep)[-1].strip()

    # Get executable name
    try:
        parts = shlex.split(clean_cmd)
        exe = os.path.basename(parts[0]) if parts else ""
    except Exception:
        exe = clean_cmd.split()[0] if clean_cmd else ""

    desktop_id = _APP_DESKTOP_MAP.get(exe)
    if not desktop_id:
        return False

    try:
        time.sleep(0.5)  # Small wait for app to register with compositor
        subprocess.run(
            f"gtk-launch {desktop_id}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        return True
    except Exception:
        return False


def _resolve_desktop_id(launch_command):
    """
    Given a shell command like 'gnome-text-editor "/path/file"' or
    'echo hello > file && gnome-text-editor file', extract the GUI app
    executable and return its .desktop ID if known.
    """
    clean = launch_command.strip()

    # For compound commands (&&, ;), take the LAST part (usually the GUI app)
    for sep in ["&&", "||", ";"]:
        if sep in clean:
            clean = clean.split(sep)[-1].strip()

    # Get executable name
    try:
        parts = shlex.split(clean)
        exe = os.path.basename(parts[0]) if parts else ""
    except Exception:
        exe = clean.split()[0] if clean else ""

    return _APP_DESKTOP_MAP.get(exe)


def _extract_app_args(launch_command):
    """
    Extract file arguments from a launch command for passing to gtk-launch.
    E.g. 'gnome-text-editor "/path/to/file.txt"' → '"/path/to/file.txt"'
    """
    clean = launch_command.strip()

    # For compound commands, take the LAST part
    for sep in ["&&", "||", ";"]:
        if sep in clean:
            clean = clean.split(sep)[-1].strip()

    try:
        parts = shlex.split(clean)
        if len(parts) > 1:
            # Return all args after the executable, properly quoted
            return " ".join(f'"{arg}"' if " " in arg else arg for arg in parts[1:])
    except Exception:
        pass
    return ""

def _dbus_activate_app(desktop_id):
    """
    Attempt to bring an already running app to foreground on Wayland
    by calling the org.freedesktop.Application.Activate D-Bus method
    with a startup-id activation token.
    """
    try:
        import dbus
        import dbus.mainloop.glib
        import os
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        # Some apps use org.gnome.TextEditor, some use org.gnome.Nautilus etc as bus name
        # We try to use the desktop_id as the bus name
        proxy = bus.get_object(desktop_id, f"/{desktop_id.replace('.', '/')}")
        iface = dbus.Interface(proxy, 'org.freedesktop.Application')
        
        # Pass a fake startup ID to get focus
        platform_data = dbus.Dictionary({
            'desktop-startup-id': dbus.String(f"xyran_focus_{os.getpid()}_{time.time()}", variant_level=1),
        }, signature='sv')
        
        iface.Activate(platform_data)
        return True
    except Exception:
        return False

def run_command(command):
    try:
        stripped_command = command.strip()
        executable_error = get_command_executable_error(stripped_command)
        if executable_error:
            return executable_error

        if stripped_command.endswith("&"):
            launch_command = stripped_command[:-1].strip()

            # Intercept browser launches and force --new-window to guarantee focus on Wayland
            try:
                parts = shlex.split(launch_command)
                exe = os.path.basename(parts[0]) if parts else ""
            except Exception:
                exe = launch_command.split()[0] if launch_command else ""
                parts = []

            if exe in ("brave-browser", "google-chrome", "google-chrome-stable", "firefox"):
                if parts and "--new-window" not in parts:
                    # Inject --new-window right after the browser executable
                    parts.insert(1, "--new-window")
                    # Reconstruct properly quoted command string
                    launch_command = " ".join(shlex.quote(p) for p in parts)
                
                subprocess.Popen(
                    launch_command,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env={**os.environ, "DISPLAY": ":0"},
                )
                return "Done."

            # Try gtk-launch for known GUI apps (Wayland foreground focus)
            desktop_id = _resolve_desktop_id(launch_command)
            if desktop_id:
                # If compound command (echo && editor), run pre-steps first
                has_compound = any(sep in launch_command for sep in ["&&", "||", ";"])
                if has_compound:
                    # Run everything BEFORE the last command (the GUI app)
                    for sep in ["&&", "||", ";"]:
                        if sep in launch_command:
                            parts = launch_command.rsplit(sep, 1)
                            pre_cmd = parts[0].strip()
                            # Run the pre-commands synchronously
                            subprocess.run(
                                pre_cmd,
                                shell=True,
                                capture_output=True,
                                text=True,
                                timeout=10,
                                env={**os.environ, "DISPLAY": ":0"},
                            )
                            break

                # Now launch the GUI app via gtk-launch (foreground!)
                args = _extract_app_args(launch_command)
                gtk_cmd = f"gtk-launch {desktop_id}"
                if args:
                    gtk_cmd += f" {args}"
                subprocess.Popen(
                    gtk_cmd,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                # Also try D-Bus Activate to bring already-running apps to foreground
                _dbus_activate_app(desktop_id)
                return "Done."

            # Fallback: direct Popen for unknown apps
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
    error_indicators = [
        "error:", "command not found", "no such schema", "no such key",
        "no such file", "permission denied", "failed to", "invalid option",
        "unknown option", "error"
    ]
    return any(indicator in lowered for indicator in error_indicators)



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

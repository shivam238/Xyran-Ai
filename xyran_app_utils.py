import os
import shutil
import time
from datetime import datetime
from urllib.parse import quote_plus

from xyran_command_utils import focus_window, get_xdotool_window_ids
from xyran_search import resolve_website_alias
from xyran_input_utils import (
    extract_requested_app_name,
    resolve_app_alias,
    wants_new_tab,
)


def resolve_app_launch(user_input, run_command, command_failed):
    requested_app = extract_requested_app_name(user_input)
    if not requested_app:
        return None

    alias_key, app_info = resolve_app_alias(requested_app)
    if not app_info:
        return None

    output = None
    for command in app_info["commands"]:
        output = run_command(f"{command} &")
        if not command_failed(output):
            return {
                "requested_app": requested_app,
                "resolved_key": alias_key,
                "label": app_info["label"],
                "command": f"{command} &",
                "output": output,
            }

    return {
        "requested_app": requested_app,
        "resolved_key": alias_key,
        "label": app_info["label"],
        "command": f'{app_info["commands"][0]} &',
        "output": output,
    }


def resolve_known_website(user_input):
    requested_target = extract_requested_app_name(user_input)
    if not requested_target:
        return None

    alias_key, website = resolve_website_alias(requested_target)
    if not website:
        return None

    return {
        "requested_target": requested_target,
        "resolved_key": alias_key,
        "website": website,
    }


def get_available_browser():
    for candidate in ["google-chrome", "google-chrome-stable", "brave-browser", "firefox"]:
        if shutil.which(candidate):
            return candidate
    return None


def get_browser_for_request(user_input):
    lowered = user_input.lower().strip()
    requested_name = None
    requested_browser = None

    if "firefox" in lowered:
        requested_name = "Firefox"
        requested_browser = "firefox"
    elif "google chrome" in lowered or "chrome" in lowered:
        requested_name = "Google Chrome"
        requested_browser = "google-chrome"
    elif "brave" in lowered:
        requested_name = "Brave"
        requested_browser = "brave-browser"

    if requested_browser and shutil.which(requested_browser):
        return requested_browser, requested_name

    browser = get_available_browser()
    return browser, requested_name


def get_browser_friendly_name(browser):
    if browser in {"google-chrome", "google-chrome-stable"}:
        return "Google Chrome"
    if browser == "brave-browser":
        return "Brave"
    if browser == "firefox":
        return "Firefox"
    return browser or "Browser"


def smart_open_browser(user_input, run_command):
    browser, requested_name = get_browser_for_request(user_input)
    if not browser:
        return "Koi supported browser nahi mila. `brave-browser` ya `firefox` install hona chahiye."

    friendly_name = get_browser_friendly_name(browser)
    run_command(f"{browser} &")
    if requested_name and requested_name != friendly_name:
        return f"{requested_name} installed nahi mila, isliye {friendly_name} khol diya."
    return f"{friendly_name} khol diya."


def smart_open_website(target, user_input, run_command):
    browser, requested_name = get_browser_for_request(user_input)
    if not browser:
        return "Koi supported browser nahi mila. `brave-browser` ya `firefox` install hona chahiye."

    friendly_name = get_browser_friendly_name(browser)
    normalized_target = target.strip()
    if not normalized_target.startswith(("http://", "https://")):
        normalized_target = f"https://{normalized_target}"

    run_command(f'{browser} "{normalized_target}" &')
    if requested_name and requested_name != friendly_name:
        return f"{requested_name} installed nahi mila, isliye website {friendly_name} mein khol di."
    return f"Website {friendly_name} mein khol di."


def smart_search_web(query, user_input, run_command):
    browser, requested_name = get_browser_for_request(user_input)
    if not browser:
        return "Koi supported browser nahi mila. `brave-browser` ya `firefox` install hona chahiye."

    friendly_name = get_browser_friendly_name(browser)
    search_url = f"https://www.google.com/search?q={quote_plus(query)}"
    run_command(f'{browser} "{search_url}" &')
    if requested_name and requested_name != friendly_name:
        return f"{requested_name} installed nahi mila, isliye `{query}` ko {friendly_name} mein search kar diya."
    return f"`{query}` ko {friendly_name} mein search kar diya."


def smart_open_youtube(user_input, run_command, last_browser_action):
    now = time.monotonic()
    browser, requested_name = get_browser_for_request(user_input)
    if not browser:
        return "Koi supported browser nahi mila. `brave-browser` ya `firefox` install hona chahiye.", last_browser_action

    browser_name = get_browser_friendly_name(browser)
    if (
        last_browser_action["target"] == "youtube"
        and last_browser_action.get("browser") == browser
        and now - last_browser_action["time"] < 3
    ):
        return "YouTube abhi abhi handle kiya tha, isliye dobara open nahi kar raha.", last_browser_action

    youtube_window_ids = get_xdotool_window_ids("YouTube")
    browser_window_ids = get_xdotool_window_ids(browser, use_class=True)

    if wants_new_tab(user_input):
        run_command(f'{browser} --new-tab "https://youtube.com" &')
        if browser_window_ids:
            focus_window(browser_window_ids[-1])
        updated_action = {"target": "youtube", "browser": browser, "time": now}
        if requested_name and requested_name != browser_name:
            return f"{requested_name} installed nahi mila, isliye YouTube {browser_name} ke naye tab mein khol diya.", updated_action
        return f"YouTube {browser_name} ke naye tab mein khol diya.", updated_action

    if youtube_window_ids:
        focus_window(youtube_window_ids[-1])
        updated_action = {"target": "youtube", "browser": browser, "time": now}
        return "YouTube pehle se open tha, usi tab ko saamne le aaya.", updated_action

    run_command(f'{browser} "https://youtube.com" &')
    updated_browser_window_ids = get_xdotool_window_ids(browser, use_class=True)
    if updated_browser_window_ids:
        focus_window(updated_browser_window_ids[-1])
    updated_action = {"target": "youtube", "browser": browser, "time": now}
    if requested_name and requested_name != browser_name:
        return f"{requested_name} installed nahi mila, isliye YouTube {browser_name} mein khol diya.", updated_action
    return f"YouTube {browser_name} mein khol diya.", updated_action


def save_screenshot_copy(temp_path, ai_name):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = os.path.expanduser(f"~/Pictures/{ai_name}-Screenshots")
    os.makedirs(folder, exist_ok=True)
    final_path = os.path.join(folder, f"screenshot-{timestamp}.png")
    shutil.copy(temp_path, final_path)
    return final_path

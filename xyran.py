import os
import subprocess
import json
import re
import shutil
import random
import difflib
import shlex
import urllib.request
import urllib.error
import urllib.parse
import time
from datetime import datetime
from groq import Groq, RateLimitError
from config import GROQ_API_KEY, MODEL, AI_NAME, USER_NAME, NEWS_API_KEY
from vision import analyze_screen, take_screenshot
import base64

try:
    import pyjokes
except Exception:
    pyjokes = None

client = Groq(api_key=GROQ_API_KEY)
conversation_history = []
last_input_used_vision = False
vision_followup_turns_left = 0
last_screenshot_path = None
last_editor_file_path = None
last_created_code_file = None
last_rate_limit_wait_text = None
last_provider_used = "groq"
last_browser_action = {"target": None, "time": 0.0}
last_news_titles = []
last_news_query_signature = None
last_news_page = 1
last_news_articles = []

LOCAL_JOKES = [
    "Programmer ne paani kyu nahi piya? Kyunki usne socha bug liquid state mein bhi ho sakta hai.",
    "Ek coder bola: meri life sorted hai. Phir usne semicolon miss kar diya.",
    "Debugging wahi process hai jahan hum detective bhi hote hain aur criminal bhi.",
    "Computer ko thand kyu lag gayi? Kyunki usne Windows khuli chhod di.",
    "Code itna clean tha ki bug ko rehne ke liye alag room lena pada."
]

FALLBACK_API_KEY = os.environ.get("FALLBACK_API_KEY", "").strip()
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL", "").strip()
FALLBACK_BASE_URL = os.environ.get(
    "FALLBACK_BASE_URL",
    "https://openrouter.ai/api/v1/chat/completions"
).strip()
NEWS_API_URL = "https://newsapi.org/v2/top-headlines"
NEWS_STATE_PATH = os.path.join(os.path.dirname(__file__), "progress", "news_state.json")

SYSTEM_PROMPT = f"""You are {AI_NAME}, a powerful personal AI agent on {USER_NAME}'s Fedora Linux + GNOME + Wayland system.
You also have VISION — you can see the screen via screenshots.

You MUST always reply in this JSON format only — no extra text:
{{"action": "run", "command": "shell command", "explain": "kya kar raha hoon"}}
{{"action": "run_multi", "commands": ["cmd1", "cmd2"], "explain": "kya kar raha hoon"}}
{{"action": "answer", "message": "your answer here"}}
{{"action": "look_and_act", "command": "shell command after seeing screen", "explain": "screen dekh ke ye kar raha hoon"}}

SYSTEM INFO:
- OS: Fedora Linux, GNOME, Wayland
- Home: /home/{USER_NAME}
- Desktop: /home/{USER_NAME}/Desktop
- Downloads: /home/{USER_NAME}/Downloads
- Shell: bash

APPS:
- Browser: google-chrome, brave-browser, or firefox
- If user says Chrome/Google Chrome, prefer google-chrome if installed, otherwise brave-browser, otherwise firefox
- Files: nautilus
- Terminal: ptyxis, gnome-terminal, kgx, or gnome-console
- Calculator: gnome-calculator
- Text editor: gedit or gnome-text-editor
- VS Code: code
- Settings: gnome-control-center
- Append & to run GUI apps in background

FILE OPERATIONS:
- Create file: touch ~/path/name.txt
- Create folder: mkdir -p ~/path/folder
- Delete: rm ~/path/file or rm -rf ~/path/folder
- Move: mv source dest
- Copy: cp source dest
- List: ls -la ~/path
- Find: find ~/ -name "filename"
- Read: cat ~/path/file
- Write: echo "content" > ~/path/file

BROWSER:
- Open site: brave-browser "https://site.com" &
- Google search: brave-browser "https://www.google.com/search?q=query" &
- YouTube: brave-browser "https://youtube.com" &

SYSTEM:
- Time: date +'%r'
- Date: date +'%A, %d %B %Y'
- Disk: df -h ~
- RAM: free -h
- CPU: lscpu | grep "Model name"
- Battery: upower -i $(upower -e | grep battery) | grep -E "percentage|state|time to"
- Kill app: pkill appname
- Shutdown: systemctl poweroff
- Restart: systemctl reboot
- Volume up: wpctl set-mute @DEFAULT_AUDIO_SINK@ 0 && wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+
- Volume down: wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-
- Mute: wpctl set-mute @DEFAULT_AUDIO_SINK@ 1
- Unmute: wpctl set-mute @DEFAULT_AUDIO_SINK@ 0
- Volume full: wpctl set-mute @DEFAULT_AUDIO_SINK@ 0 && wpctl set-volume @DEFAULT_AUDIO_SINK@ 100%
- Screenshot already handled internally

PACKAGE MANAGEMENT:
- Install: sudo dnf install appname -y
- Remove: sudo dnf remove appname -y
- Update: sudo dnf update -y
- Search: dnf search appname

NETWORK:
- Check internet: ping -c 1 google.com
- IP: ip addr show
- Wifi: nmcli dev wifi

VISION RULES:
- If user says "screen dekho", "kya chal raha hai", "screen pe kya hai", "dekh ke batao" — use action "answer", vision already handled
- If user says "ye wali file kholo", "jo browser mein khula hai", referring to something on screen — vision context already given to you
- Always use screen context when available to give smarter answers

RULES:
- Always use & when opening GUI apps
- Respond in same language as user (Hindi/English/Hinglish)
- explain field mein batao kya kar rahe ho
- If unsure, say so honestly
"""

VISION_SYSTEM_PROMPT = f"""You are {AI_NAME}'s screen-reading vision module.

Your job is to describe ONLY what is clearly visible in the provided screenshot.

Hard rules:
- Start by identifying the frontmost/center-most active window first.
- If multiple windows are visible, mention all clearly visible windows in visual priority order.
- Give higher priority to the large centered dialog/window than to sidebars or background editors.
- Never guess the website, app, tab, or file name from dock/sidebar icons alone.
- Never assume YouTube, Brave, Chrome, terminal content, or any other app unless it is clearly readable in the main visible window.
- If text is blurry, partially hidden, too small, or uncertain, say that honestly.
- Focus on the main foreground window/content, not the launcher/dock/app grid.
- Distinguish between "installed apps shown as icons" and "actually open visible windows".
- Prefer answers like "clear nahi dikh raha" over invented details.

Return ONLY valid JSON in one of these formats:
{{"action": "answer", "message": "screen par jo clearly visible hai woh yahan batao"}}
{{"action": "look_and_act", "command": "shell command", "explain": "screen dekh ke kya kar raha hoon"}}
"""


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
                env={**os.environ, "DISPLAY": ":0"}
            )
            return "Done."
        result = subprocess.run(
            stripped_command, shell=True, capture_output=True,
            text=True, timeout=15,
            env={**os.environ, "DISPLAY": ":0"}
        )
        output = result.stdout.strip() + result.stderr.strip()
        return output if output else "Done."
    except subprocess.TimeoutExpired:
        return "Command timeout ho gaya."
    except Exception as e:
        return f"Error: {e}"


def get_command_executable_error(command):
    if not command:
        return None

    stripped = command.strip()
    if stripped.endswith("&"):
        stripped = stripped[:-1].strip()

    if not stripped:
        return None

    if any(token in stripped for token in ["|", "&&", "||", ";", "$(", "`", ">","<"]):
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
        "set", "unset", "true", "false", "printf"
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


def has_fallback_provider():
    return bool(FALLBACK_API_KEY and FALLBACK_MODEL and FALLBACK_BASE_URL)


def call_fallback_chat(messages, model, temperature=0.2, max_tokens=600):
    payload = {
        "model": FALLBACK_MODEL or model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        FALLBACK_BASE_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {FALLBACK_API_KEY}",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"].strip()


def summarize_output(output):
    """Long command output ko AI se 1-2 line mein summarize karao."""
    try:
        followup = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        'Summarize this command output in 1-2 lines in Hinglish. '
                        'Only show what matters to the user (e.g. battery %, charging state, disk space, RAM). '
                        'Return ONLY JSON: {"action": "answer", "message": "summary here"}'
                    )
                },
                {"role": "user", "content": output}
            ],
            max_tokens=120
        )
        summary_reply = followup.choices[0].message.content.strip()
        summary_data = clean_json(summary_reply)
        s = json.loads(summary_data)
        return s.get("message", output[:200])
    except Exception:
        return output[:200]


def load_news_state():
    global last_news_titles, last_news_query_signature, last_news_page, last_news_articles
    try:
        if not os.path.exists(NEWS_STATE_PATH):
            return
        with open(NEWS_STATE_PATH, "r", encoding="utf-8") as file_obj:
            state = json.load(file_obj)
        last_news_titles = state.get("last_news_titles", [])
        last_news_query_signature = state.get("last_news_query_signature")
        last_news_page = int(state.get("last_news_page", 1))
        last_news_articles = state.get("last_news_articles", [])
    except Exception:
        last_news_titles = []
        last_news_query_signature = None
        last_news_page = 1
        last_news_articles = []


def save_news_state():
    try:
        os.makedirs(os.path.dirname(NEWS_STATE_PATH), exist_ok=True)
        with open(NEWS_STATE_PATH, "w", encoding="utf-8") as file_obj:
            json.dump(
                {
                    "last_news_titles": last_news_titles,
                    "last_news_query_signature": last_news_query_signature,
                    "last_news_page": last_news_page,
                    "last_news_articles": last_news_articles,
                },
                file_obj,
                ensure_ascii=True,
                indent=2,
            )
    except Exception:
        pass


def should_use_vision(user_input):
    vision_keywords = [
        "screen dekho", "kya chal raha", "kya khula", "kya dikh raha",
        "screen pe kya", "dikhao", "jo khula hai", "kon se apps",
        "can u see", "screen check", "dekh ke batao", "window mein",
        "browser mein kya", "screen pe", "kya open hai", "screen par",
        "screen pr", "screen par hai", "screen pr hai", "padho",
        "read the code", "code padh", "koi file dikh", "konsa folder",
        "kaun sa folder", "ab check", "dobara dekho", "fir dekho"
    ]
    lowered = user_input.lower()
    return any(kw in lowered for kw in vision_keywords)


def is_vision_followup(user_input):
    followup_keywords = [
        "haan", "batao", "btao", "padho", "check", "dekho", "dobara",
        "fir", "again", "screen pr hai", "screen par hai", "kya hai",
        "kya dikh", "koi file", "folder", "file ka naam", "kon kon",
        "kaun kaun", "isme", "usme", "waha", "vahaan", "details",
        "detail", "sari details", "sab details", "aur batao",
        "uski details", "poori details", "full details", "kya chal",
        "kya open", "kya khula", "kya chal raha"
    ]
    lowered = user_input.lower()
    return any(kw in lowered for kw in followup_keywords)


def is_ambiguous_short_followup(user_input):
    lowered = user_input.lower().strip()
    word_count = len(lowered.split())
    ambiguous_phrases = [
        "sari details do", "sab details do", "details do", "detail do",
        "aur batao", "aur btao", "ab batao", "ab dekho", "ab check karo",
        "ab check kro", "uski details do", "poori details do",
        "full details do", "sahi se batao"
    ]
    return word_count <= 5 and any(phrase in lowered for phrase in ambiguous_phrases)


def is_acknowledgement(user_input):
    lowered = user_input.lower().strip()
    acknowledgements = {
        "ok", "okay", "okk", "k", "kk", "haan", "hm", "hmm", "hmmm",
        "thanks", "thank you", "thx", "theek", "theek hai", "achha",
        "acha", "nice", "good", "great", "cool"
    }
    return lowered in acknowledgements


def is_greeting(user_input):
    lowered = user_input.lower().strip()
    if lowered in {"yo", "namaste", "salam"}:
        return True
    compact = re.sub(r"(.)\1+", r"\1", lowered)
    return compact in {"hi", "hello", "hey"}


def get_local_smalltalk_reply(user_input):
    lowered = user_input.lower().strip()

    farewell_map = {
        "bye": "Theek hai, phir milte hain.",
        "goodbye": "Theek hai, phir milte hain.",
        "good bye": "Theek hai, phir milte hain.",
        "milte hain": "Theek hai, phir milte hain.",
        "phir milte hain": "Theek hai, phir milte hain.",
        "see you": "Theek hai, phir milte hain.",
        "cya": "Theek hai, phir milte hain.",
    }
    thanks_map = {
        "shukriya": "Khushi hui help karke.",
        "dhanyawad": "Khushi hui help karke.",
        "dhanyavaad": "Khushi hui help karke.",
        "thanku": "Khushi hui help karke.",
        "thank u": "Khushi hui help karke.",
        "ty": "Khushi hui help karke.",
    }
    night_map = {
        "good night": "Good night. Aaram se rest karo.",
        "gn": "Good night. Aaram se rest karo.",
        "night": "Good night. Aaram se rest karo.",
    }

    if lowered in farewell_map:
        return farewell_map[lowered]
    if lowered in thanks_map:
        return thanks_map[lowered]
    if lowered in night_map:
        return night_map[lowered]
    return None


def is_app_launch_request(user_input):
    lowered = user_input.lower().strip()
    open_words = ["open", "khol", "khol do", "kholo", "open karo", "open kr"]
    return any(word in lowered for word in open_words)


def extract_requested_app_name(user_input):
    lowered = user_input.lower().strip()
    patterns = [
        (r"^(.*?)\s+(open|khol|khol do|kholo|open karo|open kr)$", 1),
        (r"^(open|khol|khol do|kholo|open karo|open kr)\s+(.+)$", 2),
    ]
    for pattern, group_index in patterns:
        match = re.search(pattern, lowered)
        if match:
            candidate = match.group(group_index)
            candidate = re.sub(r"\b(app|application)\b", "", candidate).strip()
            candidate = " ".join(candidate.split())
            if candidate:
                return candidate
    return None


def get_app_aliases():
    return {
        "terminal": {
            "label": "Terminal",
            "commands": ["ptyxis", "gnome-terminal", "kgx", "gnome-console"],
        },
        "extensions": {
            "label": "GNOME Extensions",
            "commands": ["gnome-control-center extensions"],
        },
        "settings": {
            "label": "Settings",
            "commands": ["gnome-control-center"],
        },
        "files": {
            "label": "Files",
            "commands": ["nautilus"],
        },
        "file manager": {
            "label": "Files",
            "commands": ["nautilus"],
        },
        "helvum": {
            "label": "Helvum",
            "commands": ["helvum"],
        },
        "code": {
            "label": "VS Code",
            "commands": ["code"],
        },
        "vs code": {
            "label": "VS Code",
            "commands": ["code"],
        },
        "vscode": {
            "label": "VS Code",
            "commands": ["code"],
        },
        "calculator": {
            "label": "Calculator",
            "commands": ["gnome-calculator"],
        },
    }


def resolve_app_launch(user_input):
    requested_app = extract_requested_app_name(user_input)
    if not requested_app:
        return None

    aliases = get_app_aliases()
    alias_key = requested_app
    if alias_key not in aliases:
        close_matches = difflib.get_close_matches(alias_key, list(aliases.keys()), n=1, cutoff=0.72)
        if close_matches:
            alias_key = close_matches[0]
        else:
            return None

    app_info = aliases[alias_key]
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


def is_screenshot_request(user_input):
    lowered = user_input.lower()
    screenshot_words = ["screenshot", "screen shot", "ss le", "ss lo", "capture screen"]
    return any(word in lowered for word in screenshot_words)


def is_files_open_request(user_input):
    lowered = user_input.lower()
    open_words = ["open", "khol", "khol do", "kholde", "khol do", "open kr", "open karo"]
    file_words = ["files", "file manager", "nautilus", "folder"]
    return any(word in lowered for word in open_words) and any(word in lowered for word in file_words)


def wants_to_show_screenshot(user_input):
    lowered = user_input.lower()
    return any(word in lowered for word in ["dikha", "dikhao", "show", "open", "khol"])


def is_text_editor_request(user_input):
    lowered = user_input.lower()
    editor_words = ["text editor", "editor", "gedit", "gnome-text-editor", "notepad"]
    open_words = ["open", "khol", "khol do", "kholde", "open kr", "open karo"]
    write_words = ["likh", "write", "type"]
    return any(word in lowered for word in editor_words) and (
        any(word in lowered for word in open_words) or any(word in lowered for word in write_words)
    )


def is_python_file_request(user_input):
    lowered = user_input.lower()
    create_words = ["new", "banao", "bnao", "create", "bana do", "bna do"]
    python_words = ["py file", "python file", ".py"]
    return any(word in lowered for word in create_words) and any(word in lowered for word in python_words)


def extract_text_to_write(user_input):
    patterns = [
        r"likh\s+(.+)$",
        r"likho\s+(.+)$",
        r"write\s+(.+)$",
        r"type\s+(.+)$",
        r"(.+?)\s+likh$",
        r"(.+?)\s+likho$",
        r"(.+?)\s+write$",
        r"(.+?)\s+type$",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_input, re.IGNORECASE)
        if match:
            text = match.group(1).strip().strip("\"'")
            if text:
                cleanup_patterns = [
                    r"^(text editor|editor|gedit|gnome-text-editor|notepad)\s+",
                    r"^(open|open kr|open karo|khol|khol do|kholo|kholde)\s+",
                    r"^(or|aur)\s+",
                ]
                changed = True
                while changed:
                    changed = False
                    for cleanup_pattern in cleanup_patterns:
                        updated = re.sub(cleanup_pattern, "", text, flags=re.IGNORECASE).strip()
                        if updated != text:
                            text = updated
                            changed = True
            if text:
                return text
    return None


def get_available_text_editor():
    for candidate in ["gnome-text-editor", "gedit"]:
        if shutil.which(candidate):
            return candidate
    return None


def prepare_editor_file(initial_text=None):
    global last_editor_file_path
    folder = os.path.expanduser(f"~/Documents/{AI_NAME}")
    os.makedirs(folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_path = os.path.join(folder, f"note-{timestamp}.txt")
    with open(file_path, "w", encoding="utf-8") as file_obj:
        if initial_text:
            file_obj.write(initial_text)
            if not initial_text.endswith("\n"):
                file_obj.write("\n")
    last_editor_file_path = file_path
    return file_path


def prepare_python_file(initial_code=None):
    global last_created_code_file
    folder = os.path.expanduser(f"~/Documents/{AI_NAME}")
    os.makedirs(folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    file_path = os.path.join(folder, f"script-{timestamp}.py")
    with open(file_path, "w", encoding="utf-8") as file_obj:
        if initial_code:
            file_obj.write(initial_code)
            if not initial_code.endswith("\n"):
                file_obj.write("\n")
    last_created_code_file = file_path
    return file_path


def extract_python_code_request(user_input):
    lowered = user_input.lower()
    if "hello print" in lowered or "print hello" in lowered:
        return 'print("hello")'
    if "hello world print" in lowered or "print hello world" in lowered:
        return 'print("hello world")'
    return None


def get_editor_open_command(file_path):
    editor = shutil.which("code")
    if editor:
        return f'code "{file_path}" &'
    editor = get_available_text_editor()
    if editor:
        return f'{editor} "{file_path}" &'
    return None


def humanize_wait_time(wait_text):
    normalized = re.sub(r"(\d+)\.\d+s", r"\1s", wait_text.lower())
    parts = re.findall(r"(\d+)([hms])", normalized)
    if not parts:
        return wait_text

    labels = {"h": "hour", "m": "minute", "s": "second"}
    human_parts = []
    for value, unit in parts:
        label = labels[unit]
        if value != "1":
            label += "s"
        human_parts.append(f"{value} {label}")
    return " ".join(human_parts)


def is_rate_limit_time_query(user_input):
    lowered = user_input.lower().strip()
    phrases = [
        "kitna time bacha hai",
        "kitna wait hai",
        "kab tak wait",
        "kab tak rukna hai",
        "how much time left",
        "time left",
        "kitni der baaki hai",
    ]
    return any(phrase in lowered for phrase in phrases)


def is_joke_request(user_input):
    lowered = user_input.lower().strip()
    phrases = [
        "tell me a joke", "joke suna", "joke sunao", "koi joke",
        "majak suna", "funny bol", "hasao", "make me laugh"
    ]
    return any(phrase in lowered for phrase in phrases)


def get_local_joke():
    if pyjokes:
        try:
            return pyjokes.get_joke()
        except Exception:
            pass
    return random.choice(LOCAL_JOKES)


def is_news_request(user_input):
    lowered = user_input.lower().strip()
    return "news" in lowered or "headlines" in lowered


def is_more_news_request(user_input):
    global last_news_query_signature
    lowered = user_input.lower().strip()
    phrases = [
        "more news", "aur news", "next news", "next headlines",
        "more headlines", "aur headlines", "dusri news", "doosri news",
        "agli news"
    ]
    short_followups = {"next", "aur", "more", "dusri", "doosri", "agli"}
    if lowered in short_followups:
        return bool(last_news_query_signature)
    return any(phrase in lowered for phrase in phrases)


def is_news_summary_request(user_input):
    lowered = user_input.lower().strip()
    summary_words = [
        "summary", "summarize", "explain", "detail", "details",
        "samjha", "samjhao", "detail mein", "brief", "gist"
    ]
    reference_words = [
        "news", "headline", "article", "pehli", "dusri", "doosri",
        "teesri", "fourth", "fifth", "first", "second", "third",
        "1", "2", "3", "4", "5"
    ]
    return any(word in lowered for word in summary_words) and (
        any(word in lowered for word in reference_words) or bool(last_news_articles)
    )


def extract_news_selection_index(user_input, max_items):
    lowered = user_input.lower().strip()
    match = re.search(r"\b([1-9])\b", lowered)
    if match:
        index = int(match.group(1)) - 1
        if 0 <= index < max_items:
            return index

    ordinal_map = {
        "first": 0,
        "pehli": 0,
        "pehla": 0,
        "1st": 0,
        "second": 1,
        "dusri": 1,
        "doosri": 1,
        "dusra": 1,
        "2nd": 1,
        "third": 2,
        "teesri": 2,
        "teesra": 2,
        "3rd": 2,
        "fourth": 3,
        "chauthi": 3,
        "chautha": 3,
        "4th": 3,
        "fifth": 4,
        "paanchvi": 4,
        "paanchva": 4,
        "5th": 4,
    }
    for word, index in ordinal_map.items():
        if word in lowered and index < max_items:
            return index
    return 0 if max_items else None


def get_news_query_params(user_input):
    lowered = user_input.lower().strip()
    params = {"country": "in", "pageSize": "5"}

    categories = {
        "tech": "technology",
        "technology": "technology",
        "sports": "sports",
        "sport": "sports",
        "business": "business",
        "health": "health",
        "science": "science",
        "entertainment": "entertainment",
        "general": "general",
    }

    countries = {
        "india": "in",
        "indian": "in",
        "us": "us",
        "usa": "us",
        "america": "us",
        "uk": "gb",
        "britain": "gb",
    }

    for keyword, category in categories.items():
        if keyword in lowered:
            params["category"] = category
            break

    for keyword, country in countries.items():
        if keyword in lowered:
            params["country"] = country
            break

    query_cleanup = re.sub(
        r"\b(latest|today|news|headlines|batao|sunao|show|tell me|about|do|de|dena|dijiye|please|plz|more|next|aur|dusri|doosri|agli|second)\b",
        "",
        lowered
    )
    query_cleanup = " ".join(query_cleanup.split()).strip()
    if query_cleanup and query_cleanup not in categories and query_cleanup not in countries:
        params["q"] = query_cleanup

    return params


def summarize_news_article(user_input):
    if not last_news_articles:
        return "Pehle `news` chalao, phir main selected article ka summary de dunga."

    index = extract_news_selection_index(user_input, len(last_news_articles))
    if index is None or not (0 <= index < len(last_news_articles)):
        return "Kaunsi news chahiye woh clear nahi hua. Jaise `1 ka summary` ya `dusri news explain` bolo."

    article = last_news_articles[index]
    title = article.get("title", "Untitled")
    source = article.get("source", "Unknown source")
    description = article.get("description", "")
    content = article.get("content", "")
    url = article.get("url", "")

    info_parts = [
        f"Title: {title}",
        f"Source: {source}",
    ]
    if description:
        info_parts.append(f"Description: {description}")
    if content:
        info_parts.append(f"Content snippet: {content}")
    if url:
        info_parts.append(f"URL: {url}")
    article_context = "\n".join(info_parts)

    messages = [
        {
            "role": "system",
            "content": (
                "You summarize news in short Hinglish. Keep it factual and concise. "
                "If details are limited, say that clearly. "
                "Return ONLY plain text, no JSON."
            )
        },
        {
            "role": "user",
            "content": (
                "Is news article ko 3 short lines mein samjhao. "
                "Line 1: kya hua. Line 2: kyu matter karta hai. "
                "Line 3: agar context limited ho to mention karo.\n\n"
                f"{article_context}"
            )
        }
    ]

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=180
        )
        reply = response.choices[0].message.content.strip()
        return f"{index + 1}. {title} - {source}\n{reply}"
    except RateLimitError:
        if has_fallback_provider():
            try:
                reply = call_fallback_chat(messages, MODEL, temperature=0.2, max_tokens=180)
                return f"{index + 1}. {title} - {source}\n{reply}"
            except Exception:
                pass
        return "Abhi summary API limit hit ho gayi hai. Thodi der baad phir try karo."
    except Exception as e:
        return f"Summary nahi bana paya: {e}"


def fetch_news_headlines(user_input):
    global last_news_titles, last_news_query_signature, last_news_page, last_news_articles
    if not NEWS_API_KEY:
        return "NEWS_API_KEY configured nahi hai. `.env` mein add karo."

    def request_news(params):
        query_string = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            f"{NEWS_API_URL}?{query_string}",
            headers={"X-Api-Key": NEWS_API_KEY},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    params = get_news_query_params(user_input)
    is_more_request = is_more_news_request(user_input)
    default_params = {"country": "in", "pageSize": "5"}
    if is_more_request and params == default_params and last_news_query_signature:
        try:
            params = json.loads(last_news_query_signature)
        except Exception:
            pass
    query_signature = json.dumps(params, sort_keys=True)
    target_page = 1

    if is_more_request and last_news_query_signature == query_signature:
        target_page = last_news_page + 1
        params["page"] = str(target_page)
    else:
        params["page"] = "1"

    fallback_params_list = [params]

    if "q" in params and not is_more_request:
        without_q = dict(params)
        without_q.pop("q", None)
        fallback_params_list.append(without_q)

    if params.get("country") != "us" and not is_more_request:
        us_fallback = dict(params)
        us_fallback["country"] = "us"
        us_fallback.pop("q", None)
        fallback_params_list.append(us_fallback)

    generic_fallback = {"country": "us", "pageSize": "5", "page": str(target_page)}
    if not is_more_request and generic_fallback not in fallback_params_list:
        fallback_params_list.append(generic_fallback)

    articles = []
    last_error = None
    for attempt_params in fallback_params_list:
        try:
            body = request_news(attempt_params)
        except urllib.error.HTTPError as e:
            try:
                error_body = json.loads(e.read().decode("utf-8"))
                last_error = f"News API error: {error_body.get('message', str(e))}"
            except Exception:
                last_error = f"News API error: {e}"
            continue
        except Exception as e:
            last_error = f"News fetch nahi ho payi: {e}"
            continue

        fetched_articles = body.get("articles", [])
        if last_news_titles:
            filtered_articles = [
                article for article in fetched_articles
                if article.get("title") not in last_news_titles
            ]
        else:
            filtered_articles = fetched_articles

        articles = filtered_articles[:5] if filtered_articles else fetched_articles[:5]
        if articles:
            last_news_query_signature = json.dumps(
                {k: v for k, v in attempt_params.items() if k != "page"},
                sort_keys=True
            )
            try:
                last_news_page = int(attempt_params.get("page", "1"))
            except ValueError:
                last_news_page = 1
            last_news_titles = [article.get("title") for article in articles if article.get("title")]
            last_news_articles = [
                {
                    "title": article.get("title", ""),
                    "source": article.get("source", {}).get("name", "Unknown source"),
                    "description": article.get("description", "") or "",
                    "content": article.get("content", "") or "",
                    "url": article.get("url", "") or "",
                }
                for article in articles
            ]
            save_news_state()
            break

    if not articles:
        if last_error:
            return last_error
        if is_more_request:
            return "Aur fresh news nahi mili. Nayi category ya country try karo."
        return "Koi news headlines nahi mili."

    lines = []
    for index, article in enumerate(articles, start=1):
        title = article.get("title", "Untitled")
        source = article.get("source", {}).get("name", "Unknown source")
        lines.append(f"{index}. {title} - {source}")
    return "\n".join(lines)


def is_api_status_query(user_input):
    lowered = user_input.lower().strip()
    phrases = [
        "api aa gya hai", "api aa gaya hai", "api aagya hai",
        "api back hai", "api wapas aayi", "api chal rahi hai",
        "is api back", "api back"
    ]
    return any(phrase in lowered for phrase in phrases)


def is_open_youtube_request(user_input):
    lowered = user_input.lower().strip()
    open_words = ["open", "khol", "khol do", "kholo", "open karo", "open kr"]
    youtube_words = ["youtube", "yt"]
    return any(word in lowered for word in open_words) and any(word in lowered for word in youtube_words)


def is_browser_open_request(user_input):
    lowered = user_input.lower().strip()
    open_words = ["open", "khol", "khol do", "kholo", "open karo", "open kr"]
    browser_words = [
        "browser", "brave", "firefox", "chrome", "google chrome",
        "web browser"
    ]
    return any(word in lowered for word in open_words) and any(word in lowered for word in browser_words)


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


def smart_open_browser(user_input):
    browser, requested_name = get_browser_for_request(user_input)
    if not browser:
        return "Koi supported browser nahi mila. `brave-browser` ya `firefox` install hona chahiye."

    friendly_name = get_browser_friendly_name(browser)

    run_command(f"{browser} &")
    if requested_name and requested_name != friendly_name:
        return f"{requested_name} installed nahi mila, isliye {friendly_name} khol diya."
    return f"{friendly_name} khol diya."


def wants_new_tab(user_input):
    lowered = user_input.lower().strip()
    phrases = [
        "new tab", "naye tab", "naya tab", "dusre tab", "doosre tab",
        "another tab", "second tab", "alag tab"
    ]
    return any(phrase in lowered for phrase in phrases)


def get_xdotool_window_ids(search_term, use_class=False):
    search_flag = "--class" if use_class else "--name"
    try:
        result = subprocess.run(
            f'xdotool search {search_flag} "{search_term}"',
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, "DISPLAY": ":0"}
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
            env={**os.environ, "DISPLAY": ":0"}
        )
        return True
    except Exception:
        return False


def smart_open_youtube(user_input):
    global last_browser_action
    now = time.monotonic()
    browser, requested_name = get_browser_for_request(user_input)
    if not browser:
        return "Koi supported browser nahi mila. `brave-browser` ya `firefox` install hona chahiye."

    browser_name = get_browser_friendly_name(browser)
    if (
        last_browser_action["target"] == "youtube"
        and last_browser_action.get("browser") == browser
        and now - last_browser_action["time"] < 3
    ):
        return "YouTube abhi abhi handle kiya tha, isliye dobara open nahi kar raha."

    youtube_window_ids = get_xdotool_window_ids("YouTube")
    browser_window_ids = get_xdotool_window_ids(browser, use_class=True)

    if wants_new_tab(user_input):
        run_command(f'{browser} --new-tab "https://youtube.com" &')
        if browser_window_ids:
            focus_window(browser_window_ids[-1])
        last_browser_action = {"target": "youtube", "browser": browser, "time": now}
        if requested_name and requested_name != browser_name:
            return f"{requested_name} installed nahi mila, isliye YouTube {browser_name} ke naye tab mein khol diya."
        return f"YouTube {browser_name} ke naye tab mein khol diya."

    if youtube_window_ids:
        focus_window(youtube_window_ids[-1])
        last_browser_action = {"target": "youtube", "browser": browser, "time": now}
        return f"YouTube pehle se open tha, usi tab ko saamne le aaya."

    run_command(f'{browser} "https://youtube.com" &')
    updated_browser_window_ids = get_xdotool_window_ids(browser, use_class=True)
    if updated_browser_window_ids:
        focus_window(updated_browser_window_ids[-1])
    last_browser_action = {"target": "youtube", "browser": browser, "time": now}
    if requested_name and requested_name != browser_name:
        return f"{requested_name} installed nahi mila, isliye YouTube {browser_name} mein khol diya."
    return f"YouTube {browser_name} mein khol diya."


def save_screenshot_copy(temp_path):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = os.path.expanduser(f"~/Pictures/{AI_NAME}-Screenshots")
    os.makedirs(folder, exist_ok=True)
    final_path = os.path.join(folder, f"screenshot-{timestamp}.png")
    shutil.copy(temp_path, final_path)
    return final_path


def handle_direct_action(user_input):
    global last_screenshot_path, last_rate_limit_wait_text
    lowered = user_input.lower().strip()

    did_something = False

    if is_acknowledgement(lowered):
        print("[Xyran] Theek hai.")
        return True

    if is_greeting(lowered):
        print("[Xyran] Hello! Kya help chahiye?")
        return True

    smalltalk_reply = get_local_smalltalk_reply(lowered)
    if smalltalk_reply:
        print(f"[Xyran] {smalltalk_reply}")
        return True

    if is_joke_request(lowered):
        print(f"[Xyran] {get_local_joke()}")
        return True

    if is_news_summary_request(lowered):
        print("[Xyran] News ka summary bana raha hoon...")
        print(f"[Xyran] {summarize_news_article(user_input)}")
        return True

    if is_more_news_request(lowered):
        print("[Xyran] Aur news la raha hoon...")
        print(f"[Xyran] {fetch_news_headlines(user_input)}")
        return True

    if is_news_request(lowered):
        print("[Xyran] News la raha hoon...")
        print(f"[Xyran] {fetch_news_headlines(user_input)}")
        return True

    if is_api_status_query(lowered):
        if last_rate_limit_wait_text:
            print(f"[Xyran] Abhi nahi, lagbhag {last_rate_limit_wait_text} baad phir try karna.")
        else:
            print("[Xyran] Haan, abhi try karke dekh sakte ho.")
        return True

    if is_open_youtube_request(lowered):
        print("[Xyran] YouTube handle kar raha hoon")
        message = smart_open_youtube(user_input)
        print(f"[Xyran] {message}")
        return True

    if is_browser_open_request(lowered):
        print("[Xyran] Browser khol raha hoon...")
        message = smart_open_browser(user_input)
        print(f"[Xyran] {message}")
        return True

    if is_app_launch_request(lowered):
        app_result = resolve_app_launch(user_input)
        if app_result:
            print(f"[Xyran] {app_result['label']} khol raha hoon")
            print(f"[CMD] {app_result['command']}")
            if app_result["output"] and app_result["output"] != "Done.":
                print(f"[Output] {app_result['output']}")
            if command_failed(app_result["output"]):
                print("[Xyran] Ye app sahi se open nahi hui.")
            elif app_result["requested_app"] != app_result["resolved_key"]:
                print(f"[Xyran] `{app_result['requested_app']}` ko `{app_result['label']}` samajh kar khol diya.")
            else:
                print("[Xyran] Ho gaya.")
            return True

    if is_rate_limit_time_query(lowered):
        if last_rate_limit_wait_text:
            print(f"[Xyran] Lagbhag {last_rate_limit_wait_text} baad phir try kar sakte ho.")
        else:
            print("[Xyran] Abhi mere paas exact wait time saved nahi hai.")
        return True

    if is_python_file_request(lowered):
        code_to_write = extract_python_code_request(user_input)
        file_path = prepare_python_file(code_to_write)
        open_command = get_editor_open_command(file_path)

        if code_to_write:
            print("[Xyran] Nayi Python file bana raha hoon aur code likh raha hoon")
        else:
            print("[Xyran] Nayi Python file bana raha hoon")

        if open_command:
            print(f"[CMD] {open_command}")
            output = run_command(open_command)
            if output and output != "Done.":
                print(f"[Output] {output}")
                if command_failed(output):
                    print("[Xyran] File banana ho gaya, lekin editor khul nahi paya.")
                    return True

        if code_to_write:
            print(f"[Xyran] `{code_to_write}` likh diya: {file_path}")
        else:
            print(f"[Xyran] Python file bana di: {file_path}")
        return True

    if is_text_editor_request(lowered):
        editor = get_available_text_editor()
        if not editor:
            print("[Xyran] Koi supported text editor nahi mila. `gnome-text-editor` ya `gedit` install hona chahiye.")
            return True

        text_to_write = extract_text_to_write(user_input)
        file_path = prepare_editor_file(text_to_write)

        if text_to_write:
            print(f"[Xyran] {editor} khol raha hoon aur file mein text likh diya hai")
        else:
            print(f"[Xyran] {editor} khol raha hoon")

        print(f"[CMD] {editor} \"{file_path}\" &")
        output = run_command(f'{editor} "{file_path}" &')
        if output and output != "Done.":
            print(f"[Output] {output}")
            if command_failed(output):
                print("[Xyran] File ban gayi, lekin editor khul nahi paya.")
                return True

        if text_to_write:
            print(f"[Xyran] `{text_to_write}` file mein likh diya aur editor khol diya: {file_path}")
        else:
            print(f"[Xyran] Editor khol diya: {file_path}")
        return True

    if is_files_open_request(lowered):
        print("[Xyran] Files app khol raha hoon")
        print("[CMD] nautilus &")
        output = run_command("nautilus &")
        if output and output != "Done.":
            print(f"[Output] {output}")
        if not command_failed(output):
            print("[Xyran] Ho gaya.")
        else:
            print("[Xyran] Ye command sahi se run nahi hui.")
        did_something = True

    if is_screenshot_request(lowered):
        print("[Xyran] Screenshot le raha hoon...")
        temp_path, err = take_screenshot()
        if not temp_path:
            print(f"[Xyran] Screenshot nahi le paya: {err}")
            return True

        saved_path = save_screenshot_copy(temp_path)
        os.remove(temp_path)
        last_screenshot_path = saved_path

        if wants_to_show_screenshot(lowered):
            print(f"[CMD] xdg-open \"{saved_path}\" &")
            output = run_command(f'xdg-open "{saved_path}" &')
            if output and output != "Done.":
                print(f"[Output] {output}")
            print(f"[Xyran] Screenshot save bhi ho gaya aur khol bhi diya: {saved_path}")
        else:
            print(f"[Xyran] Screenshot save ho gaya: {saved_path}")
        did_something = True

    if "last screenshot" in lowered or "pichla screenshot" in lowered or "kaha hai screenshot" in lowered:
        if not last_screenshot_path:
            print("[Xyran] Abhi tak koi screenshot save nahi hua hai.")
            return True
        if wants_to_show_screenshot(lowered):
            print(f"[CMD] xdg-open \"{last_screenshot_path}\" &")
            output = run_command(f'xdg-open "{last_screenshot_path}" &')
            if output and output != "Done.":
                print(f"[Output] {output}")
            print(f"[Xyran] Yeh raha last screenshot: {last_screenshot_path}")
        else:
            print(f"[Xyran] Last screenshot yahan saved hai: {last_screenshot_path}")
        return True

    if did_something:
        return True

    return False


def ask_xyran(user_input, screen_context=None):
    global last_rate_limit_wait_text, last_provider_used
    content = user_input
    if screen_context:
        content = f"[SCREEN CONTEXT]\n{screen_context}\n\n[USER COMMAND]\n{user_input}"

    conversation_history.append({"role": "user", "content": content})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=600
        )
        last_provider_used = "groq"
    except RateLimitError as e:
        if has_fallback_provider():
            try:
                reply = call_fallback_chat(messages, MODEL, temperature=0.2, max_tokens=600)
                last_provider_used = "fallback"
                conversation_history.append({"role": "assistant", "content": reply})
                return reply
            except Exception:
                pass
        wait_match = re.search(r"Please try again in ([0-9hms.]+)", str(e))
        wait_text = humanize_wait_time(wait_match.group(1)) if wait_match else "thodi der"
        last_rate_limit_wait_text = wait_text
        return json.dumps({
            "action": "answer",
            "message": f"Groq API ka daily token limit hit ho gaya hai. Lagbhag {wait_text} baad phir try karo, ya direct local commands use karo. Agar fallback provider set hoga to next time auto-switch ho jayega."
        })

    reply = response.choices[0].message.content.strip()
    conversation_history.append({"role": "assistant", "content": reply})
    return reply


def ask_xyran_with_image(user_input, image_path):
    global last_rate_limit_wait_text, last_provider_used
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    messages = [
        {"role": "system", "content": VISION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_data}"}
                },
                {
                    "type": "text",
                    "text": (
                        f"Screenshot ko bahut dhyan se dekho.\n"
                        f"Left sidebar, launcher, dock, app grid, pinned icons aur task icons ko IGNORE karo.\n"
                        f"Un icons se app ya website infer mat karo.\n"
                        f"Sabse pehle center/front mein jo active ya topmost window hai usko identify karo.\n"
                        f"Uske baad background mein jo aur windows visible hain unko mention karo.\n"
                        f"Sirf main visible foreground content batao.\n"
                        f"Answer karte waqt in cheezon ko separately check karo:\n"
                        f"1) Sabse aage/topmost window ka app naam aur usme kya screen dikh rahi hai?\n"
                        f"2) Uske peeche aur kaunsi windows visible hain?\n"
                        f"3) Browser/tab/website ka naam tabhi batao jab screenshot mein clearly readable ho.\n"
                        f"4) Terminal text tabhi quote karo jab readable ho, warna bolo readable nahi hai.\n"
                        f"5) Agar code editor/file explorer/file manager visible ho, to readable file names aur folder names list karo.\n"
                        f"6) Agar settings/dialog/system window visible ho, to uske section names ya options bhi batao.\n"
                        f"7) Agar certainty low ho toh clearly mention karo ki exact cheez identify nahi ho rahi.\n"
                        f"8) Pichhle messages ya common patterns ke basis par guess mat karo.\n"
                        f"Answer ko short structured Hinglish mein do: 'Front window:', 'Also visible:', 'Readable items:'.\n"
                        f"User ka command: {user_input}\n"
                        f"JSON format mein jawab do."
                    )
                }
            ]
        }
    ]

    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=messages,
            temperature=0,
            max_tokens=600
        )
        last_provider_used = "groq"
    except RateLimitError:
        if has_fallback_provider():
            try:
                reply = call_fallback_chat(
                    messages,
                    "meta-llama/llama-4-scout-17b-16e-instruct",
                    temperature=0,
                    max_tokens=600
                )
                last_provider_used = "fallback"
                return reply
            except Exception:
                pass
        last_rate_limit_wait_text = "thodi der"
        return json.dumps({
            "action": "answer",
            "message": "Vision API ka token limit hit ho gaya hai, isliye abhi screenshot analyze nahi kar pa raha. Thodi der baad phir try karo, ya fallback provider configure karo."
        })

    reply = response.choices[0].message.content.strip()
    return reply


def clean_json(reply):
    if "```" in reply:
        parts = reply.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:]
            if part.startswith("{"):
                return part.strip()
    return reply.strip()


def process_response(reply):
    reply = clean_json(reply)
    try:
        data = json.loads(reply)
        action = data.get("action")
        explain = data.get("explain", "")

        if explain:
            print(f"\n[Xyran] {explain}")

        if action in ("run", "look_and_act"):
            command = str(data.get("command", "")).strip()
            if command.lower() in ("", "none", "null", "n/a", "no command"):
                print("\n[Xyran] Main iske liye koi valid command identify nahi kar paya. Jo visible hai usi ke basis par answer dena better hoga.")
                return
            print(f"[CMD] {command}")
            output = run_command(command)
            if output and output != "Done.":
                if len(output) > 300:
                    summary = summarize_output(output)
                    print(f"\n[Xyran] {summary}")
                else:
                    print(f"[Output] {output}")
            if not command_failed(output):
                print(f"[Xyran] Ho gaya.")
            else:
                print(f"[Xyran] Ye command sahi se run nahi hui.")

        elif action == "run_multi":
            commands = [
                str(cmd).strip() for cmd in data.get("commands", [])
                if str(cmd).strip().lower() not in ("", "none", "null", "n/a", "no command")
            ]
            if not commands:
                print("\n[Xyran] Koi valid commands nahi mile, isliye main kuch run nahi kar raha.")
                return
            had_failure = False
            for cmd in commands:
                print(f"[CMD] {cmd}")
                output = run_command(cmd)
                if output and output != "Done.":
                    if len(output) > 300:
                        summary = summarize_output(output)
                        print(f"\n[Xyran] {summary}")
                    else:
                        print(f"[Output] {output}")
                if command_failed(output):
                    had_failure = True
            if not had_failure:
                print(f"[Xyran] Sab ho gaya.")
            else:
                print(f"[Xyran] Kuch commands sahi se run nahi hui.")

        elif action == "answer":
            message = data.get("message", "")
            print(f"\n[Xyran] {message}")

    except json.JSONDecodeError:
        print(f"\n[Xyran] {reply}")


def main():
    global last_input_used_vision, vision_followup_turns_left
    load_news_state()
    print(f"""
╔══════════════════════════════════════════╗
║         XYRAN AI v2 - ONLINE             ║
║   Brain + Aankhein — Dono Ready Hain     ║
╚══════════════════════════════════════════╝
'exit' likho band karne ke liye.
""")

    while True:
        try:
            user_input = input(f"[{USER_NAME}] ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "band karo"):
                print("[Xyran] Theek hai. Phir milenge.")
                break

            if handle_direct_action(user_input):
                last_input_used_vision = False
                continue

            use_vision = (
                should_use_vision(user_input)
                or (last_input_used_vision and is_vision_followup(user_input))
                or (vision_followup_turns_left > 0 and is_ambiguous_short_followup(user_input))
            )

            if use_vision:
                print("[Xyran] Screen dekh raha hoon...")
                img_path, err = take_screenshot()
                if img_path:
                    reply = ask_xyran_with_image(user_input, img_path)
                    os.remove(img_path)
                else:
                    print(f"[Xyran] Screenshot nahi le paya: {err}")
                    reply = ask_xyran(user_input)
                last_input_used_vision = True
                vision_followup_turns_left = 2
            else:
                reply = ask_xyran(user_input)
                last_input_used_vision = False
                if vision_followup_turns_left > 0:
                    vision_followup_turns_left -= 1

            process_response(reply)

        except KeyboardInterrupt:
            print("\n[Xyran] Band ho raha hoon.")
            break
        except RateLimitError:
            print("\n[Xyran] Groq API rate limit hit ho gaya hai. Thodi der baad phir try karo.")
        except Exception as e:
            print(f"\n[Xyran] Error aaya: {e}")


if __name__ == "__main__":
    main()

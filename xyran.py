import os
import subprocess
import json
import re
import shutil
from datetime import datetime
from groq import Groq
from config import GROQ_API_KEY, MODEL, AI_NAME, USER_NAME
from vision import analyze_screen, take_screenshot
import base64

client = Groq(api_key=GROQ_API_KEY)
conversation_history = []
last_input_used_vision = False
vision_followup_turns_left = 0
last_screenshot_path = None
last_editor_file_path = None

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
- Browser: brave-browser or firefox
- Files: nautilus
- Terminal: gnome-terminal
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
        if command.strip().endswith("&"):
            subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ, "DISPLAY": ":0"}
            )
            return "Done."
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=15,
            env={**os.environ, "DISPLAY": ":0"}
        )
        output = result.stdout.strip() + result.stderr.strip()
        return output if output else "Done."
    except subprocess.TimeoutExpired:
        return "Command timeout ho gaya."
    except Exception as e:
        return f"Error: {e}"


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


def save_screenshot_copy(temp_path):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = os.path.expanduser(f"~/Pictures/{AI_NAME}-Screenshots")
    os.makedirs(folder, exist_ok=True)
    final_path = os.path.join(folder, f"screenshot-{timestamp}.png")
    shutil.copy(temp_path, final_path)
    return final_path


def handle_direct_action(user_input):
    global last_screenshot_path
    lowered = user_input.lower().strip()

    did_something = False

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
        print("[Xyran] Ho gaya.")
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
    content = user_input
    if screen_context:
        content = f"[SCREEN CONTEXT]\n{screen_context}\n\n[USER COMMAND]\n{user_input}"

    conversation_history.append({"role": "user", "content": content})

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history,
        temperature=0.2,
        max_tokens=600
    )

    reply = response.choices[0].message.content.strip()
    conversation_history.append({"role": "assistant", "content": reply})
    return reply


def ask_xyran_with_image(user_input, image_path):
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

    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=messages,
        temperature=0,
        max_tokens=600
    )

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
            print(f"[Xyran] Ho gaya.")

        elif action == "run_multi":
            commands = [
                str(cmd).strip() for cmd in data.get("commands", [])
                if str(cmd).strip().lower() not in ("", "none", "null", "n/a", "no command")
            ]
            if not commands:
                print("\n[Xyran] Koi valid commands nahi mile, isliye main kuch run nahi kar raha.")
                return
            for cmd in commands:
                print(f"[CMD] {cmd}")
                output = run_command(cmd)
                if output and output != "Done.":
                    if len(output) > 300:
                        summary = summarize_output(output)
                        print(f"\n[Xyran] {summary}")
                    else:
                        print(f"[Output] {output}")
            print(f"[Xyran] Sab ho gaya.")

        elif action == "answer":
            message = data.get("message", "")
            print(f"\n[Xyran] {message}")

    except json.JSONDecodeError:
        print(f"\n[Xyran] {reply}")


def main():
    global last_input_used_vision, vision_followup_turns_left
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


if __name__ == "__main__":
    main()

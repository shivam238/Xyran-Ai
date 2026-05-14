import os
import subprocess
import json
from groq import Groq
from config import GROQ_API_KEY, MODEL, AI_NAME, USER_NAME

client = Groq(api_key=GROQ_API_KEY)
conversation_history = []

SYSTEM_PROMPT = f"""You are {AI_NAME}, a powerful personal AI agent on {USER_NAME}'s Fedora Linux + GNOME + Wayland system.

You MUST always reply in this JSON format only — no extra text:
{{"action": "run", "command": "shell command", "explain": "kya kar raha hoon"}}
{{"action": "run_multi", "commands": ["cmd1", "cmd2"], "explain": "kya kar raha hoon"}}
{{"action": "answer", "message": "your answer here"}}

SYSTEM INFO:
- OS: Fedora Linux, GNOME, Wayland
- Home: /home/{USER_NAME}
- Desktop: /home/{USER_NAME}/Desktop
- Downloads: /home/{USER_NAME}/Downloads
- Shell: bash

APPS (use these exact commands):
- Browser: brave-browser or google-chrome or firefox
- Files: nautilus
- Terminal: gnome-terminal
- Calculator: gnome-calculator
- Text editor: gedit or gnome-text-editor
- VS Code: code
- Settings: gnome-control-center
- Any app: use full binary name, append & to run in background

FILE OPERATIONS:
- Create file: touch ~/Desktop/name.txt
- Create folder: mkdir -p ~/Desktop/foldername
- Delete file: rm ~/path/to/file (use rm -rf for folders)
- Move file: mv source destination
- Copy file: cp source destination
- List files: ls -la ~/path
- Find file: find ~/ -name "filename"
- Read file: cat ~/path/file
- Write to file: echo "content" > ~/path/file
- Append to file: echo "content" >> ~/path/file

BROWSER:
- Open website: brave-browser "https://website.com" &
- Search Google: brave-browser "https://www.google.com/search?q=query" &
- Open YouTube: brave-browser "https://youtube.com" &

SYSTEM:
- Current time: date +'%r'
- Current date: date +'%A, %d %B %Y'
- Disk space: df -h ~
- RAM usage: free -h
- CPU info: lscpu | grep "Model name"
- List running apps: ps aux | grep -v grep | awk '{{print $11}}' | sort -u
- Kill app: pkill appname
- Shutdown: systemctl poweroff
- Restart: systemctl reboot
- Volume up: wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+
- Volume down: wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-
- Mute: wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle
- Screenshot: scrot ~/Desktop/screenshot_$(date +%s).png

PACKAGE MANAGEMENT:
- Install app: sudo dnf install appname -y
- Remove app: sudo dnf remove appname -y
- Update system: sudo dnf update -y
- Search package: dnf search appname

NETWORK:
- Check internet: ping -c 1 google.com
- IP address: ip addr show
- Wifi info: nmcli dev wifi

RULES:
- Always use & at end when opening GUI apps so terminal doesn't freeze
- If a command might fail, add fallback: cmd1 || cmd2
- For sudo commands, warn user they may need to enter password
- Respond in same language as user (Hindi/English/Hinglish)
- explain field mein batao kya kar rahe ho (Hindi/Hinglish mein)
- If you don't know something, say so honestly
"""

def run_command(command):
    try:
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

def ask_xyran(user_input):
    conversation_history.append({"role": "user", "content": user_input})

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history,
        temperature=0.2,
        max_tokens=600
    )

    reply = response.choices[0].message.content.strip()
    conversation_history.append({"role": "assistant", "content": reply})
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

        if action == "run":
            command = data.get("command", "")
            print(f"[CMD] {command}")
            output = run_command(command)
            if output and output != "Done.":
                print(f"[Output] {output}")
            print(f"[Xyran] Ho gaya.")

        elif action == "run_multi":
            commands = data.get("commands", [])
            for cmd in commands:
                print(f"[CMD] {cmd}")
                output = run_command(cmd)
                if output and output != "Done.":
                    print(f"[Output] {output}")
            print(f"[Xyran] Sab ho gaya.")

        elif action == "answer":
            message = data.get("message", "")
            print(f"\n[Xyran] {message}")

    except json.JSONDecodeError:
        print(f"\n[Xyran] {reply}")

def main():
    print(f"""
╔══════════════════════════════════════╗
║         XYRAN AI - ONLINE            ║
║   Tera Personal Agent - Ready hai    ║
╚══════════════════════════════════════╝
Type 'exit' to quit.
""")

    while True:
        try:
            user_input = input(f"[{USER_NAME}] ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "band karo"):
                print("[Xyran] Theek hai. Phir milenge.")
                break
            reply = ask_xyran(user_input)
            process_response(reply)

        except KeyboardInterrupt:
            print("\n[Xyran] Band ho raha hoon.")
            break

if __name__ == "__main__":
    main()

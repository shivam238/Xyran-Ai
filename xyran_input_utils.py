import difflib
import random
import re
import shutil

from xyran_search import (
    extract_web_search_query,
    is_web_search_request,
    resolve_website_alias,
    strip_trailing_action_clauses,
)


LOCAL_JOKES = [
    "Programmer ne paani kyu nahi piya? Kyunki usne socha bug liquid state mein bhi ho sakta hai.",
    "Ek coder bola: meri life sorted hai. Phir usne semicolon miss kar diya.",
    "Debugging wahi process hai jahan hum detective bhi hote hain aur criminal bhi.",
    "Computer ko thand kyu lag gayi? Kyunki usne Windows khuli chhod di.",
    "Code itna clean tha ki bug ko rehne ke liye alag room lena pada.",
]


def should_use_vision(user_input):
    vision_keywords = [
        "screen dekho", "kya chal raha", "kya khula", "kya dikh raha",
        "screen pe kya", "dikhao", "jo khula hai", "kon se apps",
        "can u see", "screen check", "dekh ke batao", "window mein",
        "browser mein kya", "screen pe", "kya open hai", "screen par",
        "screen pr", "screen par hai", "screen pr hai", "padho",
        "read the code", "code padh", "koi file dikh", "konsa folder",
        "kaun sa folder", "ab check", "dobara dekho", "fir dekho",
    ]
    lowered = user_input.lower()
    return any(keyword in lowered for keyword in vision_keywords)


def is_vision_followup(user_input):
    followup_keywords = [
        "haan", "batao", "btao", "padho", "check", "dekho", "dobara",
        "fir", "again", "screen pr hai", "screen par hai", "kya hai",
        "kya dikh", "koi file", "folder", "file ka naam", "kon kon",
        "kaun kaun", "isme", "usme", "waha", "vahaan", "details",
        "detail", "sari details", "sab details", "aur batao",
        "uski details", "poori details", "full details", "kya chal",
        "kya open", "kya khula", "kya chal raha",
    ]
    lowered = user_input.lower()
    return any(keyword in lowered for keyword in followup_keywords)


def is_ambiguous_short_followup(user_input):
    lowered = user_input.lower().strip()
    word_count = len(lowered.split())
    ambiguous_phrases = [
        "sari details do", "sab details do", "details do", "detail do",
        "aur batao", "aur btao", "ab batao", "ab dekho", "ab check karo",
        "ab check kro", "uski details do", "poori details do",
        "full details do", "sahi se batao",
    ]
    return word_count <= 5 and any(phrase in lowered for phrase in ambiguous_phrases)


def is_acknowledgement(user_input):
    lowered = user_input.lower().strip()
    acknowledgements = {
        "ok", "okay", "okk", "k", "kk", "haan", "hm", "hmm", "hmmm",
        "thanks", "thank you", "thx", "theek", "theek hai", "achha",
        "acha", "nice", "good", "great", "cool",
    }
    return lowered in acknowledgements


def is_greeting(user_input):
    lowered = user_input.lower().strip()
    if lowered in {"yo", "namaste", "salam"}:
        return True
    compact = re.sub(r"(.)\1+", r"\1", lowered)
    return compact in {"hi", "hello", "hey"}


def is_self_identity_request(user_input):
    """Detect questions about Xyran's own identity, creator, features, tech stack, or recent updates."""
    lowered = user_input.lower().strip()
    identity_phrases = [
        # Who are you
        "tu kya hai", "tum kya ho", "aap kya hain", "you are who", "who are you",
        "what are you", "apne baare mein batao", "apne baare me btao",
        "khud ke baare mein batao", "khud ke baare me btao",
        "apna parichay do", "apna introduction do",
        # Creator / Made by
        "kisne banaya", "kisne bnaya", "kisne create kiya", "who made you",
        "who created you", "who built you", "tujhe kisne banaya",
        "tumhe kisne banaya", "creator kaun hai", "creator kon hai",
        "banane wala kaun", "developer kaun hai", "developer kon hai",
        "shivam", "shivam kumar", "shivam mahto",
        "kaise banaya", "kese banaya", "kisne design kiya",
        # Features & abilities
        "kya kya kar sakta hai", "kya kya kr sakta hai", "teri abilities",
        "teri capabilities", "teri features", "tere features",
        "kya features hain", "kya features hai", "what can you do",
        "tumhari khaasiyat", "teri khasiyat", "teri khoobiyan",
        # Tech stack
        "kaise bana hai", "kese bana hai", "kis coding se bana", "kis language mein bana",
        "kaunsi language", "konsi language", "tech stack",
        "python se bana", "built with what", "kaunsi technology",
        "groq", "gemini", "faiss", "llama", "sentence transformer",
        "kis cheez se bana", "kaise kaam karta hai internally",
        # Version & History
        "konsa version hai", "kaun sa version", "version kya hai",
        "pehle kesa tha", "pehle kaisa tha", "pehle kya tha",
        "kab bana", "kab banaya", "when were you created", "kaise evolve kiya",
        # Self Codebase / Git Updates (strictly self-referential)
        "mere updates", "tere updates", "codebase status", "apne updates",
        "mere commits", "tere commits", "apne changes", "git log", "git status",
    ]
    # Exact single word check to avoid generic triggers on things like "updates of spotify"
    exact_match = lowered in {
        "updates", "update", "commits", "changelog", "version", "history", "git"
    }
    return exact_match or any(phrase in lowered for phrase in identity_phrases)


def get_dynamic_git_and_code_info():
    """Dynamically scan Git commits, modified files, and codebase status."""
    import subprocess
    import os
    import glob

    info = {
        "commits": [],
        "total_py_files": 0,
        "total_loc": 0,
        "dirty_files": [],
        "modules": []
    }
    
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Get recent 3 git commits
    try:
        res = subprocess.run(
            ["git", "log", "-n", "3", "--pretty=format:%s (%ar)"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=base_dir
        )
        if res.returncode == 0:
            info["commits"] = [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception:
        pass

    # 2. Get uncommitted modifications (git status)
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=base_dir
        )
        if res.returncode == 0:
            dirty = []
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2:
                    dirty.append(parts[-1])
            info["dirty_files"] = [os.path.basename(d) for d in dirty if d.endswith(".py")][:5]
    except Exception:
        pass

    # 3. Scan code base files & line count
    try:
        py_files = glob.glob(os.path.join(base_dir, "*.py"))
        info["total_py_files"] = len(py_files)
        total_lines = 0
        modules_list = []
        for pf in py_files:
            bname = os.path.basename(pf)
            modules_list.append(bname)
            try:
                with open(pf, "r", encoding="utf-8", errors="ignore") as f:
                    total_lines += len(f.readlines())
            except Exception:
                pass
        info["total_loc"] = total_lines
        info["modules"] = sorted(modules_list)
    except Exception:
        pass
        
    return info


def get_self_identity_reply(user_input):
    """Return an instant Hinglish self-awareness reply based on the question type."""
    import json
    import os

    # Load dynamic identity config
    config_path = os.path.join(os.path.dirname(__file__), "xyran_identity.json")
    cfg = None
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass

    lowered = user_input.lower().strip()

    # Get dynamic Git and codebase status
    dyn = get_dynamic_git_and_code_info()
    dyn_str = ""
    if dyn:
        dyn_str += "\n\n📊 *Real-time Codebase Status (Dynamic Scan):*"
        dyn_str += f"\n- Mere paas abhi total **{dyn['total_py_files']} active Python modules** hain (total **{dyn['total_loc']} lines of code**)."
        
        if dyn["commits"]:
            dyn_str += "\n- Recent changes Shivam Kumar Mahto ne jo push kiye:"
            for i, commit in enumerate(dyn["commits"], 1):
                dyn_str += f"\n  {i}. {commit}"
                
        if dyn["dirty_files"]:
            dyn_str += f"\n- Active development files (uncommitted): {', '.join(dyn['dirty_files'])}"

    # Special case: Explicitly asking for updates, changes, commits, or status
    if any(w in lowered for w in ["update", "changes", "change", "commit", "status", "git"]):
        if dyn:
            reply = "Haan ji! Maine dynamic codebase aur Git repository status scan kiya hai. 😎"
            reply += dyn_str
            return reply
        return "Abhi tak koi naye updates nahi mile hain, main stable v1.0 version par run kar raha hoon! 🚀"

    # Creator questions
    if any(w in lowered for w in ["kisne banaya", "kisne bnaya", "kisne create", "who made", "who created", "who built", "creator", "developer", "shivam", "design kiya"]):
        if cfg:
            return (
                f"Mujhe {cfg.get('created_by', 'Shivam Kumar Mahto')} ne banaya hai! 🙌 Unka GitHub handle hai `{cfg.get('github', 'shivam238')}`. "
                f"Unhone {cfg.get('created_date', 'May 2026')} mein ek simple chatbot ko ek full self-aware AI agent mein "
                f"transform kiya — aur yeh result hai: Main, {cfg.get('name', 'Xyran')}! 🌌 Repo link: {cfg.get('repo', '')}"
            )
        return (
            "Mujhe Shivam Kumar Mahto ne banaya hai! 🙌 Unka GitHub handle hai `shivam238`. "
            "Unhone May 2026 mein ek simple chatbot ko ek full self-aware AI agent mein "
            "transform kiya — aur yeh result hai: Main, Xyran! 🌌"
        )

    # Version / history questions
    if any(w in lowered for w in ["version", "pehle kaisa", "pehle kesa", "pehle kya tha", "kab bana", "evolve", "history"]):
        if cfg and "changelog" in cfg:
            changelog_lines = ["Meri journey kuch aisi rahi hai:"]
            for log in cfg["changelog"]:
                changes_str = "\n  * ".join(log.get("changes", []))
                changelog_lines.append(f"🔹 {log.get('label', '')} ({log.get('date', '')}):\n  * {changes_str}")
            return "\n".join(changelog_lines)
        return (
            "Meri journey kuch aisi rahi hai:\n"
            "🔹 v0 (Early): Ek simple single-file chatbot tha. Bas API se sawaalon ke jawaab deta tha. "
            "Na koi memory, na koi automation, na vision.\n"
            "🔹 v0.5: Basic shell command execution add hua. Apps khol sakta tha, screenshots le sakta tha.\n"
            "🔹 v1.0 (May 2026 — Current): Full modular agentic system! Ab mujhe dual memory hai "
            "(FAISS vector + SQLite), real-time vision, hybrid LLM routing, multi-step execution engine, "
            "weather, news, image generation — sab kuch! 🚀"
        )

    # Tech stack questions
    if any(w in lowered for w in ["kaise bana", "kese bana", "kis coding", "kis language", "tech stack", "python", "groq", "gemini", "faiss", "llama", "sentence", "technology", "built with", "internally"]):
        if cfg and "tech_stack" in cfg:
            ts = cfg["tech_stack"]
            providers = ", ".join(ts.get("llm_providers", []))
            return (
                f"Main {ts.get('language', 'Python 3.10+')} se bana hoon! 🐍 Mera complete tech stack:\n"
                f"🧠 LLM: {providers}\n"
                f"👁️ Vision: {ts.get('vision_model', '')}\n"
                f"🗃️ Vector Memory: {ts.get('vector_memory', '')}\n"
                f"💾 Relational Memory: {ts.get('relational_memory', '')}\n"
                f"📸 Screenshots: {ts.get('screenshot', '')}\n"
                f"🚀 App Launch: {ts.get('app_launching', '')}\n"
                f"🌐 Web Data: {ts.get('web_data', '')}\n"
                f"🎨 Image Gen: {ts.get('image_generation', '')}\n"
                f"✨ Terminal UX: {ts.get('terminal_ux', '')}\n"
                f"💻 OS Support: {ts.get('os_support', '')}"
            )
        return (
            "Main Python 3.10+ se bana hoon! 🐍 Mera complete tech stack:\n"
            "🧠 LLM: Groq API (llama-3.3-70b) + Google Gemini API\n"
            "👁️ Vision: Llama 4 Scout Vision model (Groq)\n"
            "🗃️ Vector Memory: FAISS + SentenceTransformers (all-MiniLM-L6-v2 from HuggingFace)\n"
            "💾 Relational Memory: SQLite (Python sqlite3)\n"
            "📸 Screenshots: D-Bus / Freedesktop XDG Portal (Wayland native)\n"
            "🚀 App Launch: gtk-launch + subprocess.Popen\n"
            "🌐 Web Data: urllib.request (weather via wttr.in, news via NewsAPI)\n"
            "🎨 Image Gen: Custom modules/image_gen/ module\n"
            "✨ Terminal UX: threading.Thread (ThinkingSpinner)"
        )

    # Features / abilities questions
    if any(w in lowered for w in ["kya kya kar", "abilities", "capabilities", "features", "khasiyat", "khoobiyan", "what can you"]):
        if cfg and "features" in cfg:
            feature_lines = ["Yeh hain meri top abilities! 💪"]
            for f in cfg["features"]:
                feature_lines.append(f"{f.get('emoji', '🔹')} {f.get('name', '')} — {f.get('description', '')}")
            return "\n".join(feature_lines)
        return (
            "Yeh hain meri top abilities! 💪\n"
            "🧠 Dual Memory — FAISS vector index + SQLite facts DB. Tumhari preferences yaad rakhta hoon.\n"
            "👁️ Real-Time Vision — Screen dekh sakta hoon via Wayland native portal + Vision LLM.\n"
            "⚡ Smart Routing — Simple tasks ke liye LLM bypass, complex ke liye full AI brain.\n"
            "🖥️ System Control — Volume, brightness, DND, keyboard backlight, apps open/close.\n"
            "🌐 Multi-step Engine — 2-10 actions ek saath execute karta hoon with timing.\n"
            "🌦️ Live Weather — wttr.in se real-time mausam (no API key needed).\n"
            "📰 News — NewsAPI se live headlines, category/country filter ke saath.\n"
            "🎨 Image Generation — AI images bana sakta hoon.\n"
            "💬 Hinglish Personality — Tumhari boli mein baat karta hoon.\n"
            "🔄 Hybrid LLM — Groq (fast) / Gemini (vision/complex) / Ollama (offline fallback)."
        )

    # General "what are you" / "who are you"
    if cfg:
        return (
            f"Main {cfg.get('name', 'Xyran')} hoon — {cfg.get('description', 'ek self-aware, locally-integrated personal AI agent')}! 🌌\n"
            f"Mujhe {cfg.get('created_date', 'May 2026')} mein {cfg.get('created_by', 'Shivam Kumar Mahto')} ne banaya tha. "
            "Main sirf ek chatbot nahi hoon — mujhe apna itihaas pata hai, apni abilities pata hain, "
            "aur main khud ke baare mein poori detail mein bata sakta hoon. "
            "Mujhse pooch — kis cheez se bana hoon, kya kar sakta hoon, pehle kesa tha — sab bataoonga! 😎"
        )
    return (
        "Main Xyran hoon — ek self-aware, locally-integrated personal AI agent! 🌌\n"
        "Mujhe May 2026 mein Shivam Kumar Mahto ne banaya tha. "
        "Main sirf ek chatbot nahi hoon — mujhe apna itihaas pata hai, apni abilities pata hain, "
        "aur main khud ke baare mein poori detail mein bata sakta hoon. "
        "Mujhse pooch — kis cheez se bana hoon, kya kar sakta hoon, pehle kesa tha — sab bataoonga! 😎"
    )


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
    open_words = [
        "open", "khol", "khol do", "kholo", "kholo na", "kholna",
        "open karo", "open kr", "open kar", "open krna", "open karna",
    ]
    return any(word in lowered for word in open_words)


def extract_requested_app_name(user_input):
    lowered = user_input.lower().strip()
    patterns = [
        (r"^(.*?)\s+(open|open kr|open kar|open krna|open karna|open karo|khol|khol do|kholo|kholo na|kholna)$", 1),
        (r"^(open|open kr|open kar|open krna|open karna|open karo|khol|khol do|kholo|kholo na|kholna)\s+(.+)$", 2),
    ]
    for pattern, group_index in patterns:
        match = re.search(pattern, lowered)
        if match:
            candidate = match.group(group_index)
            candidate = re.sub(r"\b(app|application)\b", "", candidate).strip()
            candidate = strip_trailing_action_clauses(
                candidate,
                strip_search=True,
                strip_write=True,
            )
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


def resolve_app_alias(requested_app):
    aliases = get_app_aliases()
    alias_key = requested_app
    if alias_key not in aliases:
        close_matches = difflib.get_close_matches(alias_key, list(aliases.keys()), n=1, cutoff=0.72)
        if not close_matches:
            return None, None
        alias_key = close_matches[0]
    return alias_key, aliases[alias_key]


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
    phrases = [
        "show screenshot",
        "show the screenshot",
        "open screenshot",
        "open the screenshot",
        "screenshot dikha",
        "screenshot dikhao",
        "screenshot show",
        "screenshot open",
        "screenshot khol",
        "screenshot kholo",
        "open it",
        "show it",
        "dikha it",
        "dikhao it",
        "isko kholo",
        "isko dikhao",
    ]
    if any(phrase in lowered for phrase in phrases):
        return True
    return re.search(
        r"\b(?:show|open|dikha|dikhao|khol|kholo)\s+(?:it|isko|screenshot)\b",
        lowered,
        re.IGNORECASE,
    ) is not None


def is_text_editor_request(user_input):
    lowered = user_input.lower()
    editor_words = [
        "text editor", "editor", "gedit", "gnome-text-editor",
        "notepad", "notpad", "notrpad", "notepad",
    ]
    open_words = ["open", "khol", "khol do", "kholde", "open kr", "open karo"]
    write_words = ["likh", "likho", "likhna", "write", "type"]
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
        r"write\s+(?:the\s+)?(?:word|text|line)\s+(.+?)\s+on\s+(?:notepad|notpad|notrpad|text editor|editor)$",
        r"type\s+(?:the\s+)?(?:word|text|line)\s+(.+?)\s+on\s+(?:notepad|notpad|notrpad|text editor|editor)$",
        r"(.+?)\s+likhna\s+(?:notepad|notpad|notrpad|notepad|text editor|editor)(?:\s+(?:me|mein))?(?:\s+(?:ke|and|aur|or)\s+.+)?$",
        r"likh\s+(?!ke\b|and\b|aur\b)(.+)$",
        r"likho\s+(?!ke\b|and\b|aur\b)(.+)$",
        r"likhna\s+(?!ke\b|and\b|aur\b)(.+)$",
        r"write\s+(?!and\b)(.+)$",
        r"type\s+(?!and\b)(.+)$",
        r"(.+?)\s+likh(?:\s+(?:ke|and|aur)\s+.+)?$",
        r"(.+?)\s+likho(?:\s+(?:ke|and|aur)\s+.+)?$",
        r"(.+?)\s+likhna(?:\s+(?:ke|and|aur|or)\s+.+)?$",
        r"(.+?)\s+write(?:\s+(?:ke|and|aur)\s+.+)?$",
        r"(.+?)\s+type(?:\s+(?:ke|and|aur)\s+.+)?$",
        r"(.+?)\s+likh$",
        r"(.+?)\s+likho$",
        r"(.+?)\s+likhna$",
        r"(.+?)\s+write$",
        r"(.+?)\s+type$",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_input, re.IGNORECASE)
        if match:
            text = match.group(1).strip().strip("\"'")
            if text:
                cleanup_patterns = [
                    r"^(text editor|editor|gedit|gnome-text-editor|notepad|notpad|notrpad|notepad)\s+",
                    r"^(open karo|open kr|open|khol do|kholde|kholo|khol ke|kholke|khol)\s+",
                    r"^ke\s+",
                    r"^do\s+",
                    r"^(me|mein)\s+",
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
                text = strip_trailing_action_clauses(text, strip_search=False, strip_write=False)
                text = re.sub(
                    r"\s+(?:notepad|notpad|notrpad|notepad|text editor|editor)\s+(?:me|mein)$",
                    "",
                    text,
                    flags=re.IGNORECASE,
                ).strip()
                text = re.sub(
                    r"^(?:the\s+)?(?:word|text|line)\s+",
                    "",
                    text,
                    flags=re.IGNORECASE,
                ).strip()
                text = re.sub(
                    r"\s+on\s+(?:notepad|notpad|notrpad|text editor|editor)$",
                    "",
                    text,
                    flags=re.IGNORECASE,
                ).strip()
            if text:
                return text
    return None


def get_available_text_editor():
    for candidate in ["gnome-text-editor", "gedit"]:
        if shutil.which(candidate):
            return candidate
    return None


def extract_python_code_request(user_input):
    lowered = user_input.lower()
    if "hello print" in lowered or "print hello" in lowered:
        return 'print("hello")'
    if "hello world print" in lowered or "print hello world" in lowered:
        return 'print("hello world")'
    return None


def extract_code_topic_request(user_input):
    lowered = user_input.lower().strip()
    match = re.search(r"(.+?)\s+(?:kaa|ka|ki|kaa)\s+code\b", lowered)
    if match:
        topic = match.group(1).strip()
        topic = re.sub(
            r"^(?:open|open karo|open kr|khol|khol do|kholo|notepad|editor|text editor)\s+",
            "",
            topic,
            flags=re.IGNORECASE,
        ).strip()
        topic = strip_trailing_action_clauses(
            topic,
            strip_search=False,
            strip_write=False,
        )
        topic = re.sub(
            r"\b(?:implementation|implimentation|implimentaation|implementaion|implement)\b",
            "",
            topic,
            flags=re.IGNORECASE,
        ).strip()
        if topic:
            return " ".join(topic.split())
    return None


def extract_generated_note_request(user_input):
    lowered = user_input.lower().strip()
    patterns = [
        (r"(?:can u|can you|please)?\s*write\s+a\s+paragraph\s+on\s+(.+?)(?:\s+on\s+(?:notepad|notpad|notrpad|text editor|editor))?$", "paragraph"),
        (r"(.+?)\s+par\s+paragraph\s+likh(?:o|na)?(?:\s+(?:notepad|notpad|notrpad|text editor|editor)(?:\s+(?:me|mein))?)?$", "paragraph"),
        (r"(?:can u|can you|please)?\s*write\s+an?\s+essay\s+on\s+(.+?)(?:\s+on\s+(?:notepad|notpad|notrpad|text editor|editor))?$", "essay"),
        (r"(?:can u|can you|please)?\s*write\s+notes?\s+on\s+(.+?)(?:\s+on\s+(?:notepad|notpad|notrpad|text editor|editor))?$", "notes"),
        (r"(.+?)\s+ke\s+notes?\s+likh(?:o|na)?(?:\s+(?:notepad|notpad|notrpad|text editor|editor)(?:\s+(?:me|mein))?)?$", "notes"),
    ]
    for pattern, content_type in patterns:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if not match:
            continue
        topic = match.group(1).strip().strip("\"'")
        topic = strip_trailing_action_clauses(topic, strip_search=False, strip_write=False)
        topic = re.sub(
            r"\s+(?:on|in)\s+(?:notepad|notpad|notrpad|text editor|editor)$",
            "",
            topic,
            flags=re.IGNORECASE,
        ).strip()
        if topic:
            return {"type": content_type, "topic": " ".join(topic.split())}
    return None


def generate_code_from_topic(user_input):
    topic = extract_code_topic_request(user_input)
    if not topic:
        return None

    if "binary search tree" in topic or topic == "bst":
        return """class Node:
    def __init__(self, value):
        self.value = value
        self.left = None
        self.right = None


class BinarySearchTree:
    def __init__(self):
        self.root = None

    def insert(self, value):
        if self.root is None:
            self.root = Node(value)
            return
        self._insert_recursive(self.root, value)

    def _insert_recursive(self, current, value):
        if value < current.value:
            if current.left is None:
                current.left = Node(value)
            else:
                self._insert_recursive(current.left, value)
        else:
            if current.right is None:
                current.right = Node(value)
            else:
                self._insert_recursive(current.right, value)

    def inorder(self):
        result = []
        self._inorder_recursive(self.root, result)
        return result

    def _inorder_recursive(self, current, result):
        if current is None:
            return
        self._inorder_recursive(current.left, result)
        result.append(current.value)
        self._inorder_recursive(current.right, result)

    def search(self, value):
        return self._search_recursive(self.root, value)

    def _search_recursive(self, current, value):
        if current is None:
            return False
        if current.value == value:
            return True
        if value < current.value:
            return self._search_recursive(current.left, value)
        return self._search_recursive(current.right, value)


bst = BinarySearchTree()
for item in [50, 30, 70, 20, 40, 60, 80]:
    bst.insert(item)

print("Inorder traversal:", bst.inorder())
print("Search 40:", bst.search(40))
print("Search 90:", bst.search(90))
"""

    if "stack" in topic:
        return """class Stack:
    def __init__(self):
        self.items = []

    def push(self, value):
        self.items.append(value)

    def pop(self):
        if self.is_empty():
            return None
        return self.items.pop()

    def peek(self):
        if self.is_empty():
            return None
        return self.items[-1]

    def is_empty(self):
        return len(self.items) == 0

    def size(self):
        return len(self.items)


stack = Stack()
stack.push(10)
stack.push(20)
stack.push(30)

print("Top item:", stack.peek())
print("Popped item:", stack.pop())
print("Stack size:", stack.size())
print("Is empty:", stack.is_empty())
"""

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
        "majak suna", "funny bol", "hasao", "make me laugh",
    ]
    return any(phrase in lowered for phrase in phrases)


def get_local_joke(pyjokes_module):
    if pyjokes_module:
        try:
            return pyjokes_module.get_joke()
        except Exception:
            pass
    return random.choice(LOCAL_JOKES)


def is_news_request(user_input):
    lowered = user_input.lower().strip()
    return "news" in lowered or "headlines" in lowered


def is_more_news_request(user_input, has_last_query):
    lowered = user_input.lower().strip()
    phrases = [
        "more news", "aur news", "next news", "next headlines",
        "more headlines", "aur headlines", "dusri news", "doosri news",
        "agli news",
    ]
    short_followups = {"next", "aur", "more", "dusri", "doosri", "agli"}
    if lowered in short_followups:
        return has_last_query
    return any(phrase in lowered for phrase in phrases)


def is_news_summary_request(user_input, has_last_news_articles):
    lowered = user_input.lower().strip()
    # Writing/editor requests should never be hijacked by news summary intent.
    write_words = [
        "likh", "likho", "write", "type", "notepad",
        "editor", "text editor", "gnome-text-editor",
    ]
    if any(word in lowered for word in write_words):
        return False

    summary_words = [
        "summary", "summarize", "explain", "detail", "details",
        "samjha", "samjhao", "detail mein", "brief", "gist",
    ]
    reference_words = [
        "news", "headline", "article", "pehli", "dusri", "doosri",
        "teesri", "fourth", "fifth", "first", "second", "third",
        "1", "2", "3", "4", "5",
    ]
    has_summary_word = any(word in lowered for word in summary_words)
    has_reference_word = any(word in lowered for word in reference_words)
    short_followup_words = {
        "summary", "summarize", "explain", "detail", "details",
        "brief", "gist", "samjha", "samjhao",
    }

    # Allow short follow-ups like "summary" only when news context exists.
    if has_last_news_articles and lowered in short_followup_words:
        return True

    return has_summary_word and has_reference_word


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
        lowered,
    )
    query_cleanup = " ".join(query_cleanup.split()).strip()
    if query_cleanup and query_cleanup not in categories and query_cleanup not in countries:
        params["q"] = query_cleanup

    return params


def is_api_status_query(user_input):
    lowered = user_input.lower().strip()
    phrases = [
        "api aa gya hai", "api aa gaya hai", "api aagya hai",
        "api back hai", "api wapas aayi", "api chal rahi hai",
        "is api back", "api back",
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
    browser_words = ["browser", "brave", "firefox", "chrome", "google chrome", "web browser"]
    return any(word in lowered for word in open_words) and any(word in lowered for word in browser_words)


def extract_explicit_website_target(user_input):
    lowered = user_input.lower().strip()
    url_match = re.search(r"(https?://[^\s]+)", lowered)
    if url_match:
        return url_match.group(1)

    domain_match = re.search(r"\b(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+\b", lowered)
    if domain_match:
        return domain_match.group(0)

    return None


def is_explicit_website_request(user_input):
    lowered = user_input.lower().strip()
    open_words = ["open", "khol", "khol do", "kholo", "open karo", "open kr"]
    website_words = ["website", "site", "web site", "url", "link", "webpage", "web page"]
    return any(word in lowered for word in open_words) and (
        any(word in lowered for word in website_words) or extract_explicit_website_target(lowered) is not None
    )


def is_ambiguous_open_request(user_input):
    lowered = user_input.lower().strip()
    if not is_app_launch_request(lowered):
        return False
    if any(
        check(lowered) for check in (
            is_open_youtube_request,
            is_web_search_request,
            is_browser_open_request,
            is_files_open_request,
            is_text_editor_request,
            is_screenshot_request,
        )
    ):
        return False

    requested_app = extract_requested_app_name(lowered)
    if not requested_app:
        return False
    if resolve_app_alias(requested_app)[1]:
        return False
    if is_explicit_website_request(lowered):
        return False
    return True


def wants_new_tab(user_input):
    lowered = user_input.lower().strip()
    phrases = [
        "new tab", "naye tab", "naya tab", "dusre tab", "doosre tab",
        "another tab", "second tab", "alag tab",
    ]
    return any(phrase in lowered for phrase in phrases)


def extract_dnd_action(user_input, last_user_input=None, prev_action_category=None):
    lowered = user_input.lower().strip()
    off_words = ["off", "disable", "band", "deactivate", "stop", "hatado", "hata do", "bnd"]
    on_words = ["on", "enable", "chalu", "activate", "start", "lga", "laga"]
    
    dnd_match = any(word in lowered for word in ["do not disturb", "dnd", "disturb"])
    is_ambiguous_toggle = lowered in [
        "on", "off", "chalu", "band", "bnd", "on kr", "off kr", "chalu kr", 
        "band kr", "bnd kr", "on karo", "off karo", "band karo", "bnd karo", 
        "bnd krde", "band krde"
    ]
    
    if not (dnd_match or (is_ambiguous_toggle and prev_action_category == "dnd")):
        return None
        
    for word in off_words:
        if word in lowered:
            return "off"
    for word in on_words:
        if word in lowered:
            return "on"
            
    if last_user_input:
        last_lowered = last_user_input.lower().strip()
        for word in off_words:
            if word in last_lowered:
                return "off"
        for word in on_words:
            if word in last_lowered:
                return "on"
                
    return "on"


def is_dnd_request(user_input, prev_action_category=None):
    return extract_dnd_action(user_input, prev_action_category=prev_action_category) is not None


def extract_keyboard_light_action(user_input, last_user_input=None, prev_action_category=None):
    lowered = user_input.lower().strip()
    
    # Negative checks to avoid screen brightness or volume conflict
    if any(word in lowered for word in ["screen", "display", "monitor", "screen light", "screen brightness", "volume", "sound", "awaj", " आवाज"]):
        return None
        
    kb_keywords = ["keyboard", "kbd", "key board"]
    light_keywords = ["light", "brightness", "backlight", "chalu", "band", "dim", "bright", "full", "half", "medium", "percent", "%", "kam", "badha"]
    
    kb_match = any(word in lowered for word in kb_keywords)
    light_match = any(word in lowered for word in light_keywords)
    
    is_ambiguous_toggle = lowered in [
        "on", "off", "chalu", "band", "bnd", "on kr", "off kr", "chalu kr", 
        "band kr", "bnd kr", "on karo", "off karo", "band karo", "bnd karo", 
        "bnd krde", "band krde"
    ]
    
    # Check if context-aware follow-up
    is_followup = False
    if prev_action_category == "keyboard":
        followup_keywords = light_keywords + ["on", "off", "kr", "kar", "chalu", "band", "karo", "krde"]
        is_followup = any(word in lowered for word in followup_keywords) or any(char.isdigit() for char in lowered)
        
    if not ((kb_match and (light_match or "wali" in lowered or "ki" in lowered)) or is_followup or (is_ambiguous_toggle and prev_action_category == "keyboard")):
        return None
        
    off_words = ["off", "disable", "band", "deactivate", "stop", "hatado", "hata do", "zero", "bnd"]
    on_words = ["on", "enable", "chalu", "activate", "start", "lga", "laga", "full", "dim", "bright", "half", "medium", "percent", "%", "kam", "badha"]
    
    for word in off_words:
        if word in lowered:
            return "off"
    for word in on_words:
        if word in lowered:
            return "on"
            
    if last_user_input:
        last_lowered = last_user_input.lower().strip()
        for word in off_words:
            if word in last_lowered:
                return "off"
        for word in on_words:
            if word in last_lowered:
                return "on"
                
    return "on"


def extract_keyboard_light_brightness(user_input, last_user_input=None, prev_action_category=None):
    lowered = user_input.lower().strip()
    match = re.search(r"(\d+)\s*%?", lowered)
    if match:
        val = int(match.group(1))
        if 0 <= val <= 100:
            return val
            
    # Check semantic adjustment keywords
    if any(word in lowered for word in ["dim", "kam", "decrease", "down", "ghata"]):
        return 30
    if any(word in lowered for word in ["medium", "half", "50"]):
        return 50
    if any(word in lowered for word in ["bright", "full", "max", "badha", "increase", "up"]):
        return 100
        
    action = extract_keyboard_light_action(user_input, last_user_input, prev_action_category)
    if action == "off":
        return 0
    return 100


def is_keyboard_light_request(user_input, prev_action_category=None):
    return extract_keyboard_light_action(user_input, prev_action_category=prev_action_category) is not None


# ---------------------------------------------------------------------------
# Screen Brightness helpers (intel_backlight via sysfs)
# ---------------------------------------------------------------------------

SCREEN_BACKLIGHT_PATH = "/sys/class/backlight/intel_backlight"


def is_screen_brightness_request(user_input, prev_action_category=None):
    """Returns True if user is asking to adjust screen/display brightness."""
    lowered = user_input.lower().strip()
    
    # If they explicitly mention keyboard/backlight or volume, it's not a screen request
    if any(w in lowered for w in ["keyboard", "kbd", "key board", "backlight", "volume", "sound", "awaj", " आवाज", "audio"]):
        return False
        
    # Check if context-aware follow-up
    if prev_action_category == "screen":
        followup_keywords = ["kam", "badha", "ghata", "full", "half", "medium", "zero", 
                             "dim", "bright", "percent", "%", "on", "off", "chalu", "band", "bnd"]
        if any(w in lowered for w in followup_keywords) or any(char.isdigit() for char in lowered):
            return True

    screen_keywords = ["screen", "display", "monitor", "laptop screen", "brightness"]
    brightness_keywords = ["brightness", "bright", "dim", "brightness", "kam", "badha",
                           "percent", "%", "full", "half", "medium", "zero", "min", "max"]
    has_screen = any(w in lowered for w in screen_keywords)
    has_brightness = any(w in lowered for w in brightness_keywords)
    return has_screen and has_brightness


def extract_screen_brightness_percent(user_input, current_percent=None):
    """
    Returns desired brightness as a percentage (0–100).
    Parses explicit numbers, or maps semantic words.
    If current_percent is provided, handles relative 'or/aur kam/badha' adjustments.
    """
    lowered = user_input.lower().strip()
    # Explicit percentage / number
    match = re.search(r"(\d+)\s*%?", lowered)
    if match:
        val = int(match.group(1))
        if 0 <= val <= 100:
            return val

    # Relative step: "or kam", "aur kam", "thoda aur kam", "or badha" etc.
    has_relative = any(w in lowered for w in ["or", "aur", "thoda", "bhi"])
    if has_relative and current_percent is not None:
        if any(w in lowered for w in ["kam", "decrease", "down", "ghata", "dim", "low"]):
            return max(5, current_percent - 15)
        if any(w in lowered for w in ["badha", "increase", "up", "bright", "zyada"]):
            return min(100, current_percent + 15)

    # Semantic keywords (fixed presets)
    if any(w in lowered for w in ["zero", "off", "minimum", "min"]):
        return 5      # don't go full-zero on screen (unusable)
    if any(w in lowered for w in ["dim", "kam", "decrease", "down", "ghata", "low"]):
        return 30
    if any(w in lowered for w in ["medium", "half"]):
        return 50
    if any(w in lowered for w in ["full", "max", "maximum", "badha", "increase", "up", "bright"]):
        return 100
    return 50         # safe default


def get_screen_max_brightness():
    """Read max_brightness from sysfs."""
    try:
        with open(f"{SCREEN_BACKLIGHT_PATH}/max_brightness") as f:
            return int(f.read().strip())
    except Exception:
        return 21333  # fallback for this system


def percent_to_screen_raw(percent):
    """Convert 0-100% to raw brightness value."""
    max_val = get_screen_max_brightness()
    return max(0, int(round(percent / 100.0 * max_val)))


# ---------------------------------------------------------------------------
# Weather helpers
# ---------------------------------------------------------------------------

def is_weather_request(user_input):
    """Returns True if user is asking about weather/mausam."""
    lowered = user_input.lower().strip()
    weather_keywords = [
        "mausam", "weather", "temperature", "garmi", "sardi", "barish",
        "baarish", "aaj ka mausam", "kal ka mausam", "kaisa mausam",
        "kitni garmi", "kitni sardi", "rain", "sunny", "cloudy", "storm",
        "humidity", "aandhi", "toofan", "dhoop", "mausm", "mosam",
    ]
    return any(kw in lowered for kw in weather_keywords)


def extract_weather_city(user_input):
    """Extract city name from weather request. Returns None if not found."""
    lowered = user_input.lower().strip()

    # Remove filler words to isolate city
    noise_words = [
        "aaj", "kal", "parso", "ka", "ki", "ke", "mausam", "weather",
        "temperature", "kaisa", "kesa", "hai", "batao", "btao", "bata",
        "check", "dekho", "mein", "me", "pe", "par", "today", "tomorrow",
        "tell", "me", "the", "what", "is", "how", "barish", "baarish",
        "garmi", "sardi", "kitni", "how", "much",
    ]

    city_patterns = [
        r"(?:mausam|weather)\s+(?:of|in|ka|ki|ke|mein|me)\s+([a-z\s]+?)(?:\s+(?:kaisa|kesa|hai|batao|btao|bata|check|dekho))?$",
        r"([a-z\s]+?)\s+(?:mein|me|pe|par|ka|ki|ke)\s+(?:mausam|weather)",
        r"(?:in|of)\s+([a-z\s]+?)(?:\s+(?:weather|mausam|temperature))?$",
    ]
    for pattern in city_patterns:
        match = re.search(pattern, lowered)
        if match:
            city = match.group(1).strip()
            city = " ".join(w for w in city.split() if w not in noise_words)
            if city and len(city) > 1:
                return city.title()
    return None



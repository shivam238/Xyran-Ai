import difflib
import random
import re
import shutil


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
        r"likh\s+(?!ke\b|and\b|aur\b)(.+)$",
        r"likho\s+(?!ke\b|and\b|aur\b)(.+)$",
        r"write\s+(?!and\b)(.+)$",
        r"type\s+(?!and\b)(.+)$",
        r"(.+?)\s+likh(?:\s+(?:ke|and|aur)\s+.+)?$",
        r"(.+?)\s+likho(?:\s+(?:ke|and|aur)\s+.+)?$",
        r"(.+?)\s+write(?:\s+(?:ke|and|aur)\s+.+)?$",
        r"(.+?)\s+type(?:\s+(?:ke|and|aur)\s+.+)?$",
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

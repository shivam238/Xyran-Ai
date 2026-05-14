import difflib
import re


OPEN_WORD_PATTERN = r"(?:open|open karo|open kr|open kar|open krna|open karna|khol|khol do|kholo|kholo na|kholna)"
CONNECTOR_PATTERN = r"(?:and|aur|phir)"
BROWSER_TARGET_PATTERN = r"(?:google|browser|web browser|chrome|google chrome|firefox|brave)"

WEBSITE_ALIASES = {
    "amazon": "amazon.in",
    "aternos": "aternos.org",
    "chatgpt": "chatgpt.com",
    "claude": "claude.ai",
    "discord": "discord.com/app",
    "drive": "drive.google.com",
    "facebook": "facebook.com",
    "figma": "figma.com",
    "flipkart": "flipkart.com",
    "gemini": "gemini.google.com",
    "github": "github.com",
    "gmail": "mail.google.com",
    "google": "google.com",
    "google drive": "drive.google.com",
    "google gemini": "gemini.google.com",
    "instagram": "instagram.com",
    "insta": "instagram.com",
    "leetcode": "leetcode.com",
    "linkedin": "linkedin.com",
    "messenger": "messenger.com",
    "netflix": "netflix.com",
    "notion": "notion.so",
    "openai": "openai.com",
    "perplexity": "perplexity.ai",
    "reddit": "reddit.com",
    "spotify": "open.spotify.com",
    "stack overflow": "stackoverflow.com",
    "stackoverflow": "stackoverflow.com",
    "telegram": "web.telegram.org",
    "twitter": "x.com",
    "whatsapp": "web.whatsapp.com",
    "whatsapp web": "web.whatsapp.com",
    "x": "x.com",
    "youtube": "youtube.com",
    "yt": "youtube.com",
}

SCREENSHOT_TRAILING_PATTERNS = [
    r"\s+(?:and|aur|phir)\s+(?:uska\s+|iska\s+|ek\s+|bhi\s+)*(?:take|lelo|le lo|capture)\s+(?:a\s+)?screenshot(?:\s+.*)?$",
    r"\s+(?:and|aur|phir)\s+(?:uska\s+|iska\s+|ek\s+|bhi\s+)*(?:a\s+)?screenshot\s+(?:lelo|le lo|leke|lekar|le kr|open|show|dikha|dikhao|khol|kro|karo)(?:\s+.*)?$",
    r"\s+(?:and|aur|phir)\s+(?:a\s+)?screenshot\s+(?:le|lelo|le lo|leke|lekar|le kr)(?:\s+.*)?$",
]

OPEN_TRAILING_PATTERNS = [
    r"\s+(?:and|aur|phir)\s+(?:open|show|dikha|dikhao|khol)(?:\s+.*)?$",
]

SEARCH_TRAILING_PATTERNS = [
    r"\s+(?:and|aur|phir)\s+(?:google\s+)?search\s+.+$",
    r"\s+(?:and|aur|phir)\s+.+?\s+google\s+pe\s+search\s+karo(?:\s+.*)?$",
    r"\s+(?:and|aur|phir)\s+.+?\s+search\s+karo(?:\s+.*)?$",
]

WRITE_TRAILING_PATTERNS = [
    r"\s+(?:and|aur|phir)\s+(?:write|type|likh|likho)\s+.+$",
]


def strip_trailing_action_clauses(
    text,
    *,
    strip_screenshot=True,
    strip_open=True,
    strip_search=False,
    strip_write=False,
):
    if not text:
        return text

    patterns = []
    if strip_screenshot:
        patterns.extend(SCREENSHOT_TRAILING_PATTERNS)
    if strip_open:
        patterns.extend(OPEN_TRAILING_PATTERNS)
    if strip_search:
        patterns.extend(SEARCH_TRAILING_PATTERNS)
    if strip_write:
        patterns.extend(WRITE_TRAILING_PATTERNS)

    cleaned = " ".join(text.split()).strip()
    changed = True
    while changed:
        changed = False
        for pattern in patterns:
            updated = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
            if updated != cleaned:
                cleaned = updated
                changed = True
    return cleaned


def get_website_aliases():
    return dict(WEBSITE_ALIASES)


def resolve_website_alias(requested_target):
    aliases = get_website_aliases()
    alias_key = strip_trailing_action_clauses(
        requested_target.lower().strip(),
        strip_search=True,
        strip_write=True,
    )
    if alias_key in aliases:
        return alias_key, aliases[alias_key]

    close_matches = difflib.get_close_matches(alias_key, list(aliases.keys()), n=1, cutoff=0.84)
    if not close_matches:
        return None, None
    alias_key = close_matches[0]
    return alias_key, aliases[alias_key]


def has_action_connector(user_input):
    lowered = user_input.lower().strip()
    return re.search(r"\b(?:and|aur|phir)\b", lowered) is not None


def search_consumes_open_phrase(user_input):
    lowered = user_input.lower().strip()
    pattern = (
        rf"^{OPEN_WORD_PATTERN}\s+{BROWSER_TARGET_PATTERN}\s+"
        rf"(?:{CONNECTOR_PATTERN}\s+)?search\b"
    )
    return re.search(pattern, lowered, re.IGNORECASE) is not None


def extract_web_search_query(user_input):
    lowered = user_input.lower().strip()
    patterns = [
        rf"^{OPEN_WORD_PATTERN}\s+{BROWSER_TARGET_PATTERN}\s+(?:{CONNECTOR_PATTERN}\s+)?search\s+(.+)$",
        r"^(?:google\s+)?search\s+(?:kro|karo)\s+(.+)$",
        r"^(?:google\s+)?search\s+(.+)$",
        rf"(?:^|\s+{CONNECTOR_PATTERN}\s+)(?:google\s+)?search\s+(?:kro|karo)\s+(.+)$",
        rf"(?:^|\s+{CONNECTOR_PATTERN}\s+)(?:google\s+)?search\s+(.+)$",
        rf"(?:^|\s+{CONNECTOR_PATTERN}\s+)(.+?)\s+google\s+pe\s+search\s+karo(?:\s+.*)?$",
        rf"(?:^|\s+{CONNECTOR_PATTERN}\s+)(.+?)\s+search\s+karo(?:\s+.*)?$",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if not match:
            continue
        query = match.group(1).strip().strip("\"'")
        if not query:
            continue
        query = strip_trailing_action_clauses(
            query,
            strip_search=False,
            strip_write=True,
        ).strip()
        query = re.sub(r"^(?:kro|karo)\s+", "", query, flags=re.IGNORECASE).strip()
        if query:
            return query
    return None


def is_web_search_request(user_input):
    return extract_web_search_query(user_input) is not None

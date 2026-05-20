"""
Xyran Task Router — Intent Classifier / Gatekeeper Layer.
Decides routing ONLY, never execution logic.

Routes:
  "DIRECT_HANDLER" → Simple single-intent (calculator kholo, joke sunao)
  "LLM_PLANNER"    → Compound multi-step tasks (editor khol ke hello likh ke screenshot lo)
  "LLM_FALLBACK"   → Unknown / general chat (kya haal hai, explain quantum physics)
"""

# Semantic action map — groups of verbs that represent distinct user actions
ACTION_MAP = {
    "open":       ["khol", "open", "start", "launch", "chalu", "shuru", "on"],
    "close":      ["band", "close", "quit", "hatao", "bnd", "off"],
    "type":       ["likh", "write", "type", "likho", "likhna", "likho"],
    "screenshot": ["screenshot", "capture", "snip", "snap", "ss"],
    "search":     ["search", "dhundh", "khoj", "google"],
    "show":       ["dikha", "dikhao", "show", "display", "open"],
    "delete":     ["delete", "hatao", "mita", "remove"],
    "read":       ["padh", "read", "dekh"],
    "save":       ["save", "rakh", "store"],
    "install":    ["install", "download"],
    "dnd":        ["do not disturb", "dnd", "disturb"],
    "keyboard":   ["keyboard", "kbd", "key board", "dim", "percent", "%", "brightness", "kam", "badha", "full", "half", "medium", "max", "zero"],
    "screen":     ["screen", "display", "monitor"],
}

# Connectors that signal sequential multi-step intent
ACTION_CONNECTORS = [
    "ke baad", "uske baad", "phir", "fir", "then",
    "or phir", "aur phir",
    "ke sath", "ke saath",
]

# Single connector "or"/"aur" needs special handling — only compound if combined with multiple verbs
SOFT_CONNECTORS = ["or", "aur", "and"]

# GUI pipeline patterns (action combos that are always compound)
GUI_PIPELINE_PATTERNS = [
    {"open", "type"},
    {"open", "screenshot"},
    {"type", "screenshot"},
    {"open", "type", "screenshot"},
    {"screenshot", "show"},
    {"open", "close"},
    {"open", "search"},
]


def _detect_actions(text):
    """Returns set of distinct action categories found in text."""
    lowered = text.lower()
    matched = set()
    for action, keywords in ACTION_MAP.items():
        for word in keywords:
            if word in lowered:
                matched.add(action)
                break
    return matched


def has_multiple_distinct_actions(text):
    """True if text contains 2+ semantically distinct action types."""
    actions = _detect_actions(text)
    if len(actions) <= 1:
        return False
    # Exclude simple toggles (e.g. keyboard on/off, DND on/off, screen brightness) from being compound
    if actions.issubset({"keyboard", "open", "close"}):
        return False
    if actions.issubset({"dnd", "open", "close"}):
        return False
    if actions.issubset({"screen", "open", "close"}):
        return False
    if actions.issubset({"screen", "keyboard", "open", "close"}):
        return False
    return len(actions) > 1


def has_action_connectors(text):
    """True if text contains explicit sequential connectors like 'ke baad', 'phir'."""
    lowered = text.lower()
    for conn in ACTION_CONNECTORS:
        if conn in lowered:
            return True
    return False


def has_gui_pipeline_pattern(text):
    """True if text matches a known GUI multi-step pattern."""
    actions = _detect_actions(text)
    for pattern in GUI_PIPELINE_PATTERNS:
        if pattern.issubset(actions):
            return True
    return False


def is_compound_task(text):
    """
    Master detection: returns True if the input is a multi-step compound task
    that should be routed to the LLM planner instead of direct actions.
    """
    return (
        has_multiple_distinct_actions(text)
        or has_action_connectors(text)
        or has_gui_pipeline_pattern(text)
    )


def route_intent(text, prev_action_category=None):
    """
    Gatekeeper: decides where to send the user input.
    Returns one of: "LLM_PLANNER", "DIRECT_HANDLER", "LLM_FALLBACK"
    """
    # Self-identity queries always go directly to DIRECT_HANDLER (fast offline responder)
    from xyran_input_utils import is_self_identity_request
    if is_self_identity_request(text):
        return "DIRECT_HANDLER"

    # Expose screen brightness direct routing immediately
    from xyran_input_utils import is_screen_brightness_request, is_weather_request
    if is_screen_brightness_request(text, prev_action_category=prev_action_category):
        return "DIRECT_HANDLER"

    # Weather queries always go directly to DIRECT_HANDLER (handled via wttr.in)
    if is_weather_request(text):
        return "DIRECT_HANDLER"

    # News queries (headlines, summary, and next news) always go directly to DIRECT_HANDLER
    from xyran_input_utils import is_news_request, is_more_news_request, is_news_summary_request
    if is_news_request(text) or is_more_news_request(text, has_last_query=True) or is_news_summary_request(text, has_last_news_articles=True):
        return "DIRECT_HANDLER"

    if is_compound_task(text):
        return "LLM_PLANNER"

    actions = _detect_actions(text)
    
    # Simple settings toggle shortcuts should route directly to DIRECT_HANDLER
    if actions.issubset({"keyboard", "open", "close"}) and "keyboard" in actions:
        return "DIRECT_HANDLER"
    if actions.issubset({"dnd", "open", "close"}) and "dnd" in actions:
        return "DIRECT_HANDLER"
    if actions.issubset({"screen", "open", "close"}) and "screen" in actions:
        return "DIRECT_HANDLER"

    # Check if it looks like a simple direct action (has exactly 1 action verb)
    if len(actions) == 1:
        return "DIRECT_HANDLER"

    # No action verbs detected — general chat / question
    return "LLM_FALLBACK"

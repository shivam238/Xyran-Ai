import re
from xyran_memory import load_memory, save_memory
from config import AI_NAME

# -------------------------
# STEP 1 — SMART MEMORY CORE
# -------------------------
def get_fact(key):
    memory = load_memory()
    facts = memory.get("facts", {})
    if isinstance(facts, dict):
        return facts.get(key, {}).get("value")
    return None


def set_fact(key, value):
    memory = load_memory()
    if "facts" not in memory or not isinstance(memory["facts"], dict):
        memory["facts"] = {}
    memory["facts"][key] = {
        "value": value
    }
    save_memory(memory)


def has_fact(key):
    return get_fact(key) is not None


# -------------------------
# STEP 2 — INTENT DETECTOR
# -------------------------
def detect_intent(text):
    text = text.lower()

    # Question detection for personal info
    is_question = any(q in text for q in ["kya", "what", "who", "batao", "bata", "?"]) or text.endswith("?")

    if is_question:
        # ❌ USER asking assistant identity
        if any(x in text for x in ["apka naam", "tumhara naam", "apna naam", "your name", "who are you"]):
            return "get_assistant_name"
        # ❌ USER asking their own identity
        if "mera naam" in text or "my name" in text or "who am i" in text or "मेरा नाम" in text:
            return "get_user_name"
            
        if any(w in text for w in ["age", "umar", "umr", "saal"]):
            # Check if asking assistant's age vs user's age
            if any(x in text for x in ["apki", "apka", "tumhari", "your"]):
                return "get_assistant_age"
            return "get_user_age"

    if "yaad rakh" in text or "remember" in text:
        return "store"
    
    return "unknown"


# -------------------------
# EXTRA SAFETY (VERY IMPORTANT)
# -------------------------
def is_valid_name(name):
    if not name:
        return False

    bad = ["nahi", "hai", "or", "aur", "ok", "yes", "no", "he", "is", "my", "naam", "name", "mera", "thodi", "ye", "he", "she", "it", "xyran", "bot", "assistant", "kya", "kitna", "acha", "badhiya", "nice", "good"]

    if name.lower() in bad:
        return False

    if len(name) < 3:
        return False

    if any(char.isdigit() for char in name):
        return False

    return True


# -------------------------
# SAFE NAME EXTRACTOR
# -------------------------
def extract_name(user_input):
    text = user_input.lower().strip()

    # strict patterns only - matching exact end tags
    patterns = [
        r"mera naam\s+([a-zA-Z]{3,20})\s+hai",
        r"my name is\s+([a-zA-Z]{3,20})",
        r"call me\s+([a-zA-Z]{3,20})"
    ]

    for p in patterns:
        match = re.search(p, text)
        if match:
            name = match.group(1).strip().capitalize()
            if is_valid_name(name):
                return name

    return None



# -------------------------
# SAFE AGE EXTRACTOR
# -------------------------
def extract_age(user_input):
    text = user_input.lower().strip()

    # Check if they are asking a question
    if any(q in text for q in ["kya", "what", "who", "?"]):
        return None

    has_age_word = any(w in text for w in ["age", "umar", "umr", "saal"])
    is_standalone_number = re.match(r"^\s*(\d{1,3})(?:\s+hai)?\s*$", text)

    if has_age_word or is_standalone_number:
        match = re.search(r"(\d{1,3})", user_input)
        if match:
            age_val = int(match.group(1))
            if 1 <= age_val <= 120:
                return str(age_val)
    return None


# -------------------------
# STEP 3 — MAIN BRAIN LOGIC
# -------------------------
def brain(user_input, runtime_state=None):
    text = user_input.lower().strip()
    from xyran_learning import learn_from_interaction, predict_best_action
    
    # ----------------------------------------------------
    # STATEFUL CONFIRMATIONS FIRST
    # ----------------------------------------------------
    if runtime_state:
        # Pending Name Confirmation
        if runtime_state.pending_name:
            is_yes = any(y in text for y in ["yes", "y", "haan", "ha", "ok", "correct", "sahi"])
            is_no = any(n in text for n in ["no", "n", "nahi", "na", "wrong", "galat"])
            
            if is_yes:
                name = runtime_state.pending_name
                set_fact("name", name)
                runtime_state.pending_name = None
                learn_from_interaction(f"mera naam {name} hai", "store_name", success=True)
                return f"Dhanyavad! Maine yaad rakh liya ki aapka naam {name} hai."
            elif is_no:
                name = runtime_state.pending_name
                runtime_state.pending_name = None
                learn_from_interaction(f"mera naam {name} hai", "store_name", success=False)
                return "Theek hai, maine naam store nahi kiya."
            else:
                runtime_state.pending_name = None

        # Pending Age Confirmation
        if runtime_state.pending_age:
            is_yes = any(y in text for y in ["yes", "y", "haan", "ha", "ok", "correct", "sahi"])
            is_no = any(n in text for n in ["no", "n", "nahi", "na", "wrong", "galat"])
            
            if is_yes:
                age = runtime_state.pending_age
                set_fact("age", age)
                runtime_state.pending_age = None
                learn_from_interaction(f"meri age {age} hai", "store_age", success=True)
                return f"Dhanyavad! Maine yaad rakh liya ki aapki age {age} saal hai."
            elif is_no:
                age = runtime_state.pending_age
                runtime_state.pending_age = None
                learn_from_interaction(f"meri age {age} hai", "store_age", success=False)
                return "Theek hai, maine age store nahi kiya."
            else:
                runtime_state.pending_age = None

    # Predict best action from learning database before matching intent
    predicted_intent = predict_best_action(user_input)
    
    intent = detect_intent(text)
    if not intent or intent == "unknown":
        if predicted_intent:
            intent = predicted_intent

    # -------------------------
    # GET ASSISTANT IDENTITY
    # -------------------------
    if intent == "get_assistant_name":
        learn_from_interaction(user_input, "get_assistant_name", success=True)
        return f"Mera naam {AI_NAME} hai"

    if intent == "get_assistant_age":
        learn_from_interaction(user_input, "get_assistant_age", success=True)
        return "Main ek AI virtual assistant hoon, meri koi physical age nahi hai!"

    # -------------------------
    # GET USER IDENTITY
    # -------------------------
    if intent == "get_user_name":
        name = get_fact("name")
        if name:
            learn_from_interaction(user_input, "get_user_name", success=True)
            return f"Aapka naam {name} hai"
        learn_from_interaction(user_input, "get_user_name", success=False)
        return "Mujhe aapka naam nahi pata"

    # -------------------------
    # GET USER AGE
    # -------------------------
    if intent == "get_user_age":
        age = get_fact("age")
        if age:
            learn_from_interaction(user_input, "get_user_age", success=True)
            return f"Aapki age {age} hai"
        learn_from_interaction(user_input, "get_user_age", success=False)
        return "Mujhe aapki age nahi pata"

    # -------------------------
    # STORE AGE (with confirmation)
    # -------------------------
    age = extract_age(user_input)
    if age:
        if runtime_state:
            runtime_state.pending_age = age
            return f"Kya main confirm karu ki aapki age {age} saal hai? (yes/no)"
        else:
            set_fact("age", age)
            learn_from_interaction(user_input, "store_age", success=True)
            return f"Age yaad rakh li: {age}"

    # -------------------------
    # STORE NAME (with confirmation)
    # -------------------------
    if any(w in text for w in ["naam", "name"]) and not any(q in text for q in ["kya", "what", "who", "?"]):
        name = extract_name(user_input)
        if name:
            if runtime_state:
                runtime_state.pending_name = name
                return f"Kya main confirm karu ki aapka naam {name} hai? (yes/no)"
            else:
                set_fact("name", name)
                learn_from_interaction(user_input, "store_name", success=True)
                return f"Naam yaad rakh liya: {name}"

    return None

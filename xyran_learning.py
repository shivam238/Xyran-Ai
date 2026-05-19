import json
import os
from datetime import datetime

LEARN_FILE = "memory/learning.json"


def ensure_learn_file():
    os.makedirs("memory", exist_ok=True)
    if not os.path.exists(LEARN_FILE):
        with open(LEARN_FILE, "w") as f:
            json.dump([], f)


def store_learning(input_text, intent, result, confidence):
    ensure_learn_file()
    try:
        with open(LEARN_FILE, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        data = []

    # Avoid duplicate learning entries for the exact same input to keep it clean
    if not any(d.get("input") == input_text and d.get("intent") == intent for d in data):
        data.append({
            "input": input_text,
            "intent": intent,
            "result": result,
            "confidence": confidence,
            "time": datetime.now().isoformat()
        })

        with open(LEARN_FILE, "w") as f:
            json.dump(data, f, indent=4)


def learn_from_interaction(user_input, intent, success):
    confidence = 0.95 if success else 0.25
    result = "success" if success else "failed"
    store_learning(user_input.lower().strip(), intent, result, confidence)


def predict_best_action(user_input):
    ensure_learn_file()
    try:
        with open(LEARN_FILE, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return None

    user_input_clean = user_input.lower().strip()
    matches = [d for d in data if d["input"] in user_input_clean or user_input_clean in d["input"]]

    if matches:
        best = max(matches, key=lambda x: x["confidence"])
        return best["intent"]

    return None

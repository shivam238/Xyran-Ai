import json
import os
from datetime import datetime

MEMORY_FILE = "memory/memory.json"


def ensure_memory_file():
    os.makedirs("memory", exist_ok=True)

    if not os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "w") as f:
            json.dump({
                "facts": {},
                "preferences": [],
                "tasks": [],
                "projects": []
            }, f, indent=4)


def load_memory():
    ensure_memory_file()
    try:
        with open(MEMORY_FILE, "r") as f:
            data = json.load(f)
            # Safe upgrade from list to dict if needed
            if "facts" in data and isinstance(data["facts"], list):
                data["facts"] = {}
            return data
    except json.JSONDecodeError:
        # 🔥 FIX for your crash
        return {
            "facts": {},
            "preferences": [],
            "tasks": [],
            "projects": []
        }


def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=4)


def remember(category, content):
    memory = load_memory()

    if category not in memory:
        memory[category] = []

    if isinstance(memory[category], list):
        memory[category].append({
            "content": content,
            "time": datetime.now().isoformat()
        })
    elif isinstance(memory[category], dict):
        memory[category][content] = {
            "value": content,
            "time": datetime.now().isoformat()
        }

    save_memory(memory)


def recall(category=None):
    memory = load_memory()

    if category:
        return memory.get(category, [])

    return memory


def format_memory_for_ai():
    """AI ko samajh aane wala memory string"""
    memory = load_memory()
    output = []

    facts = memory.get("facts", {})
    if isinstance(facts, dict):
        for k, v in facts.items():
            output.append(f"facts: {k} is {v.get('value')}")

    for cat in ["preferences", "tasks", "projects"]:
        items = memory.get(cat, [])
        if isinstance(items, list):
            for item in items[-5:]:  # last 5 only
                output.append(f"{cat}: {item.get('content')}")

    return "\n".join(output)
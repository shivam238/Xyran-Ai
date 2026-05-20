import os
import json
import numpy as np
import faiss

INDEX_FILE = "memory/neural_memory.index"
META_FILE = "memory/neural_memory.json"
DIMENSION = 384  # 'all-MiniLM-L6-v2' outputs 384-dimensional embeddings

_model = None
_index = None
_memory_store = []

COMMON_CHITCHAT = {
    "hi", "hello", "hey", "exit", "quit", "ok", "yes", "no", "sahi", "haan", "ha", 
    "bye", "thanks", "thank you", "dhanyavad", "shukriya", "nice", "good", "bad",
    "kya", "kyu", "kyon", "kab", "kahan", "kaise", "aur", "and", "or", "what", "who", "why"
}

MEMORY_TRIGGER_WORDS = {
    "yaad", "pehle", "pasand", "remember", "past", "history", 
    "recall", "previous", "choice", "secret", "code", "personal"
}


def is_chitchat_or_short(text):
    clean = text.lower().strip()
    if len(clean) < 8:
        return True
    words = set(clean.split())
    if words.issubset(COMMON_CHITCHAT):
        return True
    return False


def should_trigger_memory(text):
    text_clean = text.lower().strip()
    return any(w in text_clean for w in MEMORY_TRIGGER_WORDS)


def get_model():
    global _model
    if _model is None:
        try:
            from huggingface_hub import login
            login()
        except Exception:
            pass
        from sentence_transformers import SentenceTransformer
        # Load model lazily so CLI startup remains fast
        print(">>> MODEL LOADING ONCE 🚀")
        _model = SentenceTransformer('all-MiniLM-L6-v2')
        print(">>> MODEL LOADED ✅")
    return _model


def ensure_neural_memory():
    global _index, _memory_store
    os.makedirs("memory", exist_ok=True)

    if _index is None:
        if os.path.exists(INDEX_FILE) and os.path.exists(META_FILE):
            try:
                _index = faiss.read_index(INDEX_FILE)
                with open(META_FILE, "r") as f:
                    _memory_store = json.load(f)
            except Exception:
                # Fallback to fresh setup on corruption
                _index = faiss.IndexFlatL2(DIMENSION)
                _memory_store = []
        else:
            _index = faiss.IndexFlatL2(DIMENSION)
            _memory_store = []


def add_neural_memory(text, rating=1):
    global _index, _memory_store
    ensure_neural_memory()
    text = text.strip()
    if not text:
        return

    # Boost rating on repetition
    for item in _memory_store:
        item_text = item["text"] if isinstance(item, dict) else item
        if item_text == text:
            if isinstance(item, dict):
                item["rating"] = item.get("rating", 1) + 1
                # Save changes
                with open(META_FILE, "w") as f:
                    json.dump(_memory_store, f, indent=4)
            return

    model = get_model()
    embedding = model.encode(text)
    vec = np.array([embedding]).astype('float32')

    _index.add(vec)
    _memory_store.append({"text": text, "rating": rating})

    # Save persistently to disk
    faiss.write_index(_index, INDEX_FILE)
    with open(META_FILE, "w") as f:
        json.dump(_memory_store, f, indent=4)


def search_neural_memory(query, k=3):
    global _index, _memory_store
    ensure_neural_memory()
    if not _memory_store:
        return []

    model = get_model()
    q_emb = model.encode(query)
    q_vec = np.array([q_emb]).astype('float32')

    k = min(k, len(_memory_store))
    distances, indices = _index.search(q_vec, k)

    matched_items = []
    for idx in indices[0]:
        if 0 <= idx < len(_memory_store):
            item = _memory_store[idx]
            if isinstance(item, str):
                item = {"text": item, "rating": 1}
            matched_items.append(item)

    # Sort matches by dynamic feedback/repetition rating
    matched_items.sort(key=lambda x: x.get("rating", 1), reverse=True)

    return [item["text"] for item in matched_items]


def detect_feedback(text):
    text_clean = text.lower().strip()
    # Positive feedback indicators
    if any(w in text_clean for w in ["good", "nice", "perfect", "sahi", "sahi hai", "thank you", "dhanyavad", "shukriya", "correct", "helpful", "great"]):
        return 1.0
    # Negative feedback indicators
    if any(w in text_clean for w in ["bad", "wrong", "galat", "useless", "incorrect", "poor", "bekar"]):
        return -1.0
    return 0.0


def update_memory_rating(memory_text, score_delta):
    global _memory_store
    ensure_neural_memory()
    for item in _memory_store:
        item_text = item["text"] if isinstance(item, dict) else item
        if item_text == memory_text:
            if isinstance(item, dict):
                # Update dynamic reinforcement score
                item["rating"] = round(item.get("rating", 1.0) + score_delta, 2)
                # Persist to disk
                with open(META_FILE, "w") as f:
                    json.dump(_memory_store, f, indent=4)
            break

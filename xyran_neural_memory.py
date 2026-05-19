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


def is_chitchat_or_short(text):
    clean = text.lower().strip()
    if len(clean) < 8:
        return True
    words = set(clean.split())
    if words.issubset(COMMON_CHITCHAT):
        return True
    return False


def get_model():
    global _model
    if _model is None:
        try:
            from huggingface_hub import login
            login(new_session=False)
        except Exception:
            pass
        from sentence_transformers import SentenceTransformer
        # Load model lazily so CLI startup remains fast
        _model = SentenceTransformer('all-MiniLM-L6-v2')
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


def add_neural_memory(text):
    global _index, _memory_store
    ensure_neural_memory()
    text = text.strip()
    if not text:
        return

    # Avoid duplicate exact memories
    if text in _memory_store:
        return

    model = get_model()
    embedding = model.encode(text)
    vec = np.array([embedding]).astype('float32')

    _index.add(vec)
    _memory_store.append(text)

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

    results = []
    for idx in indices[0]:
        if 0 <= idx < len(_memory_store):
            results.append(_memory_store[idx])

    return results

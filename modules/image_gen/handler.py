from .generate import generate_image

TRIGGER_VERBS = ["generate", "create", "make", "draw", "banao", "bnao"]
TRIGGER_NOUNS = ["image", "picture", "pic", "photo", "portrait", "tasveer", "tasvir"]

def is_image_request(text: str) -> bool:
    lowered = text.lower().strip()
    has_noun = any(n in lowered for n in TRIGGER_NOUNS)
    has_verb = any(v in lowered for v in TRIGGER_VERBS)
    if has_noun and has_verb:
        return True
    # "draw a dog" style — verb at start without explicit noun
    if lowered.startswith(("draw ", "generate ", "banao ", "bnao ")):
        return True
    return False


def extract_prompt(text: str) -> str:
    lowered = text.lower().strip()

    # Remove trigger words to isolate the subject
    prompt = lowered
    for w in TRIGGER_VERBS + TRIGGER_NOUNS + ["an", "a", "the", "of", "ka", "ki", "ke", "ek"]:
        prompt = prompt.replace(w, " ")

    prompt = " ".join(prompt.split()).strip()
    return prompt if len(prompt) >= 2 else "beautiful landscape"


def handle_image(text: str, AI_NAME: str):
    if not is_image_request(text):
        return None

    prompt = extract_prompt(text)

    try:
        print(f"[{AI_NAME}] Image generate kar raha hoon: \"{prompt}\"")
        print(f"[{AI_NAME}] Pollinations.ai se fetch ho rahi hai, thoda wait karo...")
        output_path = generate_image(prompt)
        return (
            f"[{AI_NAME}] ✅ Image ready! Saved to: {output_path}\n"
            f"[{AI_NAME}] Opening image..."
        ), output_path
    except Exception as e:
        return f"[{AI_NAME}] Image generate nahi ho payi: {e}", None
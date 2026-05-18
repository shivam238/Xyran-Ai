from .generate import generate_image

def handle_image(text, AI_NAME):
    text_lower = text.lower().strip()

    trigger_verbs = ["generate", "create", "make", "draw", "banao", "bnao"]
    trigger_nouns = ["image", "picture", "pic", "photo", "portrait"]

    if not any(v in text_lower for v in trigger_verbs + trigger_nouns):
        return None

    prompt = text_lower

    for w in trigger_verbs + trigger_nouns:
        prompt = prompt.replace(w, "")

    prompt = prompt.strip()

    if len(prompt) < 2:
        prompt = "a beautiful dog"

    try:
        output_path = generate_image(prompt)
        return f"[{AI_NAME}] Image generated → {output_path}"
    except Exception as e:
        return f"[{AI_NAME}] Image failed: {e}"
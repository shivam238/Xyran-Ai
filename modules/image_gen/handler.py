from .generate import SD_INFERENCE_STEPS, generate_image, has_network

TRIGGER_VERBS = ["generate", "create", "make", "draw", "banao", "bnao"]
TRIGGER_NOUNS = ["image", "picture", "pic", "photo", "portrait", "tasveer", "tasvir"]


def is_image_request(text: str) -> bool:
    lowered = text.lower().strip()
    has_noun = any(n in lowered for n in TRIGGER_NOUNS)
    has_verb = any(v in lowered for v in TRIGGER_VERBS)
    if has_noun and has_verb:
        return True
    if lowered.startswith(("draw ", "generate ", "banao ", "bnao ")):
        return True
    return False


def extract_prompt(text: str) -> str:
    lowered = text.lower().strip()

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
        online_available = has_network()
        if online_available:
            print(f"[{AI_NAME}] Internet mil gaya — Pollinations se try kar raha hoon (fast)...")
        else:
            print(
                f"[{AI_NAME}] Internet nahi mila — offline local model use karunga "
                f"(slow, ~{SD_INFERENCE_STEPS} steps)..."
            )

        output_path, mode = generate_image(prompt)

        if mode == "offline" and online_available:
            print(
                f"[{AI_NAME}] Pollinations fail ho gayi — offline local model par switch "
                f"(slow, ~{SD_INFERENCE_STEPS} steps)..."
            )

        if mode == "online":
            detail = "Pollinations.ai (online)"
        else:
            detail = "local Stable Diffusion (offline)"

        return (
            f"[{AI_NAME}] ✅ Image ready ({detail})! Saved to: {output_path}\n"
            f"[{AI_NAME}] Opening image..."
        ), output_path
    except Exception as e:
        return f"[{AI_NAME}] Image generate nahi ho payi: {e}", None

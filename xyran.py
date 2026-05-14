import os

from groq import Groq, RateLimitError
from config import (
    AI_NAME,
    AI_PROVIDER_MODE,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GROQ_API_KEY,
    MODEL,
    NEWS_API_KEY,
    USER_NAME,
)
from vision import take_screenshot
from xyran_command_utils import command_failed, run_command
from xyran_input_utils import (
    is_ambiguous_short_followup,
    is_vision_followup,
    should_use_vision,
)
from xyran_ai import XyranAI, clean_json
from xyran_direct_actions import handle_direct_action
from xyran_news import NewsManager
from xyran_prompts import build_system_prompt, build_vision_system_prompt
from xyran_response import process_response
from xyran_runtime_state import RuntimeState
from xyran_terminal_input import read_user_input

try:
    import pyjokes
except Exception:
    pyjokes = None

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
runtime_state = RuntimeState()
FALLBACK_API_KEY = os.environ.get("FALLBACK_API_KEY", "").strip()
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL", "").strip()
FALLBACK_BASE_URL = os.environ.get(
    "FALLBACK_BASE_URL",
    "https://openrouter.ai/api/v1/chat/completions"
).strip()
NEWS_API_URL = "https://newsapi.org/v2/top-headlines"
NEWS_STATE_PATH = os.path.join(
    os.path.expanduser("~"),
    ".local",
    "state",
    AI_NAME.lower(),
    "news_state.json",
)

SYSTEM_PROMPT = build_system_prompt(AI_NAME, USER_NAME)
VISION_SYSTEM_PROMPT = build_vision_system_prompt(AI_NAME)
ai = XyranAI(
    client=client,
    groq_api_key=GROQ_API_KEY,
    model=MODEL,
    gemini_api_key=GEMINI_API_KEY,
    gemini_model=GEMINI_MODEL,
    provider_mode=AI_PROVIDER_MODE,
    system_prompt=SYSTEM_PROMPT,
    vision_system_prompt=VISION_SYSTEM_PROMPT,
    fallback_api_key=FALLBACK_API_KEY,
    fallback_model=FALLBACK_MODEL,
    fallback_base_url=FALLBACK_BASE_URL,
    runtime_state=runtime_state,
)
news_manager = NewsManager(
    news_api_key=NEWS_API_KEY,
    news_api_url=NEWS_API_URL,
    news_state_path=NEWS_STATE_PATH,
    generate_text_reply=ai.generate_text_reply,
)


def main():
    news_manager.load_state()
    print(f"""
╔══════════════════════════════════════════╗
║         XYRAN AI v2 - ONLINE             ║
║   Brain + Aankhein — Dono Ready Hain     ║
╚══════════════════════════════════════════╝
'exit' likho band karne ke liye.
""")

    while True:
        try:
            user_input = read_user_input(f"[{USER_NAME}] ").strip()
            if not user_input:
                continue
            runtime_state.last_user_input = user_input
            if user_input.lower() in ("exit", "quit", "band karo"):
                print("[Xyran] Theek hai. Phir milenge.")
                break

            if handle_direct_action(user_input, runtime_state, news_manager, pyjokes, run_command, command_failed, ai):
                runtime_state.last_input_used_vision = False
                continue

            use_vision = (
                should_use_vision(user_input)
                or (runtime_state.last_input_used_vision and is_vision_followup(user_input))
                or (runtime_state.vision_followup_turns_left > 0 and is_ambiguous_short_followup(user_input))
            )

            if use_vision:
                print("[Xyran] Screen dekh raha hoon...")
                img_path, err = take_screenshot()
                if img_path:
                    reply = ai.ask_with_image(user_input, img_path)
                    os.remove(img_path)
                else:
                    print(f"[Xyran] Screenshot nahi le paya: {err}")
                    reply = ai.ask(user_input)
                runtime_state.last_input_used_vision = True
                runtime_state.vision_followup_turns_left = 2
            else:
                reply = ai.ask(user_input)
                runtime_state.last_input_used_vision = False
                if runtime_state.vision_followup_turns_left > 0:
                    runtime_state.vision_followup_turns_left -= 1

            process_response(reply, run_command, command_failed, ai.summarize_output, clean_json, runtime_state)

        except KeyboardInterrupt:
            print("\n[Xyran] Band ho raha hoon.")
            break
        except RateLimitError:
            print("\n[Xyran] Groq API rate limit hit ho gaya hai. Thodi der baad phir try karo.")
        except Exception as e:
            print(f"\n[Xyran] Error aaya: {e}")


if __name__ == "__main__":
    main()

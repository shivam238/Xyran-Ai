import os
from pathlib import Path


def load_dotenv(dotenv_path=None):
    """Minimal .env loader so secrets can stay out of source files."""
    if dotenv_path is None:
        dotenv_path = Path(__file__).resolve().parent / ".env"

    path = Path(dotenv_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if value and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "put-your-groq-key-in-.env")
MODEL = os.getenv("MODEL", "llama-3.3-70b-versatile")
AI_NAME = os.getenv("AI_NAME", "Xyran")
USER_NAME = os.getenv("USER_NAME", "darkeeidea")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

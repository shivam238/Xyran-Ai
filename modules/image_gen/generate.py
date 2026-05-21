"""
Image generation via pollinations.ai
- No API key needed
- Free and fast (~3-5 seconds)
- Returns a saved PNG path
"""

import os
import time
import urllib.parse
import urllib.request


def generate_image(prompt: str) -> str:
    """
    Fetches a generated image from pollinations.ai and saves it locally.
    Returns the saved file path.
    """
    output_dir = os.path.expanduser("~/Pictures/xyran")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = int(time.time())
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in prompt[:30]).strip()
    safe_name = safe_name.replace(" ", "_") or "xyran_image"
    output_path = os.path.join(output_dir, f"{safe_name}_{timestamp}.png")

    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&seed={timestamp}"

    headers = {
        "User-Agent": "XyranAI/1.0",
        "Accept": "image/png,image/*",
    }

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        image_data = resp.read()

    with open(output_path, "wb") as f:
        f.write(image_data)

    return output_path
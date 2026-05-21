"""
Hybrid image generation for Xyran.
- Online: Pollinations.ai (fast, default when network is available)
- Offline: local Stable Diffusion v1.5 on CPU (slow fallback)
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.parse
import urllib.request

from xyran_network import has_internet

POLLINATIONS_HOST = "image.pollinations.ai"
POLLINATIONS_TIMEOUT = 60
SD_MODEL_ID = "runwayml/stable-diffusion-v1-5"
SD_INFERENCE_STEPS = 20

_sd_pipe = None


def _output_dir() -> str:
    output_dir = os.path.expanduser("~/Pictures/xyran")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _build_output_path(prompt: str) -> str:
    timestamp = int(time.time())
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in prompt[:30]).strip()
    safe_name = safe_name.replace(" ", "_") or "xyran_image"
    return os.path.join(_output_dir(), f"{safe_name}_{timestamp}.png")


def has_network(timeout: float = 3.0) -> bool:
    """Quick connectivity check without downloading an image."""
    return has_internet(timeout)


def generate_image_online(prompt: str, output_path: str) -> None:
    encoded_prompt = urllib.parse.quote(prompt)
    timestamp = int(time.time())
    url = (
        f"https://{POLLINATIONS_HOST}/prompt/{encoded_prompt}"
        f"?width=1024&height=1024&nologo=true&seed={timestamp}"
    )

    headers = {
        "User-Agent": "XyranAI/1.0",
        "Accept": "image/png,image/*",
    }

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=POLLINATIONS_TIMEOUT) as resp:
        image_data = resp.read()

    if not image_data:
        raise RuntimeError("Pollinations ne khali response diya.")

    with open(output_path, "wb") as f:
        f.write(image_data)


def _load_sd_pipe():
    global _sd_pipe
    if _sd_pipe is not None:
        return _sd_pipe

    try:
        import torch
        from diffusers import StableDiffusionPipeline
    except ImportError as exc:
        raise RuntimeError(
            "Offline image ke liye torch aur diffusers chahiye. "
            "Install: pip install -r requirements-image-offline.txt"
        ) from exc

    _sd_pipe = StableDiffusionPipeline.from_pretrained(
        SD_MODEL_ID,
        torch_dtype=torch.float32,
    )
    _sd_pipe = _sd_pipe.to("cpu")
    return _sd_pipe


def generate_image_offline(prompt: str, output_path: str) -> None:
    pipe = _load_sd_pipe()
    result = pipe(prompt, num_inference_steps=SD_INFERENCE_STEPS)
    result.images[0].save(output_path)


def generate_image(prompt: str) -> tuple[str, str]:
    """
    Generate an image and return (output_path, mode).
    mode is \"online\" or \"offline\".
    """
    output_path = _build_output_path(prompt)

    if has_network():
        try:
            generate_image_online(prompt, output_path)
            return output_path, "online"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, RuntimeError):
            pass

    generate_image_offline(prompt, output_path)
    return output_path, "offline"

import os
import torch
from diffusers import StableDiffusionPipeline

pipe = None

def load_model():
    global pipe
    if pipe is None:
        model_id = "runwayml/stable-diffusion-v1-5"

        pipe = StableDiffusionPipeline.from_pretrained(
            model_id,
            torch_dtype=torch.float32
        )

        pipe = pipe.to("cpu")

    return pipe


def generate_image(prompt: str):
    model = load_model()

    output_dir = os.path.expanduser("~/Pictures/xyran")
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, "xyran.png")

    image = model(prompt, num_inference_steps=20).images[0]
    image.save(output_path)

    return output_path
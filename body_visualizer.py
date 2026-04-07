"""
DietFocus – body_visualizer.py
AI-powered body visualization using Replicate image-to-image models.
Shows how the user would look after losing a specified amount of weight.
"""

import io
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _kg_to_prompt(kg: float) -> tuple[str, float]:
    """Convert kg loss to a descriptive prompt and image strength."""
    if kg <= 2:
        desc = "slightly slimmer figure, subtle weight loss"
        strength = 0.30
    elif kg <= 5:
        desc = "noticeably slimmer figure, slimmer waist and face, visible weight loss"
        strength = 0.42
    elif kg <= 10:
        desc = "significantly slimmer figure, much thinner waist, slimmer face and body"
        strength = 0.55
    elif kg <= 15:
        desc = "very slim figure, major weight loss, thin waist, slim arms and legs"
        strength = 0.65
    else:
        desc = "very slim athletic figure, dramatic weight loss transformation, thin and toned"
        strength = 0.72
    return desc, strength


class BodyVisualizer:
    def __init__(self):
        token = os.getenv("REPLICATE_API_TOKEN", "")
        self.enabled = bool(token and "your-" not in token and len(token) > 10)
        self.client = None

        if self.enabled:
            try:
                import replicate
                self.client = replicate.Client(api_token=token)
                print("✅ Body visualizer ready.")
            except ImportError:
                print("⚠️  replicate package not installed.")
                self.enabled = False
        else:
            print("⚠️  REPLICATE_API_TOKEN not set – body visualization disabled.")

    def visualize(self, image_bytes: bytes, kg_to_lose: float) -> Optional[str]:
        """
        Generate a weight-loss visualization.
        Returns the URL of the generated image, or None on failure.
        """
        if not self.enabled:
            return None

        desc, strength = _kg_to_prompt(kg_to_lose)

        prompt = (
            f"photorealistic portrait of the same person, {desc}, "
            "same face, same hairstyle, same clothing, same background, "
            "high quality photo, natural lighting, realistic"
        )
        negative_prompt = (
            "different person, ugly, deformed, bad anatomy, distorted face, "
            "different clothes, cartoon, illustration, painting, blurry"
        )

        try:
            import replicate
            output = replicate.run(
                "stability-ai/stable-diffusion-img2img:"
                "15a3689ee13b0d2616e98820eca31d4af4a36bde6782fc7d238b10a05d01e3de",
                input={
                    "image":             io.BytesIO(image_bytes),
                    "prompt":            prompt,
                    "negative_prompt":   negative_prompt,
                    "strength":          strength,
                    "guidance_scale":    8.0,
                    "num_inference_steps": 35,
                    "scheduler":         "K_EULER_ANCESTRAL",
                },
            )
            if output:
                return output[0] if isinstance(output, list) else str(output)
            return None
        except Exception as e:
            print(f"Replicate error: {e}")
            return None

    def unavailable_reason(self) -> str:
        token = os.getenv("REPLICATE_API_TOKEN", "")
        if not token or "your-" in token:
            return "REPLICATE_API_TOKEN not configured in Streamlit secrets."
        return "replicate package not installed — run: pip install replicate"

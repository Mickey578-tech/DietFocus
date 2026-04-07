"""
DietFocus – body_visualizer.py
AI-powered body visualization using Replicate API (via HTTP, no SDK needed).
Shows how the user would look after losing a specified amount of weight.
Uses instruct-pix2pix which edits an existing image rather than generating a new one.
"""

import base64
import io
import os
import time
from typing import Optional, Tuple

import requests
from dotenv import load_dotenv
from PIL import Image as PILImage

load_dotenv()

REPLICATE_API_URL = "https://api.replicate.com/v1/predictions"
# instruct-pix2pix: edits an existing image based on a text instruction.
# image_guidance_scale keeps the output close to the original photo.
MODEL_VERSION = "30c1d0b916a6f8efce20493f5d61ee27491ab2a60437c13c588468b9810ec23f"


def _kg_to_params(kg: float) -> tuple[str, float, float]:
    """
    Returns (instruction_prompt, guidance_scale, image_guidance_scale).
    image_guidance_scale: how much to stay faithful to the original photo.
      Higher = more faithful to original (range 1.0 – 3.0).
    guidance_scale: how strongly to follow the text instruction.
    """
    if kg <= 2:
        instruction = "Make this person's body very slightly slimmer, just a subtle reduction in waist size"
        guidance_scale = 7.0
        image_guidance_scale = 2.2
    elif kg <= 5:
        instruction = "Make this person noticeably slimmer with a slimmer waist and slightly thinner face, keep everything else identical"
        guidance_scale = 7.5
        image_guidance_scale = 2.0
    elif kg <= 10:
        instruction = "Make this person significantly slimmer with a much thinner waist and slimmer body, keep the face, hair, clothes and background identical"
        guidance_scale = 8.0
        image_guidance_scale = 1.8
    elif kg <= 15:
        instruction = "Make this person very slim with a thin waist, slim arms and legs, keep the face, hair, clothes and background identical"
        guidance_scale = 8.5
        image_guidance_scale = 1.7
    else:
        instruction = "Make this person dramatically slimmer and more athletic with a very thin waist and toned body, keep the face, hair, clothes and background identical"
        guidance_scale = 9.0
        image_guidance_scale = 1.6
    return instruction, guidance_scale, image_guidance_scale


class BodyVisualizer:
    def __init__(self):
        self.enabled = bool(self._get_token())

    def _get_token(self) -> str:
        token = os.getenv("REPLICATE_API_TOKEN", "")
        if token and "your-" not in token and len(token) > 10:
            return token
        try:
            import streamlit as st
            token = st.secrets["REPLICATE_API_TOKEN"]
            if token and len(token) > 10:
                return token
        except Exception:
            pass
        return ""

    def _resize_image(self, image_bytes: bytes, max_size: int = 512) -> bytes:
        """Resize image so longest side = max_size, return as JPEG bytes."""
        img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        if max(w, h) > max_size:
            ratio = max_size / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), PILImage.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=90)
        return out.getvalue()

    def visualize(self, image_bytes: bytes, kg_to_lose: float) -> Tuple[Optional[str], Optional[str]]:
        """
        Call Replicate instruct-pix2pix via HTTP (no SDK needed).
        Returns (image_url, error_message) — one of them will be None.
        """
        token = self._get_token()
        if not token:
            return None, "No API token found."

        instruction, guidance_scale, image_guidance_scale = _kg_to_params(kg_to_lose)
        negative_prompt = (
            "different person, different face, different hair, multiple people, "
            "different clothes, different background, ugly, deformed, blurry, low quality"
        )

        # Resize and encode image
        resized = self._resize_image(image_bytes)
        b64 = base64.b64encode(resized).decode("utf-8")
        image_uri = f"data:image/jpeg;base64,{b64}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Start prediction
        try:
            response = requests.post(
                REPLICATE_API_URL,
                headers=headers,
                json={
                    "version": MODEL_VERSION,
                    "input": {
                        "image":               image_uri,
                        "prompt":              instruction,
                        "negative_prompt":     negative_prompt,
                        "guidance_scale":      guidance_scale,
                        "image_guidance_scale": image_guidance_scale,
                        "num_inference_steps": 50,
                        "num_outputs":         1,
                    },
                },
                timeout=60,
            )
            prediction = response.json()
            if not response.ok:
                return None, f"API error {response.status_code}: {prediction.get('detail', response.text)}"
        except Exception as e:
            return None, f"Request failed: {e}"

        # If synchronous response already has output
        if prediction.get("status") == "succeeded":
            output = prediction.get("output")
            if isinstance(output, list) and output:
                return output[0], None
            if output:
                return str(output), None

        # Poll for result (max 3 minutes)
        prediction_url = prediction.get("urls", {}).get("get")
        if not prediction_url:
            return None, f"No polling URL returned. Response: {prediction}"

        for _ in range(36):
            time.sleep(5)
            try:
                poll = requests.get(prediction_url, headers=headers, timeout=15)
                result = poll.json()
                status = result.get("status")
                if status == "succeeded":
                    output = result.get("output")
                    if isinstance(output, list) and output:
                        return output[0], None
                    return str(output), None if output else (None, "Empty output")
                elif status in ("failed", "canceled"):
                    return None, f"Prediction {status}: {result.get('error', 'unknown error')}"
            except Exception as e:
                return None, f"Poll error: {e}"

        return None, "Timeout: generation took too long (over 3 minutes)"

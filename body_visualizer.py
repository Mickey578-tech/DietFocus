"""
DietFocus – body_visualizer.py
AI-powered body visualization using Replicate API (via HTTP, no SDK needed).
Shows how the user would look after losing a specified amount of weight.
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
MODEL_OWNER = "lucataco"
MODEL_NAME  = "sdxl"


def _kg_to_prompt(kg: float) -> tuple[str, float]:
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

    def _resize_image(self, image_bytes: bytes, max_size: int = 768) -> bytes:
        """Resize image to max_size on longest side and return as JPEG bytes."""
        img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        if max(w, h) > max_size:
            ratio = max_size / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), PILImage.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=85)
        return out.getvalue()

    def _get_latest_version(self, token: str) -> Tuple[Optional[str], Optional[str]]:
        """Fetch the latest version hash for the model."""
        try:
            url = f"https://api.replicate.com/v1/models/{MODEL_OWNER}/{MODEL_NAME}/versions"
            r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
            r.raise_for_status()
            versions = r.json().get("results", [])
            if versions:
                return versions[0]["id"], None
            return None, "No versions found for model"
        except Exception as e:
            return None, f"Could not fetch model version: {e}"

    def visualize(self, image_bytes: bytes, kg_to_lose: float) -> Tuple[Optional[str], Optional[str]]:
        """
        Call Replicate API directly via HTTP (no SDK needed).
        Returns (image_url, error_message) — one of them will be None.
        """
        token = self._get_token()
        if not token:
            return None, "No API token found."

        desc, strength = _kg_to_prompt(kg_to_lose)
        prompt = (
            f"The exact same woman, same face, same hair, same outfit, same room background, "
            f"but with a {desc}. Photorealistic, high quality, natural lighting. "
            f"Preserve all facial features exactly."
        )
        negative_prompt = (
            "different person, different face, multiple people, ugly, deformed, "
            "cartoon, illustration, blurry, low quality, different clothes, different background"
        )

        # Fetch latest model version dynamically
        version_id, err = self._get_latest_version(token)
        if not version_id:
            return None, err

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
                    "version": version_id,
                    "input": {
                        "image":               image_uri,
                        "prompt":              prompt,
                        "negative_prompt":     negative_prompt,
                        "prompt_strength":     strength,
                        "num_inference_steps": 50,
                        "guidance_scale":      8.0,
                    },
                },
                timeout=60,
            )
            prediction = response.json()
            if not response.ok:
                return None, f"API error {response.status_code}: {prediction.get('detail', response.text)}"
        except Exception as e:
            return None, f"Request failed: {e}"

        # If synchronous response already has output (Prefer: wait)
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

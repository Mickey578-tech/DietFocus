"""
DietFocus – body_visualizer.py
AI-powered body visualization using Replicate API (via HTTP, no SDK needed).
Shows how the user would look after losing a specified amount of weight.
"""

import base64
import os
import time
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

REPLICATE_API_URL = "https://api.replicate.com/v1/predictions"
MODEL_VERSION = "15a3689ee13b0d2616e98820eca31d4af4a36bde6782fc7d238b10a05d01e3de"


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

    def visualize(self, image_bytes: bytes, kg_to_lose: float) -> Optional[str]:
        """
        Call Replicate API directly via HTTP (no SDK needed).
        Returns URL of generated image, or None on failure.
        """
        token = self._get_token()
        if not token:
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

        # Encode image as base64 data URI
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_uri = f"data:image/jpeg;base64,{b64}"

        headers = {
            "Authorization": f"Token {token}",
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
                        "image": image_uri,
                        "prompt": prompt,
                        "negative_prompt": negative_prompt,
                        "strength": strength,
                        "guidance_scale": 8.0,
                        "num_inference_steps": 35,
                        "scheduler": "K_EULER_ANCESTRAL",
                    },
                },
                timeout=30,
            )
            response.raise_for_status()
            prediction = response.json()
        except Exception as e:
            print(f"Replicate start error: {e}")
            return None

        # Poll for result (max 3 minutes)
        prediction_url = prediction.get("urls", {}).get("get")
        if not prediction_url:
            return None

        for _ in range(36):  # 36 × 5s = 3 min
            time.sleep(5)
            try:
                poll = requests.get(prediction_url, headers=headers, timeout=15)
                poll.raise_for_status()
                result = poll.json()
                status = result.get("status")
                if status == "succeeded":
                    output = result.get("output")
                    if isinstance(output, list) and output:
                        return output[0]
                    return str(output) if output else None
                elif status in ("failed", "canceled"):
                    print(f"Replicate prediction {status}: {result.get('error')}")
                    return None
            except Exception as e:
                print(f"Replicate poll error: {e}")
                return None

        print("Replicate timeout after 3 minutes")
        return None

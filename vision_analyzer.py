"""
DietFocus – vision_analyzer.py
Uses Claude Vision API to estimate nutrition from meal photos or text descriptions.
"""

import os
import base64
import json
import re
from typing import Optional, Dict, Union
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

NUTRITION_PROMPT = """You are a clinical dietitian specializing in low-carb, high-protein diets.

Analyze the meal provided (image or description) and return a JSON object with these exact fields:

{
  "food_items": ["item1", "item2"],
  "protein_g": 0,
  "carbs_g": 0,
  "fat_g": 0,
  "calories": 0,
  "sugar_g": 0,
  "fiber_g": 0,
  "confidence": "high|medium|low",
  "notes": "brief notes about the meal",
  "low_carb_friendly": true
}

Guidelines:
- Be accurate with typical portion sizes shown or described.
- For carbs_g, count only net carbs (total carbs minus fiber).
- If you cannot identify an ingredient, note it under "notes".
- Return ONLY valid JSON, no extra text.
"""


class VisionAnalyzer:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.enabled = bool(api_key and "your-key" not in api_key)
        self.client = None

        if self.enabled:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=api_key)
                print("✅ Vision analyzer ready.")
            except ImportError:
                print("⚠️  anthropic package not installed. Run: pip install anthropic")
                self.enabled = False
        else:
            print("⚠️  ANTHROPIC_API_KEY not set – vision analysis disabled.")

    # ─── Public API ────────────────────────────────────────────────────────────

    def analyze_image(self, image_bytes: bytes, media_type: str = "image/jpeg") -> Dict:
        """Analyze a meal image and return nutrition estimates."""
        if not self.enabled:
            return self._unavailable_response("Vision API not configured.")

        try:
            b64_image = base64.standard_b64encode(image_bytes).decode("utf-8")
            response = self.client.messages.create(
                model="claude-opus-4-6",
                max_tokens=512,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64_image,
                                },
                            },
                            {"type": "text", "text": NUTRITION_PROMPT},
                        ],
                    }
                ],
            )
            return self._parse_response(response.content[0].text)
        except Exception as e:
            return self._error_response(str(e))

    def analyze_text(self, description: str) -> Dict:
        """Estimate nutrition from a free-text meal description."""
        if not self.enabled:
            return self._unavailable_response("Vision API not configured.")

        try:
            prompt = (
                f"Meal description: {description}\n\n"
                + NUTRITION_PROMPT
            )
            response = self.client.messages.create(
                model="claude-opus-4-6",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._parse_response(response.content[0].text)
        except Exception as e:
            return self._error_response(str(e))

    def analyze_image_file(self, file_path: Union[str, Path]) -> Dict:
        """Convenience wrapper: read file then analyze."""
        path = Path(file_path)
        if not path.exists():
            return self._error_response(f"File not found: {file_path}")
        suffix = path.suffix.lower()
        media_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                     ".png": "image/png", ".webp": "image/webp",
                     ".gif": "image/gif"}
        media_type = media_map.get(suffix, "image/jpeg")
        return self.analyze_image(path.read_bytes(), media_type)

    # ─── Helpers ───────────────────────────────────────────────────────────────

    def _parse_response(self, text: str) -> Dict:
        """Extract and validate JSON from Claude's response."""
        # Strip markdown code fences if present
        clean = re.sub(r"```(?:json)?", "", text).strip()
        try:
            data = json.loads(clean)
            return self._validate(data)
        except json.JSONDecodeError:
            # Try to find JSON object inside text
            match = re.search(r"\{.*\}", clean, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                    return self._validate(data)
                except json.JSONDecodeError:
                    pass
            return self._error_response(f"Could not parse JSON from response:\n{text}")

    def _validate(self, data: Dict) -> Dict:
        """Ensure all expected fields exist with sensible defaults."""
        defaults = {
            "food_items": [],
            "protein_g": 0.0,
            "carbs_g": 0.0,
            "fat_g": 0.0,
            "calories": 0,
            "sugar_g": 0.0,
            "fiber_g": 0.0,
            "confidence": "medium",
            "notes": "",
            "low_carb_friendly": False,
            "error": None,
        }
        result = {**defaults, **data}
        # Coerce numerics
        for key in ("protein_g", "carbs_g", "fat_g", "sugar_g", "fiber_g"):
            result[key] = float(result.get(key) or 0)
        result["calories"] = int(result.get("calories") or 0)
        return result

    def _unavailable_response(self, msg: str) -> Dict:
        return {
            "food_items": [],
            "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0,
            "calories": 0, "sugar_g": 0.0, "fiber_g": 0.0,
            "confidence": "low",
            "notes": msg,
            "low_carb_friendly": False,
            "error": "unavailable",
        }

    def _error_response(self, msg: str) -> Dict:
        return {
            "food_items": [],
            "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0,
            "calories": 0, "sugar_g": 0.0, "fiber_g": 0.0,
            "confidence": "low",
            "notes": f"Analysis error: {msg}",
            "low_carb_friendly": False,
            "error": msg,
        }

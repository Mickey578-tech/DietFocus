"""
DietFocus – notifications.py
WhatsApp push notifications via Twilio or Make.com webhook.
"""

import os
import json
import requests
from datetime import date, datetime
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class NotificationManager:
    def __init__(self):
        self.provider = os.getenv("NOTIFICATION_PROVIDER", "twilio").lower()
        self.twilio_enabled = self._init_twilio()
        self.make_enabled = self._init_make()
        self.enabled = self.twilio_enabled or self.make_enabled

        if not self.enabled:
            print("⚠️  No notification provider configured.")

    # ─── Initialization ────────────────────────────────────────────────────────

    def _init_twilio(self) -> bool:
        sid   = os.getenv("TWILIO_ACCOUNT_SID", "")
        token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_from = os.getenv("TWILIO_WHATSAPP_FROM", "")
        self.twilio_to   = os.getenv("TWILIO_WHATSAPP_TO", "")

        if not all([sid, token, self.twilio_from, self.twilio_to,
                    "AC" in sid, "your" not in token]):
            return False
        try:
            from twilio.rest import Client
            self.twilio_client = Client(sid, token)
            print("✅ Twilio WhatsApp ready.")
            return True
        except ImportError:
            print("⚠️  twilio package not installed.")
            return False
        except Exception as e:
            print(f"⚠️  Twilio init failed: {e}")
            return False

    def _init_make(self) -> bool:
        self.make_url = os.getenv("MAKE_WEBHOOK_URL", "")
        if not self.make_url or "your-webhook" in self.make_url:
            return False
        print("✅ Make.com webhook ready.")
        return True

    # ─── Public Notifications ──────────────────────────────────────────────────

    def send_weigh_in_reminder(self) -> bool:
        """Send Monday morning weight-in reminder."""
        msg = (
            "⚖️ *DietFocus* – Good morning!\n\n"
            "It's time for your weekly weigh-in 🌅\n"
            "Please log your weight in the app before breakfast.\n"
            "Remember: weigh yourself after using the bathroom, before eating."
        )
        return self._send(msg)

    def send_missing_meal_alert(self, meals_logged: int) -> bool:
        """Alert when no meals have been logged by evening."""
        msg = (
            f"🍽️ *DietFocus* – Meal Reminder\n\n"
            f"You've only logged {meals_logged} meal(s) today.\n"
            "Don't forget to log your meals – tracking is key! 💪\n"
            "Open the app: your data helps you see patterns."
        )
        return self._send(msg)

    def send_carb_alert(self, current_carbs: float, limit: float) -> bool:
        """Alert when daily carb limit is exceeded."""
        over = round(current_carbs - limit, 1)
        msg = (
            f"🚨 *DietFocus* – Carb Limit Alert\n\n"
            f"You've consumed {current_carbs}g of carbs today "
            f"({over}g over your {limit}g limit).\n"
            "Consider a lighter second meal to stay on track. 🥗"
        )
        return self._send(msg)

    def send_daily_summary(self, summary: dict) -> bool:
        """Send end-of-day macro summary."""
        fasting_icon = "✅" if summary.get("fasting_ok") else "❌"
        msg = (
            f"📊 *DietFocus* – Daily Summary for {date.today().strftime('%A, %d %b')}\n\n"
            f"Protein: {summary.get('protein_g', 0):.0f}g\n"
            f"Carbs:   {summary.get('carbs_g', 0):.0f}g\n"
            f"Fat:     {summary.get('fat_g', 0):.0f}g\n"
            f"Calories:{summary.get('calories', 0)} kcal\n\n"
            f"Fasting window kept: {fasting_icon}\n"
            f"Meals logged: {summary.get('meals_logged', 0)}/2\n\n"
            "Great work staying focused! 🌟"
        )
        return self._send(msg)

    def send_test_message(self) -> bool:
        """Send a test notification to verify the setup."""
        msg = (
            "✅ *DietFocus* – Test Notification\n\n"
            "Notifications are working correctly!\n"
            f"Sent at: {datetime.now().strftime('%H:%M on %d/%m/%Y')}"
        )
        return self._send(msg)

    # ─── Internal Send ─────────────────────────────────────────────────────────

    def _send(self, message: str) -> bool:
        """Try Twilio first, then fall back to Make.com."""
        if self.provider == "make" and self.make_enabled:
            return self._send_make(message)
        if self.twilio_enabled:
            return self._send_twilio(message)
        if self.make_enabled:
            return self._send_make(message)
        print(f"[NOTIFICATION – no provider]\n{message}")
        return False

    def _send_twilio(self, message: str) -> bool:
        try:
            self.twilio_client.messages.create(
                body=message,
                from_=self.twilio_from,
                to=self.twilio_to,
            )
            print("📱 WhatsApp message sent via Twilio.")
            return True
        except Exception as e:
            print(f"Twilio send error: {e}")
            return False

    def _send_make(self, message: str) -> bool:
        try:
            payload = {
                "message": message,
                "timestamp": datetime.now().isoformat(),
                "app": "DietFocus",
            }
            response = requests.post(
                self.make_url,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            print("📱 WhatsApp message sent via Make.com.")
            return True
        except Exception as e:
            print(f"Make.com send error: {e}")
            return False

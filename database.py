"""
DietFocus – database.py
Supabase integration for weight logs, meal logs, and fasting logs.
Falls back to demo data when not configured.
"""

import base64
import hashlib
import hmac
import os
import random
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from dotenv import load_dotenv

load_dotenv()


class DatabaseManager:
    def __init__(self):
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_ANON_KEY", "")

        self.connected = False
        self.client = None

        if not url or not key or "your-project-id" in url:
            print("⚠️  Supabase not configured – running in demo mode.")
            return

        try:
            from supabase import create_client
            self.client = create_client(url, key)
            self.client.table("weight_logs").select("id").limit(1).execute()
            self.connected = True
            print("✅ Supabase connected.")
        except Exception as e:
            print(f"⚠️  Supabase connection failed: {e}\nRunning in demo mode.")

    # ─── Auth ──────────────────────────────────────────────────────────────────

    def _hash_password(self, password: str) -> str:
        salt = os.urandom(32)
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return base64.b64encode(salt + key).decode("utf-8")

    def _verify_password(self, password: str, stored_hash: str) -> bool:
        try:
            decoded = base64.b64decode(stored_hash.encode("utf-8"))
            salt = decoded[:32]
            stored_key = decoded[32:]
            key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
            return hmac.compare_digest(key, stored_key)
        except Exception:
            return False

    def register_user(self, username: str, password: str, display_name: str = "") -> tuple:
        """Register a new user. Returns (user_id, error_message)."""
        if not self.connected:
            return None, "Database not connected"
        if len(username.strip()) < 3:
            return None, "Username must be at least 3 characters"
        if len(password) < 6:
            return None, "Password must be at least 6 characters"
        try:
            existing = self.client.table("users").select("id").eq("username", username.lower().strip()).execute()
            if existing.data:
                return None, "Username already taken"
            result = self.client.table("users").insert({
                "username": username.lower().strip(),
                "password_hash": self._hash_password(password),
                "display_name": display_name.strip() or username.strip(),
            }).execute()
            if result.data:
                return result.data[0]["id"], None
            return None, "Registration failed"
        except Exception as e:
            return None, str(e)

    def authenticate_user(self, username: str, password: str) -> tuple:
        """Authenticate user. Returns (user_id, display_name, error_message)."""
        if not self.connected:
            return None, None, "Database not connected"
        try:
            result = self.client.table("users").select("id, display_name, password_hash").eq(
                "username", username.lower().strip()
            ).execute()
            if not result.data:
                return None, None, "Username not found"
            user = result.data[0]
            if not self._verify_password(password, user["password_hash"]):
                return None, None, "Incorrect password"
            return user["id"], user["display_name"] or username, None
        except Exception as e:
            return None, None, str(e)

    def change_password(self, user_id: str, new_password: str) -> tuple:
        """Change password. Returns (success, error_message)."""
        if not self.connected:
            return False, "Database not connected"
        if len(new_password) < 6:
            return False, "Password must be at least 6 characters"
        try:
            self.client.table("users").update({
                "password_hash": self._hash_password(new_password)
            }).eq("id", user_id).execute()
            return True, None
        except Exception as e:
            return False, str(e)

    # ─── Remember Me Tokens ────────────────────────────────────────────────────

    def create_remember_token(self, user_id: str, days: int = 30) -> str:
        """Create a persistent remember-me token. Returns token string."""
        if not self.connected:
            return ""
        try:
            token = secrets.token_urlsafe(32)
            expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
            # Remove any existing tokens for this user
            self.client.table("remember_tokens").delete().eq("user_id", user_id).execute()
            self.client.table("remember_tokens").insert({
                "user_id": user_id,
                "token": token,
                "expires_at": expires_at,
            }).execute()
            return token
        except Exception as e:
            print(f"Error creating remember token: {e}")
            return ""

    def validate_remember_token(self, token: str) -> tuple:
        """Validate a remember-me token. Returns (user_id, display_name) or (None, None)."""
        if not self.connected or not token:
            return None, None
        try:
            result = (
                self.client.table("remember_tokens")
                .select("user_id, expires_at")
                .eq("token", token)
                .execute()
            )
            if not result.data:
                return None, None
            row = result.data[0]
            # Check expiry
            expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
            if expires < datetime.now(timezone.utc):
                self.client.table("remember_tokens").delete().eq("token", token).execute()
                return None, None
            # Fetch user info
            user = self.client.table("users").select("id, display_name").eq("id", row["user_id"]).execute()
            if user.data:
                return user.data[0]["id"], user.data[0].get("display_name", "")
            return None, None
        except Exception as e:
            print(f"Error validating remember token: {e}")
            return None, None

    def delete_remember_token_for_user(self, user_id: str):
        """Remove remember-me token (on logout)."""
        if not self.connected:
            return
        try:
            self.client.table("remember_tokens").delete().eq("user_id", user_id).execute()
        except Exception:
            pass

    # ─── Weight Logs ───────────────────────────────────────────────────────────

    def log_weight(self, weight_kg: float, log_date: date, user_id: str, notes: str = "") -> bool:
        if not self.connected:
            return False
        try:
            existing = self.client.table("weight_logs").select("id").eq("date", str(log_date)).eq("user_id", user_id).execute()
            if existing.data:
                self.client.table("weight_logs").update({"weight_kg": weight_kg, "notes": notes}).eq("id", existing.data[0]["id"]).execute()
            else:
                self.client.table("weight_logs").insert({"date": str(log_date), "weight_kg": weight_kg, "notes": notes, "user_id": user_id}).execute()
            return True
        except Exception as e:
            print(f"Error saving weight: {e}")
            return False

    def get_weight_history(self, days: int = 90, user_id: str = "") -> List[Dict]:
        if not self.connected:
            return self._demo_weight_data(days)
        try:
            from_date = date.today() - timedelta(days=days)
            result = (
                self.client.table("weight_logs")
                .select("*")
                .eq("user_id", user_id)
                .gte("date", str(from_date))
                .order("date")
                .execute()
            )
            return result.data
        except Exception as e:
            print(f"Error fetching weight history: {e}")
            return []

    def delete_weight(self, weight_id: str) -> bool:
        if not self.connected:
            return False
        try:
            self.client.table("weight_logs").delete().eq("id", weight_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting weight: {e}")
            return False

    def get_latest_weight(self, user_id: str = "") -> Optional[Dict]:
        if not self.connected:
            return {"weight_kg": 74.2, "date": str(date.today()), "notes": "Demo"}
        try:
            result = (
                self.client.table("weight_logs")
                .select("*")
                .eq("user_id", user_id)
                .order("date", desc=True)
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error fetching latest weight: {e}")
            return None

    def get_previous_weight(self, user_id: str = "") -> Optional[Dict]:
        if not self.connected:
            return {"weight_kg": 74.8, "date": str(date.today() - timedelta(days=7))}
        try:
            result = (
                self.client.table("weight_logs")
                .select("*")
                .eq("user_id", user_id)
                .order("date", desc=True)
                .limit(2)
                .execute()
            )
            return result.data[1] if len(result.data) >= 2 else None
        except Exception as e:
            print(f"Error fetching previous weight: {e}")
            return None

    # ─── Meal Logs ─────────────────────────────────────────────────────────────

    def log_meal(self, meal_data: Dict) -> bool:
        if not self.connected:
            return False
        try:
            self.client.table("meal_logs").insert(meal_data).execute()
            return True
        except Exception as e:
            print(f"Error saving meal: {e}")
            return False

    def update_meal(self, meal_id: str, updates: Dict) -> bool:
        if not self.connected:
            return False
        try:
            self.client.table("meal_logs").update(updates).eq("id", meal_id).execute()
            return True
        except Exception as e:
            print(f"Error updating meal: {e}")
            return False

    def delete_meal(self, meal_id: str) -> bool:
        if not self.connected:
            return False
        try:
            self.client.table("meal_logs").delete().eq("id", meal_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting meal: {e}")
            return False

    def get_meals_for_date(self, log_date: date, user_id: str = "") -> List[Dict]:
        if not self.connected:
            return self._demo_meals_today()
        try:
            result = (
                self.client.table("meal_logs")
                .select("*")
                .eq("user_id", user_id)
                .eq("date", str(log_date))
                .order("meal_number")
                .execute()
            )
            return result.data
        except Exception as e:
            print(f"Error fetching meals: {e}")
            return []

    def get_meal_history(self, days: int = 30, user_id: str = "") -> List[Dict]:
        if not self.connected:
            return []
        try:
            from_date = date.today() - timedelta(days=days)
            result = (
                self.client.table("meal_logs")
                .select("*")
                .eq("user_id", user_id)
                .gte("date", str(from_date))
                .order("date", desc=True)
                .execute()
            )
            return result.data
        except Exception as e:
            print(f"Error fetching meal history: {e}")
            return []

    def get_daily_totals(self, days: int = 30, user_id: str = "") -> List[Dict]:
        if not self.connected:
            return self._demo_daily_totals(days)
        try:
            meals = self.get_meal_history(days, user_id=user_id)
            if not meals:
                return []

            import pandas as pd
            df = pd.DataFrame(meals)
            df["date"] = pd.to_datetime(df["date"]).dt.date
            totals = (
                df.groupby("date")
                .agg(
                    protein_g=("protein_g", "sum"),
                    carbs_g=("carbs_g", "sum"),
                    fat_g=("fat_g", "sum"),
                    calories=("calories", "sum"),
                    meals_logged=("id", "count"),
                )
                .reset_index()
                .sort_values("date")
            )
            return totals.to_dict("records")
        except Exception as e:
            print(f"Error computing daily totals: {e}")
            return []

    # ─── Fasting Logs ──────────────────────────────────────────────────────────

    def log_fasting(self, log_date: date, completed: bool, user_id: str,
                    first_meal_time: Optional[str] = None, notes: str = "") -> bool:
        if not self.connected:
            return False
        try:
            existing = self.client.table("fasting_logs").select("id").eq("date", str(log_date)).eq("user_id", user_id).execute()
            data = {"date": str(log_date), "completed_fast": completed,
                    "first_meal_time": first_meal_time, "notes": notes, "user_id": user_id}
            if existing.data:
                self.client.table("fasting_logs").update(data).eq("id", existing.data[0]["id"]).execute()
            else:
                self.client.table("fasting_logs").insert(data).execute()
            return True
        except Exception as e:
            print(f"Error saving fasting log: {e}")
            return False

    def get_fasting_streak(self, user_id: str = "") -> int:
        if not self.connected:
            return 5
        try:
            meals = self.get_meal_history(days=60, user_id=user_id)
            logged_dates = {m["date"][:10] for m in meals}
            if not logged_dates:
                return 0
            check = str(date.today())
            if check not in logged_dates:
                check = str(date.today() - timedelta(days=1))
            streak = 0
            from datetime import date as dt_date
            check_d = dt_date.fromisoformat(check)
            while str(check_d) in logged_dates:
                streak += 1
                check_d -= timedelta(days=1)
            return streak
        except Exception as e:
            print(f"Error fetching streak: {e}")
            return 0

    # ─── User Settings ─────────────────────────────────────────────────────────

    def get_settings(self, user_id: str = "") -> Dict:
        if not self.connected:
            return {}
        try:
            result = self.client.table("user_settings").select("*").eq("user_id", user_id).execute()
            return {row["key"]: row["value"] for row in result.data}
        except Exception as e:
            print(f"Error loading settings: {e}")
            return {}

    def save_setting(self, key: str, value: str, user_id: str = "") -> bool:
        if not self.connected:
            return False
        try:
            existing = self.client.table("user_settings").select("id").eq("key", key).eq("user_id", user_id).execute()
            if existing.data:
                self.client.table("user_settings").update({"value": str(value)}).eq("id", existing.data[0]["id"]).execute()
            else:
                self.client.table("user_settings").insert({"key": key, "value": str(value), "user_id": user_id}).execute()
            return True
        except Exception as e:
            print(f"Error saving setting {key}: {e}")
            return False

    def save_settings(self, settings: Dict, user_id: str = "") -> bool:
        return all(self.save_setting(k, v, user_id=user_id) for k, v in settings.items())

    # ─── Demo / Fallback Data ──────────────────────────────────────────────────

    def _demo_weight_data(self, days: int = 90) -> List[Dict]:
        random.seed(42)
        data = []
        weight = 75.5
        for i in range(days):
            d = date.today() - timedelta(days=days - i)
            if i % 3 == 0:
                weight = round(weight + random.uniform(-0.4, 0.2), 1)
                data.append({"date": str(d), "weight_kg": weight, "notes": "Demo"})
        return data

    def _demo_meals_today(self) -> List[Dict]:
        return [
            {
                "id": "demo-1",
                "date": str(date.today()),
                "meal_number": 1,
                "description": "Grilled chicken breast with salad and olive oil",
                "protein_g": 45.0,
                "carbs_g": 6.0,
                "fat_g": 14.0,
                "calories": 330,
            }
        ]

    def _demo_daily_totals(self, days: int = 30) -> List[Dict]:
        random.seed(7)
        data = []
        for i in range(days):
            d = date.today() - timedelta(days=days - i)
            data.append({
                "date": d,
                "protein_g": round(random.uniform(90, 140), 1),
                "carbs_g": round(random.uniform(15, 35), 1),
                "fat_g": round(random.uniform(40, 75), 1),
                "calories": random.randint(1100, 1600),
                "meals_logged": random.choice([1, 2]),
            })
        return data

"""
DietFocus – database.py
Supabase integration for weight logs, meal logs, and fasting logs.
Falls back to demo data when not configured.
"""

import os
import random
from datetime import date, timedelta
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
            # Ping to verify connection
            self.client.table("weight_logs").select("id").limit(1).execute()
            self.connected = True
            print("✅ Supabase connected.")
        except Exception as e:
            print(f"⚠️  Supabase connection failed: {e}\nRunning in demo mode.")

    # ─── Weight Logs ───────────────────────────────────────────────────────────

    def log_weight(self, weight_kg: float, log_date: date, notes: str = "") -> bool:
        """Insert or update a weight entry for the given date."""
        if not self.connected:
            return False
        try:
            self.client.table("weight_logs").upsert(
                {"date": str(log_date), "weight_kg": weight_kg, "notes": notes},
                on_conflict="date"
            ).execute()
            return True
        except Exception as e:
            print(f"Error saving weight: {e}")
            return False

    def get_weight_history(self, days: int = 90) -> List[Dict]:
        """Return all weight entries for the last N days."""
        if not self.connected:
            return self._demo_weight_data(days)
        try:
            from_date = date.today() - timedelta(days=days)
            result = (
                self.client.table("weight_logs")
                .select("*")
                .gte("date", str(from_date))
                .order("date")
                .execute()
            )
            return result.data
        except Exception as e:
            print(f"Error fetching weight history: {e}")
            return []

    def delete_weight(self, weight_id: str) -> bool:
        """Delete a weight entry by id."""
        if not self.connected:
            return False
        try:
            self.client.table("weight_logs").delete().eq("id", weight_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting weight: {e}")
            return False

    def get_latest_weight(self) -> Optional[Dict]:
        """Return the most recent weight entry."""
        if not self.connected:
            return {"weight_kg": 74.2, "date": str(date.today()), "notes": "Demo"}
        try:
            result = (
                self.client.table("weight_logs")
                .select("*")
                .order("date", desc=True)
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error fetching latest weight: {e}")
            return None

    def get_previous_weight(self) -> Optional[Dict]:
        """Return the second most recent weight entry (for delta calculation)."""
        if not self.connected:
            return {"weight_kg": 74.8, "date": str(date.today() - timedelta(days=7))}
        try:
            result = (
                self.client.table("weight_logs")
                .select("*")
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
        """Insert a meal entry."""
        if not self.connected:
            return False
        try:
            self.client.table("meal_logs").insert(meal_data).execute()
            return True
        except Exception as e:
            print(f"Error saving meal: {e}")
            return False

    def update_meal(self, meal_id: str, updates: Dict) -> bool:
        """Update an existing meal entry by id."""
        if not self.connected:
            return False
        try:
            self.client.table("meal_logs").update(updates).eq("id", meal_id).execute()
            return True
        except Exception as e:
            print(f"Error updating meal: {e}")
            return False

    def delete_meal(self, meal_id: str) -> bool:
        """Delete a meal entry."""
        if not self.connected:
            return False
        try:
            self.client.table("meal_logs").delete().eq("id", meal_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting meal: {e}")
            return False

    def get_meals_for_date(self, log_date: date) -> List[Dict]:
        """Return all meals logged on a specific date."""
        if not self.connected:
            return self._demo_meals_today()
        try:
            result = (
                self.client.table("meal_logs")
                .select("*")
                .eq("date", str(log_date))
                .order("meal_number")
                .execute()
            )
            return result.data
        except Exception as e:
            print(f"Error fetching meals: {e}")
            return []

    def get_meal_history(self, days: int = 30) -> List[Dict]:
        """Return all meals for the last N days."""
        if not self.connected:
            return []
        try:
            from_date = date.today() - timedelta(days=days)
            result = (
                self.client.table("meal_logs")
                .select("*")
                .gte("date", str(from_date))
                .order("date", desc=True)
                .execute()
            )
            return result.data
        except Exception as e:
            print(f"Error fetching meal history: {e}")
            return []

    def get_daily_totals(self, days: int = 30) -> List[Dict]:
        """Return per-day macro totals for the last N days."""
        if not self.connected:
            return self._demo_daily_totals(days)
        try:
            meals = self.get_meal_history(days)
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

    def log_fasting(self, log_date: date, completed: bool,
                    first_meal_time: Optional[str] = None, notes: str = "") -> bool:
        if not self.connected:
            return False
        try:
            self.client.table("fasting_logs").upsert(
                {
                    "date": str(log_date),
                    "completed_fast": completed,
                    "first_meal_time": first_meal_time,
                    "notes": notes,
                },
                on_conflict="date"
            ).execute()
            return True
        except Exception as e:
            print(f"Error saving fasting log: {e}")
            return False

    def get_fasting_streak(self) -> int:
        """Count consecutive days (ending today or yesterday) where at least one meal was logged."""
        if not self.connected:
            return 5
        try:
            # Use get_meal_history which is known to work reliably
            meals = self.get_meal_history(days=60)
            logged_dates = set()
            for m in meals:
                logged_dates.add(m["date"][:10])

            if not logged_dates:
                return 0

            check = str(date.today())
            if check not in logged_dates:
                check = str(date.today() - timedelta(days=1))

            streak = 0
            check_d = date.fromisoformat(check)
            while str(check_d) in logged_dates:
                streak += 1
                check_d -= timedelta(days=1)
            return streak
        except Exception as e:
            print(f"Error fetching streak: {e}")
            return 0

    # ─── User Settings ─────────────────────────────────────────────────────────

    def get_settings(self) -> Dict:
        """Load all user settings from Supabase, returns empty dict if not connected."""
        if not self.connected:
            return {}
        try:
            result = self.client.table("user_settings").select("*").execute()
            return {row["key"]: row["value"] for row in result.data}
        except Exception as e:
            print(f"Error loading settings: {e}")
            return {}

    def save_setting(self, key: str, value: str) -> bool:
        """Save a single setting key/value to Supabase."""
        if not self.connected:
            return False
        try:
            self.client.table("user_settings").upsert(
                {"key": key, "value": str(value), "updated_at": "now()"},
                on_conflict="key"
            ).execute()
            return True
        except Exception as e:
            print(f"Error saving setting {key}: {e}")
            return False

    def save_settings(self, settings: Dict) -> bool:
        """Save multiple settings at once."""
        return all(self.save_setting(k, v) for k, v in settings.items())

    # ─── Demo / Fallback Data ──────────────────────────────────────────────────

    def _demo_weight_data(self, days: int = 90) -> List[Dict]:
        random.seed(42)
        data = []
        weight = 75.5
        for i in range(days):
            d = date.today() - timedelta(days=days - i)
            if i % 3 == 0:  # only log some days
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

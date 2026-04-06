"""
DietFocus – app.py
Main Streamlit dashboard for weight & diet tracking.
Run with: streamlit run app.py
"""

import io
import os
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yaml
from dotenv import load_dotenv

from database import DatabaseManager
from notifications import NotificationManager
from vision_analyzer import VisionAnalyzer

load_dotenv()

# ─── Config ────────────────────────────────────────────────────────────────────

@st.cache_resource
def load_config() -> Dict:
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

@st.cache_resource
def get_db() -> DatabaseManager:
    return DatabaseManager()

@st.cache_resource
def get_analyzer() -> VisionAnalyzer:
    return VisionAnalyzer()

@st.cache_resource
def get_notifier() -> NotificationManager:
    return NotificationManager()

cfg = load_config()
db  = get_db()
analyzer  = get_analyzer()
notifier  = get_notifier()

TARGETS = cfg["targets"]
FASTING = cfg["fasting"]
EATING_START = time.fromisoformat(FASTING["eating_window_start"])
EATING_END   = time.fromisoformat(FASTING["eating_window_end"])

# ─── Page Setup ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="DietFocus",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .main { background-color: #f8faf8; }

    .page-title {
        font-size: 2rem; font-weight: 700;
        color: #1a3c1a; margin-bottom: 0.2rem;
    }
    .page-subtitle { font-size: 0.95rem; color: #666; margin-bottom: 1.5rem; }

    .kpi-card {
        background: white;
        border-radius: 14px;
        padding: 1.2rem 1.4rem;
        box-shadow: 0 2px 10px rgba(0,0,0,0.07);
        text-align: center;
        border-top: 4px solid #4CAF50;
    }
    .kpi-value  { font-size: 2rem; font-weight: 700; color: #1B5E20; }
    .kpi-delta  { font-size: 0.85rem; margin-top: 2px; }
    .kpi-label  { font-size: 0.78rem; color: #888; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.04em; }

    .fast-active {
        background: linear-gradient(135deg, #E8F5E9, #C8E6C9);
        border: 1px solid #A5D6A7; border-radius: 12px;
        padding: 1rem 1.4rem; margin-bottom: 1rem;
    }
    .fast-closed {
        background: #FFF3E0; border: 1px solid #FFCC80;
        border-radius: 12px; padding: 1rem 1.4rem; margin-bottom: 1rem;
    }
    .meal-card {
        background: white; border-radius: 12px;
        border-left: 5px solid #66BB6A;
        padding: 1rem 1.2rem; margin-bottom: 0.8rem;
        box-shadow: 0 1px 6px rgba(0,0,0,0.06);
    }
    .alert-warning {
        background: #FFF8E1; border-left: 4px solid #FFC107;
        padding: 0.8rem 1rem; border-radius: 6px; margin: 0.5rem 0;
    }
    .alert-danger {
        background: #FFEBEE; border-left: 4px solid #EF5350;
        padding: 0.8rem 1rem; border-radius: 6px; margin: 0.5rem 0;
    }
    .alert-success {
        background: #E8F5E9; border-left: 4px solid #4CAF50;
        padding: 0.8rem 1rem; border-radius: 6px; margin: 0.5rem 0;
    }
    div[data-testid="stProgress"] > div > div > div {
        background-color: #4CAF50 !important;
    }
    .stButton > button {
        border-radius: 8px; font-weight: 600;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ─── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🥗 DietFocus")
    st.caption("Low-carb · High-protein · IF 16:8")
    st.divider()

    page = st.radio(
        "Navigation",
        ["🏠 Dashboard", "⚖️ Log Weight", "🍽️ Log Meal", "📊 History", "🔔 Notifications", "⚙️ Settings"],
        label_visibility="collapsed",
    )

    st.divider()

    # Live fasting status in sidebar
    now = datetime.now().time()
    if EATING_START <= now <= EATING_END:
        remaining = datetime.combine(date.today(), EATING_END) - datetime.now()
        h, m = divmod(remaining.seconds // 60, 60)
        st.success(f"🟢 Eating window\n{h}h {m}m remaining")
    elif now < EATING_START:
        until = datetime.combine(date.today(), EATING_START) - datetime.now()
        h, m = divmod(until.seconds // 60, 60)
        st.info(f"⏳ Fasting\n{h}h {m}m until window")
    else:
        st.warning("🔒 Eating window closed")

    st.divider()
    status = "🟢 Connected" if db.connected else "🔴 Demo mode"
    st.caption(f"DB: {status}")

# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: Dashboard
# ═══════════════════════════════════════════════════════════════════════════════

if page == "🏠 Dashboard":
    st.markdown('<div class="page-title">Dashboard</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="page-subtitle">{date.today().strftime("%A, %d %B %Y")}</div>',
        unsafe_allow_html=True,
    )

    # ── KPI Row ────────────────────────────────────────────────────────────────
    latest  = db.get_latest_weight()
    prev    = db.get_previous_weight()
    meals   = db.get_meals_for_date(date.today())

    curr_weight = latest["weight_kg"] if latest else None
    prev_weight = prev["weight_kg"] if prev else None
    delta = round(curr_weight - prev_weight, 1) if (curr_weight and prev_weight) else None

    today_protein = sum(m.get("protein_g", 0) for m in meals)
    today_carbs   = sum(m.get("carbs_g", 0)   for m in meals)
    today_cals    = sum(m.get("calories", 0)   for m in meals)
    streak        = db.get_fasting_streak()

    c1, c2, c3, c4, c5 = st.columns(5)

    def kpi(col, value, label, delta_text="", color="#1B5E20"):
        col.markdown(
            f"""<div class="kpi-card">
                <div class="kpi-value" style="color:{color}">{value}</div>
                <div class="kpi-delta">{delta_text}</div>
                <div class="kpi-label">{label}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    weight_display = f"{curr_weight} kg" if curr_weight else "–"
    delta_display  = (f"{'▲' if delta > 0 else '▼'} {abs(delta)} kg vs last" if delta else "")
    delta_color    = "color:#EF5350" if (delta and delta > 0) else "color:#4CAF50"

    c1.markdown(
        f"""<div class="kpi-card" style="border-top-color:#2196F3">
            <div class="kpi-value" style="color:#1565C0">{weight_display}</div>
            <div class="kpi-delta" style="{delta_color}">{delta_display}</div>
            <div class="kpi-label">Current Weight</div>
        </div>""",
        unsafe_allow_html=True,
    )

    prot_pct = int(today_protein / TARGETS["daily_protein_g"] * 100) if TARGETS["daily_protein_g"] else 0
    kpi(c2, f"{today_protein:.0f}g", "Protein today",
        f"{prot_pct}% of {TARGETS['daily_protein_g']}g target",
        "#1B5E20" if prot_pct >= 80 else "#E65100")

    carb_color = "#EF5350" if today_carbs > TARGETS["daily_carbs_g"] else "#1B5E20"
    kpi(c3, f"{today_carbs:.0f}g", "Net Carbs today",
        f"Limit: {TARGETS['daily_carbs_g']}g", carb_color)

    kpi(c4, today_cals, "Calories today",
        f"Target: {TARGETS['daily_calories']} kcal")

    kpi(c5, f"{streak}🔥", "Fasting Streak", "days in a row",
        "#E65100" if streak > 0 else "#888")

    st.divider()

    # ── Macro Progress ─────────────────────────────────────────────────────────
    st.subheader("Today's Macro Progress")
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        prot_frac = min(today_protein / TARGETS["daily_protein_g"], 1.0)
        st.write(f"**Protein** – {today_protein:.0f} / {TARGETS['daily_protein_g']} g")
        st.progress(prot_frac)

    with col_b:
        carb_frac = min(today_carbs / TARGETS["daily_carbs_g"], 1.0)
        st.write(f"**Net Carbs** – {today_carbs:.0f} / {TARGETS['daily_carbs_g']} g")
        st.progress(carb_frac)
        if today_carbs > TARGETS["daily_carbs_g"]:
            st.markdown(
                '<div class="alert-danger">⚠️ Carb limit exceeded!</div>',
                unsafe_allow_html=True,
            )

    with col_c:
        cal_frac = min(today_cals / TARGETS["daily_calories"], 1.0)
        st.write(f"**Calories** – {today_cals} / {TARGETS['daily_calories']} kcal")
        st.progress(cal_frac)

    st.divider()

    # ── Today's Meals ──────────────────────────────────────────────────────────
    st.subheader("Today's Meals")
    if meals:
        for m in meals:
            st.markdown(
                f"""<div class="meal-card">
                    <strong>Meal {m['meal_number']}</strong> &nbsp;·&nbsp;
                    {m['description']}<br>
                    <small>
                        🥩 Protein: {m.get('protein_g', 0):.0f}g &nbsp;|&nbsp;
                        🌾 Carbs: {m.get('carbs_g', 0):.0f}g &nbsp;|&nbsp;
                        🫒 Fat: {m.get('fat_g', 0):.0f}g &nbsp;|&nbsp;
                        🔥 {m.get('calories', 0)} kcal
                    </small>
                </div>""",
                unsafe_allow_html=True,
            )
    else:
        st.info("No meals logged today. Use **🍽️ Log Meal** to add one.")

    st.divider()

    # ── Weight Trend Chart ─────────────────────────────────────────────────────
    st.subheader("Weight Trend")
    weight_data = db.get_weight_history(days=cfg["visualization"]["weight_chart_days"])

    if weight_data:
        df = pd.DataFrame(weight_data)
        df["date"] = pd.to_datetime(df["date"])

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["weight_kg"],
                mode="lines+markers",
                name="Weight",
                line=dict(color="#2E7D32", width=2.5),
                marker=dict(size=6, color="#4CAF50"),
                hovertemplate="<b>%{x|%d %b}</b><br>%{y:.1f} kg<extra></extra>",
            )
        )
        # 7-day rolling average
        if len(df) >= 7:
            df["rolling_avg"] = df["weight_kg"].rolling(7, min_periods=1).mean()
            fig.add_trace(
                go.Scatter(
                    x=df["date"],
                    y=df["rolling_avg"],
                    mode="lines",
                    name="7-day avg",
                    line=dict(color="#FF8F00", width=1.5, dash="dot"),
                    hovertemplate="Avg: %{y:.1f} kg<extra></extra>",
                )
            )
        fig.update_layout(
            height=320,
            plot_bgcolor="white",
            paper_bgcolor="white",
            margin=dict(l=0, r=0, t=10, b=0),
            legend=dict(orientation="h", y=1.1),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Start logging your weight to see the trend chart.")

# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: Log Weight
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "⚖️ Log Weight":
    st.markdown('<div class="page-title">Log Weight</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">Record your weight – ideally every Monday morning, fasted.</div>',
        unsafe_allow_html=True,
    )

    latest = db.get_latest_weight()
    if latest:
        st.markdown(
            f'<div class="alert-success">Last recorded: <strong>{latest["weight_kg"]} kg</strong>'
            f' on {latest["date"]}</div>',
            unsafe_allow_html=True,
        )

    with st.form("weight_form"):
        col1, col2 = st.columns([1, 2])
        with col1:
            log_date = st.date_input("Date", value=date.today(), max_value=date.today())
            weight = st.number_input(
                "Weight (kg)",
                min_value=30.0,
                max_value=250.0,
                value=float(latest["weight_kg"]) if latest else 70.0,
                step=0.1,
                format="%.1f",
            )
        with col2:
            notes = st.text_area("Notes (optional)", placeholder="e.g. after gym, felt bloated…", height=100)

        submitted = st.form_submit_button("💾 Save Weight", use_container_width=True)
        if submitted:
            if db.log_weight(weight, log_date, notes):
                prev = db.get_previous_weight()
                delta = round(weight - prev["weight_kg"], 1) if prev else None
                if delta is not None:
                    direction = "▲ gained" if delta > 0 else "▼ lost"
                    st.success(f"✅ Saved {weight} kg — you {direction} {abs(delta)} kg since last entry.")
                else:
                    st.success(f"✅ Saved {weight} kg for {log_date}.")
                st.cache_resource.clear()
            elif not db.connected:
                st.warning("⚠️ Not connected to database – entry not saved (demo mode).")
            else:
                st.error("❌ Could not save. Check your Supabase connection.")

    # Recent history table with delete buttons
    st.divider()
    st.subheader("Recent Weigh-Ins")
    history = db.get_weight_history(days=60)
    if history:
        records = sorted(history, key=lambda x: x["date"], reverse=True)
        for row in records:
            col1, col2, col3, col4 = st.columns([2, 1, 3, 0.5])
            col1.write(row["date"])
            col2.write(f"**{row['weight_kg']} kg**")
            col3.write(row.get("notes", ""))
            if col4.button("🗑️", key=f"del_w_{row['id']}"):
                if db.delete_weight(row["id"]):
                    st.success("Entry deleted.")
                    st.rerun()
                else:
                    st.error("Could not delete entry.")
    else:
        st.info("No weight entries yet.")

# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: Log Meal
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "🍽️ Log Meal":
    st.markdown('<div class="page-title">Log Meal</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">Describe your meal or upload a photo for automatic nutrition analysis.</div>',
        unsafe_allow_html=True,
    )

    # Fasting window check
    now = datetime.now().time()
    if now < EATING_START:
        until = datetime.combine(date.today(), EATING_START) - datetime.now()
        h, m = divmod(until.seconds // 60, 60)
        st.markdown(
            f'<div class="fast-closed">⏳ <strong>Fasting window active.</strong> '
            f'Eating window opens in {h}h {m}m (at {FASTING["eating_window_start"]}).</div>',
            unsafe_allow_html=True,
        )
    elif now > EATING_END:
        st.markdown(
            '<div class="fast-closed">🔒 <strong>Eating window closed</strong> for today.</div>',
            unsafe_allow_html=True,
        )
    else:
        remaining = datetime.combine(date.today(), EATING_END) - datetime.now()
        h, m = divmod(remaining.seconds // 60, 60)
        st.markdown(
            f'<div class="fast-active">🟢 <strong>Eating window open</strong> – '
            f'{h}h {m}m remaining (closes at {FASTING["eating_window_end"]}).</div>',
            unsafe_allow_html=True,
        )

    col_form, col_result = st.columns([1, 1])

    with col_form:
        with st.form("meal_form"):
            log_date    = st.date_input("Date", value=date.today(), max_value=date.today())
            meal_number = st.selectbox("Meal", [1, 2],
                                       format_func=lambda x: cfg["meals"]["meal_labels"][x - 1])
            description = st.text_area(
                "Meal description",
                placeholder="e.g. Grilled salmon fillet, steamed broccoli, olive oil dressing…",
                height=100,
            )
            uploaded_file = st.file_uploader(
                "📷 Upload meal photo (optional)",
                type=["jpg", "jpeg", "png", "webp"],
            )

            st.markdown("**Manual macro entry** (leave 0 to use AI estimate)")
            mc1, mc2, mc3, mc4 = st.columns(4)
            manual_protein  = mc1.number_input("Protein (g)", 0.0, 500.0, 0.0, 0.5)
            manual_carbs    = mc2.number_input("Carbs (g)",   0.0, 500.0, 0.0, 0.5)
            manual_fat      = mc3.number_input("Fat (g)",     0.0, 500.0, 0.0, 0.5)
            manual_calories = mc4.number_input("Calories",    0,   5000,  0,   10)

            submitted = st.form_submit_button("🔍 Analyze & Save", use_container_width=True)

    with col_result:
        if submitted:
            if not description and not uploaded_file:
                st.error("Please provide a meal description or photo.")
            else:
                analysis = {}
                with st.spinner("Analyzing meal…"):
                    if uploaded_file:
                        image_bytes = uploaded_file.read()
                        media_type  = f"image/{uploaded_file.type.split('/')[-1]}"
                        analysis    = analyzer.analyze_image(image_bytes, media_type)
                        from PIL import Image as PILImage
                        st.image(PILImage.open(io.BytesIO(image_bytes)), caption="Uploaded meal", use_column_width=True)
                    elif description:
                        analysis = analyzer.analyze_text(description)

                # Use manual values if provided, else AI values
                final_protein  = manual_protein  if manual_protein  > 0 else analysis.get("protein_g",  0)
                final_carbs    = manual_carbs    if manual_carbs    > 0 else analysis.get("carbs_g",    0)
                final_fat      = manual_fat      if manual_fat      > 0 else analysis.get("fat_g",      0)
                final_calories = manual_calories if manual_calories > 0 else analysis.get("calories",   0)

                if analysis and not analysis.get("error") == "unavailable":
                    st.success(f"✅ Analysis complete (confidence: {analysis.get('confidence', 'n/a')})")
                    if analysis.get("food_items"):
                        st.markdown("**Identified items:** " + ", ".join(analysis["food_items"]))
                    if analysis.get("notes"):
                        st.caption(f"Note: {analysis['notes']}")

                st.markdown("#### Nutrition Summary")
                n1, n2, n3, n4 = st.columns(4)
                n1.metric("Protein", f"{final_protein:.0f}g")
                n2.metric("Net Carbs", f"{final_carbs:.0f}g",
                          delta=f"limit: {TARGETS['daily_carbs_g']}g",
                          delta_color="inverse")
                n3.metric("Fat", f"{final_fat:.0f}g")
                n4.metric("Calories", f"{final_calories}")

                meal_data = {
                    "date": str(log_date),
                    "meal_number": meal_number,
                    "description": description or "Photo meal",
                    "protein_g": final_protein,
                    "carbs_g": final_carbs,
                    "fat_g": final_fat,
                    "calories": final_calories,
                    "analysis_raw": str(analysis),
                }

                if st.button("💾 Confirm & Save", key="save_meal"):
                    if db.log_meal(meal_data):
                        st.success("Meal saved! ✅")
                        # Check carb alert
                        today_meals  = db.get_meals_for_date(log_date)
                        total_carbs  = sum(m.get("carbs_g", 0) for m in today_meals) + final_carbs
                        if total_carbs > TARGETS["daily_carbs_g"]:
                            st.markdown(
                                f'<div class="alert-warning">⚠️ Daily carbs now '
                                f'{total_carbs:.0f}g – over your {TARGETS["daily_carbs_g"]}g limit.</div>',
                                unsafe_allow_html=True,
                            )
                    elif not db.connected:
                        st.warning("Demo mode – meal not persisted.")
                    else:
                        st.error("Could not save meal.")

    # Today's meals list
    st.divider()
    st.subheader(f"Meals logged today ({date.today().strftime('%d %b')})")
    today_meals = db.get_meals_for_date(date.today())
    if today_meals:
        for m in today_meals:
            cols = st.columns([3, 1, 1, 1, 1, 0.5])
            cols[0].write(f"**Meal {m['meal_number']}** – {m['description']}")
            cols[1].write(f"🥩 {m.get('protein_g', 0):.0f}g")
            cols[2].write(f"🌾 {m.get('carbs_g', 0):.0f}g")
            cols[3].write(f"🫒 {m.get('fat_g', 0):.0f}g")
            cols[4].write(f"🔥 {m.get('calories', 0)} kcal")
            if cols[5].button("🗑️", key=f"del_{m['id']}"):
                db.delete_meal(m["id"])
                st.rerun()
    else:
        st.info("No meals logged today.")

# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: History
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "📊 History":
    st.markdown('<div class="page-title">History & Reports</div>', unsafe_allow_html=True)

    days_options = {7: "Last 7 days", 14: "Last 14 days", 30: "Last 30 days", 90: "Last 90 days"}
    selected_days = st.selectbox("Time range", list(days_options.keys()),
                                 format_func=lambda x: days_options[x], index=2)

    tab1, tab2, tab3 = st.tabs(["📈 Macros Over Time", "🥗 Meal Log", "⚖️ Weight Table"])

    with tab1:
        totals = db.get_daily_totals(days=selected_days)
        if totals:
            df = pd.DataFrame(totals)
            df["date"] = pd.to_datetime(df["date"])

            # Macro bar chart
            fig = go.Figure()
            fig.add_bar(x=df["date"], y=df["protein_g"], name="Protein", marker_color="#2E7D32")
            fig.add_bar(x=df["date"], y=df["carbs_g"],   name="Net Carbs", marker_color="#FF8F00")
            fig.add_bar(x=df["date"], y=df["fat_g"],     name="Fat",     marker_color="#1565C0")
            fig.update_layout(
                barmode="group", height=340,
                plot_bgcolor="white", paper_bgcolor="white",
                margin=dict(l=0, r=0, t=10, b=0),
                legend=dict(orientation="h", y=1.1),
                xaxis=dict(showgrid=False),
                yaxis=dict(title="grams", showgrid=True, gridcolor="#f0f0f0"),
            )
            # Carb limit reference line
            fig.add_hline(
                y=TARGETS["daily_carbs_g"],
                line_dash="dot",
                line_color="#EF5350",
                annotation_text=f"Carb limit ({TARGETS['daily_carbs_g']}g)",
                annotation_position="top right",
            )
            st.plotly_chart(fig, use_container_width=True)

            # Summary stats
            st.subheader("Period Averages")
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Avg Protein",  f"{df['protein_g'].mean():.0f}g",  f"target {TARGETS['daily_protein_g']}g")
            s2.metric("Avg Net Carbs", f"{df['carbs_g'].mean():.0f}g",   f"limit {TARGETS['daily_carbs_g']}g")
            s3.metric("Avg Fat",       f"{df['fat_g'].mean():.0f}g")
            s4.metric("Avg Calories",  f"{df['calories'].mean():.0f}")

            days_over_carbs = (df["carbs_g"] > TARGETS["daily_carbs_g"]).sum()
            days_hit_protein = (df["protein_g"] >= TARGETS["daily_protein_g"] * 0.8).sum()
            st.info(
                f"📊 Days over carb limit: **{days_over_carbs}** | "
                f"Days hitting ≥80% protein target: **{days_hit_protein}** of {len(df)}"
            )
        else:
            st.info("No macro data in this range yet.")

    with tab2:
        meals = db.get_meal_history(days=selected_days)
        if meals:
            df_meals = pd.DataFrame(meals)[
                ["date", "meal_number", "description", "protein_g", "carbs_g", "fat_g", "calories"]
            ].sort_values("date", ascending=False)
            df_meals.columns = ["Date", "Meal #", "Description", "Protein (g)", "Carbs (g)", "Fat (g)", "Calories"]
            st.dataframe(df_meals, use_container_width=True, hide_index=True)

            csv = df_meals.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download CSV",
                data=csv,
                file_name=f"dietfocus_meals_{date.today()}.csv",
                mime="text/csv",
            )
        else:
            st.info("No meal data in this range yet.")

    with tab3:
        weight_data = db.get_weight_history(days=selected_days)
        if weight_data:
            df_w = pd.DataFrame(weight_data)[["date", "weight_kg", "notes"]].sort_values("date", ascending=False)
            df_w.columns = ["Date", "Weight (kg)", "Notes"]
            df_w["Change (kg)"] = df_w["Weight (kg)"].diff(periods=-1).round(1)
            st.dataframe(df_w, use_container_width=True, hide_index=True)
        else:
            st.info("No weight data in this range yet.")

# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: Notifications
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "🔔 Notifications":
    st.markdown('<div class="page-title">Notifications</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="page-subtitle">Test or manually trigger WhatsApp reminders.</div>',
        unsafe_allow_html=True,
    )

    provider_status = "🟢 Enabled" if notifier.enabled else "🔴 Not configured"
    st.info(f"Notification provider: **{provider_status}**")

    if not notifier.enabled:
        st.markdown(
            """<div class="alert-warning">
            WhatsApp notifications are not configured.<br>
            Add <code>TWILIO_*</code> or <code>MAKE_WEBHOOK_URL</code> to your <code>.env</code> file.
            </div>""",
            unsafe_allow_html=True,
        )

    st.divider()
    st.subheader("Manual Triggers")

    col_a, col_b = st.columns(2)

    with col_a:
        if st.button("📱 Send Test Message", use_container_width=True):
            if notifier.send_test_message():
                st.success("Test message sent!")
            else:
                st.error("Failed to send. Check your .env configuration.")

        if st.button("⚖️ Weigh-In Reminder", use_container_width=True):
            if notifier.send_weigh_in_reminder():
                st.success("Weigh-in reminder sent!")
            else:
                st.error("Failed to send.")

    with col_b:
        meals_today = db.get_meals_for_date(date.today())
        if st.button("🍽️ Missing Meal Alert", use_container_width=True):
            if notifier.send_missing_meal_alert(len(meals_today)):
                st.success("Meal alert sent!")
            else:
                st.error("Failed to send.")

        if st.button("🚨 Carb Limit Alert", use_container_width=True):
            total_carbs = sum(m.get("carbs_g", 0) for m in meals_today)
            if notifier.send_carb_alert(total_carbs, TARGETS["daily_carbs_g"]):
                st.success("Carb alert sent!")
            else:
                st.error("Failed to send.")

    st.divider()
    st.subheader("Schedule Reference")
    st.markdown(
        f"""
| Alert | Trigger |
|---|---|
| ⚖️ Weigh-In Reminder | Every **{cfg['notifications']['weigh_in_day']}** at {cfg['notifications']['weigh_in_reminder_time']} |
| 🍽️ Missing Meal Alert | Daily at {cfg['notifications']['meal_missing_alert_time']} if meals < 2 |
| 🚨 Carb Limit Alert | Immediately when daily carbs exceed {TARGETS['daily_carbs_g']}g |
"""
    )
    st.caption("For automated scheduling, configure a cron job or use Make.com's scheduler.")

# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: Settings
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "⚙️ Settings":
    st.markdown('<div class="page-title">Settings</div>', unsafe_allow_html=True)

    tab_s1, tab_s2, tab_s3 = st.tabs(["🎯 Targets", "🔑 Setup Guide", "ℹ️ About"])

    with tab_s1:
        st.subheader("Daily Macro Targets")
        st.info("Edit `config.yaml` to change these values. Restart the app to apply.")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Protein target", f"{TARGETS['daily_protein_g']}g / day")
            st.metric("Net Carbs limit", f"{TARGETS['daily_carbs_g']}g / day")
        with col2:
            st.metric("Fat target",     f"{TARGETS['daily_fat_g']}g / day")
            st.metric("Calories",       f"{TARGETS['daily_calories']} kcal / day")

        st.subheader("Fasting Window")
        st.metric("Eating window",
                  f"{FASTING['eating_window_start']} – {FASTING['eating_window_end']}",
                  "16:8 Intermittent Fasting")
        st.caption(f"Allowed before window: {', '.join(FASTING['allowed_before_window'])}")

        st.subheader("Connection Status")
        s1, s2, s3 = st.columns(3)
        s1.metric("Supabase",  "🟢 Connected"   if db.connected           else "🔴 Demo mode")
        s2.metric("Vision AI", "🟢 Ready"        if analyzer.enabled       else "🔴 Not configured")
        s3.metric("Notifications", "🟢 Ready"    if notifier.enabled       else "🔴 Not configured")

    with tab_s2:
        st.subheader("Step-by-Step Setup Guide")
        st.markdown(
            """
### 1. Supabase (Database) – Free tier

1. Go to [supabase.com](https://supabase.com) → **Start your project** → sign up with GitHub.
2. Create a new project → choose a region close to you → set a DB password.
3. Once created, go to **Settings → API** and copy:
   - **Project URL** → paste as `SUPABASE_URL` in your `.env`
   - **anon public key** → paste as `SUPABASE_ANON_KEY`
4. Go to **SQL Editor** → paste the contents of `schema.sql` → click **Run**.

---

### 2. Anthropic API (Vision Analysis)

1. Go to [console.anthropic.com](https://console.anthropic.com) → sign up.
2. Navigate to **API Keys** → **Create Key**.
3. Paste the key as `ANTHROPIC_API_KEY` in your `.env`.
4. New accounts get free credits to get started.

---

### 3a. Twilio WhatsApp (Recommended)

1. Go to [twilio.com](https://twilio.com) → **Sign Up** (free trial).
2. In the Console, go to **Messaging → Try it Out → WhatsApp Sandbox**.
3. Follow the instructions to connect your WhatsApp to the sandbox.
4. Copy **Account SID** → `TWILIO_ACCOUNT_SID`
5. Copy **Auth Token** → `TWILIO_AUTH_TOKEN`
6. Set `TWILIO_WHATSAPP_FROM=whatsapp:+14155238886` (Twilio sandbox number)
7. Set `TWILIO_WHATSAPP_TO=whatsapp:+972XXXXXXXXX` (your number)

### 3b. Make.com Webhook (Alternative)

1. Go to [make.com](https://make.com) → Sign up → **Create a scenario**.
2. Add a **Webhooks → Custom Webhook** trigger module.
3. Connect it to a **WhatsApp Business** send-message module.
4. Activate the scenario and copy the webhook URL → `MAKE_WEBHOOK_URL`

---

### 4. Local Setup

```bash
# 1. Copy environment template
cp .env.example .env
# (edit .env with your keys)

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
streamlit run app.py
```
Open [http://localhost:8501](http://localhost:8501)
"""
        )

    with tab_s3:
        st.subheader("About DietFocus")
        st.markdown(
            f"""
**DietFocus v{cfg['app']['version']}**

A personal weight loss & diet tracking app built for:
- Low-carb, high-protein eating
- Intermittent fasting 16:8 (eating window: {FASTING['eating_window_start']}–{FASTING['eating_window_end']})
- 2 meals per day
- Weekly weigh-ins

Built with Streamlit · Supabase · Claude Vision · Twilio
"""
        )

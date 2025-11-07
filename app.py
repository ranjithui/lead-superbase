"""
Lead Management Streamlit App
---------------------------------
Features:
1. Dashboard — show lead counts (team + individuals)
2. Daily Upload — two forms: add daily leads + update conversions
3. Reporting — weekly/monthly summary
4. Admin Panel — create teams, add/update members with targets (CRUD + per-team tables)

Backend: Supabase (Postgres)
Host: Streamlit Cloud
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import uuid

# --- Supabase setup ---
try:
    from supabase import create_client, Client
except Exception:
    create_client = None
    Client = None

SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL"))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY"))

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_KEY and create_client:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Lead Management App", layout="wide")
st.title("📊 Lead Management System")

tab = st.sidebar.radio("Go to", ["Dashboard", "Daily Upload", "Reporting", "Admin"])

# ---------------------- Dashboard ----------------------
if tab == "Dashboard":
    st.header("📈 Dashboard")

    today = datetime.utcnow().date()
    start = st.date_input("Start Date", value=today - timedelta(days=30))
    end = st.date_input("End Date", value=today)

    def get_leads_supabase(start_date=None, end_date=None):
        if not supabase:
            return pd.DataFrame()
        try:
            query = supabase.table("leads").select("*")
            if start_date:
                query = query.gte("created_at", start_date.isoformat())
            if end_date:
                query = query.lte("created_at", end_date.isoformat())
            res = query.execute()
            df = pd.DataFrame(res.data if hasattr(res, "data") else res)
            return df
        except Exception as e:
            st.warning(f"⚠️ Failed to fetch leads: {e}")
            return pd.DataFrame()

    leads_df = get_leads_supabase(start_date=start, end_date=end)

    if leads_df.empty:
        st.warning("No leads found for this period.")
    else:
        if "created_at" in leads_df.columns:
            leads_df["created_at"] = pd.to_datetime(leads_df["created_at"])
        team_counts = leads_df.groupby("team_id", dropna=False).size().reset_index(name="Lead Count")
        owner_counts = leads_df.groupby("owner_id", dropna=False).size().reset_index(name="Lead Count")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("By Team")
            st.dataframe(team_counts)
        with col2:
            st.subheader("By Member")
            st.dataframe(owner_counts)

        st.subheader("Recent Leads")
        st.dataframe(leads_df.sort_values("created_at", ascending=False).head(50))

# ---------------------- Daily Upload ----------------------
elif tab == "Daily Upload":
    st.header("📤 Daily Lead Update")

    # helper functions
    def get_table(name):
        try:
            res = supabase.table(name).select("*").execute()
            df = pd.DataFrame(res.data if hasattr(res, "data") else res)
            return df
        except Exception as e:
            st.warning(f"⚠️ Failed to fetch {name}: {e}")
            return pd.DataFrame()

    def insert_leads(team_id, owner_id, lead_count, date):
        try:
            rows = []
            for _ in range(int(lead_count)):
                rows.append({
                    "team_id": team_id,
                    "owner_id": owner_id,
                    "created_at": datetime.combine(date, datetime.min.time()).isoformat(),
                    "converted": False,
                    "sales_value": 0,
                })
            supabase.table("leads").insert(rows).execute()
            st.success(f"✅ {lead_count} leads added for member.")
        except Exception as e:
            st.error(f"Error inserting leads: {e}")

    def update_sales(team_id, owner_id, converted_count, sales_value, date):
        try:
            leads_to_update = (
                supabase.table("leads")
                .select("id")
                .eq("team_id", team_id)
                .eq("owner_id", owner_id)
                .eq("converted", False)
                .limit(converted_count)
                .execute()
            )
            if hasattr(leads_to_update, "data") and leads_to_update.data:
                ids = [r["id"] for r in leads_to_update.data]
                for lid in ids:
                    supabase.table("leads").update({
                        "converted": True,
                        "sales_value": float(sales_value) / len(ids),
                        "updated_at": datetime.combine(date, datetime.min.time()).isoformat()
                    }).eq("id", lid).execute()
                st.success(f"✅ Updated {len(ids)} leads as converted.")
            else:
                st.warning("No unconverted leads found to update.")
        except Exception as e:
            st.error(f"Error updating sales: {e}")

    # fetch dropdown data
    teams_df = get_table("teams")
    users_df = get_table("users")

    team_dict = {row["name"]: row["id"] for _, row in teams_df.iterrows()} if not teams_df.empty else {}

    # ---------------------- Form 1: Upload Leads ----------------------
    st.subheader("📋 Add Daily Leads")
    with st.form("daily_leads_form"):
        team_name = st.selectbox("Select Team", list(team_dict.keys()) if team_dict else ["No Teams Found"])
        team_id = team_dict.get(team_name)
        member_df = users_df[users_df["team_id"] == team_id] if not users_df.empty and team_id else pd.DataFrame()
        member_dict = {m["name"]: m["id"] for _, m in member_df.iterrows()} if not member_df.empty else {}
        member_name = st.selectbox("Select Team Member", list(member_dict.keys()) if member_dict else ["No Members"])
        lead_count = st.number_input("Lead Count", min_value=1, value=1)
        date = st.date_input("Select Date", datetime.utcnow().date())
        submitted = st.form_submit_button("Submit Leads")

        if submitted and team_id and member_dict.get(member_name):
            insert_leads(team_id, member_dict.get(member_name), lead_count, date)

    st.markdown("---")

    # ---------------------- Form 2: Update Sales ----------------------
    st.subheader("💰 Update Sales Conversion")
    with st.form("update_sales_form"):
        team_name2 = st.selectbox("Select Team", list(team_dict.keys()) if team_dict else ["No Teams Found"], key="sales_team")
        team_id2 = team_dict.get(team_name2)
        member_df2 = users_df[users_df["team_id"] == team_id2] if not users_df.empty and team_id2 else pd.DataFrame()
        member_dict2 = {m["name"]: m["id"] for _, m in member_df2.iterrows()} if not member_df2.empty else {}
        member_name2 = st.selectbox("Select Team Member", list(member_dict2.keys()) if member_dict2 else ["No Members"], key="sales_member")
        converted = st.number_input("Converted Leads", min_value=0, value=0)
        sales_value = st.number_input("Total Sales Value", min_value=0.0, value=0.0)
        date2 = st.date_input("Conversion Date", datetime.utcnow().date())
        submitted2 = st.form_submit_button("Update Sales")

        if submitted2 and team_id2 and member_dict2.get(member_name2):
            update_sales(team_id2, member_dict2.get(member_name2), converted, sales_value, date2)

# ---------------------- Reporting ----------------------
elif tab == "Reporting":
    st.header("📅 Reporting")

    report_type = st.selectbox("Report Type", ["Weekly", "Monthly"])
    ref_date = st.date_input("Reference Date", value=datetime.utcnow().date())

    def get_leads():
        if not supabase:
            return pd.DataFrame()
        try:
            res = supabase.table("leads").select("*").execute()
            return pd.DataFrame(res.data if hasattr(res, "data") else res)
        except Exception as e:
            st.warning(f"⚠️ Could not fetch leads: {e}")
            return pd.DataFrame()

    df = get_leads()
    if df.empty:
        st.warning("No data available.")
    else:
        if "created_at" in df.columns:
            df["created_at"] = pd.to_datetime(df["created_at"])
        if report_type == "Weekly":
            start = pd.to_datetime(ref_date) - pd.Timedelta(days=7)
        else:
            start = pd.to_datetime(ref_date) - pd.Timedelta(days=30)
        filt = df[(df["created_at"] >= start) & (df["created_at"] <= pd.to_datetime(ref_date))]

        summary = (
            filt.groupby("team_id", dropna=False)
            .agg(
                total_leads=("id", "count"),
                converted=("converted", "sum"),
                total_sales=("sales_value", "sum"),
            )
            .reset_index()
        )
        st.dataframe(summary)
        st.download_button(
            "Download CSV",
            summary.to_csv(index=False),
            file_name=f"report_{report_type.lower()}_{ref_date}.csv",
        )

# ---------------------- Admin ----------------------
elif tab == "Admin":
    # (Same as previous Admin panel with per-team tables)
    st.header("🛠️ Admin Panel — Manage Teams & Members (Form-Based CRUD)")
    # [Your working admin code from before goes here — unchanged]

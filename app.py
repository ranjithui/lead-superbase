"""
Lead Management Streamlit App
---------------------------------
Features:
1. Dashboard — show lead counts (team + individuals)
2. Daily Upload — upload CSV or add single lead
3. Reporting — weekly/monthly summary
4. Admin Panel — create teams, add/update members with targets (form-based CRUD)

Backend: Supabase (Postgres)
Host: Streamlit Cloud
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from dateutil import parser
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
BACKEND = "supabase"

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
        query = supabase.table("leads").select("*")
        if start_date:
            query = query.gte("created_at", start_date.isoformat())
        if end_date:
            query = query.lte("created_at", end_date.isoformat())
        res = query.execute()
        return pd.DataFrame(res.data if hasattr(res, "data") else res)

    leads_df = get_leads_supabase(start_date=start, end_date=end)

    if leads_df.empty:
        st.warning("No leads found for this period.")
    else:
        leads_df["created_at"] = pd.to_datetime(leads_df["created_at"])
        team_counts = leads_df.groupby("team_id").size().reset_index(name="Lead Count")
        owner_counts = leads_df.groupby("owner_id").size().reset_index(name="Lead Count")

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
    st.header("📤 Daily Upload")

    def insert_leads_supabase(df):
        if not supabase or df.empty:
            return None
        records = df.to_dict(orient="records")
        return supabase.table("leads").insert(records).execute()

    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    if uploaded is not None:
        df = pd.read_csv(uploaded)
        st.dataframe(df.head())
        if st.button("Insert Leads"):
            res = insert_leads_supabase(df)
            st.success("Leads inserted successfully!") if res else st.error("Insert failed.")

    st.markdown("---")
    st.subheader("Add Single Lead")
    with st.form("single_lead"):
        owner = st.text_input("Owner ID")
        team = st.text_input("Team ID")
        name = st.text_input("Lead Name")
        contact = st.text_input("Contact")
        src = st.text_input("Source")
        converted = st.checkbox("Converted")
        sales_val = st.number_input("Sales Value", value=0)
        submitted = st.form_submit_button("Add Lead")

        if submitted and supabase:
            row = {
                "owner_id": owner,
                "team_id": team,
                "name": name,
                "contact": contact,
                "source": src,
                "created_at": datetime.utcnow().isoformat(),
                "converted": converted,
                "sales_value": float(sales_val),
            }
            supabase.table("leads").insert(row).execute()
            st.success("Lead added successfully!")

# ---------------------- Reporting ----------------------
elif tab == "Reporting":
    st.header("📅 Reporting")

    report_type = st.selectbox("Report Type", ["Weekly", "Monthly"])
    ref_date = st.date_input("Reference Date", value=datetime.utcnow().date())

    def get_leads():
        if not supabase:
            return pd.DataFrame()
        res = supabase.table("leads").select("*").execute()
        return pd.DataFrame(res.data if hasattr(res, "data") else res)

    df = get_leads()
    if df.empty:
        st.warning("No data available.")
    else:
        df["created_at"] = pd.to_datetime(df["created_at"])
        if report_type == "Weekly":
            start = pd.to_datetime(ref_date) - pd.Timedelta(days=7)
        else:
            start = pd.to_datetime(ref_date) - pd.Timedelta(days=30)
        filt = df[(df["created_at"] >= start) & (df["created_at"] <= pd.to_datetime(ref_date))]

        summary = (
            filt.groupby("team_id")
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
    st.header("🛠️ Admin Panel — Manage Teams & Members (Form-Based CRUD)")
    st.write("Create or update teams and members via forms. View all records below.")

    # ---------- Helper Functions ----------
    def get_teams():
        if not supabase:
            return pd.DataFrame()
        res = supabase.table("teams").select("*").execute()
        return pd.DataFrame(res.data if hasattr(res, "data") else res)

    def get_members():
        if not supabase:
            return pd.DataFrame()
        res = supabase.table("users").select("*").execute()
        df = pd.DataFrame(res.data if hasattr(res, "data") else res)
        teams = get_teams()
        if not teams.empty and not df.empty:
            df = df.merge(
                teams[["id", "name"]],
                left_on="team_id",
                right_on="id",
                how="left",
                suffixes=("", "_team"),
            )
            df.rename(columns={"name_team": "team_name"}, inplace=True)
        tgt_res = supabase.table("targets").select("*").execute()
        targets = pd.DataFrame(tgt_res.data if hasattr(tgt_res, "data") else tgt_res)
        if not targets.empty and not df.empty:
            df = df.merge(targets, left_on="id", right_on="user_id", how="left")
        return df

    def create_team(name, description):
        if not name:
            return None
        tid = str(uuid.uuid4())
        supabase.table("teams").insert({"id": tid, "name": name, "description": description}).execute()
        return tid

    def create_or_update_member(uid, name, team_id, weekly, monthly):
        if not name or not team_id:
            return None
        if not uid:
            uid = str(uuid.uuid4())
            supabase.table("users").insert({"id": uid, "name": name, "team_id": team_id}).execute()
        else:
            res = supabase.table("users").select("id").eq("id", uid).execute()
            if res.data:
                supabase.table("users").update({"name": name, "team_id": team_id}).eq("id", uid).execute()
            else:
                supabase.table("users").insert({"id": uid, "name": name, "team_id": team_id}).execute()
        supabase.table("targets").upsert({"user_id": uid, "weekly": int(weekly), "monthly": int(monthly)}).execute()
        return uid

    # ---------- Create Team Form ----------
    st.subheader("Create Team")
    with st.form("create_team_form", clear_on_submit=True):
        team_name = st.text_input("Team Name")
        team_desc = st.text_area("Description")
        submitted_team = st.form_submit_button("Create Team")
        if submitted_team:
            if team_name:
                create_team(team_name, team_desc)
                st.success(f"Team '{team_name}' created successfully!")
            else:
                st.warning("Team name is required.")

    # ---------- Add / Update Member Form ----------
    st.subheader("Add or Update Member")
    teams = get_teams()
    team_options = {row["name"]: row["id"] for _, row in teams.iterrows()} if not teams.empty else {}

    with st.form("member_form", clear_on_submit=True):
        uid = st.text_input("Member ID (leave blank to create new)")
        name = st.text_input("Member Name")
        team_name_sel = st.selectbox("Select Team", list(team_options.keys()) if team_options else [])
        weekly = st.number_input("Weekly Target", min_value=0, value=0)
        monthly = st.number_input("Monthly Target", min_value=0, value=0)
        submitted_member = st.form_submit_button("Save Member")

        if submitted_member:
            if not team_options:
                st.error("Please create a team first.")
            elif not name:
                st.warning("Member name is required.")
            else:
                tid = team_options.get(team_name_sel)
                mid = create_or_update_member(uid, name, tid, weekly, monthly)
                st.success(f"Member '{name}' saved (ID: {mid})")

    # ---------- Display Tables ----------
    st.markdown("---")
    st.subheader("All Teams")
    teams_df = get_teams()
    if teams_df.empty:
        st.info("No teams found.")
    else:
        st.dataframe(teams_df[["id", "name", "description"]], use_container_width=True)

    st.subheader("All Members")
    members_df = get_members()
    if members_df.empty:
        st.info("No members found.")
    else:
        cols = ["id", "name", "team_name", "weekly", "monthly"]
        for c in cols:
            if c not in members_df.columns:
                members_df[c] = ""
        st.dataframe(members_df[cols], use_container_width=True)

# ---------------------- End of File ----------------------

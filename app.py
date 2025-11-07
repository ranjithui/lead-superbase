"""
Lead Management Streamlit App
---------------------------------
Features:
1. Dashboard — lead counts by team & members
2. Daily Upload — add daily leads and update sales conversion
3. Reporting — weekly and monthly summaries
4. Admin Panel — create teams, manage members, assign targets, and view per-team data

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
# ---------------------- Daily Upload ----------------------
elif tab == "Daily Upload":
    import pandas as pd
    from datetime import datetime
    import streamlit as st

    st.header("📤 Daily Lead Upload & Sales Update")

    # ✅ Safe Supabase fetch helper
    def get_table(name):
        try:
            res = supabase.table(name).select("*").execute()
            df = pd.DataFrame(res.data if hasattr(res, "data") else res)
            if not df.empty:
                if "id" in df.columns:
                    df["id"] = df["id"].astype(str)
                if "team_id" in df.columns:
                    df["team_id"] = df["team_id"].astype(str)
            return df
        except Exception as e:
            st.warning(f"⚠️ Failed to fetch {name}: {e}")
            return pd.DataFrame()

    # ✅ DB operations
    def insert_leads(team_id, owner_id, lead_count, date):
        try:
            rows = [{
                "team_id": team_id,
                "owner_id": owner_id,
                "created_at": datetime.combine(date, datetime.min.time()).isoformat(),
                "converted": False,
                "sales_value": 0,
            } for _ in range(int(lead_count))]
            supabase.table("leads").insert(rows).execute()
            st.success(f"✅ {lead_count} leads added successfully for this member.")
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
                per_lead_value = float(sales_value) / len(ids) if ids else 0
                for lid in ids:
                    supabase.table("leads").update({
                        "converted": True,
                        "sales_value": per_lead_value,
                        "updated_at": datetime.combine(date, datetime.min.time()).isoformat()
                    }).eq("id", lid).execute()
                st.success(f"✅ {len(ids)} leads marked as converted.")
            else:
                st.warning("⚠️ No unconverted leads available for this member.")
        except Exception as e:
            st.error(f"Error updating sales: {e}")

    def get_leads():
        try:
            res = supabase.table("leads").select("*").execute()
            df = pd.DataFrame(res.data if hasattr(res, "data") else res)
            if not df.empty and "created_at" in df.columns:
                df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
            return df
        except Exception:
            return pd.DataFrame()

    # ✅ Load base data
    teams_df = get_table("teams")
    users_df = get_table("users")
    leads_df = get_leads()

    team_dict = {r["name"]: r["id"] for _, r in teams_df.iterrows()} if not teams_df.empty else {}

    # --- Step 1: Select Team ---
    st.subheader("🏢 Select Team")
    selected_team_name = st.selectbox("Team", list(team_dict.keys()) if team_dict else ["No Teams Found"])
    selected_team_id = team_dict.get(selected_team_name)

    # --- Step 2: Filter Members by Team ---
    if not users_df.empty and selected_team_id:
        filtered_members = users_df[users_df["team_id"] == selected_team_id]
    else:
        filtered_members = pd.DataFrame()

    member_dict = {m["name"]: m["id"] for _, m in filtered_members.iterrows()} if not filtered_members.empty else {}

    st.markdown("---")

    # --- Form 1: Add Daily Leads ---
    st.subheader("📋 Add Daily Leads")
    with st.form("daily_leads_form"):
        member_name = st.selectbox("Select Team Member", list(member_dict.keys()) if member_dict else ["No Members"])
        lead_count = st.number_input("Lead Count", min_value=1, value=1)
        date = st.date_input("Select Date", datetime.utcnow().date())
        submitted = st.form_submit_button("Submit Leads")

        if submitted:
            if selected_team_id and member_dict.get(member_name):
                insert_leads(selected_team_id, member_dict.get(member_name), lead_count, date)
            else:
                st.warning("⚠️ Please select a valid team and member.")

    st.markdown("---")

    # --- Form 2: Update Sales Conversion ---
    st.subheader("💰 Update Converted Leads & Sales Value")
    with st.form("update_sales_form"):
        member_name2 = st.selectbox("Select Team Member", list(member_dict.keys()) if member_dict else ["No Members"], key="sales_member")
        converted = st.number_input("Converted Leads", min_value=0, value=0)
        sales_value = st.number_input("Total Sales Value", min_value=0.0, value=0.0)
        date2 = st.date_input("Conversion Date", datetime.utcnow().date())
        submitted2 = st.form_submit_button("Update Sales")

        if submitted2:
            if selected_team_id and member_dict.get(member_name2):
                update_sales(selected_team_id, member_dict.get(member_name2), converted, sales_value, date2)
            else:
                st.warning("⚠️ Please select a valid team and member.")

    st.markdown("---")

    # ✅ Today’s Summary Table
    st.subheader("📊 Today's Summary")

    if leads_df.empty or selected_team_id is None:
        st.info("No leads found.")
    else:
        today = datetime.utcnow().date()
        team_leads = leads_df[
            (leads_df["team_id"] == selected_team_id)
            & (leads_df["created_at"].dt.date == today)
        ].copy()

        if team_leads.empty:
            st.info(f"No leads submitted today for team: {selected_team_name}")
        else:
            # Aggregate summary by member
            summary = (
                team_leads.groupby("owner_id")
                .agg(
                    Total_Leads=("id", "count"),
                    Converted=("converted", "sum"),
                    Total_Sales=("sales_value", "sum")
                )
                .reset_index()
            )

            summary["Conversion_%"] = (summary["Converted"] / summary["Total_Leads"] * 100).round(2)

            # Merge with member names
            summary = summary.merge(
                users_df[["id", "name"]].rename(columns={"id": "owner_id", "name": "Member"}),
                on="owner_id", how="left"
            )[["Member", "Total_Leads", "Converted", "Total_Sales", "Conversion_%"]]

            st.dataframe(summary, use_container_width=True)
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
    st.header("🛠️ Admin Panel — Manage Teams & Members")

    def get_table(name):
        try:
            res = supabase.table(name).select("*").execute()
            return pd.DataFrame(res.data if hasattr(res, "data") else res)
        except Exception:
            return pd.DataFrame()

    def create_team(name, description):
        if not name:
            return
        tid = str(uuid.uuid4())
        supabase.table("teams").insert({"id": tid, "name": name, "description": description}).execute()
        st.success(f"Team '{name}' created!")

    def create_or_update_member(uid, name, team_id, weekly, monthly):
        if not name or not team_id:
            return
        if not uid:
            uid = str(uuid.uuid4())
            supabase.table("users").insert({"id": uid, "name": name, "team_id": team_id}).execute()
        else:
            supabase.table("users").update({"name": name, "team_id": team_id}).eq("id", uid).execute()
        supabase.table("targets").upsert({"user_id": uid, "weekly": int(weekly), "monthly": int(monthly)}).execute()
        st.success(f"Member '{name}' saved!")

    st.subheader("Create Team")
    with st.form("create_team_form", clear_on_submit=True):
        team_name = st.text_input("Team Name")
        team_desc = st.text_area("Description")
        if st.form_submit_button("Create Team") and team_name:
            create_team(team_name, team_desc)

    st.subheader("Add or Update Member")
    teams_df = get_table("teams")
    team_opts = {r["name"]: r["id"] for _, r in teams_df.iterrows()} if not teams_df.empty else {}
    with st.form("member_form", clear_on_submit=True):
        uid = st.text_input("Member ID (blank for new)")
        name = st.text_input("Member Name")
        team_name = st.selectbox("Team", list(team_opts.keys()) if team_opts else [])
        weekly = st.number_input("Weekly Target", 0)
        monthly = st.number_input("Monthly Target", 0)
        if st.form_submit_button("Save Member"):
            if not team_opts:
                st.warning("Create a team first.")
            else:
                create_or_update_member(uid, name, team_opts.get(team_name), weekly, monthly)

    st.markdown("---")
    st.subheader("Team Overview")

    members_df = get_table("users")
    targets_df = get_table("targets")
    leads_df = get_table("leads")

    if teams_df.empty:
        st.info("No teams created yet.")
    else:
        for _, team in teams_df.iterrows():
            team_id = team["id"]
            team_name = team["name"]
            st.markdown(f"### 🧩 Team: {team_name}")

            team_members = members_df[members_df["team_id"] == team_id] if "team_id" in members_df.columns else pd.DataFrame()
            if team_members.empty:
                st.write("No members yet.")
                continue

            team_members = team_members.merge(targets_df, left_on="id", right_on="user_id", how="left")

            team_leads = pd.DataFrame()
            lead_stats = pd.DataFrame(columns=["owner_id", "Lead_Count", "Converted", "Total_Sales"])

            if isinstance(leads_df, pd.DataFrame) and not leads_df.empty and "team_id" in leads_df.columns:
                team_leads = leads_df[leads_df["team_id"] == team_id]
                if not team_leads.empty and all(c in team_leads.columns for c in ["owner_id", "id", "converted", "sales_value"]):
                    lead_stats = (
                        team_leads.groupby("owner_id")
                        .agg(
                            Lead_Count=("id", "count"),
                            Converted=("converted", "sum"),
                            Total_Sales=("sales_value", "sum"),
                        )
                        .reset_index()
                    )

            merged = team_members.merge(lead_stats, left_on="id", right_on="owner_id", how="left")[
                ["name", "weekly", "monthly", "Lead_Count", "Converted", "Total_Sales"]
            ].fillna(0)

            total_row = pd.DataFrame({
                "name": ["TOTAL"],
                "weekly": [merged["weekly"].sum()],
                "monthly": [merged["monthly"].sum()],
                "Lead_Count": [merged["Lead_Count"].sum()],
                "Converted": [merged["Converted"].sum()],
                "Total_Sales": [merged["Total_Sales"].sum()],
            })
            merged = pd.concat([merged, total_row], ignore_index=True)
            st.dataframe(merged, use_container_width=True)
            st.markdown("---")

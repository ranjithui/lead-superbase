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
# ---------------------- Admin Panel ----------------------
elif tab == "Admin":
    import pandas as pd
    import streamlit as st

    st.header("👑 Admin Panel – Manage Teams & Members")

    # ✅ Helper function to fetch tables
    def get_table(name):
        try:
            res = supabase.table(name).select("*").execute()
            df = pd.DataFrame(res.data if hasattr(res, "data") else res)
            if not df.empty and "id" in df.columns:
                df["id"] = df["id"].astype(str)
            if "team_id" in df.columns:
                df["team_id"] = df["team_id"].astype(str)
            return df
        except Exception as e:
            st.warning(f"⚠️ Error loading {name}: {e}")
            return pd.DataFrame()

    # Load all data
    teams_df = get_table("teams")
    users_df = get_table("users")
    targets_df = get_table("targets")

    # ---------------- Create Team ----------------
    st.subheader("➕ Create Team")
    with st.form("create_team_form"):
        team_name = st.text_input("Team Name")
        team_description = st.text_area("Description")
        submitted = st.form_submit_button("Create Team")

        if submitted:
            if team_name:
                try:
                    supabase.table("teams").insert({
                        "name": team_name,
                        "description": team_description
                    }).execute()
                    st.success(f"✅ Team '{team_name}' created.")
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"Error creating team: {e}")
            else:
                st.warning("⚠️ Team name is required.")

    st.markdown("---")

    # ---------------- Display Teams ----------------
    st.subheader("🏢 Teams List")
    if teams_df.empty:
        st.info("No teams found.")
    else:
        for _, team in teams_df.iterrows():
            with st.expander(f"🏷 {team['name']}"):
                st.write(f"**Description:** {team.get('description', '—')}")
                col1, col2 = st.columns(2)

                with col1:
                    if st.button("🗑 Delete Team", key=f"del_team_{team['id']}"):
                        try:
                            supabase.table("teams").delete().eq("id", team["id"]).execute()
                            st.success(f"✅ Deleted team {team['name']}")
                            st.experimental_rerun()
                        except Exception as e:
                            st.error(f"Error deleting team: {e}")

                with col2:
                    st.write(f"Team ID: `{team['id']}`")

    st.markdown("---")

    # ---------------- Add Member ----------------
    st.subheader("👤 Add Member")
    team_options = {row["name"]: row["id"] for _, row in teams_df.iterrows()} if not teams_df.empty else {}

    with st.form("add_member_form"):
        member_name = st.text_input("Member Name")
        team_choice = st.selectbox("Select Team", list(team_options.keys()) if team_options else ["No Teams"])
        target_weekly = st.number_input("Weekly Target", min_value=0, value=0)
        target_monthly = st.number_input("Monthly Target", min_value=0, value=0)
        submitted = st.form_submit_button("Add Member")

        if submitted:
            if member_name and team_options:
                try:
                    team_id = team_options.get(team_choice)
                    user_res = supabase.table("users").insert({
                        "name": member_name,
                        "team_id": team_id
                    }).execute()

                    # Create target record
                    user_id = user_res.data[0]["id"] if user_res.data else None
                    if user_id:
                        supabase.table("targets").insert({
                            "user_id": user_id,
                            "weekly_target": target_weekly,
                            "monthly_target": target_monthly
                        }).execute()

                    st.success(f"✅ Member '{member_name}' added to {team_choice}.")
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"Error adding member: {e}")
            else:
                st.warning("⚠️ Please fill out all fields.")

    st.markdown("---")

    # ---------------- Manage Members (CRUD + Update Targets) ----------------
    st.subheader("👥 Manage Members")

    if users_df.empty:
        st.info("No members found.")
    else:
        # Merge user → team names
        users_df = users_df.merge(
            teams_df[["id", "name"]].rename(columns={"id": "team_id", "name": "team_name"}),
            on="team_id", how="left"
        )

        # Merge user → targets
        if not targets_df.empty:
            users_df = users_df.merge(
                targets_df.rename(columns={
                    "user_id": "id",
                    "weekly_target": "Weekly_Target",
                    "monthly_target": "Monthly_Target"
                }),
                on="id", how="left"
            )

        for _, member in users_df.iterrows():
            with st.expander(f"👤 {member['name']} ({member.get('team_name', 'No Team')})"):
                col1, col2, col3 = st.columns([1, 1, 2])

                # -------- Delete Member --------
                with col1:
                    if st.button("🗑 Delete", key=f"del_member_{member['id']}"):
                        try:
                            supabase.table("users").delete().eq("id", member["id"]).execute()
                            st.success(f"✅ Deleted {member['name']}")
                            st.experimental_rerun()
                        except Exception as e:
                            st.error(f"Error deleting member: {e}")

                # -------- Move Member --------
                with col2:
                    move_team = st.selectbox(
                        "Move to Team",
                        list(team_options.keys()) if team_options else ["No Teams"],
                        index=list(team_options.keys()).index(member["team_name"]) if member["team_name"] in team_options else 0,
                        key=f"move_{member['id']}"
                    )
                    if st.button("🔁 Move", key=f"move_btn_{member['id']}"):
                        try:
                            new_team_id = team_options[move_team]
                            supabase.table("users").update({"team_id": new_team_id}).eq("id", member["id"]).execute()
                            st.success(f"✅ Moved {member['name']} to {move_team}")
                            st.experimental_rerun()
                        except Exception as e:
                            st.error(f"Error moving member: {e}")

                # -------- Info --------
                with col3:
                    st.write(f"**Current Team:** {member.get('team_name', '—')}")
                    st.write(f"**Member ID:** `{member['id']}`")

                st.markdown("---")

                # -------- Update Targets --------
                st.write("🎯 **Update Weekly / Monthly Target**")
                current_weekly = int(member.get("Weekly_Target", 0))
                current_monthly = int(member.get("Monthly_Target", 0))

                with st.form(f"update_target_form_{member['id']}"):
                    new_weekly = st.number_input(
                        "Weekly Target", min_value=0, value=current_weekly, key=f"wk_{member['id']}"
                    )
                    new_monthly = st.number_input(
                        "Monthly Target", min_value=0, value=current_monthly, key=f"mn_{member['id']}"
                    )
                    submit_target = st.form_submit_button("💾 Update Targets")

                    if submit_target:
                        try:
                            # Check if target exists for this user
                            target_row = targets_df[targets_df["user_id"] == member["id"]]
                            if not target_row.empty:
                                supabase.table("targets").update({
                                    "weekly_target": new_weekly,
                                    "monthly_target": new_monthly
                                }).eq("user_id", member["id"]).execute()
                            else:
                                supabase.table("targets").insert({
                                    "user_id": member["id"],
                                    "weekly_target": new_weekly,
                                    "monthly_target": new_monthly
                                }).execute()
                            st.success(f"✅ Updated targets for {member['name']}")
                        except Exception as e:
                            st.error(f"Error updating targets: {e}")

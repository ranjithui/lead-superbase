#Lead Management Streamlit App

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
# ---------------------- DASHBOARD ----------------------
elif tab == "Dashboard":
    st.header("📊 Performance Dashboard")
    st.caption("Track weekly progress, carry forward incomplete targets, and view automatic reminders")

    # ---------- Helper ----------
    def get_table(name):
        try:
            res = supabase.table(name).select("*").execute()
            df = pd.DataFrame(res.data if hasattr(res, "data") else res)
            return df if not df.empty else pd.DataFrame()
        except Exception as e:
            st.warning(f"⚠️ Error loading {name}: {e}")
            return pd.DataFrame()

    # ---------- Load Data ----------
    users_df = get_table("users")
    teams_df = get_table("teams")
    targets_df = get_table("targets")
    progress_df = get_table("progress")  # user_id, week, achieved
    notes_df = get_table("notes")        # user_id, week, note, auto (bool), timestamp

    # ---------- Current User ----------
    user = st.session_state.get("current_user")
    if not user:
        st.warning("Please log in to see your dashboard.")
        st.stop()

    user_id = user.get("id")
    user_name = user.get("name", "Unknown")

    # ---------- Team & Target Info ----------
    user_team = users_df.loc[users_df["id"] == user_id, "team_id"].values[0] if not users_df.empty else None
    team_name = teams_df.loc[teams_df["id"] == user_team, "name"].values[0] if not teams_df.empty and user_team else "Unassigned"

    target_row = targets_df[targets_df["user_id"] == user_id]
    weekly_target = int(target_row["weekly_target"].values[0]) if not target_row.empty else 0
    monthly_target = int(target_row["monthly_target"].values[0]) if not target_row.empty else 0

    # ---------- Date / Week Context ----------
    today = pd.Timestamp.now()
    current_week = today.isocalendar().week
    month_start_week = pd.Timestamp(today.year, today.month, 1).isocalendar().week
    total_weeks_in_month = 4

    # ---------- Progress Summary ----------
    achieved_total = progress_df[progress_df["user_id"] == user_id]["achieved"].sum() if not progress_df.empty else 0
    overall_progress = min(achieved_total / monthly_target, 1.0) if monthly_target else 0

    # ---------- Split Layout ----------
    left, right = st.columns([1, 1])

    with left:
        st.subheader("📈 Overview")
        st.metric("Team", team_name)
        st.metric("Member", user_name)
        st.metric("Monthly Target", monthly_target)
        st.metric("Achieved", achieved_total)
        st.progress(overall_progress)

    with right:
        st.subheader("📅 Weekly Breakdown")

        weeks = [month_start_week + i for i in range(total_weeks_in_month)]
        week_data = []
        carry_forward = 0

        for week in weeks:
            achieved = progress_df[
                (progress_df["user_id"] == user_id) &
                (progress_df["week"] == week)
            ]["achieved"].sum() if not progress_df.empty else 0

            target_with_carry = weekly_target + carry_forward
            shortfall = max(0, target_with_carry - achieved)
            carry_forward = shortfall

            progress = min(achieved / target_with_carry, 1.0) if target_with_carry else 0

            # ---------------- AUTO NOTES LOGIC ----------------
            auto_note = None
            if achieved >= target_with_carry and target_with_carry > 0:
                auto_note = "✅ Great job! You achieved your weekly target!"
            elif shortfall > 0 and achieved > 0:
                auto_note = f"⚠️ You achieved {achieved}/{target_with_carry}. The remaining {shortfall} will carry forward."
            elif achieved == 0:
                auto_note = f"🔴 No progress logged this week. {target_with_carry} will carry forward."
            elif carry_forward > 0:
                auto_note = f"📈 Your target increased this week due to earlier shortfall."

            # Save auto note if not already present
            if auto_note:
                existing_auto = notes_df[
                    (notes_df["user_id"] == user_id) &
                    (notes_df["week"] == week) &
                    (notes_df.get("auto", False) == True)
                ]
                if existing_auto.empty:
                    try:
                        supabase.table("notes").insert({
                            "user_id": user_id,
                            "week": week,
                            "note": auto_note,
                            "auto": True,
                            "timestamp": str(today)
                        }).execute()
                    except Exception as e:
                        st.error(f"Error saving auto note: {e}")

            # Combine notes
            week_notes = notes_df[
                (notes_df["user_id"] == user_id) &
                (notes_df["week"] == week)
            ]
            auto_notes = week_notes[week_notes.get("auto", False) == True]["note"].tolist()

            week_data.append({
                "Week": week,
                "Target": target_with_carry,
                "Achieved": achieved,
                "Shortfall": shortfall,
                "Progress": progress,
                "Auto_Notes": auto_notes,
            })

        # ---------- Render Weekly Cards ----------
        for w in week_data:
            with st.expander(f"📅 Week {w['Week']}"):
                # Color-coded progress bar
                prog_color = "green" if w["Progress"] >= 1 else "orange" if w["Progress"] >= 0.5 else "red"
                st.markdown(
                    f"""
                    <div style="background:#f8f9fa;border:1px solid #ddd;padding:8px 12px;border-radius:8px;">
                        <div style="font-weight:bold;">🎯 Target: {w['Target']} | ✅ Achieved: {w['Achieved']}</div>
                        <div style="height:10px;background:#eee;border-radius:5px;overflow:hidden;margin-top:6px;">
                            <div style="width:{w['Progress']*100}%;background:{prog_color};height:100%;"></div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                if w["Shortfall"] > 0:
                    st.warning(f"Carry Forward: {w['Shortfall']}")

                # --- Auto Notes Display ---
                if w["Auto_Notes"]:
                    for n in w["Auto_Notes"]:
                        st.info(n)

    # ---------- Summary ----------
    st.markdown("---")
    st.subheader("📊 Summary of All Weeks")

    summary_df = pd.DataFrame(week_data)
    summary_df["Progress (%)"] = (summary_df["Progress"] * 100).astype(int)
    st.dataframe(
        summary_df[["Week", "Target", "Achieved", "Shortfall", "Progress (%)"]],
        use_container_width=True,
        hide_index=True
    )

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
# ---------------------- ADMIN PANEL ----------------------
elif tab == "Admin":
    st.header("👑 Admin Panel")
    st.caption("Manage teams, members, and their targets efficiently")

    # ---------- Helper: Load Table ----------
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

    # ---------- Load Data ----------
    teams_df = get_table("teams")
    users_df = get_table("users")
    targets_df = get_table("targets")

    # ---------------- Create Team ----------------
    with st.expander("➕ Create New Team", expanded=False):
        with st.form("create_team_form", clear_on_submit=True):
            team_name = st.text_input("Team Name")
            team_description = st.text_input("Description")
            submitted = st.form_submit_button("Add Team")

            if submitted:
                if team_name:
                    try:
                        supabase.table("teams").insert({
                            "name": team_name,
                            "description": team_description
                        }).execute()
                        st.success(f"✅ Team '{team_name}' created successfully.")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Error creating team: {e}")
                else:
                    st.warning("⚠️ Please enter a team name.")

    # ---------------- Display Teams ----------------
    st.subheader("🏢 Teams List")

    if teams_df.empty:
        st.info("No teams found.")
    else:
        st.dataframe(
            teams_df[["name", "description", "id"]],
            use_container_width=True,
            hide_index=True
        )

        team_to_delete = st.selectbox("🗑 Select Team to Delete", ["Select"] + list(teams_df["name"]))
        if team_to_delete != "Select":
            team_id = teams_df.loc[teams_df["name"] == team_to_delete, "id"].values[0]
            if st.button("Confirm Delete Team"):
                try:
                    supabase.table("teams").delete().eq("id", team_id).execute()
                    st.success(f"✅ Deleted team '{team_to_delete}'.")
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"Error deleting team: {e}")

    st.markdown("---")

    # ---------------- Add Member ----------------
    with st.expander("👤 Add New Member", expanded=False):
        team_options = {row["name"]: row["id"] for _, row in teams_df.iterrows()} if not teams_df.empty else {}

        with st.form("add_member_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            member_name = c1.text_input("Member Name")
            team_choice = c2.selectbox("Team", list(team_options.keys()) if team_options else ["No Teams"])
            target_weekly = c3.number_input("Weekly Target", min_value=0, value=0)

            c4, c5 = st.columns([1, 1])
            target_monthly = c4.number_input("Monthly Target", min_value=0, value=0)
            submitted = c5.form_submit_button("Add Member")

            if submitted:
                if member_name and team_options:
                    try:
                        team_id = team_options.get(team_choice)
                        user_res = supabase.table("users").insert({
                            "name": member_name,
                            "team_id": team_id
                        }).execute()

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
                    st.warning("⚠️ Please fill all fields.")

    st.markdown("---")

    # ---------------- Hierarchical Team & Member Target View ----------------
    st.subheader("📋 Team & Member Targets Overview")

    if teams_df.empty:
        st.info("No teams found.")
    else:
        # Merge users with targets
        users_targets = users_df.merge(
            targets_df.rename(columns={
                "user_id": "id",
                "weekly_target": "Weekly_Target",
                "monthly_target": "Monthly_Target"
            }),
            on="id", how="left"
        ) if not users_df.empty else pd.DataFrame()

        # Loop through each team
        for _, team in teams_df.iterrows():
            team_id = team["id"]
            team_name = team["name"]

            team_members = users_targets[users_targets["team_id"] == team_id]

            # Calculate team total target
            team_weekly_target = team_members["Weekly_Target"].sum() if not team_members.empty else 0
            team_monthly_target = team_members["Monthly_Target"].sum() if not team_members.empty else 0

            with st.expander(f"🏢 {team_name} — {len(team_members)} Members", expanded=False):
                st.markdown(
                    f"""
                    <div style="
                        background:#f8f9fa;
                        border:1px solid #e0e0e0;
                        border-radius:10px;
                        padding:10px 14px;
                        margin-bottom:8px;
                    ">
                        <div style="display:flex; justify-content:space-between;">
                            <div><b>Team Target</b></div>
                            <div>
                                Weekly: <b>{int(team_weekly_target)}</b> |
                                Monthly: <b>{int(team_monthly_target)}</b>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                if team_members.empty:
                    st.info("No members in this team yet.")
                else:
                    for _, member in team_members.iterrows():
                        col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
                        col1.write(f"👤 **{member['name']}**")
                        col2.write(f"Weekly: {int(member.get('Weekly_Target', 0))}")
                        col3.write(f"Monthly: {int(member.get('Monthly_Target', 0))}")

                        # --- Edit Member Button ---
                        if col4.button("✏️ Edit", key=f"edit_{member['id']}"):
                            with st.form(f"edit_member_{member['id']}", clear_on_submit=True):
                                st.write(f"### Edit {member['name']}")
                                new_team = st.selectbox(
                                    "Switch Team",
                                    options=list(teams_df["name"]),
                                    index=list(teams_df["id"]).index(member["team_id"]) if member["team_id"] in list(teams_df["id"]) else 0
                                )
                                new_weekly = st.number_input("Weekly Target", value=int(member.get("Weekly_Target", 0)))
                                new_monthly = st.number_input("Monthly Target", value=int(member.get("Monthly_Target", 0)))
                                save = st.form_submit_button("💾 Save Changes")

                                if save:
                                    try:
                                        new_team_id = teams_df.loc[teams_df["name"] == new_team, "id"].values[0]
                                        # Update team
                                        supabase.table("users").update({"team_id": new_team_id}).eq("id", member["id"]).execute()
                                        # Update targets
                                        supabase.table("targets").update({
                                            "weekly_target": new_weekly,
                                            "monthly_target": new_monthly
                                        }).eq("user_id", member["id"]).execute()
                                        st.success(f"✅ Updated {member['name']}'s details.")
                                        st.experimental_rerun()
                                    except Exception as e:
                                        st.error(f"Error updating member: {e}")

                        # --- Delete Member Button ---
                        if col4.button("🗑 Delete", key=f"delete_{member['id']}"):
                            try:
                                supabase.table("users").delete().eq("id", member["id"]).execute()
                                st.success(f"✅ Deleted {member['name']}.")
                                st.experimental_rerun()
                            except Exception as e:
                                st.error(f"Error deleting member: {e}")

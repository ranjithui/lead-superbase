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
# ---------------------- Dashboard ----------------------
if tab == "Dashboard":
    st.header("📊 Performance Dashboard")
    st.caption("Track weekly progress, carry forward incomplete targets, and view automatic notes")

    # ---------- Helper ----------
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
    leads_df = get_table("leads")
    notes_df = get_table("notes")  # optional table for auto notes

    if teams_df.empty or users_df.empty:
        st.info("Please add teams and members in the Admin panel first.")
        st.stop()

    # ---------- Aggregate Lead & Target Data ----------
    leads_df["converted"] = leads_df.get("converted", False)
    leads_df["sales_value"] = leads_df.get("sales_value", 0)

    lead_summary = leads_df.groupby("owner_id").agg(
        total_leads=("id", "count"),
        converted=("converted", "sum"),
        total_sales=("sales_value", "sum")
    ).reset_index() if not leads_df.empty else pd.DataFrame(columns=["owner_id", "total_leads", "converted", "total_sales"])

    members = (
        users_df
        .merge(teams_df[["id", "name"]].rename(columns={"id": "team_id", "name": "team_name"}), on="team_id", how="left")
        .merge(targets_df.rename(columns={"user_id": "id"}), on="id", how="left")
        .merge(lead_summary.rename(columns={"owner_id": "id"}), on="id", how="left")
        .fillna(0)
    )

    # ---------- Layout Split ----------
    left, right = st.columns([1, 1])

    with left:
        st.subheader("🏢 Overall Summary")
        total_leads = members["total_leads"].sum()
        total_converted = members["converted"].sum()
        total_sales = members["total_sales"].sum()
        overall_progress = (total_converted / total_leads) if total_leads > 0 else 0

        st.metric("Teams", len(teams_df))
        st.metric("Members", len(users_df))
        st.progress(overall_progress)

        st.caption(f"Total Leads: {int(total_leads)} | Converted: {int(total_converted)} | Sales ₹{total_sales:,.0f}")

    with right:
        st.subheader("🗓 Weekly Target Progress")
        today = pd.Timestamp.now()
        current_week = today.isocalendar().week
        total_weeks = 4
        start_week = current_week - total_weeks + 1

        weekly_data = []
        carry_forward = 0

        for week in range(start_week, current_week + 1):
            week_achieved = members["converted"].sum() // total_weeks  # distribute conversion approx evenly
            weekly_target = members["weekly_target"].sum() + carry_forward
            shortfall = max(0, weekly_target - week_achieved)
            carry_forward = shortfall

            progress_ratio = min(week_achieved / weekly_target, 1) if weekly_target > 0 else 0
            weekly_data.append({
                "Week": week,
                "Target": weekly_target,
                "Achieved": week_achieved,
                "Shortfall": shortfall,
                "Progress": progress_ratio
            })

            # --- Auto Notes ---
            note_text = ""
            if week_achieved >= weekly_target and weekly_target > 0:
                note_text = "✅ Great job! Weekly target achieved."
            elif week_achieved > 0 and shortfall > 0:
                note_text = f"⚠️ Partial progress ({week_achieved}/{weekly_target}). Carry forward {shortfall}."
            elif week_achieved == 0:
                note_text = f"🔴 No progress recorded this week. {weekly_target} carried forward."

            # Save auto note if not already in DB
            if note_text and supabase:
                existing = notes_df[
                    (notes_df["week"] == week)
                    & (notes_df.get("auto", False) == True)
                ]
                if existing.empty:
                    try:
                        supabase.table("notes").insert({
                            "week": week,
                            "note": note_text,
                            "auto": True,
                            "timestamp": str(today)
                        }).execute()
                    except Exception:
                        pass

        for w in weekly_data:
            prog_color = "green" if w["Progress"] >= 1 else "orange" if w["Progress"] >= 0.5 else "red"
            st.markdown(
                f"""
                <div style="background:#fff;border:1px solid #ddd;border-radius:8px;padding:8px 12px;margin-bottom:6px;">
                    <b>Week {w['Week']}</b> — Target {int(w['Target'])}, Achieved {int(w['Achieved'])}
                    <div style="background:#eee;border-radius:4px;height:8px;margin-top:4px;">
                        <div style="width:{w['Progress']*100}%;background:{prog_color};height:8px;border-radius:4px;"></div>
                    </div>
                    <div style="font-size:11px;color:gray;">Carry Forward: {int(w['Shortfall'])}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

    # ---------- Auto Notes Section ----------
    st.markdown("---")
    st.subheader("🗒 Automatic Notes")

    if "notes" in locals() and not notes_df.empty:
        auto_notes = notes_df[notes_df.get("auto", False) == True]
        if auto_notes.empty:
            st.info("No automatic notes yet.")
        else:
            for _, note in auto_notes.sort_values("week").iterrows():
                st.info(f"**Week {note['week']}** — {note['note']}")
    else:
        st.info("No automatic notes found.")

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

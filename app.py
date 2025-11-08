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
    st.header("📊 Team & Member Performance Dashboard")
    st.caption("Weekly performance overview with auto carry-forward and system notes.")

    # --- Helper to fetch Supabase tables ---
    def get_table(name):
        try:
            res = supabase.table(name).select("*").execute()
            df = pd.DataFrame(res.data if hasattr(res, "data") else res)
            if not df.empty:
                for col in ["id", "team_id", "user_id"]:
                    if col in df.columns:
                        df[col] = df[col].astype(str)
            return df
        except Exception as e:
            st.warning(f"⚠️ Failed to load {name}: {e}")
            return pd.DataFrame()

    # --- Load all tables ---
    teams_df = get_table("teams")
    users_df = get_table("users")
    targets_df = get_table("targets")
    leads_df = get_table("leads")
    notes_df = get_table("notes")

    # --- Prepare Notes week column ---
    if not notes_df.empty:
        notes_df["created_at"] = pd.to_datetime(notes_df["created_at"], errors="coerce")
        notes_df["week"] = notes_df["created_at"].dt.isocalendar().week
    else:
        notes_df = pd.DataFrame(columns=["id", "user_id", "team_id", "note", "note_type", "created_at", "week"])

    # --- Get current week ---
    current_week = datetime.utcnow().isocalendar().week

    # --- Lead Summary ---
    if not leads_df.empty:
        leads_df["converted"] = leads_df["converted"].astype(bool)
        leads_df["sales_value"] = leads_df["sales_value"].fillna(0)
        leads_df["created_at"] = pd.to_datetime(leads_df["created_at"], errors="coerce")
        leads_df["week"] = leads_df["created_at"].dt.isocalendar().week

        lead_summary = leads_df.groupby(["owner_id", "week"]).agg(
            total_leads=("id", "count"),
            converted=("converted", "sum"),
            total_sales=("sales_value", "sum")
        ).reset_index()
    else:
        lead_summary = pd.DataFrame(columns=["owner_id", "week", "total_leads", "converted", "total_sales"])

    # --- Merge users, teams, and targets ---
    members = users_df.merge(
        teams_df[["id", "name"]].rename(columns={"id": "team_id", "name": "team_name"}),
        on="team_id", how="left"
    )
    if not targets_df.empty:
        members = members.merge(
            targets_df.rename(columns={"user_id": "id"}), on="id", how="left"
        )
    members["weekly_target"] = members.get("weekly_target", 0).fillna(0)

    # --- Summary Header ---
    col1, col2, col3 = st.columns(3)
    col1.metric("🏢 Total Teams", len(teams_df))
    col2.metric("👥 Members", len(users_df))
    col3.metric("📆 Current Week", current_week)

    st.markdown("---")

    # --- Loop over Teams ---
    for _, team in teams_df.iterrows():
        team_id = team["id"]
        team_name = team["name"]
        team_members = members[members["team_id"] == team_id]

        if team_members.empty:
            continue

        st.subheader(f"🏢 {team_name}")

        # --- Team-level weekly totals ---
        team_leads = lead_summary[
            (lead_summary["owner_id"].isin(team_members["id"])) &
            (lead_summary["week"] == current_week)
        ]

        # --- Safe calculations ---
        total_converted = float(team_leads["converted"].sum() if "converted" in team_leads else 0)
        total_sales = float(team_leads["total_sales"].sum() if "total_sales" in team_leads else 0)
        total_target = float(team_members["weekly_target"].sum() if "weekly_target" in team_members else 0)

        progress = (total_converted / total_target * 100) if total_target > 0 else 0

        st.progress(min(progress / 100, 1.0))
        st.caption(f"🎯 Progress: {progress:.1f}% — Converted {int(total_converted)}/{int(total_target)} leads — ₹{total_sales:,.0f}")

        # --- Carry Forward Logic (safe) ---
        if total_target > 0 and progress < 100:
            incomplete = max(total_target - total_converted, 0)
            note_exists = not notes_df[
                (notes_df["team_id"] == team_id) & (notes_df["week"] == current_week)
            ].empty

            if not note_exists and incomplete > 0:
                try:
                    note_text = f"Carried forward {int(incomplete)} incomplete leads to next week."
                    supabase.table("notes").insert({
                        "team_id": team_id,
                        "note": note_text,
                        "note_type": "auto"
                    }).execute()
                except Exception as e:
                    st.warning(f"⚠️ Failed to save auto note: {e}")

        # --- Display Recent Notes ---
        recent_notes = notes_df[notes_df["team_id"] == team_id].sort_values("created_at", ascending=False).head(3)
        if not recent_notes.empty:
            st.markdown("**📝 Recent Notes:**")
            for _, n in recent_notes.iterrows():
                st.markdown(
                    f"- *Week {int(n['week'])}*: {n['note']} ({n['created_at'].strftime('%Y-%m-%d')})"
                )
        else:
            st.caption("No notes yet for this team.")

        # --- Member Breakdown ---
        st.markdown("### 👥 Team Members")
        for _, member in team_members.iterrows():
            m_id = member["id"]
            m_target = float(member.get("weekly_target", 0))
            m_leads = lead_summary[
                (lead_summary["owner_id"] == m_id) &
                (lead_summary["week"] == current_week)
            ]
            converted = int(m_leads["converted"].sum()) if not m_leads.empty else 0
            sales = float(m_leads["total_sales"].sum()) if not m_leads.empty else 0
            progress_m = (converted / m_target * 100) if m_target > 0 else 0

            st.markdown(
                f"""
                <div style="
                    background:#f9f9f9;
                    border:1px solid #e0e0e0;
                    border-radius:8px;
                    padding:6px 10px;
                    margin-bottom:4px;
                ">
                    <div style="display:flex; justify-content:space-between;">
                        <div>👤 <b>{member['name']}</b></div>
                        <div>{converted}/{int(m_target)} leads | ₹{sales:,.0f}</div>
                    </div>
                    <div style="background:#e9ecef; border-radius:4px; height:5px; margin-top:3px;">
                        <div style="background:#28a745; width:{min(progress_m,100)}%; height:5px; border-radius:4px;"></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

        st.markdown("---")

    # --- Overall Summary ---
    total_leads = lead_summary[lead_summary["week"] == current_week]["total_leads"].sum()
    total_converted = lead_summary[lead_summary["week"] == current_week]["converted"].sum()
    total_sales = lead_summary[lead_summary["week"] == current_week]["total_sales"].sum()
    overall_progress = (total_converted / total_leads * 100) if total_leads > 0 else 0

    st.subheader("📈 Overall Company Summary")
    st.progress(min(overall_progress / 100, 1.0))
    st.caption(f"Total Leads: {int(total_leads)} | Converted: {int(total_converted)} | Sales: ₹{total_sales:,.0f} | Conversion Rate: {overall_progress:.1f}%")


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
# ---------------------- Reporting ----------------------
elif tab == "Reporting":
    st.header("📅 Lead & Sales Reporting")
    st.caption("Generate weekly, monthly, or custom range reports.")

    import io
    from datetime import timedelta

    # --- Fetch Helper ---
    def get_table(name):
        try:
            res = supabase.table(name).select("*").execute()
            df = pd.DataFrame(res.data if hasattr(res, "data") else res)
            if not df.empty:
                for c in ["id", "team_id", "owner_id"]:
                    if c in df.columns:
                        df[c] = df[c].astype(str)
            return df
        except Exception as e:
            st.warning(f"⚠️ Could not load {name}: {e}")
            return pd.DataFrame()

    # --- Load data ---
    leads_df = get_table("leads")
    teams_df = get_table("teams")
    users_df = get_table("users")

    if leads_df.empty:
        st.info("No leads data found yet.")
        st.stop()

    # --- Preprocess ---
    leads_df["created_at"] = pd.to_datetime(leads_df.get("created_at"), errors="coerce")
    leads_df["sales_value"] = leads_df.get("sales_value", 0).fillna(0)
    leads_df["converted"] = leads_df.get("converted", False).astype(bool)

    # --- Filter controls ---
    st.subheader("🔍 Filters")
    report_type = st.selectbox("Select Report Type", ["Weekly", "Monthly", "Custom Range"])
    today = datetime.utcnow().date()

    if report_type == "Weekly":
        start_date = st.date_input("Start Date", today - timedelta(days=7))
    elif report_type == "Monthly":
        start_date = st.date_input("Start Date", today - timedelta(days=30))
    else:
        start_date = st.date_input("Start Date", today - timedelta(days=15))
    end_date = st.date_input("End Date", today)

    leads_df = leads_df[
        (leads_df["created_at"].dt.date >= start_date) &
        (leads_df["created_at"].dt.date <= end_date)
    ]

    if leads_df.empty:
        st.warning("No data found for this period.")
        st.stop()

    # --- Merge user & team info ---
    leads_df = leads_df.merge(
        users_df[["id", "name", "team_id"]].rename(columns={"id": "owner_id", "name": "Member"}),
        on="owner_id", how="left"
    ).merge(
        teams_df[["id", "name"]].rename(columns={"id": "team_id", "name": "Team"}),
        on="team_id", how="left"
    )

    # --- KPI cards ---
    total_leads = len(leads_df)
    total_converted = leads_df["converted"].sum()
    total_sales = leads_df["sales_value"].sum()
    conversion_rate = (total_converted / total_leads * 100) if total_leads else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📋 Total Leads", total_leads)
    c2.metric("✅ Converted", int(total_converted))
    c3.metric("💰 Sales", f"₹{total_sales:,.0f}")
    c4.metric("📈 Conversion Rate", f"{conversion_rate:.1f}%")

    st.markdown("---")

    # --- Team Summary ---
    st.subheader("🏢 Team Summary")
    team_summary = (
        leads_df.groupby("Team", dropna=False)
        .agg(
            Total_Leads=("id", "count"),
            Converted=("converted", "sum"),
            Total_Sales=("sales_value", "sum")
        )
        .reset_index()
    )
    team_summary["Conversion_%"] = (team_summary["Converted"] / team_summary["Total_Leads"] * 100).round(2)
    st.dataframe(team_summary, use_container_width=True)

    # --- Member Summary ---
    st.subheader("👥 Member Summary")
    member_summary = (
        leads_df.groupby(["Member", "Team"], dropna=False)
        .agg(
            Total_Leads=("id", "count"),
            Converted=("converted", "sum"),
            Total_Sales=("sales_value", "sum")
        )
        .reset_index()
    )
    member_summary["Conversion_%"] = (member_summary["Converted"] / member_summary["Total_Leads"] * 100).round(2)
    st.dataframe(member_summary.sort_values("Converted", ascending=False), use_container_width=True)

    st.markdown("---")

    # --- Top Performers ---
    st.subheader("🏆 Top Performers")
    if not member_summary.empty:
        top_member = member_summary.iloc[member_summary["Converted"].idxmax()]
        st.success(f"👤 **{top_member['Member']} ({top_member['Team']})** — {int(top_member['Converted'])} conversions.")
    if not team_summary.empty:
        top_team = team_summary.iloc[team_summary["Converted"].idxmax()]
        st.info(f"🏢 **{top_team['Team']}** — {int(top_team['Converted'])} conversions.")

    st.markdown("---")

    # --- Export Excel ---
    st.subheader("📦 Export Data")
    excel_buffer = io.BytesIO()
    try:
        with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
            team_summary.to_excel(writer, index=False, sheet_name="Team Summary")
            member_summary.to_excel(writer, index=False, sheet_name="Member Summary")
        st.download_button(
            label="📘 Download Excel Report",
            data=excel_buffer.getvalue(),
            file_name=f"lead_report_{start_date}_{end_date}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        st.warning(f"⚠️ Could not create Excel file: {e}")

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

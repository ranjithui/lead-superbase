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
if tab == "Dashboard":

    st.header("📊 Dashboard Overview")

    # ---------- Helper: Load Table ----------
    def get_table(name):
        try:
            res = supabase.table(name).select("*").execute()
            data = res.data if hasattr(res, "data") and res.data else []
            df = pd.DataFrame(data)
            # Ensure 'id' and 'team_id' columns exist even if table is empty
            if "id" not in df.columns:
                df["id"] = []
            if "team_id" in df.columns:
                df["team_id"] = df["team_id"].astype(str)
            return df
        except Exception as e:
            st.warning(f"⚠️ Error loading {name}: {e}")
            return pd.DataFrame(columns=["id"])

    # ---------- Load Data ----------
    users_df = get_table("users")
    teams_df = get_table("teams")
    leads_df = get_table("leads")
    targets_df = get_table("targets")

    # ---------- Safe Merge for Members ----------
    if not users_df.empty and "team_id" in users_df.columns and not teams_df.empty:
        members = users_df.merge(
            teams_df[["id", "name"]].rename(columns={"id": "team_id", "name": "team_name"}),
            on="team_id", how="left"
        )
    else:
        members = pd.DataFrame()

    # ---------- Summary Stats ----------
    total_teams = len(teams_df)
    total_members = len(users_df)
    total_leads = len(leads_df)

    st.markdown(
        f"""
        <div style='display:flex; justify-content:space-around; background:#f8f9fa;
        border-radius:10px; padding:10px; margin-bottom:15px;'>
            <div><b>🏢 Teams:</b> {total_teams}</div>
            <div><b>👥 Members:</b> {total_members}</div>
            <div><b>📋 Leads:</b> {total_leads}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ---------- Leads Overview ----------
    st.subheader("📈 Leads Overview")
    if leads_df.empty:
        st.info("No leads data available yet.")
    else:
        lead_counts = leads_df.groupby("status").size().reset_index(name="count")
        st.dataframe(lead_counts, use_container_width=True)

    # ---------- Members and Targets ----------
    st.subheader("🎯 Members & Targets")
    if members.empty:
        st.info("No team or member data yet.")
    else:
        # Merge members with targets
        if not targets_df.empty and "user_id" in targets_df.columns:
            merged = members.merge(
                targets_df.rename(columns={
                    "user_id": "id",
                    "weekly_target": "Weekly_Target",
                    "monthly_target": "Monthly_Target"
                }),
                on="id", how="left"
            )
        else:
            merged = members.copy()
            merged["Weekly_Target"] = 0
            merged["Monthly_Target"] = 0

        # Display
        st.dataframe(
            merged[["name", "team_name", "Weekly_Target", "Monthly_Target"]],
            use_container_width=True,
            hide_index=True
        )

        # ---------- Summary by Team ----------
        st.subheader("🏆 Team Target Summary")
        team_summary = (
            merged.groupby("team_name")[["Weekly_Target", "Monthly_Target"]]
            .sum()
            .reset_index()
        )
        st.dataframe(team_summary, use_container_width=True)

        # ---------- Charts ----------
        import matplotlib.pyplot as plt

        if not team_summary.empty:
            fig, ax = plt.subplots()
            ax.bar(team_summary["team_name"], team_summary["Monthly_Target"])
            ax.set_title("Monthly Targets by Team")
            ax.set_xlabel("Team")
            ax.set_ylabel("Monthly Target")
            st.pyplot(fig)

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
    st.header("📊 Reporting & Insights")
    st.caption("View weekly or monthly summaries of team and member performance")

    # --- Load Data Helper ---
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
            st.warning(f"⚠️ Could not load {name}: {e}")
            return pd.DataFrame()

    # --- Fetch Data ---
    teams_df = get_table("teams")
    users_df = get_table("users")
    leads_df = get_table("leads")

    if leads_df.empty:
        st.info("No lead data available yet.")
        st.stop()

    # --- Clean up date fields ---
    leads_df["created_at"] = pd.to_datetime(leads_df["created_at"], errors="coerce")
    leads_df["week"] = leads_df["created_at"].dt.isocalendar().week
    leads_df["month"] = leads_df["created_at"].dt.month
    leads_df["year"] = leads_df["created_at"].dt.year

    # --- Filters ---
    st.sidebar.header("📅 Filters")
    report_type = st.sidebar.selectbox("Report Type", ["Weekly", "Monthly"])
    selected_team = st.sidebar.selectbox("Team", ["All"] + list(teams_df["name"]))
    selected_year = st.sidebar.number_input("Year", min_value=2020, max_value=datetime.now().year, value=datetime.now().year)

    # --- Apply Filters ---
    df_filtered = leads_df[leads_df["year"] == selected_year]
    if selected_team != "All":
        team_id = teams_df.loc[teams_df["name"] == selected_team, "id"].values[0]
        df_filtered = df_filtered[df_filtered["team_id"] == team_id]

    # --- Summary Metrics ---
    total_leads = len(df_filtered)
    converted = df_filtered["converted"].sum()
    total_sales = df_filtered["sales_value"].sum()
    conversion_rate = (converted / total_leads * 100) if total_leads > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📥 Total Leads", total_leads)
    col2.metric("✅ Converted", int(converted))
    col3.metric("📊 Conversion Rate", f"{conversion_rate:.1f}%")
    col4.metric("💰 Total Sales", f"₹{total_sales:,.0f}")

    st.markdown("---")

    # --- Team Performance Summary ---
    st.subheader("🏢 Team Performance Summary")
    team_summary = (
        df_filtered.groupby("team_id")
        .agg(
            Total_Leads=("id", "count"),
            Converted=("converted", "sum"),
            Total_Sales=("sales_value", "sum"),
        )
        .reset_index()
    )

    team_summary = team_summary.merge(
        teams_df[["id", "name"]], left_on="team_id", right_on="id", how="left"
    ).rename(columns={"name": "Team"})[["Team", "Total_Leads", "Converted", "Total_Sales"]]

    team_summary["Conversion_%"] = (team_summary["Converted"] / team_summary["Total_Leads"] * 100).round(2)

    st.dataframe(team_summary, use_container_width=True)

    # --- Member Leaderboard ---
    st.subheader("🏆 Member Leaderboard")
    member_summary = (
        df_filtered.groupby("owner_id")
        .agg(
            Total_Leads=("id", "count"),
            Converted=("converted", "sum"),
            Total_Sales=("sales_value", "sum"),
        )
        .reset_index()
    )

    member_summary = (
        member_summary.merge(users_df[["id", "name", "team_id"]], left_on="owner_id", right_on="id", how="left")
        .merge(teams_df[["id", "name"]].rename(columns={"id": "team_id", "name": "Team"}), on="team_id", how="left")
        .rename(columns={"name": "Member"})
    )[["Member", "Team", "Total_Leads", "Converted", "Total_Sales"]]

    member_summary["Conversion_%"] = (member_summary["Converted"] / member_summary["Total_Leads"] * 100).round(2)
    member_summary = member_summary.sort_values("Total_Sales", ascending=False)

    st.dataframe(member_summary, use_container_width=True)

    # --- Export Reports ---
    st.markdown("### 📁 Export Reports")
    csv_data = member_summary.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="📥 Download Member Report (CSV)",
        data=csv_data,
        file_name=f"member_report_{report_type.lower()}_{selected_year}.csv",
        mime="text/csv",
    )

    # Excel export
    import io
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
        team_summary.to_excel(writer, sheet_name="Team Summary", index=False)
        member_summary.to_excel(writer, sheet_name="Member Leaderboard", index=False)
    st.download_button(
        label="📘 Download Full Report (Excel)",
        data=excel_buffer.getvalue(),
        file_name=f"lead_report_{report_type.lower()}_{selected_year}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # --- Summary Insights ---
    st.markdown("---")
    st.subheader("🧠 Insights Summary")

    if not team_summary.empty:
        best_team = team_summary.loc[team_summary["Total_Sales"].idxmax(), "Team"]
        top_member = member_summary.loc[member_summary["Total_Sales"].idxmax(), "Member"]
        st.success(
            f"🏅 **Top Team:** {best_team}\n\n"
            f"💼 **Top Performer:** {top_member}\n\n"
            f"📈 Overall conversion rate: {conversion_rate:.1f}%"
        )
    else:
        st.info("Not enough data to generate insights.")


# ---------------------- Admin ----------------------
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
            if "user_id" in df.columns:
                df["user_id"] = df["user_id"].astype(str)
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
        # ---- Merge users and targets safely ----
        if not users_df.empty and not targets_df.empty:
            if "user_id" in targets_df.columns:
                safe_targets = targets_df.rename(columns={
                    "user_id": "id",
                    "weekly_target": "Weekly_Target",
                    "monthly_target": "Monthly_Target"
                })
            else:
                safe_targets = targets_df.copy()
            if "id" in users_df.columns and "id" in safe_targets.columns:
                users_targets = users_df.merge(safe_targets, on="id", how="left")
            else:
                users_targets = users_df.copy()
        else:
            users_targets = users_df.copy()

        # ---- Loop through each team ----
        for _, team in teams_df.iterrows():
            team_id = team.get("id", None)
            team_name = team.get("name", "Unnamed Team")

            if "team_id" in users_targets.columns:
                team_members = users_targets[users_targets["team_id"] == team_id]
            else:
                team_members = pd.DataFrame()

            team_weekly_target = team_members["Weekly_Target"].sum() if "Weekly_Target" in team_members else 0
            team_monthly_target = team_members["Monthly_Target"].sum() if "Monthly_Target" in team_members else 0

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
                        col1.write(f"👤 **{member.get('name', 'Unknown')}**")
                        col2.write(f"Weekly: {int(member.get('Weekly_Target', 0))}")
                        col3.write(f"Monthly: {int(member.get('Monthly_Target', 0))}")

                        # --- Edit Member Button ---
                        if col4.button("✏️ Edit", key=f"edit_{member.get('id', '')}"):
                            with st.form(f"edit_member_{member.get('id', '')}", clear_on_submit=True):
                                st.write(f"### Edit {member.get('name', 'Unknown')}")
                                new_team = st.selectbox(
                                    "Switch Team",
                                    options=list(teams_df["name"]),
                                    index=list(teams_df["id"]).index(member.get("team_id")) if member.get("team_id") in list(teams_df["id"]) else 0
                                )
                                new_weekly = st.number_input("Weekly Target", value=int(member.get("Weekly_Target", 0)))
                                new_monthly = st.number_input("Monthly Target", value=int(member.get("Monthly_Target", 0)))
                                save = st.form_submit_button("💾 Save Changes")

                                if save:
                                    try:
                                        new_team_id = teams_df.loc[teams_df["name"] == new_team, "id"].values[0]
                                        supabase.table("users").update({"team_id": new_team_id}).eq("id", member.get("id")).execute()
                                        supabase.table("targets").update({
                                            "weekly_target": new_weekly,
                                            "monthly_target": new_monthly
                                        }).eq("user_id", member.get("id")).execute()
                                        st.success(f"✅ Updated {member.get('name')}'s details.")
                                        st.experimental_rerun()
                                    except Exception as e:
                                        st.error(f"Error updating member: {e}")

                        # --- Delete Member Button ---
                        if col4.button("🗑 Delete", key=f"delete_{member.get('id', '')}"):
                            try:
                                supabase.table("users").delete().eq("id", member.get("id")).execute()
                                st.success(f"✅ Deleted {member.get('name')}.")
                                st.experimental_rerun()
                            except Exception as e:
                                st.error(f"Error deleting member: {e}")

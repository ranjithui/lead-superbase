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
# ----------------------------- ADMIN BLOCK -----------------------------
elif tab == "Admin":
    st.title("👑 Admin Panel")
    st.write("Manage users, teams, and targets here.")

    # --- Load data safely ---
    try:
        users_df = pd.DataFrame(supabase.table("users").select("*").execute().data)
        teams_df = pd.DataFrame(supabase.table("teams").select("*").execute().data)
        targets_df = pd.DataFrame(supabase.table("targets").select("*").execute().data)
    except Exception as e:
        st.error(f"Error loading data: {e}")
        st.stop()

    # --- Handle empty tables gracefully ---
    if users_df.empty:
        st.warning("No users found.")
        st.stop()
    if teams_df.empty:
        st.warning("No teams found.")
        st.stop()
    if targets_df.empty:
        targets_df = pd.DataFrame(columns=["user_id", "weekly_target", "monthly_target"])

    # --- Merge users with teams ---
    if "team_id" in users_df.columns and "id" in teams_df.columns:
        members = users_df.merge(
            teams_df[["id", "name"]].rename(columns={"id": "team_id", "name": "team_name"}),
            on="team_id", how="left"
        )
    else:
        st.error("Missing columns in users or teams table.")
        st.stop()

    # --- Merge users with targets ---
    merged_targets = targets_df.rename(columns={
        "weekly_target": "Weekly_Target",
        "monthly_target": "Monthly_Target",
        "user_id": "id"
    })
    users_targets = users_df.merge(merged_targets, on="id", how="left")

    # --- Display user management table ---
    st.subheader("👥 Manage Team Members")
    for _, member in members.iterrows():
        col1, col2, col3, col4 = st.columns([3, 3, 2, 2])
        col1.write(f"**{member['name']}**")
        col2.write(f"Team: {member.get('team_name', 'N/A')}")
        col3.write(f"Weekly: {member.get('Weekly_Target', 0)} | Monthly: {member.get('Monthly_Target', 0)}")

        if col4.button("✏️ Edit", key=f"edit_{member['id']}"):
            with st.form(f"edit_member_{member['id']}", clear_on_submit=True):
                st.write(f"### Edit {member['name']}")

                # --- Fix: Safe index lookup for team selection ---
                existing_team_ids = list(teams_df["id"])
                default_index = (
                    existing_team_ids.index(member["team_id"])
                    if member.get("team_id") in existing_team_ids
                    else 0
                )

                new_team = st.selectbox(
                    "Switch Team",
                    options=list(teams_df["name"]),
                    index=default_index
                )

                new_weekly = st.number_input(
                    "Weekly Target",
                    value=int(member.get("Weekly_Target", 0))
                )
                new_monthly = st.number_input(
                    "Monthly Target",
                    value=int(member.get("Monthly_Target", 0))
                )

                save = st.form_submit_button("💾 Save Changes")

                if save:
                    try:
                        new_team_id = teams_df.loc[
                            teams_df["name"] == new_team, "id"
                        ].values[0]

                        # Update team
                        supabase.table("users").update(
                            {"team_id": new_team_id}
                        ).eq("id", member["id"]).execute()

                        # Update targets
                        supabase.table("targets").update({
                            "weekly_target": new_weekly,
                            "monthly_target": new_monthly
                        }).eq("user_id", member["id"]).execute()

                        st.success(f"✅ Updated {member['name']}'s details.")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Error updating member: {e}")

    st.markdown("---")

    # --- Add New Member Section ---
    st.subheader("➕ Add New Member")
    with st.form("add_member_form"):
        new_name = st.text_input("Full Name")
        new_team = st.selectbox("Assign to Team", options=list(teams_df["name"]))
        new_weekly = st.number_input("Weekly Target", min_value=0)
        new_monthly = st.number_input("Monthly Target", min_value=0)

        submitted = st.form_submit_button("Add Member")

        if submitted:
            try:
                new_team_id = teams_df.loc[teams_df["name"] == new_team, "id"].values[0]

                # Manually assign a unique user ID (important!)
                import uuid
                new_user_id = str(uuid.uuid4())

                # Insert into users table
                supabase.table("users").insert({
                    "id": new_user_id,
                    "name": new_name,
                    "team_id": new_team_id
                }).execute()

                # Insert targets
                supabase.table("targets").insert({
                    "user_id": new_user_id,
                    "weekly_target": new_weekly,
                    "monthly_target": new_monthly
                }).execute()

                st.success(f"✅ Added {new_name} successfully!")
                st.experimental_rerun()

            except Exception as e:
                st.error(f"Error adding member: {e}")

    st.markdown("---")

    # --- Manage Teams ---
    st.subheader("🏢 Manage Teams")
    with st.form("add_team_form"):
        new_team_name = st.text_input("New Team Name")
        add_team = st.form_submit_button("Add Team")

        if add_team:
            try:
                import uuid
                new_team_id = str(uuid.uuid4())
                supabase.table("teams").insert({
                    "id": new_team_id,
                    "name": new_team_name
                }).execute()
                st.success(f"✅ Added new team: {new_team_name}")
                st.experimental_rerun()
            except Exception as e:
                st.error(f"Error adding team: {e}")

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
# ---------------------- Dashboard ----------------------
elif tab == "Dashboard":
    import pandas as pd
    import streamlit as st
    from datetime import datetime

    st.header("📊 Team Performance Dashboard")
    st.caption("Track weekly and monthly progress by team and member.")

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
    leads_df = get_table("leads")

    if teams_df.empty:
        st.info("No teams available yet. Please create some in the Admin panel.")
        st.stop()

    # ---------- Prepare Lead Stats ----------
    if not leads_df.empty:
        leads_df["converted"] = leads_df["converted"].astype(bool)
        lead_summary = leads_df.groupby("owner_id").agg(
            total_leads=("id", "count"),
            converted=("converted", "sum"),
            total_sales=("sales_value", "sum")
        ).reset_index()
    else:
        lead_summary = pd.DataFrame(columns=["owner_id", "total_leads", "converted", "total_sales"])

    # ---------- Combine all Data ----------
    members = users_df.merge(
        teams_df[["id", "name"]].rename(columns={"id": "team_id", "name": "team_name"}),
        on="team_id", how="left"
    )
    members = members.merge(
        targets_df.rename(columns={"user_id": "id"}), on="id", how="left"
    )
    members = members.merge(
        lead_summary.rename(columns={"owner_id": "id"}), on="id", how="left"
    ).fillna(0)

    # ---------- Display Teams as Cards ----------
    st.markdown("---")
    st.subheader("🏆 Team Overview")

    for _, team in teams_df.iterrows():
        team_name = team["name"]
        team_id = team["id"]

        team_members = members[members["team_id"] == team_id]
        if team_members.empty:
            continue

        # Team totals
        total_weekly = team_members["weekly_target"].sum()
        total_monthly = team_members["monthly_target"].sum()
        total_completed = team_members["converted"].sum()

        # Calculate progress safely
        weekly_progress = (
            total_completed / total_weekly * 100 if total_weekly > 0 else 0
        )
        monthly_progress = (
            total_completed / total_monthly * 100 if total_monthly > 0 else 0
        )

        # Team Card Layout
        st.markdown(
            f"""
            <div style="
                background: linear-gradient(135deg, #007BFF, #004D99);
                padding: 20px 25px; 
                border-radius: 16px; 
                margin-bottom: 30px; 
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                color: white;">
                <h3 style="margin-bottom: 8px;">🏢 {team_name}</h3>
                <p style="font-size: 13px; opacity: 0.8;">Team ID: {team_id}</p>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <p style="font-size: 14px;">Weekly Target: <b>{int(total_weekly)}</b></p>
                        <p style="font-size: 14px;">Monthly Target: <b>{int(total_monthly)}</b></p>
                    </div>
                    <div style="text-align: right;">
                        <p style="font-size: 14px;">Completed: <b>{int(total_completed)}</b></p>
                        <p style="font-size: 14px;">Sales Value: ₹{team_members['total_sales'].sum():,.2f}</p>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Progress Bars
        st.markdown("**🎯 Weekly Target Completion**")
        st.progress(min(weekly_progress / 100, 1.0))

        st.markdown("**📅 Monthly Target Completion**")
        st.progress(min(monthly_progress / 100, 1.0))

        # Member Details
        with st.expander(f"👥 View {team_name} Members"):
            display_df = team_members[[
                "name", "weekly_target", "monthly_target", "total_leads", "converted", "total_sales"
            ]].rename(columns={
                "name": "Member",
                "weekly_target": "Weekly Target",
                "monthly_target": "Monthly Target",
                "total_leads": "Leads",
                "converted": "Converted",
                "total_sales": "Sales Value"
            })
            st.dataframe(display_df, use_container_width=True, hide_index=True)

        st.markdown("---")


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

    st.header("👑 Admin Panel – Team & Member Management")
    st.caption("Manage teams, members, and their targets in a compact list view.")

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
                        st.success(f"✅ Team '{team_name}' created.")
                        st.experimental_rerun()
                    except Exception as e:
                        st.error(f"Error creating team: {e}")
                else:
                    st.warning("⚠️ Team name is required.")

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
            if st.button("Confirm Delete Team", key="delete_team_button"):
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

    # ---------------- Manage Members ----------------
    st.subheader("🧑‍💼 Manage Members")

    if users_df.empty:
        st.info("No members found.")
    else:
        # Merge related data
        users_df = users_df.merge(
            teams_df[["id", "name"]].rename(columns={"id": "team_id", "name": "team_name"}),
            on="team_id", how="left"
        )

        if not targets_df.empty:
            users_df = users_df.merge(
                targets_df.rename(columns={
                    "user_id": "id",
                    "weekly_target": "Weekly_Target",
                    "monthly_target": "Monthly_Target"
                }),
                on="id", how="left"
            )

        # Show in table-style view
        st.write("### 📋 Member List")
        compact_df = users_df[[
            "name", "team_name", "Weekly_Target", "Monthly_Target", "id"
        ]].rename(columns={
            "name": "Member",
            "team_name": "Team",
            "Weekly_Target": "Weekly Target",
            "Monthly_Target": "Monthly Target",
            "id": "Member ID"
        })

        st.dataframe(compact_df, use_container_width=True, hide_index=True)

        st.markdown("### ✏️ Update or Delete Member")

        member_to_edit = st.selectbox(
            "Select Member", ["Select"] + list(users_df["name"])
        )

        if member_to_edit != "Select":
            member = users_df[users_df["name"] == member_to_edit].iloc[0]

            st.write(f"**Current Team:** {member.get('team_name', '—')}")
            st.write(f"**Member ID:** `{member['id']}`")

            col1, col2, col3, col4 = st.columns(4)

            new_team = col1.selectbox(
                "Move to Team",
                list(teams_df["name"]) if not teams_df.empty else [],
                index=list(teams_df["name"]).index(member["team_name"]) if member["team_name"] in list(teams_df["name"]) else 0
            )

            new_weekly = col2.number_input("Weekly Target", min_value=0, value=int(member.get("Weekly_Target", 0)))
            new_monthly = col3.number_input("Monthly Target", min_value=0, value=int(member.get("Monthly_Target", 0)))

            update_btn = col4.button("💾 Update", use_container_width=True)
            delete_btn = st.button("🗑 Delete Member", type="secondary")

            if update_btn:
                try:
                    new_team_id = teams_df.loc[teams_df["name"] == new_team, "id"].values[0]
                    supabase.table("users").update({"team_id": new_team_id}).eq("id", member["id"]).execute()

                    # Update or insert targets
                    target_exists = not targets_df[targets_df["user_id"] == member["id"]].empty
                    if target_exists:
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
                    st.success(f"✅ Updated {member_to_edit}'s details.")
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"Error updating member: {e}")

            if delete_btn:
                try:
                    supabase.table("users").delete().eq("id", member["id"]).execute()
                    st.success(f"✅ Deleted member {member_to_edit}.")
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"Error deleting member: {e}")

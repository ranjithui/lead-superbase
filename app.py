import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime

# ----------------- SUPABASE SETUP -----------------
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="Lead Management System", layout="wide")

# Sidebar navigation
tab = st.sidebar.radio("📂 Navigate", ["Admin Panel", "Daily Update", "Dashboard"])

# ----------------- HELPER FUNCTION -----------------
def get_table(name):
    try:
        res = supabase.table(name).select("*").execute()
        df = pd.DataFrame(res.data if hasattr(res, "data") else res)
        if not df.empty and "id" in df.columns:
            df["id"] = df["id"].astype(str)
        return df
    except Exception as e:
        st.warning(f"⚠️ Error loading {name}: {e}")
        return pd.DataFrame()

# =====================================================
#                     ADMIN PANEL
# =====================================================
if tab == "Admin Panel":
    st.title("👑 Admin Panel")
    st.caption("Manage teams, members, and targets easily.")

    # ---- TEAM CRUD ----
    st.subheader("🏢 Team Management")
    teams_df = get_table("teams")

    with st.form("create_team"):
        team_name = st.text_input("Team Name")
        team_submit = st.form_submit_button("➕ Create Team")

        if team_submit and team_name:
            supabase.table("teams").insert({"name": team_name}).execute()
            st.success(f"✅ Team '{team_name}' created successfully!")

    if not teams_df.empty:
        st.markdown("### Existing Teams")
        st.dataframe(teams_df[["id", "name"]], use_container_width=True)

        delete_team = st.selectbox("Select Team to Delete", teams_df["name"], key="delete_team")
        if st.button("🗑️ Delete Selected Team"):
            team_id = teams_df.loc[teams_df["name"] == delete_team, "id"].values[0]
            supabase.table("teams").delete().eq("id", team_id).execute()
            st.success(f"Deleted team: {delete_team}")

    st.divider()

    # ---- TEAM MEMBERS CRUD ----
    st.subheader("👥 Team Member Management")
    users_df = get_table("users")
    teams_df = get_table("teams")

    with st.form("add_member"):
        member_name = st.text_input("Member Name")
        team_name_select = st.selectbox("Assign to Team", teams_df["name"] if not teams_df.empty else [])
        weekly_target = st.number_input("Weekly Target", min_value=0)
        monthly_target = st.number_input("Monthly Target", min_value=0)
        submit_member = st.form_submit_button("➕ Add Member")

        if submit_member and member_name and team_name_select:
            team_id = teams_df.loc[teams_df["name"] == team_name_select, "id"].values[0]
            member_insert = supabase.table("users").insert({
                "name": member_name,
                "team_id": team_id
            }).execute()

            user_id = member_insert.data[0]["id"]
            supabase.table("targets").insert({
                "user_id": user_id,
                "weekly_target": weekly_target,
                "monthly_target": monthly_target
            }).execute()
            st.success(f"✅ Member '{member_name}' added to {team_name_select}")

    if not users_df.empty:
        st.markdown("### Current Members")
        members_view = users_df.merge(
            teams_df, left_on="team_id", right_on="id", suffixes=("_user", "_team")
        )[["name_user", "name_team", "team_id"]].rename(columns={
            "name_user": "Member", "name_team": "Team"
        })
        st.dataframe(members_view, use_container_width=True)

        # Change Team
        st.markdown("#### 🔄 Move Member to Another Team")
        member_to_move = st.selectbox("Select Member", users_df["name"])
        new_team = st.selectbox("Select New Team", teams_df["name"], key="move_team")
        if st.button("🔁 Update Team Assignment"):
            member_id = users_df.loc[users_df["name"] == member_to_move, "id"].values[0]
            new_team_id = teams_df.loc[teams_df["name"] == new_team, "id"].values[0]
            supabase.table("users").update({"team_id": new_team_id}).eq("id", member_id).execute()
            st.success(f"✅ {member_to_move} moved to {new_team}")

        # Delete Member
        st.markdown("#### 🗑️ Delete Member")
        member_to_delete = st.selectbox("Select Member to Delete", users_df["name"], key="delete_member")
        if st.button("🧹 Delete Selected Member"):
            member_id = users_df.loc[users_df["name"] == member_to_delete, "id"].values[0]
            supabase.table("users").delete().eq("id", member_id).execute()
            st.success(f"Deleted member: {member_to_delete}")

    st.divider()

    # ---- TARGET UPDATE ----
    st.subheader("🎯 Update Targets")
    targets_df = get_table("targets")

    if not users_df.empty:
        selected_member = st.selectbox("Select Member", users_df["name"], key="target_member")
        user_id = users_df.loc[users_df["name"] == selected_member, "id"].values[0]
        new_weekly = st.number_input("Weekly Target", min_value=0, key="update_weekly")
        new_monthly = st.number_input("Monthly Target", min_value=0, key="update_monthly")

        if st.button("💾 Update Targets"):
            supabase.table("targets").update({
                "weekly_target": new_weekly,
                "monthly_target": new_monthly
            }).eq("user_id", user_id).execute()
            st.success(f"🎯 Targets updated for {selected_member}!")

# =====================================================
#                     DAILY UPDATE
# =====================================================
elif tab == "Daily Update":
    st.title("📅 Daily Upload & Sales Update")

    teams_df = get_table("teams")
    users_df = get_table("users")

    # --- Upload Leads ---
    st.subheader("📥 Upload Leads")
    with st.form("lead_upload"):
        team_name = st.selectbox("Select Team", teams_df["name"] if not teams_df.empty else [])
        if team_name:
            team_id = teams_df.loc[teams_df["name"] == team_name, "id"].values[0]
            team_members = users_df[users_df["team_id"] == team_id]
            member_name = st.selectbox("Select Member", team_members["name"])
        else:
            member_name = None

        lead_count = st.number_input("Leads Uploaded", min_value=1)
        date = st.date_input("Select Date", datetime.now().date())
        submit_leads = st.form_submit_button("📤 Submit Leads")

        if submit_leads and team_name and member_name:
            member_id = team_members.loc[team_members["name"] == member_name, "id"].values[0]
            for _ in range(lead_count):
                supabase.table("leads").insert({
                    "owner_id": member_id,
                    "team_id": team_id,
                    "date": date.isoformat(),
                    "converted": False
                }).execute()
            st.success(f"✅ {lead_count} leads uploaded for {member_name} in {team_name}")

    st.divider()

    # --- Update Sales ---
    st.subheader("💰 Update Sales Conversion")
    leads_df = get_table("leads")
    if leads_df.empty:
        st.info("No leads uploaded yet.")
    else:
        with st.form("sales_update"):
            unconverted = leads_df[leads_df["converted"] == False]
            lead_ids = unconverted["id"].tolist()
            member_ids = unconverted["owner_id"].tolist()

            if len(lead_ids) == 0:
                st.info("✅ All leads already converted.")
            else:
                selected_member = st.selectbox("Select Member to Update Sales", users_df["name"])
                converted_leads = st.number_input("Number of Leads Converted", min_value=1)
                per_lead_value = st.number_input("Sales Value per Lead", min_value=0.0)
                date = st.date_input("Conversion Date", datetime.now().date())
                submit_sales = st.form_submit_button("💾 Update Sales")

                if submit_sales:
                    member_id = users_df.loc[users_df["name"] == selected_member, "id"].values[0]
                    member_leads = unconverted[unconverted["owner_id"] == member_id].head(converted_leads)
                    for lid in member_leads["id"].tolist():
                        supabase.table("leads").update({
                            "converted": True,
                            "sales_value": per_lead_value
                        }).eq("id", lid).execute()
                    st.success(f"✅ Updated {converted_leads} leads as converted for {selected_member}")

# =====================================================
#                     DASHBOARD
# =====================================================
elif tab == "Dashboard":
    st.title("📊 Team Performance Dashboard")

    teams_df = get_table("teams")
    users_df = get_table("users")
    targets_df = get_table("targets")
    leads_df = get_table("leads")

    if teams_df.empty:
        st.info("No teams found.")
        st.stop()

    # Lead summary
    if not leads_df.empty:
        leads_df["converted"] = leads_df["converted"].astype(bool)
        lead_summary = leads_df.groupby("owner_id").agg(
            total_leads=("id", "count"),
            converted=("converted", "sum"),
            total_sales=("sales_value", "sum")
        ).reset_index()
    else:
        lead_summary = pd.DataFrame(columns=["owner_id", "total_leads", "converted", "total_sales"])

    # Combine
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

    st.markdown("---")
    st.subheader("🏆 Team Overview")

    for _, team in teams_df.iterrows():
        team_name = team["name"]
        team_id = team["id"]

        team_members = members[members["team_id"] == team_id]
        if team_members.empty:
            continue

        total_weekly = team_members["weekly_target"].sum()
        total_monthly = team_members["monthly_target"].sum()
        total_completed = team_members["converted"].sum()

        weekly_progress = (total_completed / total_weekly * 100) if total_weekly > 0 else 0
        monthly_progress = (total_completed / total_monthly * 100) if total_monthly > 0 else 0

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
                <div style="display: flex; justify-content: space-between;">
                    <div>
                        <p>Weekly Target: <b>{int(total_weekly)}</b></p>
                        <p>Monthly Target: <b>{int(total_monthly)}</b></p>
                    </div>
                    <div style="text-align: right;">
                        <p>Completed: <b>{int(total_completed)}</b></p>
                        <p>Sales Value: ₹{team_members['total_sales'].sum():,.2f}</p>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True
        )

        st.markdown("**🎯 Weekly Target Completion**")
        st.progress(min(weekly_progress / 100, 1.0))
        st.markdown("**📅 Monthly Target Completion**")
        st.progress(min(monthly_progress / 100, 1.0))

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

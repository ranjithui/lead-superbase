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
    st.header("📊 Team & Member Performance Overview")
    st.caption("Compact view of each team and their members’ performance.")

    # --- Load Data ---
    def get_table(name):
        try:
            res = supabase.table(name).select("*").execute()
            df = pd.DataFrame(res.data if hasattr(res, "data") else res)
            if not df.empty and "id" in df.columns:
                df["id"] = df["id"].astype(str)
            if "team_id" in df.columns:
                df["team_id"] = df["team_id"].astype(str)
            return df
        except Exception:
            return pd.DataFrame()

    teams_df = get_table("teams")
    users_df = get_table("users")
    targets_df = get_table("targets")
    leads_df = get_table("leads")

    if teams_df.empty:
        st.info("No teams found. Please add some teams in the Admin panel.")
        st.stop()

    # --- Prepare Lead Summary ---
    if not leads_df.empty:
        leads_df["converted"] = leads_df["converted"].astype(bool)
        leads_df["sales_value"] = leads_df["sales_value"].fillna(0)
        lead_summary = leads_df.groupby("owner_id").agg(
            total_leads=("id", "count"),
            converted=("converted", "sum"),
            total_sales=("sales_value", "sum")
        ).reset_index()
    else:
        lead_summary = pd.DataFrame(columns=["owner_id", "total_leads", "converted", "total_sales"])

    # --- Merge Data ---
    members = users_df.merge(
        teams_df[["id", "name"]].rename(columns={"id": "team_id", "name": "team_name"}),
        on="team_id", how="left"
    ).merge(
        targets_df.rename(columns={"user_id": "id"}), on="id", how="left"
    ).merge(
        lead_summary.rename(columns={"owner_id": "id"}), on="id", how="left"
    ).fillna(0)

    # --- Small Top Summary ---
    col1, col2, col3 = st.columns(3)
    col1.metric("🏢 Teams", len(teams_df))
    col2.metric("👥 Members", len(users_df))
    col3.metric("🎯 Total Conversions", int(members["converted"].sum()))

    st.markdown("---")

    # --- Modern Compact Team Cards ---
    for _, team in teams_df.iterrows():
        team_id = team["id"]
        team_name = team["name"]
        team_members = members[members["team_id"] == team_id]

        if team_members.empty:
            continue

        total_weekly_target = team_members["weekly_target"].sum()
        total_converted = team_members["converted"].sum()
        total_sales = team_members["total_sales"].sum()

        team_progress = (total_converted / total_weekly_target * 100) if total_weekly_target > 0 else 0

        # --- Compact Team Card ---
        st.markdown(
            f"""
            <div style="
                background: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 10px;
                padding: 10px 14px;
                margin-bottom: 10px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.05);
            ">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <strong style="font-size:16px;">🏢 {team_name}</strong><br>
                        <span style="font-size:12px; color:gray;">{len(team_members)} Members</span>
                    </div>
                    <div style="text-align:right;">
                        <strong>{int(total_converted)}</strong> / {int(total_weekly_target)}  
                        <div style="font-size:12px; color:gray;">Leads Converted</div>
                    </div>
                </div>
                <div style="margin-top:4px;">
                    <div style="background:#eee; border-radius:4px; height:6px;">
                        <div style="background:#007bff; width:{min(team_progress,100)}%; height:6px; border-radius:4px;"></div>
                    </div>
                    <div style="font-size:11px; color:gray; margin-top:2px;">Progress: {team_progress:.1f}% | ₹{total_sales:,.0f} Sales</div>
                </div>
            </div>
            """, unsafe_allow_html=True
        )

        # --- Inline Member Performance (Compact View) ---
        for _, m in team_members.iterrows():
            member_progress = (m["converted"] / m["weekly_target"] * 100) if m["weekly_target"] > 0 else 0
            st.markdown(
                f"""
                <div style="
                    background:#f9f9f9;
                    border:1px solid #eee;
                    border-radius:8px;
                    padding:6px 10px;
                    margin:4px 0 4px 20px;
                ">
                    <div style="display:flex; justify-content:space-between;">
                        <div>
                            <span style="font-weight:500;">👤 {m['name']}</span>
                            <span style="font-size:11px; color:gray;"> — {int(m['converted'])}/{int(m['weekly_target'])} leads</span>
                        </div>
                        <div style="font-size:11px; color:gray;">₹{m['total_sales']:,.0f}</div>
                    </div>
                    <div style="background:#e9ecef; border-radius:4px; height:5px; margin-top:3px;">
                        <div style="background:#28a745; width:{min(member_progress,100)}%; height:5px; border-radius:4px;"></div>
                    </div>
                </div>
                """, unsafe_allow_html=True
            )

        st.markdown("")

    # --- Overall Summary ---
    total_leads = members["total_leads"].sum()
    total_converted = members["converted"].sum()
    total_sales = members["total_sales"].sum()
    overall_progress = (total_converted / total_leads * 100) if total_leads > 0 else 0

    st.markdown("---")
    st.markdown(
        f"""
        <div style="
            background:#f8f9fa;
            padding:12px;
            border-radius:10px;
            border:1px solid #e0e0e0;
            box-shadow:0 1px 4px rgba(0,0,0,0.05);
        ">
            <strong>📈 Overall Performance</strong><br>
            Leads: <b>{int(total_leads)}</b> | Converted: <b>{int(total_converted)}</b> | Sales: ₹{total_sales:,.0f}
            <div style="background:#ddd; border-radius:4px; height:6px; margin-top:4px;">
                <div style="background:#17a2b8; width:{min(overall_progress,100)}%; height:6px; border-radius:4px;"></div>
            </div>
            <div style="font-size:11px; color:gray; margin-top:3px;">Total Conversion Rate: {overall_progress:.1f}%</div>
        </div>
        """,
        unsafe_allow_html=True
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

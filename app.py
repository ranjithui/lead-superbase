# Lead Management Streamlit App (Full, robust version)
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import io

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
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        st.warning(f"⚠️ Supabase client init failed: {e}")
        supabase = None

st.set_page_config(page_title="Lead Management App", layout="wide")
st.title("📊 Lead Management System")

tab = st.sidebar.radio("Go to", ["Dashboard", "Daily Upload", "Reporting", "Admin"])

# ----------------------
# Helper: safe table fetch
# ----------------------
def get_table(name):
    """Fetch a full table from Supabase safely and normalize id-like cols to str."""
    try:
        if not supabase:
            return pd.DataFrame()
        res = supabase.table(name).select("*").execute()
        data = res.data if hasattr(res, "data") else res
        df = pd.DataFrame(data)
        if not df.empty:
            # Convert common id columns to strings for safe merging/comparisons
            for col in df.columns:
                if col.lower() in {"id", "team_id", "user_id", "owner_id"}:
                    df[col] = df[col].astype(str)
        return df
    except Exception as e:
        st.warning(f"⚠️ Failed to load `{name}`: {e}")
        return pd.DataFrame()

# ---------------------- Dashboard ----------------------
if tab == "Dashboard":
    st.header("📊 Team & Member Performance Dashboard")
    st.caption("Weekly performance overview with auto carry-forward and system notes.")

    # Load tables
    teams_df = get_table("teams")
    users_df = get_table("users")
    targets_df = get_table("targets")
    leads_df = get_table("leads")
    notes_df = get_table("notes")

    # Normalize notes
    if not notes_df.empty and "created_at" in notes_df.columns:
        notes_df["created_at"] = pd.to_datetime(notes_df["created_at"], errors="coerce")
        notes_df["week"] = notes_df["created_at"].dt.isocalendar().week
    else:
        notes_df = pd.DataFrame(columns=["id", "user_id", "team_id", "note", "note_type", "created_at", "week"])

    # Current week
    current_week = datetime.utcnow().isocalendar().week

    # Prepare leads summary by owner and week
    if not leads_df.empty:
        if "created_at" in leads_df.columns:
            leads_df["created_at"] = pd.to_datetime(leads_df["created_at"], errors="coerce")
            leads_df["week"] = leads_df["created_at"].dt.isocalendar().week
        else:
            leads_df["week"] = None

        leads_df["converted"] = leads_df.get("converted", False).astype(bool)
        leads_df["sales_value"] = leads_df.get("sales_value", 0).fillna(0)

        lead_summary = (
            leads_df.groupby(["owner_id", "week"], dropna=False)
            .agg(total_leads=("id", "count"), converted=("converted", "sum"), total_sales=("sales_value", "sum"))
            .reset_index()
        )
    else:
        lead_summary = pd.DataFrame(columns=["owner_id", "week", "total_leads", "converted", "total_sales"])

    # Merge users with teams safely
    if not users_df.empty and not teams_df.empty and "team_id" in users_df.columns and "id" in teams_df.columns:
        members = users_df.merge(
            teams_df[["id", "name"]].rename(columns={"id": "team_id", "name": "team_name"}),
            on="team_id", how="left"
        )
    else:
        members = users_df.copy() if not users_df.empty else pd.DataFrame()

    # Merge targets if available: targets may use user_id
    if not targets_df.empty and "user_id" in targets_df.columns and "id" in members.columns:
        targets_renamed = targets_df.rename(columns={"user_id": "id"})
        members = members.merge(targets_renamed, on="id", how="left")
    else:
        # ensure target columns exist
        members["weekly_target"] = members.get("weekly_target", 0)
        members["monthly_target"] = members.get("monthly_target", 0)

    # Fill NaNs and ensure numeric types for targets
    if "weekly_target" in members.columns:
        members["weekly_target"] = pd.to_numeric(members["weekly_target"].fillna(0), errors="coerce").fillna(0)
    else:
        members["weekly_target"] = 0

    # Header KPIs
    col1, col2, col3 = st.columns(3)
    col1.metric("🏢 Total Teams", len(teams_df))
    col2.metric("👥 Members", len(users_df))
    col3.metric("📆 Current Week", current_week)

    st.markdown("---")

    # Loop teams
    if teams_df.empty:
        st.info("No teams found. Add teams in Admin.")
    else:
        for _, team in teams_df.iterrows():
            team_id = str(team.get("id", ""))
            team_name = team.get("name", "Unnamed Team")
            team_members = members[members.get("team_id", "") == team_id] if not members.empty else pd.DataFrame()

            if team_members.empty:
                continue

            st.subheader(f"🏢 {team_name}")

            # Team-level weekly totals
            team_leads = lead_summary[
                (lead_summary["owner_id"].isin(team_members["id"])) & (lead_summary["week"] == current_week)
            ] if not lead_summary.empty else pd.DataFrame()

            total_converted = float(team_leads["converted"].sum()) if not team_leads.empty else 0.0
            total_sales = float(team_leads["total_sales"].sum()) if not team_leads.empty else 0.0
            total_target = float(team_members["weekly_target"].sum()) if "weekly_target" in team_members.columns else 0.0

            progress = (total_converted / total_target * 100) if total_target > 0 else 0.0

            st.progress(min(progress / 100, 1.0))
            st.caption(f"🎯 Progress: {progress:.1f}% — Converted {int(total_converted)}/{int(total_target)} leads — ₹{total_sales:,.0f}")

            # Carry forward note creation (auto note) — safe: check existing
            if total_target > 0 and progress < 100:
                incomplete = max(total_target - total_converted, 0)
                # check existing note for this week & team
                note_exists = False
                if not notes_df.empty and "team_id" in notes_df.columns and "week" in notes_df.columns:
                    note_exists = not notes_df[(notes_df["team_id"] == team_id) & (notes_df["week"] == current_week)].empty

                if not note_exists and incomplete > 0 and supabase:
                    try:
                        note_text = f"Carried forward {int(incomplete)} incomplete leads to next week."
                        supabase.table("notes").insert({
                            "team_id": team_id,
                            "note": note_text,
                            "note_type": "auto",
                            "created_at": datetime.utcnow().isoformat()
                        }).execute()
                    except Exception as e:
                        st.warning(f"⚠️ Failed to save auto note: {e}")

            # Recent notes
            recent_notes = pd.DataFrame()
            if not notes_df.empty and "team_id" in notes_df.columns:
                recent_notes = notes_df[notes_df["team_id"] == team_id].sort_values("created_at", ascending=False).head(3)

            if not recent_notes.empty:
                st.markdown("**📝 Recent Notes:**")
                for _, n in recent_notes.iterrows():
                    week_val = int(n.get("week", current_week)) if pd.notna(n.get("week", None)) else current_week
                    created = n.get("created_at")
                    created_str = pd.to_datetime(created).strftime("%Y-%m-%d") if pd.notna(created) else "-"
                    st.markdown(f"- *Week {week_val}*: {n.get('note','')} ({created_str})")
            else:
                st.caption("No notes yet for this team.")

            # Member breakdown
            st.markdown("### 👥 Team Members")
            for _, member in team_members.iterrows():
                m_id = str(member.get("id", ""))
                m_target = float(member.get("weekly_target", 0))
                m_leads = lead_summary[
                    (lead_summary["owner_id"] == m_id) & (lead_summary["week"] == current_week)
                ] if not lead_summary.empty else pd.DataFrame()
                converted = int(m_leads["converted"].sum()) if not m_leads.empty else 0
                sales = float(m_leads["total_sales"].sum()) if not m_leads.empty else 0.0
                progress_m = (converted / m_target * 100) if m_target > 0 else 0.0

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
                            <div>👤 <b>{member.get('name','—')}</b></div>
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

    # Overall company summary
    overall_week = lead_summary[lead_summary["week"] == current_week] if not lead_summary.empty else pd.DataFrame()
    total_leads = int(overall_week["total_leads"].sum()) if not overall_week.empty else 0
    total_converted = int(overall_week["converted"].sum()) if not overall_week.empty else 0
    total_sales = float(overall_week["total_sales"].sum()) if not overall_week.empty else 0.0
    overall_progress = (total_converted / total_leads * 100) if total_leads > 0 else 0.0

    st.subheader("📈 Overall Company Summary")
    st.progress(min(overall_progress / 100, 1.0))
    st.caption(f"Total Leads: {total_leads} | Converted: {total_converted} | Sales: ₹{total_sales:,.0f} | Conversion Rate: {overall_progress:.1f}%")

# ---------------------- Daily Upload ----------------------
elif tab == "Daily Upload":
    st.header("📤 Daily Lead Upload & Sales Update")

    # Safe helpers (redefine locally for clarity)
    def insert_leads(team_id, owner_id, lead_count, date):
        try:
            rows = [{
                "team_id": str(team_id),
                "owner_id": str(owner_id),
                "created_at": datetime.combine(date, datetime.min.time()).isoformat(),
                "converted": False,
                "sales_value": 0
            } for _ in range(int(lead_count))]
            if supabase:
                supabase.table("leads").insert(rows).execute()
                st.success(f"✅ {lead_count} leads added successfully for this member.")
            else:
                st.warning("⚠️ Supabase not configured — cannot insert.")
        except Exception as e:
            st.error(f"Error inserting leads: {e}")

    def update_sales(team_id, owner_id, converted_count, sales_value, date):
        try:
            if not supabase:
                st.warning("⚠️ Supabase not configured — cannot update.")
                return
            leads_to_update = (
                supabase.table("leads")
                .select("id")
                .eq("team_id", team_id)
                .eq("owner_id", owner_id)
                .eq("converted", False)
                .limit(converted_count)
                .execute()
            )
            ids = [r["id"] for r in leads_to_update.data] if hasattr(leads_to_update, "data") and leads_to_update.data else []
            if ids:
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

    # Load base data
    teams_df = get_table("teams")
    users_df = get_table("users")
    leads_df = get_table("leads")

    team_dict = {r["name"]: r["id"] for _, r in teams_df.iterrows()} if not teams_df.empty else {}

    st.subheader("🏢 Select Team")
    selected_team_name = st.selectbox("Team", list(team_dict.keys()) if team_dict else ["No Teams Found"])
    selected_team_id = team_dict.get(selected_team_name)

    # Filter members
    if not users_df.empty and selected_team_id:
        filtered_members = users_df[users_df.get("team_id", "") == selected_team_id]
    else:
        filtered_members = pd.DataFrame()

    member_dict = {m["name"]: m["id"] for _, m in filtered_members.iterrows()} if not filtered_members.empty else {}

    st.markdown("---")

    # Add daily leads
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

    # Update sales conversion
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

    # Today's summary
    st.subheader("📊 Today's Summary")
    if leads_df.empty or selected_team_id is None:
        st.info("No leads found.")
    else:
        today = datetime.utcnow().date()
        if "created_at" in leads_df.columns:
            team_leads = leads_df[
                (leads_df.get("team_id", "") == selected_team_id) &
                (leads_df["created_at"].dt.date == today)
            ].copy()
        else:
            team_leads = pd.DataFrame()

        if team_leads.empty:
            st.info(f"No leads submitted today for team: {selected_team_name}")
        else:
            summary = (
                team_leads.groupby("owner_id")
                .agg(Total_Leads=("id", "count"), Converted=("converted", "sum"), Total_Sales=("sales_value", "sum"))
                .reset_index()
            )
            summary["Conversion_%"] = (summary["Converted"] / summary["Total_Leads"] * 100).round(2)
            # merge with member names safely
            if not users_df.empty and "id" in users_df.columns:
                summary = summary.merge(users_df[["id", "name"]].rename(columns={"id": "owner_id", "name": "Member"}),
                                        on="owner_id", how="left")[
                                          ["Member", "Total_Leads", "Converted", "Total_Sales", "Conversion_%"]]
            st.dataframe(summary, use_container_width=True)

# ---------------------- Reporting ----------------------
elif tab == "Reporting":
    st.header("📅 Lead & Sales Reporting")
    st.caption("Generate weekly, monthly, or custom range reports.")

    # load data
    leads_df = get_table("leads")
    teams_df = get_table("teams")
    users_df = get_table("users")

    if leads_df.empty:
        st.info("No leads data found yet.")
        st.stop()

    # preprocess leads
    leads_df["created_at"] = pd.to_datetime(leads_df.get("created_at"), errors="coerce")
    leads_df["sales_value"] = leads_df.get("sales_value", 0).fillna(0)
    leads_df["converted"] = leads_df.get("converted", False).astype(bool)

    # filters
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

    # apply filter safely
    try:
        leads_df = leads_df[
            (leads_df["created_at"].dt.date >= start_date) &
            (leads_df["created_at"].dt.date <= end_date)
        ]
    except Exception as e:
        st.error(f"Date filtering failed: {e}")
        st.stop()

    if leads_df.empty:
        st.warning("No data found for this period.")
        st.stop()

    # safe merges
    if not users_df.empty and "id" in users_df.columns:
        users_ren = users_df[["id", "name", "team_id"]].rename(columns={"id": "owner_id", "name": "Member"})
        leads_df = leads_df.merge(users_ren, on="owner_id", how="left")
    else:
        leads_df["Member"] = leads_df.get("owner_id", "")

    if not teams_df.empty and "id" in teams_df.columns:
        teams_ren = teams_df[["id", "name"]].rename(columns={"id": "team_id", "name": "Team"})
        leads_df = leads_df.merge(teams_ren, on="team_id", how="left")
    else:
        leads_df["Team"] = "Unassigned"

    # KPIs
    total_leads = len(leads_df)
    total_converted = int(leads_df["converted"].sum())
    total_sales = float(leads_df["sales_value"].sum())
    conversion_rate = (total_converted / total_leads * 100) if total_leads else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📋 Total Leads", total_leads)
    c2.metric("✅ Converted", total_converted)
    c3.metric("💰 Sales", f"₹{total_sales:,.0f}")
    c4.metric("📈 Conversion Rate", f"{conversion_rate:.1f}%")

    st.markdown("---")

    # Team summary
    st.subheader("🏢 Team Summary")
    team_summary = (
        leads_df.groupby("Team", dropna=False)
        .agg(Total_Leads=("id", "count"), Converted=("converted", "sum"), Total_Sales=("sales_value", "sum"))
        .reset_index()
    )
    team_summary["Conversion_%"] = (team_summary["Converted"] / team_summary["Total_Leads"] * 100).round(2)
    st.dataframe(team_summary, use_container_width=True)

    st.markdown("---")

    # Member summary
    st.subheader("👥 Member Summary")
    member_summary = (
        leads_df.groupby(["Member", "Team"], dropna=False)
        .agg(Total_Leads=("id", "count"), Converted=("converted", "sum"), Total_Sales=("sales_value", "sum"))
        .reset_index()
    )
    member_summary["Conversion_%"] = (member_summary["Converted"] / member_summary["Total_Leads"] * 100).round(2)
    st.dataframe(member_summary.sort_values("Converted", ascending=False), use_container_width=True)

    st.markdown("---")

    # Top performers
    st.subheader("🏆 Top Performers")
    if not member_summary.empty:
        idx = member_summary["Converted"].idxmax()
        top_member = member_summary.loc[idx]
        st.success(f"👤 **{top_member['Member']} ({top_member['Team']})** — {int(top_member['Converted'])} conversions.")
    if not team_summary.empty:
        idx2 = team_summary["Converted"].idxmax()
        top_team = team_summary.loc[idx2]
        st.info(f"🏢 **{top_team['Team']}** — {int(top_team['Converted'])} conversions.")

    st.markdown("---")

    # Export Excel (auto detect engine)
    st.subheader("📦 Export Data")
    excel_buffer = io.BytesIO()
    # pick an engine if available
    engine = None
    try:
        import xlsxwriter  # type: ignore
        engine = "xlsxwriter"
    except Exception:
        try:
            import openpyxl  # type: ignore
            engine = "openpyxl"
        except Exception:
            engine = None

    if engine:
        try:
            with pd.ExcelWriter(excel_buffer, engine=engine) as writer:
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
    else:
        st.info("Excel export is unavailable (install xlsxwriter/openpyxl in the environment to enable).")

# ---------------------- Admin ----------------------
# =====================================
# 🛠️ ADMIN PANEL (FIXED, SAME FEATURES)
# =====================================
import uuid
import streamlit as st

st.header("🛠️ Admin Panel")

# --- Load teams and members (keep your original query style) ---
try:
    teams = supabase.table("teams").select("*").execute().data or []
    members = supabase.table("users").select("*").execute().data or []
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

# --- List Members ---
st.subheader("👥 Team Members")

if not members:
    st.info("No members found.")
else:
    # ✅ enumerate() gives each row a unique index to prevent duplicate keys
    for i, member in enumerate(members):
        col1, col2, col3, col4 = st.columns([3, 3, 2, 2])
        col1.write(member.get("name", "Unnamed"))
        team_name = next((t["name"] for t in teams if t["id"] == member.get("team_id")), "—")
        col2.write(team_name)

        # ✅ Add unique suffix using uuid4() + loop index to prevent duplicate keys
        if col3.button("✏️ Edit", key=f"edit_{member.get('id', str(uuid.uuid4()))}_{i}"):
            st.session_state["edit_member"] = member
            st.session_state["edit_mode"] = True

        if col4.button("❌ Delete", key=f"delete_{member.get('id', str(uuid.uuid4()))}_{i}"):
            try:
                supabase.table("users").delete().eq("id", member["id"]).execute()
                st.success(f"Deleted {member.get('name', 'Member')}")
                st.rerun()
            except Exception as e:
                st.error(f"Error deleting member: {e}")

# --- Edit Member (unchanged, only safer key) ---
if st.session_state.get("edit_mode", False):
    st.markdown("---")
    st.subheader("✏️ Edit Member")
    edit_member = st.session_state.get("edit_member", {})

    with st.form(key=f"edit_form_{edit_member.get('id', str(uuid.uuid4()))}"):
        new_name = st.text_input("Name", value=edit_member.get("name", ""))
        team_options = {t["name"]: t["id"] for t in teams}
        current_team_name = next((t["name"] for t in teams if t["id"] == edit_member.get("team_id")), "")
        selected_team = st.selectbox(
            "Team",
            list(team_options.keys()),
            index=list(team_options.keys()).index(current_team_name) if current_team_name in team_options else 0
        )

        save = st.form_submit_button("💾 Save")
        cancel = st.form_submit_button("❌ Cancel")

        if save:
            try:
                supabase.table("users").update({
                    "name": new_name,
                    "team_id": team_options[selected_team]
                }).eq("id", edit_member["id"]).execute()
                st.success(f"Updated {new_name}")
                st.session_state["edit_mode"] = False
                st.session_state["edit_member"] = None
                st.rerun()
            except Exception as e:
                st.error(f"Error updating member: {e}")

        if cancel:
            st.session_state["edit_mode"] = False
            st.session_state["edit_member"] = None
            st.rerun()

# --- Add Member (unchanged, only safer key) ---
st.markdown("---")
st.subheader("➕ Add Member")

with st.form(key=f"add_member_form_{uuid.uuid4()}"):
    new_name = st.text_input("Member Name")
    team_options = {t["name"]: t["id"] for t in teams}
    selected_team = st.selectbox("Assign to Team", list(team_options.keys()) or ["No Teams Available"])
    add_submit = st.form_submit_button("Add Member")

    if add_submit:
        if not new_name.strip():
            st.warning("Please enter a name.")
        else:
            try:
                team_id = team_options.get(selected_team)
                supabase.table("users").insert({
                    "name": new_name,
                    "team_id": team_id
                }).execute()
                st.success(f"Added {new_name} to {selected_team}")
                st.rerun()
            except Exception as e:
                st.error(f"Error adding member: {e}")

"""
Lead Management Streamlit App
File: lead_management_streamlit_app.py

This is a starter single-file Streamlit app implementing:
  - Dashboard (team & individual lead counts)
  - Daily Upload (CSV upload + per-member manual entry)
  - Reporting (weekly/monthly summaries & export)
  - Admin panel (create teams, add members, set targets)

Default data backend: Supabase (Postgres). Alternatives described below: Firestore, Airtable, GitHub-hosted JSON (read-only caveats).

Instructions:
  1. Create a Supabase project (free tier) and create tables: leads, users, teams, targets. See schema at the bottom.
  2. Add SUPABASE_URL and SUPABASE_KEY as Streamlit secrets or environment variables.
  3. Add dependencies to requirements.txt: streamlit, supabase, pandas, python-dateutil
  4. Push this repo to GitHub and deploy on Streamlit Community Cloud (connect GitHub repo).

Note: This file is a practical skeleton — customize validations, auth, security rules, and UI per your needs.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from dateutil import parser
import os

# Optional: import supabase client
try:
    from supabase import create_client, Client
except Exception:
    create_client = None
    Client = None

# ---------------------- Configuration ----------------------
BACKEND = st.secrets.get("BACKEND", "supabase")  # 'supabase' | 'firestore' | 'airtable' | 'json'

# Supabase config (recommended)
SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL"))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY"))

# Initialize supabase client if available
supabase: Client | None = None
if BACKEND == "supabase" and create_client and SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------- Helper DB functions (Supabase example) ----------------------

def get_leads_supabase(start_date=None, end_date=None):
    """Fetch leads from supabase optionally filtered by date."""
    if not supabase:
        return pd.DataFrame()
    query = supabase.table('leads').select('*')
    if start_date:
        query = query.gte('created_at', start_date.isoformat())
    if end_date:
        query = query.lte('created_at', end_date.isoformat())
    res = query.execute()
    data = res.data if hasattr(res, 'data') else res
    return pd.DataFrame(data)


def insert_leads_supabase(df: pd.DataFrame):
    """Insert multiple leads (expects DataFrame with columns matching table)."""
    if not supabase or df.empty:
        return None
    records = df.to_dict(orient='records')
    res = supabase.table('leads').insert(records).execute()
    return res


def update_lead_converted_supabase(lead_id, converted, sales_value=0):
    if not supabase:
        return None
    res = supabase.table('leads').update({'converted': converted, 'sales_value': sales_value}).eq('id', lead_id).execute()
    return res

# ---------------------- UI ----------------------

st.set_page_config(page_title="Lead Management", layout="wide")
st.title("Lead Management App — Starter")

# Tabs
tab = st.sidebar.radio("Go to", ['Dashboard', 'Daily Upload', 'Reporting', 'Admin'])

# ---------------------- Dashboard ----------------------
if tab == 'Dashboard':
    st.header("Dashboard")
    col1, col2 = st.columns(2)

    # Quick date range
    today = datetime.utcnow().date()
    start = st.date_input("Start date", value=today - timedelta(days=30))
    end = st.date_input("End date", value=today)

    # Load data from backend
    if BACKEND == 'supabase':
        leads_df = get_leads_supabase(start_date=start, end_date=end)
    else:
        st.info("Other backends not implemented in this skeleton. Use Supabase or extend functions.")
        leads_df = pd.DataFrame()

    if leads_df.empty:
        st.warning("No leads found for selected range (or DB not configured).")
    else:
        # Ensure created_at parsed
        leads_df['created_at'] = pd.to_datetime(leads_df['created_at'])
        # team & owner counts
        team_counts = leads_df.groupby('team_id').size().reset_index(name='leads')
        owner_counts = leads_df.groupby('owner_id').size().reset_index(name='leads')

        with col1:
            st.subheader("Leads by Team")
            st.dataframe(team_counts)

        with col2:
            st.subheader("Leads by Owner")
            st.dataframe(owner_counts)

        st.subheader("Recent Leads")
        st.dataframe(leads_df.sort_values('created_at', ascending=False).head(50))

# ---------------------- Daily Upload ----------------------
elif tab == 'Daily Upload':
    st.header("Daily Upload")
    st.write("Upload CSV of leads (cols: id, owner_id, team_id, name, contact, source, created_at, converted, sales_value)")
    uploaded = st.file_uploader("Upload CSV file", type=['csv'])

    if uploaded is not None:
        df = pd.read_csv(uploaded)
        st.dataframe(df.head())
        if st.button("Insert leads to DB"):
            res = insert_leads_supabase(df)
            st.success("Inserted to DB") if res else st.error("Insert failed or DB not configured")

    st.markdown("---")
    st.write("Quick single lead entry")
    with st.form("single_lead"):
        owner = st.text_input("Owner ID")
        team = st.text_input("Team ID")
        name = st.text_input("Lead name")
        contact = st.text_input("Contact")
        src = st.text_input("Source")
        converted = st.checkbox("Converted")
        sales_val = st.number_input("Sales value", value=0)
        submitted = st.form_submit_button("Add lead")
        if submitted:
            row = {
                'owner_id': owner,
                'team_id': team,
                'name': name,
                'contact': contact,
                'source': src,
                'created_at': datetime.utcnow().isoformat(),
                'converted': converted,
                'sales_value': float(sales_val)
            }
            if supabase:
                supabase.table('leads').insert(row).execute()
                st.success("Lead added")
            else:
                st.error("DB not configured")

# ---------------------- Reporting ----------------------
elif tab == 'Reporting':
    st.header("Reporting")
    st.write("Generate weekly and monthly reports")

    report_type = st.selectbox("Report type", ['weekly', 'monthly'])
    ref_date = st.date_input("Reference date", value=datetime.utcnow().date())

    if BACKEND == 'supabase':
        df = get_leads_supabase()
    else:
        df = pd.DataFrame()

    if df.empty:
        st.warning("No data to report")
    else:
        df['created_at'] = pd.to_datetime(df['created_at'])
        if report_type == 'weekly':
            start = pd.to_datetime(ref_date) - pd.Timedelta(days=7)
        else:
            start = pd.to_datetime(ref_date) - pd.Timedelta(days=30)
        filt = df[(df['created_at'] >= start) & (df['created_at'] <= pd.to_datetime(ref_date))]

        st.subheader(f"{report_type.title()} summary ({start.date()} to {ref_date})")
        by_team = filt.groupby('team_id').agg(total_leads=('id', 'count'), converted=('converted', 'sum'), sales=('sales_value', 'sum')).reset_index()
        st.dataframe(by_team)

        st.download_button("Download CSV", by_team.to_csv(index=False), file_name=f"report_{report_type}_{ref_date}.csv")

# ---------------------- Admin ----------------------
elif tab == 'Admin':
    st.header("Admin Panel")
    st.write("Create teams, add users, set weekly/monthly targets")

    with st.expander("Create Team"):
        team_name = st.text_input("Team name")
        team_desc = st.text_area("Description")
        if st.button("Create Team"):
            if supabase:
                supabase.table('teams').insert({'name': team_name, 'description': team_desc}).execute()
                st.success("Team created")
            else:
                st.error("DB not configured")

    with st.expander("Add User"):
        uid = st.text_input("User ID (string)")
        uname = st.text_input("User name")
        user_team = st.text_input("Team ID")
        if st.button("Add User"):
            if supabase:
                supabase.table('users').insert({'id': uid, 'name': uname, 'team_id': user_team}).execute()
                st.success("User added")
            else:
                st.error("DB not configured")

    with st.expander("Set Targets"):
        target_user = st.text_input("User ID for target")
        weekly = st.number_input("Weekly upload target", value=0)
        monthly = st.number_input("Monthly upload target", value=0)
        if st.button("Set Target"):
            if supabase:
                supabase.table('targets').upsert({'user_id': target_user, 'weekly': int(weekly), 'monthly': int(monthly)}).execute()
                st.success("Target set")
            else:
                st.error("DB not configured")


# ---------------------- Schema suggestion ----------------------
# (This section is a reference—create these tables in Supabase/PG)
#
# leads:
#  id: uuid primary key
#  owner_id: text (references users.id)
#  team_id: text (references teams.id)
#  name: text
#  contact: text
#  source: text
#  created_at: timestamptz default now()
#  converted: boolean default false
#  sales_value: numeric default 0
#
# users:
#  id: text primary key
#  name: text
#  team_id: text
#
# teams:
#  id: text primary key
#  name: text
#  description: text
#
# targets:
#  user_id: text primary key
#  weekly: int
#  monthly: int

# ---------------------- Notes & Alternatives ----------------------
# - Supabase (recommended): Postgres with REST and realtime. Easy to use from Python and supports row-level security.
# - Firestore: Good if you need a NoSQL document store and global scaling; use google-cloud-firestore or REST API.
# - Airtable: Very quick low-code option, easy UI for non-devs; accessible via REST API but limited for heavy loads.
# - GitHub-hosted JSON: Simple for read-only prototyping (raw.githubusercontent), but writes require auth and are not ideal for production.

# End of file

import streamlit as st
import pandas as pd
import plotly.express as px
from pymongo import MongoClient
from datetime import datetime, timedelta
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from streamlit_autorefresh import st_autorefresh

# ==================================================
# Streamlit Page Setup
# ==================================================
st.set_page_config(page_title="Internal Reporting Dashboard", layout="wide")
st.title("📊 Typo SignUps Dashboard")


# ==================================================
# Auto-refresh every 10 minutes (600,000 ms)
# ==================================================
st_autorefresh(interval=600000, key="datarefresh")


# ==================================================
# MongoDB Connection
# ==================================================
CONNECTION_STRING = "mongodb+srv://admin:Huddle_8768sdjhf^&hgdsfjkk_Up@typo-prod.81pnw.mongodb.net/typo?retryWrites=true&w=majority"
client = MongoClient(CONNECTION_STRING)
db = client["typo"]

organizations = db["organizations"]
installations = db["installations"]
alerts = db["alerts"]
alertconfigs = db["alertconfigs"]
userevents = db["userevents"]
users = db["users"]


# ==================================================
# 1. Metrics Section
# ==================================================
total_signups = organizations.count_documents({"toBeSynced": True})
github_int = installations.count_documents({"source": "github"})
gitlab_int = installations.count_documents({"source": "gitlab"})
bitbucket_int = installations.count_documents({"source": "bitbucket"})
jira_int = installations.count_documents({"source": "jira"})
slack_int = installations.count_documents({"source": "slack"})

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Total Signups", total_signups)
col2.metric("Github Integrations", github_int)
col3.metric("Gitlab Integrations", gitlab_int)
col4.metric("Bitbucket Integrations", bitbucket_int)
col5.metric("Jira Integrations", jira_int)
col6.metric("Slack Integrations", slack_int)

# # Other integrations
# sources = ["github", "gitlab", "bitbucket", "clickup", "linear"]
# counts = [installations.count_documents({"source": s}) for s in sources]
# df_integrations = pd.DataFrame({"Integration": sources, "Count": counts})

# fig_pie = px.pie(df_integrations, values="Count",
#                  names="Integration", title="Integrations Breakdown")
# st.plotly_chart(fig_pie, use_container_width=True)

# ==================================================
# 2. Daily Signups Chart (last 6 months only)
# ==================================================
six_months_ago = datetime.utcnow() - timedelta(days=180)
daily_signups = list(organizations.aggregate([
    {"$match": {"createdAt": {"$gte": six_months_ago}}},
    {"$group": {
        "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$createdAt"}},
        "count": {"$sum": 1}
    }},
    {"$sort": {"_id": 1}}
]))
df_daily = pd.DataFrame(daily_signups)

if not df_daily.empty:
    df_daily.rename(columns={"_id": "Date", "count": "Signups"}, inplace=True)
    total_6mo_signups = int(df_daily["Signups"].sum())

    fig_line = px.line(
        df_daily, x="Date", y="Signups",
        title="Daily Signups (last 6 months)", markers=True
    )

    # add a total badge inside the plot area (top-left)
    fig_line.add_annotation(
        xref="paper", yref="paper",
        x=0.01, y=0.98,
        text=f"<b>Total (6 mo): {total_6mo_signups}</b>",
        showarrow=False,
        align="left",
        bordercolor="rgba(0,0,0,0.2)",
        borderwidth=1,
        bgcolor="rgba(255,255,255,0.85)",
        font=dict(size=12)
    )

    st.plotly_chart(fig_line, use_container_width=True)
else:
    st.info("No signups in the last 6 months.")


# ==================================================
# 3. Company Data Table (Optimized)
# ==================================================
st.subheader("Company Data (Latest 50 Orgs)")

# Fetch 50 latest orgs at once
org_ids = list(organizations.find(
    {"toBeSynced": True},
    {"_id": 1, "createdAt": 1, "name": 1, "utmTag": 1, "installationUser": 1}
).sort("createdAt", -1).limit(50))

org_df = pd.DataFrame(org_ids)
if org_df.empty:
    st.warning("No organizations found.")
else:
    now = datetime.utcnow()
    companies = []

    # Pre-fetch related data in bulk
    org_id_list = [o["_id"] for o in org_ids]
    user_id_list = [o.get("installationUser")
                    for o in org_ids if o.get("installationUser")]

    # Users info in bulk
    users_map = {str(u["_id"]): u for u in users.find(
        {"_id": {"$in": user_id_list}}, {"name": 1, "login": 1, "email": 1})}

    # Alerts count per org
    alerts_count_map = {str(a["_id"]): alerts.count_documents(
        {"org": a["_id"]}) for a in org_ids}

    # Goals count per org
    goals_count_map = {str(a["_id"]): alertconfigs.count_documents(
        {"org": a["_id"], "isActive": True}) for a in org_ids}

    # Dev counts in bulk
    dev_counts = {str(org["_id"]): users.count_documents(
        {"organizations": {"$in": [org["_id"]]}}) for org in org_ids}

    for org in org_ids:
        org_id = org["_id"]
        created_at = org.get("createdAt")
        name = org.get("name", "NA")
        utm_tag = org.get("utmTag", "-")
        inst_user = org.get("installationUser")

        # Admin user
        admin_user = users_map.get(str(inst_user), {})
        admin_name = admin_user.get("name", "NA")
        login = admin_user.get("login", "NA")
        email = admin_user.get("email", "NA")

        # Trial days remaining
        trial_end = (created_at + timedelta(days=30)) if created_at < datetime(2023,
                                                                               5, 15) else (created_at + timedelta(days=14))
        days_remaining = (trial_end - now).days
        days_remaining = str(
            days_remaining) if days_remaining > 0 else "Trial Ended"

        # Activities count
        activities_count = userevents.count_documents(
            {"user": inst_user}) if inst_user else 0

        # Last activity date
        last_activity = userevents.find_one({"user": inst_user}, sort=[
            ("createdAt", -1)]) if inst_user else None
        last_activity_date = last_activity["createdAt"].strftime(
            "%d-%m-%Y") if last_activity else "NA"

        companies.append({
            "Company": name,
            "Admin Name": admin_name,
            "Login": login,
            "Email": email,
            "Dev Count": dev_counts.get(str(org_id), 0),
            "Sign Up Date": created_at.strftime("%d-%m-%Y") if created_at else "NA",
            "FT Days Remaining": days_remaining,
            "Activities": activities_count,
            "Last Activity Date": last_activity_date,
            "Goals Live": goals_count_map.get(str(org_id), 0),
            "Alerts Generated": alerts_count_map.get(str(org_id), 0),
            # "Source": utm_tag,
            "User Id": str(inst_user) if inst_user else "-"
        })

    df_companies = pd.DataFrame(companies)

    # Interactive AgGrid
    gb = GridOptionsBuilder.from_dataframe(df_companies)
    gb.configure_pagination(paginationAutoPageSize=True)
    gb.configure_side_bar()
    gb.configure_default_column(resizable=True, filter=True, sortable=True)
    gridOptions = gb.build()

    AgGrid(
        df_companies,
        gridOptions=gridOptions,
        enable_enterprise_modules=False,
        update_mode=GridUpdateMode.NO_UPDATE,
        theme="streamlit",
        fit_columns_on_grid_load=True
    )

    # Download buttons
    csv = df_companies.to_csv(index=False).encode("utf-8")
    df_companies.to_excel("company_data.xlsx", index=False, engine="openpyxl")

    col7, col8 = st.columns(2)
    with col7:
        st.download_button("📥 Download as CSV", data=csv,
                           file_name="company_data.csv", mime="text/csv")
    with col8:
        with open("company_data.xlsx", "rb") as f:
            st.download_button("📥 Download as Excel", data=f, file_name="company_data.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

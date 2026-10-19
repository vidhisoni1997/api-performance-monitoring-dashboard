
from streamlit_autorefresh import st_autorefresh
import requests
import pandas as pd
import plotly.express as px
import streamlit as st

API_URL = "https://api-performance-monitoring-dashboard.onrender.com"

st.set_page_config(
    page_title="API Performance Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("📊 API Performance Monitoring Dashboard")
st.caption("Live metrics from your FastAPI backend and PostgreSQL database")

# Fetch data from FastAPI
def fetch_data(endpoint, params=None):
    try:
        response = requests.get(
            f"{API_URL}{endpoint}",
            params=params,
            timeout=5
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        st.error(f"Could not fetch {endpoint}: {error}")
        return None

def fetch_advanced_metrics(window_minutes=5):
    try:
        response = requests.get(
            f"{API_URL}/metrics/advanced",
            params={"window_minutes": window_minutes},
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        st.error(f"Could not fetch advanced metrics: {error}")
        return None





# Dashboard refresh settings
st.sidebar.header("Dashboard Settings")

refresh_seconds = st.sidebar.selectbox(
    "Auto-refresh interval",
    options=[5, 10, 30, 60],
    index=1,
    format_func=lambda seconds: f"{seconds} seconds"
)

refresh_count = st_autorefresh(
    interval=refresh_seconds * 1000,
    limit=None,
    key="dashboard_autorefresh"
)

st.sidebar.success(
    f"Auto-refresh enabled: every {refresh_seconds} seconds"
)


overview = fetch_data("/metrics/overview")
metrics = fetch_data("/metrics", {"limit": 100})
slow_data = fetch_data(
    "/metrics/slow",
    {"threshold_ms": 500, "limit": 100}
)

if overview is not None:
    st.subheader("Performance Overview")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Total Requests",
        overview["total_requests"]
    )
    col2.metric(
        "Avg Response Time",
        f'{overview["average_response_time_ms"]} ms'
    )
    col3.metric(
        "Error Rate",
        f'{overview["error_rate_percent"]}%'
    )
    col4.metric(
        "Slow Requests (500+ ms)",
        overview["slow_request_count"]
    )

    st.subheader("API Health")
    status = overview["health_status"].upper()

    if status == "HEALTHY":
        st.success(f"System status: {status}")
    elif status == "DEGRADED":
        st.warning(f"System status: {status}")
    else:
        st.error(f"System status: {status}")

st.subheader("Advanced Performance Metrics")

advanced_data = fetch_advanced_metrics(window_minutes=5)

if advanced_data is not None:
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "P95 Response Time",
            f"{advanced_data['p95_response_time_ms']:.2f} ms"
        )

    with col2:
        st.metric(
            "Requests Per Second",
            f"{advanced_data['requests_per_second']:.4f}"
        )

    with col3:
        st.metric(
            "Requests in Last 5 Minutes",
            advanced_data["total_requests"]
        )

if advanced_data is not None:
    endpoint_errors = advanced_data["endpoint_errors"]

    st.subheader("Endpoint-wise Error Rate")

    if endpoint_errors:
        error_df = pd.DataFrame(endpoint_errors)

        error_df["endpoint"] = (
            error_df["method"] + " " + error_df["path"]
        )

        fig = px.bar(
            error_df,
            x="endpoint",
            y="error_rate_percent",
            color="error_rate_percent",
            title="Error Rate by Endpoint",
            labels={
                "endpoint": "API Endpoint",
                "error_rate_percent": "Error Rate (%)"
            },
            hover_data=[
                "total_requests",
                "error_count"
            ]
        )

        fig.update_layout(
            yaxis_range=[0, 100]
        )

        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("No requests found in the selected time window.")



if metrics is not None:
    df = pd.DataFrame(metrics)

    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])

        # Sidebar filters
        st.sidebar.header("Metric Filters")

        endpoints = sorted(df["path"].dropna().unique().tolist())

        selected_endpoints = st.sidebar.multiselect(
            "Select API endpoints",
            options=endpoints,
            default=endpoints
        )

        min_date = df["created_at"].min().date()
        max_date = df["created_at"].max().date()

        selected_dates = st.sidebar.date_input(
            "Select date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )

        # Apply filters
        filtered_df = df[df["path"].isin(selected_endpoints)]

        if isinstance(selected_dates, (tuple, list)):
            if len(selected_dates) == 2:
                start_date, end_date = selected_dates

                filtered_df = filtered_df[
                    (filtered_df["created_at"].dt.date >= start_date)
                    & (filtered_df["created_at"].dt.date <= end_date)
                ]

        st.subheader("Filtered API Metrics")
        st.caption(f"Showing {len(filtered_df)} matching requests")

        if not filtered_df.empty:
            # Response-time chart
            fig = px.line(
                filtered_df.sort_values("created_at"),
                x="created_at",
                y="response_time_ms",
                color="path",
                markers=True,
                title="API Response Time Over Time",
                labels={
                    "created_at": "Request Time",
                    "response_time_ms": "Response Time (ms)",
                    "path": "API Endpoint"
                }
            )
            st.plotly_chart(fig, use_container_width=True)

            # Status-code chart
            status_counts = (
                filtered_df["status_code"]
                .value_counts()
                .sort_index()
                .rename_axis("status_code")
                .reset_index(name="count")
            )

            fig_status = px.bar(
                status_counts,
                x="status_code",
                y="count",
                title="Requests by HTTP Status Code",
                labels={
                    "status_code": "HTTP Status Code",
                    "count": "Number of Requests"
                }
            )
            st.plotly_chart(fig_status, use_container_width=True)
            
# Statistics based on the selected filters
            st.subheader("Filtered Performance Summary")

            total = len(filtered_df)

            avg_response = filtered_df["response_time_ms"].mean()

            error_count = (
    filtered_df["status_code"] >= 400
).sum()

            error_rate = (
                (error_count / total) * 100
                if total > 0
                else 0
            )

            slow_count = (
                filtered_df["response_time_ms"] >= 500
            ).sum()

            col1, col2, col3, col4 = st.columns(4)

            col1.metric("Filtered Requests", total)
            col2.metric(
                "Average Response Time",
                f"{avg_response:.2f} ms"
            )
            col3.metric("Error Rate", f"{error_rate:.2f}%")
            col4.metric("Slow Requests", int(slow_count))
 
            # Filtered request table
            st.subheader("Recent API Requests")
            st.dataframe(
                filtered_df.sort_values(
                    "created_at", ascending=False
                ),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No requests match the selected filters.")
    else:
        st.info("No API metrics have been recorded yet.")


if slow_data is not None:
    st.subheader("Slow API Requests")

    slow_requests = slow_data.get("slow_requests", [])

    if slow_requests:
        st.dataframe(
            pd.DataFrame(slow_requests),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.success("No requests exceeded 500 ms.")

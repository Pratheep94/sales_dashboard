"""
Business Analytics Dashboard
-----------------------------
A pure-Python web app (Streamlit handles both the frontend UI and the
backend logic — no separate JS frontend needed) that lets a user pick
one or more "business points" to analyze:

    1. Monthly Sales Analysis
    2. Monthly Product Analysis

joblib is used in two ways:
  - joblib.Memory: disk-caches the (potentially expensive) analysis
    functions so re-running the same query on the same data is instant.
  - joblib.dump/load: lets the user save a processed analysis result
    ("model"/summary object) to disk and reload it later without
    re-uploading or recomputing anything.

Run with:
    pip install -r requirements.txt
    streamlit run app.py
"""

import io
import hmac
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import joblib

# --------------------------------------------------------------------------
# Setup: joblib disk cache
# --------------------------------------------------------------------------
CACHE_DIR = Path(__file__).parent / "cache"
SAVED_DIR = Path(__file__).parent / "saved_results"
CACHE_DIR.mkdir(exist_ok=True)
SAVED_DIR.mkdir(exist_ok=True)

memory = joblib.Memory(location=str(CACHE_DIR), verbose=0)

st.set_page_config(
    page_title="Business Analytics Dashboard",
    page_icon="📊",
    layout="wide",
)

BUSINESS_POINTS = [
    "Monthly Sales Analysis",
    "Monthly Product Analysis",
]

REQUIRED_COLUMNS = ["Date", "Vendor_Name", "Territory", "Product", "Quantity", "Price_Pce", "Sales", "Type"]



# --------------------------------------------------------------------------
# Simple password gate
# --------------------------------------------------------------------------
def check_password() -> bool:
    """
    Shows a password prompt and returns True only once the correct
    password has been entered. The password is read from Streamlit
    secrets (st.secrets['app_password']) so it is never hard-coded into
    the source file — see the 'Setting the password' note in README.md.
    Uses hmac.compare_digest to avoid timing-attack leakage.
    """
    if st.session_state.get("authenticated", False):
        return True

    st.title("📊 Business Analytics Dashboard")
    st.subheader("🔒 Sign in")

    configured_password = st.secrets.get("app_password")
    if not configured_password:
        st.error(
            "No password is configured for this app. Set `app_password` "
            "in .streamlit/secrets.toml (locally) or in the app's "
            "'Secrets' settings (Streamlit Community Cloud) before deploying."
        )
        st.stop()

    with st.form("login_form"):
        entered = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Enter")

    if submitted:
        if hmac.compare_digest(entered, configured_password):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password. Please try again.")

    return False


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------
def _read_any(file_bytes: bytes, filename: str) -> pd.DataFrame:
    buf = io.BytesIO(file_bytes)
    if filename.lower().endswith(".csv"):
        return pd.read_csv(buf)
    return pd.read_excel(buf)


@memory.cache
def load_and_clean(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Load an uploaded file and normalize it into a standard schema.
    Cached by joblib: identical file bytes -> instant reload."""
    df = _read_any(file_bytes, filename)
    df.columns = [c.strip().title() for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required column(s): {', '.join(missing)}. "
            f"Expected columns: {', '.join(REQUIRED_COLUMNS)}"
        )

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df["Sales"] = pd.to_numeric(df["Sales"], errors="coerce").fillna(0)
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)
    df["Month"] = df["Date"].dt.to_period("M").astype(str)
    df = df[df['Type'] == 'Sales']
    return df


def generate_sample_data(n_months: int = 12) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    products = ["Widget A", "Widget B", "Gadget X", "Gadget Y", "Gizmo Z"]
    rows = []
    start = pd.Timestamp.today().normalize().replace(day=1) - pd.DateOffset(months=n_months - 1)
    for m in range(n_months):
        month_start = start + pd.DateOffset(months=m)
        days_in_month = pd.Period(month_start, freq="M").days_in_month
        for _ in range(60):
            day = rng.integers(1, days_in_month + 1)
            date = month_start.replace(day=int(day))
            product = rng.choice(products)
            qty = int(rng.integers(1, 20))
            price = {"Widget A": 25, "Widget B": 40, "Gadget X": 120,
                     "Gadget Y": 80, "Gizmo Z": 15}[product]
            sales = qty * price * rng.uniform(0.9, 1.1)
            rows.append([date, product, round(sales, 2), qty])
    df = pd.DataFrame(rows, columns=["Date", "Product", "Sales", "Quantity"])
    df["Month"] = df["Date"].dt.to_period("M").astype(str)
    return df


# --------------------------------------------------------------------------
# Analysis functions (joblib-cached)
# --------------------------------------------------------------------------
@memory.cache
def monthly_sales_analysis(df: pd.DataFrame) -> dict:
    monthly = (
        df.groupby("Month")
        .agg(Total_Sales=("Sales", "sum"), Orders=("Sales", "count"))
        .reset_index()
        .sort_values("Month")
    )
    monthly["MoM_Growth_%"] = monthly["Total_Sales"].pct_change().mul(100).round(2)
    monthly["Avg_Order_Value"] = (monthly["Total_Sales"] / monthly["Orders"]).round(2)

    summary = {
        "total_sales": float(df["Sales"].sum()),
        "total_orders": int(len(df)),
        "avg_monthly_sales": float(monthly["Total_Sales"].mean()),
        "best_month": monthly.loc[monthly["Total_Sales"].idxmax(), "Month"],
        "worst_month": monthly.loc[monthly["Total_Sales"].idxmin(), "Month"],
    }
    return {"table": monthly, "summary": summary}


@memory.cache
def monthly_product_analysis(df: pd.DataFrame) -> dict:
    monthly_product = (
        df.groupby(["Month", "Product"])
        .agg(Total_Sales=("Sales", "sum"), Units_Sold=("Quantity", "sum"))
        .reset_index()
        .sort_values(["Month", "Total_Sales"], ascending=[True, False])
    )

    product_totals = (
        df.groupby("Product")
        .agg(Total_Sales=("Sales", "sum"), Units_Sold=("Quantity", "sum"))
        .reset_index()
        .sort_values("Total_Sales", ascending=False)
    )

    top_per_month = (
        monthly_product.sort_values(["Month", "Total_Sales"], ascending=[True, False])
        .groupby("Month")
        .first()
        .reset_index()[["Month", "Product", "Total_Sales"]]
        .rename(columns={"Product": "Top_Product", "Total_Sales": "Top_Product_Sales"})
    )

    summary = {
        "best_selling_product": product_totals.iloc[0]["Product"],
        "best_selling_product_total": float(product_totals.iloc[0]["Total_Sales"]),
        "num_products": int(df["Product"].nunique()),
    }
    return {
        "monthly_product": monthly_product,
        "product_totals": product_totals,
        "top_per_month": top_per_month,
        "summary": summary,
    }


# --------------------------------------------------------------------------
# UI sections
# --------------------------------------------------------------------------
def show_monthly_sales(df: pd.DataFrame):
    st.header("📈 Monthly Sales Analysis")
    result = monthly_sales_analysis(df)
    table, summary = result["table"], result["summary"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Sales", f"{summary['total_sales']:,.2f}")
    c2.metric("Total Orders", f"{summary['total_orders']:,}")
    c3.metric("Avg Monthly Sales", f"{summary['avg_monthly_sales']:,.2f}")

    fig = px.bar(table, x="Month", y="Total_Sales", title="Total Sales by Month",
                 text_auto=".2s")
    st.plotly_chart(fig, use_container_width=True)

    fig2 = px.line(table, x="Month", y="MoM_Growth_%", markers=True,
                    title="Month-over-Month Growth (%)")
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Details")
    st.dataframe(table, use_container_width=True)

    st.caption(
        f"Best month: **{summary['best_month']}** · "
        f"Worst month: **{summary['worst_month']}**"
    )

    return result


def show_monthly_product(df: pd.DataFrame):
    st.header("📦 Monthly Product Analysis")
    result = monthly_product_analysis(df)
    monthly_product = result["monthly_product"]
    product_totals = result["product_totals"]
    top_per_month = result["top_per_month"]
    summary = result["summary"]

    c1, c2 = st.columns(2)
    c1.metric("Best-Selling Product", summary["best_selling_product"],
               f"{summary['best_selling_product_total']:,.2f} total sales")
    c2.metric("Distinct Products", summary["num_products"])

    fig = px.bar(product_totals, x="Product", y="Total_Sales",
                 title="Total Sales by Product", text_auto=".2s")
    st.plotly_chart(fig, use_container_width=True)

    fig2 = px.bar(monthly_product, x="Month", y="Total_Sales", color="Product",
                  title="Monthly Sales by Product (stacked)", barmode="stack")
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Top Product per Month")
    st.dataframe(top_per_month, use_container_width=True)

    st.subheader("Full Detail")
    st.dataframe(monthly_product, use_container_width=True)

    return result


# --------------------------------------------------------------------------
# Save / load processed results with joblib
# --------------------------------------------------------------------------
def save_results(name: str, payload: dict):
    path = SAVED_DIR / f"{name}.joblib"
    joblib.dump(payload, path)
    return path


def list_saved_results():
    return sorted(SAVED_DIR.glob("*.joblib"))


# --------------------------------------------------------------------------
# Main app
# --------------------------------------------------------------------------
def main():
    if not check_password():
        return

    st.title("📊 Business Analytics Dashboard")
    st.write(
        "Select one or more business points, provide your data, and get "
        "instant analysis. Results are cached and can be saved with `joblib` "
        "for later reuse."
    )

    if st.sidebar.button("🚪 Log out"):
        st.session_state["authenticated"] = False
        st.rerun()

    st.sidebar.header("1. Select Business Points")
    selected = st.sidebar.multiselect(
        "Business points to analyze",
        BUSINESS_POINTS,
        default=[BUSINESS_POINTS[0]],
    )

    st.sidebar.header("2. Provide Data")
    uploaded_file = st.sidebar.file_uploader(
        "Upload sales data (CSV or Excel)", type=["csv", "xlsx"]
    )
    st.sidebar.caption(
        "Expected columns: **Date, Product, Sales, Quantity**"
    )
    use_sample = st.sidebar.button("Use sample data instead")

    df = None
    if uploaded_file is not None:
        try:
            df = load_and_clean(uploaded_file.getvalue(), uploaded_file.name)
        except ValueError as e:
            st.error(str(e))
            return
    elif use_sample or st.session_state.get("use_sample_data"):
        st.session_state["use_sample_data"] = True
        df = generate_sample_data()
        st.info("Using generated sample data.")

    if df is None:
        st.info("Upload a file or click **Use sample data instead** in the sidebar to begin.")
        return

    if not selected:
        st.warning("Select at least one business point from the sidebar.")
        return

    with st.expander("Preview raw data"):
        st.dataframe(df.head(50), use_container_width=True)

    results_to_save = {}

    if "Monthly Sales Analysis" in selected:
        results_to_save["monthly_sales_analysis"] = show_monthly_sales(df)
        st.divider()

    if "Monthly Product Analysis" in selected:
        results_to_save["monthly_product_analysis"] = show_monthly_product(df)
        st.divider()

    # Save / load section
    st.sidebar.header("3. Save / Load Results (joblib)")
    save_name = st.sidebar.text_input("Save current results as", value="latest_run")
    if st.sidebar.button("💾 Save with joblib"):
        path = save_results(save_name, results_to_save)
        st.sidebar.success(f"Saved to {path.name}")

    saved = list_saved_results()
    if saved:
        pick = st.sidebar.selectbox(
            "Load a previous run", [p.name for p in saved]
        )
        if st.sidebar.button("📂 Load selected"):
            loaded = joblib.load(SAVED_DIR / pick)
            st.sidebar.success(f"Loaded {pick} — see below")
            st.header(f"Loaded result: {pick}")
            for key, val in loaded.items():
                st.subheader(key.replace("_", " ").title())
                if "table" in val:
                    st.dataframe(val["table"])
                if "monthly_product" in val:
                    st.dataframe(val["monthly_product"])
                st.json(val["summary"])


if __name__ == "__main__":
    main()

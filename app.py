# app.py
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import os
from datetime import datetime
import altair as alt

st.set_page_config(page_title="Ola Ride Insights", layout="wide")

# ---------- PATHS (relative/portable) ----------
# Use the current working directory so the app works on Streamlit Cloud and locally
PROJECT_DIR = os.getcwd()
EXCEL_PATH = os.path.join(PROJECT_DIR, "OLA_DataSet.xlsx")           # optional local Excel
CLEAN_CSV = os.path.join(PROJECT_DIR, "Cleaned_OLA_Data.csv")       # prefer CSV in repo root
SQLITE_DB = os.path.join(PROJECT_DIR, "ola.db")                     # created inside project folder
IMG_FOLDER = os.path.join(PROJECT_DIR, "powerbi_images")

# ---------- Helper: load or create cleaned CSV ----------
@st.cache_data
def load_and_clean():
    # 1) Try to load cleaned CSV from project directory
    if os.path.exists(CLEAN_CSV):
        try:
            df = pd.read_csv(CLEAN_CSV, parse_dates=["Ride_Timestamp"], low_memory=False)
            return df
        except Exception:
            # try without parse_dates if Ride_Timestamp missing/has different format
            df = pd.read_csv(CLEAN_CSV, low_memory=False)
            return df

    # 2) If CSV not present, try to read Excel from project directory (useful for local runs)
    if os.path.exists(EXCEL_PATH):
        df = pd.read_excel(EXCEL_PATH, engine="openpyxl")
    else:
        # Nothing available in project folder: show helpful message in UI and stop
        st.error(
            f"Neither cleaned CSV found at {CLEAN_CSV} nor Excel at {EXCEL_PATH}. "
            "Please add Cleaned_OLA_Data.csv to the project root or upload the Excel."
        )
        return None

    # Basic standardization: make column names consistent
    df.columns = [c.strip() for c in df.columns]

    # Fix Date and Time -> Ride_Timestamp
    if "Date" in df.columns and "Time" in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df['Time'] = df['Time'].astype(str)
        df['Ride_Timestamp'] = pd.to_datetime(
            df['Date'].dt.strftime('%Y-%m-%d') + ' ' + df['Time'],
            errors='coerce'
        )
    else:
        if "Ride_Timestamp" in df.columns:
            df['Ride_Timestamp'] = pd.to_datetime(df['Ride_Timestamp'], errors='coerce')

    # Replace blank Payment_Method and Incomplete_Rides_Reason with labels
    if 'Payment_Method' in df.columns:
        df['Payment_Method'] = df['Payment_Method'].fillna('').astype(str).str.strip()
        df.loc[df['Payment_Method']=='', 'Payment_Method'] = 'Other'
    if 'Incomplete_Rides_Reason' in df.columns:
        df['Incomplete_Rides_Reason'] = df['Incomplete_Rides_Reason'].fillna('').astype(str).str.strip()
        df.loc[df['Incomplete_Rides_Reason']=='', 'Incomplete_Rides_Reason'] = 'Unknown Reason'

    # Numeric coercions
    if 'Ride_Distance' in df.columns:
        df['Ride_Distance'] = pd.to_numeric(df['Ride_Distance'], errors='coerce').fillna(0).astype(int)
    for col in ['Driver_Ratings', 'Customer_Rating']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'Booking_Value' in df.columns:
        df['Booking_Value'] = pd.to_numeric(df['Booking_Value'], errors='coerce').fillna(0).astype(int)

    # Save cleaned CSV into project dir so deployed app and local runs share the same file
    try:
        df.to_csv(CLEAN_CSV, index=False)
    except Exception:
        # if writing is not allowed (rare on some hosts), ignore silently
        pass

    return df

# Load data
df = load_and_clean()
if df is None:
    st.stop()

# ---------- Create sqlite db and table ----------
conn = sqlite3.connect(SQLITE_DB, check_same_thread=False)
try:
    df.to_sql("ola_rides", conn, if_exists="replace", index=False)
except Exception as e:
    st.warning(f"Could not write to sqlite DB: {e}")

st.title("Ola Ride Insights — Streamlit App")
st.caption("Interactive app to view SQL results, key metrics, and embed Power BI visuals (if published).")

# ---------- Run the 10 SQL queries and show results ----------
st.header("SQL Queries & Results (selected)")

queries = {
    "Query 1: All successful bookings": "SELECT * FROM ola_rides WHERE LOWER(Booking_Status) = 'success';",
    "Query 2: Avg ride distance per vehicle type": "SELECT Vehicle_Type, ROUND(AVG(CAST(Ride_Distance AS REAL)),3) AS Avg_Ride_Distance FROM ola_rides GROUP BY Vehicle_Type ORDER BY Avg_Ride_Distance DESC;",
    "Query 3: Total cancelled by customers": "SELECT COUNT(*) AS Total_Cancelled_By_Customer FROM ola_rides WHERE Canceled_Rides_by_Customer IS NOT NULL OR LOWER(Booking_Status) = 'canceled by customer' OR LOWER(Booking_Status) = 'cancelled by customer';",
    "Query 4: Top 5 customers by rides": "SELECT Customer_ID, COUNT(*) AS Total_Rides, SUM(Booking_Value) AS Total_Booking_Value FROM ola_rides GROUP BY Customer_ID ORDER BY Total_Rides DESC, Total_Booking_Value DESC LIMIT 5;",
    "Query 5: Driver cancellations (personal & car issues)": """
SELECT 
    SUM(CASE WHEN LOWER(Canceled_Rides_by_Driver) LIKE '%personal%' THEN 1 ELSE 0 END) AS Cancelled_By_Driver_Personal_Issues,
    SUM(CASE WHEN LOWER(Canceled_Rides_by_Driver) LIKE '%car%' 
          OR LOWER(Canceled_Rides_by_Driver) LIKE '%vehicle%' 
          OR LOWER(Canceled_Rides_by_Driver) LIKE '%breakdown%' THEN 1 ELSE 0 END) AS Cancelled_By_Driver_Car_Issues
FROM ola_rides 
WHERE Canceled_Rides_by_Driver IS NOT NULL;
""",
    "Query 6: Max & Min driver rating for Prime Sedan": "SELECT MAX(Driver_Ratings) AS Max_Driver_Rating, MIN(Driver_Ratings) AS Min_Driver_Rating, COUNT(*) AS Total_Prime_Sedan_Rides_With_Rating FROM ola_rides WHERE LOWER(Vehicle_Type) = 'prime sedan' AND Driver_Ratings IS NOT NULL;",
    "Query 7: Rides paid via UPI": "SELECT * FROM ola_rides WHERE LOWER(Payment_Method) = 'upi';",
    "Query 8: Avg customer rating per vehicle type": "SELECT Vehicle_Type, ROUND(AVG(Customer_Rating),3) AS Avg_Customer_Rating, COUNT(Customer_Rating) AS Rating_Count FROM ola_rides WHERE Customer_Rating IS NOT NULL GROUP BY Vehicle_Type ORDER BY Avg_Customer_Rating DESC;",
    "Query 9: Total booking value of successful rides": "SELECT SUM(Booking_Value) AS Total_Revenue_Successful_RIDES, COUNT(*) AS Total_Successful_Rides, ROUND(AVG(Booking_Value),2) AS Avg_Booking_Value FROM ola_rides WHERE LOWER(Booking_Status) = 'success';",
    "Query 10: All incomplete rides with reason": "SELECT Booking_ID, Ride_Timestamp, Booking_Status, Incomplete_Rides, Incomplete_Rides_Reason FROM ola_rides WHERE LOWER(Incomplete_Rides) = 'yes' OR Incomplete_Rides_Reason IS NOT NULL ORDER BY Ride_Timestamp;"
}

# Show a compact listing with an expander for each query
for title, q in queries.items():
    with st.expander(title):
        try:
            res = pd.read_sql_query(q, conn, parse_dates=['Ride_Timestamp'])
        except Exception:
            res = pd.read_sql_query(q, conn)
        st.write(f"Rows: {res.shape[0]}")
        st.dataframe(res.head(50), use_container_width=True)

# ---------- Simple dashboard-like visuals using Altair ----------
st.header("Quick Visuals derived from SQL results")

# 1) Ride volume over time (count per day)
if 'Ride_Timestamp' in df.columns:
    df['Ride_Date'] = pd.to_datetime(df['Ride_Timestamp']).dt.date
else:
    # fallback: try Date column
    df['Ride_Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date if 'Date' in df.columns else pd.NaT

rides_per_day = df.groupby('Ride_Date').size().reset_index(name='rides')
chart1 = alt.Chart(rides_per_day).mark_line(point=True).encode(
    x=alt.X('Ride_Date:T', title='Date'),
    y=alt.Y('rides:Q', title='Number of Rides')
).properties(height=250, width=800, title="Ride Volume Over Time")
st.altair_chart(chart1, use_container_width=True)

# 2) Booking status breakdown
if 'Booking_Status' in df.columns:
    status_counts = df['Booking_Status'].fillna('Unknown').value_counts().reset_index()
    status_counts.columns = ['Booking_Status','count']
    chart2 = alt.Chart(status_counts).mark_bar().encode(
        x=alt.X('Booking_Status:N', sort='-y'),
        y='count:Q',
        color='Booking_Status:N'
    ).properties(height=250, width=400, title='Booking Status Breakdown')
    st.altair_chart(chart2, use_container_width=True)
else:
    st.info("Booking_Status column not found in dataset.")

# ---------- Power BI embedding options ----------
st.header("Power BI visuals (optional)")

st.markdown("""
**Option A — Embed published Power BI visuals (recommended for live embed):**  
If you publish your report to Power BI service and create a *Publish to web* embed link (or an embed URL), paste the iframe URL below and it will render inside the app.

> **Note:** *Publish to web* makes the report public. If that is OK for your project demo, publish and paste the link here.

**Option B — Export Power BI visuals as PNG and show them here (private):**  
Export the key visuals as PNG (Power BI Desktop → Export → Export to PDF or Export visual as PNG), copy PNG files into this project folder (e.g., `powerbi_images/overall.png`) and they will be shown below automatically.
""")

# A: iframe embed - user pastes embed url
embed_url = st.text_input("If you have a Power BI Publish-to-web iframe URL, paste it here (the src URL). Leave blank if not using.")
if embed_url:
    st.markdown(f'<iframe width="1000" height="600" src="{embed_url}" frameborder="0" allowFullScreen="true"></iframe>', unsafe_allow_html=True)

# B: display images automatically from folder powerbi_images
if os.path.exists(IMG_FOLDER):
    imgs = [f for f in os.listdir(IMG_FOLDER) if f.lower().endswith(('.png','.jpg','.jpeg'))]
    if imgs:
        st.subheader("Embedded Power BI images (exported visuals)")
        cols = st.columns(2)
        for i, img in enumerate(imgs):
            col = cols[i % 2]
            # use_container_width instead of deprecated use_column_width
            col.image(os.path.join(IMG_FOLDER, img), caption=img, use_container_width=True)

st.write("Streams created. To run the app: `streamlit run app.py` in this folder.")

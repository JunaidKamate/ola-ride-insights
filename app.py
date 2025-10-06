# app.py
import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import os
from datetime import datetime
import altair as alt

st.set_page_config(page_title="Ola Ride Insights", layout="wide")

# ---------- PATHS ----------
EXCEL_PATH = "OLA_DataSet.xlsx"
CLEAN_CSV = "Cleaned_OLA_Data.csv"
SQLITE_DB = os.path.join(os.getcwd(), "ola.db")  # creates inside project folder

# ---------- Helper: load or create cleaned CSV ----------
@st.cache_data
def load_and_clean():
    # prefer cleaned CSV if present
    if os.path.exists(CLEAN_CSV):
        df = pd.read_csv(CLEAN_CSV, parse_dates=["Ride_Timestamp"], low_memory=False)
        return df
    # else read excel and clean
    if not os.path.exists(EXCEL_PATH):
        st.error(f"Neither cleaned CSV found at {CLEAN_CSV} nor Excel at {EXCEL_PATH}.")
        return None

    df = pd.read_excel(EXCEL_PATH, engine="openpyxl")
    # Basic standardization: make column names consistent
    df.columns = [c.strip() for c in df.columns]

    # Fix Date and Time -> Ride_Timestamp
    if "Date" in df.columns and "Time" in df.columns:
        # ensure Date is datetime
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        # convert Time -> string then to time
        df['Time'] = df['Time'].astype(str)
        # combine carefully
        df['Ride_Timestamp'] = pd.to_datetime(df['Date'].dt.strftime('%Y-%m-%d') + ' ' + df['Time'], errors='coerce')
    else:
        # try to fallback if Ride_Timestamp exists already
        if "Ride_Timestamp" in df.columns:
            df['Ride_Timestamp'] = pd.to_datetime(df['Ride_Timestamp'], errors='coerce')

    # Replace blank Payment_Method and Incomplete_Rides_Reason with labels
    if 'Payment_Method' in df.columns:
        df['Payment_Method'] = df['Payment_Method'].fillna('').astype(str).str.strip()
        df.loc[df['Payment_Method']=='', 'Payment_Method'] = 'Other'
    if 'Incomplete_Rides_Reason' in df.columns:
        df['Incomplete_Rides_Reason'] = df['Incomplete_Rides_Reason'].fillna('').astype(str).str.strip()
        df.loc[df['Incomplete_Rides_Reason']=='', 'Incomplete_Rides_Reason'] = 'Unknown Reason'

    # If Ride_Distance is not numeric, coerce
    if 'Ride_Distance' in df.columns:
        df['Ride_Distance'] = pd.to_numeric(df['Ride_Distance'], errors='coerce').fillna(0).astype(int)

    # Ensure ratings numeric
    for col in ['Driver_Ratings', 'Customer_Rating']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # If Booking_Value string -> numeric
    if 'Booking_Value' in df.columns:
        df['Booking_Value'] = pd.to_numeric(df['Booking_Value'], errors='coerce').fillna(0).astype(int)

    # If Incomplete_Rides exists as Yes/No, keep as is
    # Save cleaned CSV
    df.to_csv(CLEAN_CSV, index=False)
    return df

df = load_and_clean()
if df is None:
    st.stop()

# ---------- Create sqlite db and table ----------
conn = sqlite3.connect(SQLITE_DB, check_same_thread=False)
df.to_sql("ola_rides", conn, if_exists="replace", index=False)

st.title("Ola Ride Insights — Streamlit App")
st.caption("Interactive app to view SQL results, key metrics, and embed Power BI visuals (if published).")

# ---------- Run the 10 SQL queries and show results ----------
st.header("SQL Queries & Results (selected)")

queries = {
    "Query 1: All successful bookings": "SELECT * FROM ola_rides WHERE LOWER(Booking_Status) = 'success';",
    "Query 2: Avg ride distance per vehicle type": "SELECT Vehicle_Type, ROUND(AVG(CAST(Ride_Distance AS REAL)),3) AS Avg_Ride_Distance FROM ola_rides GROUP BY Vehicle_Type ORDER BY Avg_Ride_Distance DESC;",
    "Query 3: Total cancelled by customers": "SELECT COUNT(*) AS Total_Cancelled_By_Customer FROM ola_rides WHERE Canceled_Rides_by_Customer IS NOT NULL OR LOWER(Booking_Status) = 'cancelled by customer';",
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
    "Query 9: Total booking value of successful rides": "SELECT SUM(Booking_Value) AS Total_Revenue_Successful_Rides, COUNT(*) AS Total_Successful_Rides, ROUND(AVG(Booking_Value),2) AS Avg_Booking_Value FROM ola_rides WHERE LOWER(Booking_Status) = 'success';",
    "Query 10: All incomplete rides with reason": "SELECT Booking_ID, Ride_Timestamp, Booking_Status, Incomplete_Rides, Incomplete_Rides_Reason FROM ola_rides WHERE LOWER(Incomplete_Rides) = 'yes' OR Incomplete_Rides_Reason IS NOT NULL ORDER BY Ride_Timestamp;"
}

# Show a compact listing with an expander for each query
for title, q in queries.items():
    with st.expander(title):
        res = pd.read_sql_query(q, conn, parse_dates=['Ride_Timestamp'])
        st.write(f"Rows: {res.shape[0]}")
        st.dataframe(res.head(50), use_container_width=True)

# ---------- Simple dashboard-like visuals using Altair ----------
st.header("Quick Visuals derived from SQL results")

# 1) Ride volume over time (count per day)
df['Ride_Date'] = pd.to_datetime(df['Ride_Timestamp']).dt.date
rides_per_day = df.groupby('Ride_Date').size().reset_index(name='rides')
chart1 = alt.Chart(rides_per_day).mark_line(point=True).encode(
    x=alt.X('Ride_Date:T', title='Date'),
    y=alt.Y('rides:Q', title='Number of Rides')
).properties(height=250, width=800, title="Ride Volume Over Time")
st.altair_chart(chart1, use_container_width=True)

# 2) Booking status breakdown
status_counts = df['Booking_Status'].value_counts().reset_index()
status_counts.columns = ['Booking_Status','count']
chart2 = alt.Chart(status_counts).mark_bar().encode(
    x=alt.X('Booking_Status:N', sort='-y'),
    y='count:Q',
    color='Booking_Status:N'
).properties(height=250, width=400, title='Booking Status Breakdown')
st.altair_chart(chart2, use_container_width=True)

# ---------- Power BI embedding options ----------
st.subheader("Power BI visuals")
st.write("This section displays Power BI dashboards related to the project.")


# B: display images automatically from folder powerbi_images
img_folder = os.path.join(os.getcwd(), "powerbi_images")
if os.path.exists(img_folder):
    imgs = [f for f in os.listdir(img_folder) if f.lower().endswith(('.png','.jpg','.jpeg'))]
    if imgs:
        st.subheader("Embedded Power BI images")
        cols = st.columns(2)
        for i, img in enumerate(imgs):
            col = cols[i % 2]
            col.image(os.path.join(img_folder, img), caption=img, use_column_width=True)

st.write("Streams created. To run the app: `streamlit run app.py` in this folder.")


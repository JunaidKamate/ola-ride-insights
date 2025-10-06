# Ola Ride Insights

**Short description:**  
Ola Ride Insights — SQL, Power BI and Streamlit analytics on Ola ride data.

## Project overview
This project analyzes Ola ride-hailing data to extract operational and business insights. It includes:
- Data cleaning & preprocessing (Pandas)
- SQL queries (SQLite) to answer business questions
- Interactive visualizations (Power BI)
- A Streamlit app that combines SQL outputs, charts and exported Power BI visuals

## Repository contents
- `app.py` — Streamlit application (main)
- `Cleaned_OLA_Data.csv` — cleaned dataset used by the app
- `powerbi_images/` — exported Power BI visuals (PNGs)
- `requirements.txt` — Python dependencies
- `.gitignore` — excludes local DB / env files

## Quick start (run locally)
1. Clone the repo:
```bash
git clone https://github.com/<your-username>/ola-ride-insights.git
cd ola-ride-insights

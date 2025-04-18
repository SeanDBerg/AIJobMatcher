# adzuna_ranked_skills.py - Fetches ranked skills from Adzuna GB and saves to JSON
import requests
import json
from datetime import datetime

# === Configuration ===
ADZUNA_APP_ID = "your_app_id"
ADZUNA_API_KEY = "your_api_key"
COUNTRY = "gb"  # use 'gb' because 'us' does not support hiring-skills endpoint
DATE_FROM = "2025-01-01"
DATE_TO = datetime.now().strftime("%Y-%m-%d")
OUTPUT_FILE = "ranked_skills_gb.json"

# === Function ===
def fetch_ranked_skills(country: str, date_from: str, date_to: str, output_file: str):
    """Fetch ranked skills from Adzuna GB and store to a JSON file"""
    url = f"https://api.intelligence.adzuna.com/api/v1.1/{country}/reports/hiring-skills/"
    headers = {"Authorization": f"{ADZUNA_API_KEY}"}
    params = {
        "date_from": date_from,
        "date_to": date_to
    }

    try:
        print(f"📡 Fetching ranked skills from {date_from} to {date_to} for {country.upper()}")
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        skills_data = response.json()

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(skills_data, f, indent=2)
        print(f"✅ Ranked skills saved to {output_file}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching skill data: {e}")

# === Entry Point ===
if __name__ == "__main__":
    fetch_ranked_skills(COUNTRY, DATE_FROM, DATE_TO, OUTPUT_FILE)

# adzuna_categories_fetcher.py - Fetch and save Adzuna job categories for a country
import requests
import json
import os

# === Configuration ===
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")  # Fetching from secrets
ADZUNA_API_KEY = os.getenv("ADZUNA_API_KEY")  # Fetching from secrets
COUNTRY_CODE = "us"  # Example: "us" for United States
OUTPUT_FILE = "adzuna_categories.json"

# === Fetch categories ===
def fetch_adzuna_categories(app_id, app_key, country):
    """Fetch job categories from Adzuna API"""
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/categories"
    params = {"app_id": app_id, "app_key": app_key}

    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()["results"]
    else:
        raise Exception(f"Failed to fetch categories: {response.status_code} - {response.text}")

# === Save categories to file ===
def save_categories_to_file(categories, filepath):
    """Save category list to a JSON file"""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(categories, f, indent=2)
    print(f"Saved {len(categories)} categories to {filepath}")

# === Main ===
if __name__ == "__main__":
    categories = fetch_adzuna_categories(ADZUNA_APP_ID, ADZUNA_API_KEY, COUNTRY_CODE)
    save_categories_to_file(categories, OUTPUT_FILE)

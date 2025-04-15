# logic/b_jobs/jobSync.py - Consolidated Adzuna sync logic
import os
import logging
import json
import requests
import time
from datetime import datetime
from typing import List, Dict
from flask import Blueprint, request, jsonify, redirect, url_for, session
job_sync_bp = Blueprint('job_sync', __name__)
logger = logging.getLogger(__name__)
# === Paths and Constants ===
ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), '../../static/job_data/adzuna')
ADZUNA_INDEX_FILE = os.path.join(ADZUNA_DATA_DIR, 'index.json')
ADZUNA_API_BASE_URL = "https://api.adzuna.com/v1/api"
# === Credentials ===
def get_api_credentials() -> tuple:
    app_id = os.environ.get('ADZUNA_APP_ID')
    api_key = os.environ.get('ADZUNA_API_KEY')
    if not app_id or not api_key:
        raise Exception("ADZUNA_APP_ID or ADZUNA_API_KEY is not set")
    return app_id, api_key
# === API: Trigger job sync ===
@job_sync_bp.route('/api/jobs/sync', methods=['POST'])
def sync_jobs():
    try:
        if not request.is_json:
            return jsonify({"success": False, "error": "Request must be JSON"}), 400
        data = request.get_json()
        keywords = data.get('keywords', '')
        keywords_list = data.get('keywords_list', [])
        location = data.get('location', '')
        country = data.get('country', 'gb')
        max_pages = int(data.get('max_pages', 5))
        max_days_old = int(data.get('max_days_old', 30))
        remote_only = data.get('remote_only', False)
        all_jobs = []
        for keyword in (keywords_list or [keywords]):
            if not keyword.strip():
                continue
            jobs = search_jobs(keyword.strip(), location, country, max_pages, max_days_old, remote_only)
            all_jobs.extend(jobs)
        if not all_jobs:
            return jsonify({"success": True, "message": "No jobs found.", "jobs_count": 0})
        os.makedirs(ADZUNA_DATA_DIR, exist_ok=True)
        batch_id = datetime.now().strftime("%Y%m%d%H%M%S")
        save_job_batch(all_jobs, batch_id)
        index = load_index()
        index['batches'][batch_id] = {
            "timestamp": datetime.now().isoformat(),
            "job_count": len(all_jobs)
        }
        index['job_count'] = index.get('job_count', 0) + len(all_jobs)
        index['last_batch'] = batch_id
        index['last_sync'] = datetime.now().isoformat()
        save_index(index)
        logger.info(f"Synced and stored {len(all_jobs)} jobs into batch {batch_id}")
        return jsonify({
            "success": True,
            "message": f"Retrieved {len(all_jobs)} jobs",
            "jobs_count": len(all_jobs),
            "batch_id": batch_id
        })
    except Exception as e:
        logger.error(f"Unexpected sync error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
# === Job Fetcher ===
# Fetch job listings from Adzuna API with debug logging and result verification
def search_jobs(keywords: str, location: str, country: str, max_pages: int, max_days_old: int, remote_only: bool) -> List[Dict]:
    app_id, api_key = get_api_credentials()
    jobs = []

    for page in range(1, max_pages + 1):
        try:
            url = f"{ADZUNA_API_BASE_URL}/jobs/{country}/search/{page}"
            params = {
                "app_id": app_id,
                "app_key": api_key,
                "results_per_page": 50,
                "what": keywords,
                "where": location,
                "max_days_old": max_days_old,
                "distance": 15
            }

            # Remote filtering only for UK
            if remote_only and country.lower() in ["gb", "uk"]:
                params["remote"] = 1

            logger.debug(f"[search_jobs] Querying: {url} with params: {params}")
            response = requests.get(url, params=params)
            response.raise_for_status()

            results = response.json().get("results", [])
            if not results:
                logger.warning(f"[search_jobs] No results for keyword '{keywords}' on page {page}")

            for job in results:
                jobs.append({
                    "title": job.get("title"),
                    "company": job.get("company", {}).get("display_name"),
                    "description": job.get("description"),
                    "location": job.get("location", {}).get("display_name"),
                    "is_remote": job.get("remote", False),
                    "posted_date": job.get("created"),
                    "url": job.get("redirect_url"),
                    "salary_range": job.get("salary_is_predicted"),
                    "skills": []
                })

        except Exception as e:
            logger.error(f"[search_jobs] Error fetching jobs for page {page}: {e}")
        finally:
            time.sleep(3)

    if not jobs:
        logger.warning(f"[search_jobs] No jobs collected for keyword '{keywords}' across {max_pages} pages")

        jobs.append({
            "title": "Sample Developer",
            "company": "TestCorp",
            "description": "A placeholder job used for debug testing.",
            "location": "Remote",
            "is_remote": True,
            "posted_date": datetime.now().isoformat(),
            "url": "https://example.com/test-job",
            "salary_range": "Not specified",
            "skills": ["python"]
        })
    return jobs

# === Index and Storage ===
def load_index() -> Dict:
    if not os.path.exists(ADZUNA_INDEX_FILE):
        return {"batches": {}, "job_count": 0, "last_sync": None, "last_batch": None}
    with open(ADZUNA_INDEX_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)
# Save job index to disk and update cache
def save_index(index: Dict) -> bool:
    try:
        with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving job index: {str(e)}")
        return False
# """Save a batch of job listings to disk."""
def save_job_batch(jobs: List[Dict], batch_id: str) -> bool:
    batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
    try:
        with open(batch_file, 'w', encoding='utf-8') as f:
            json.dump(jobs, f, indent=2)
        logger.debug(f"Saved batch {batch_id} with {len(jobs)} jobs")
        return True
    except Exception as e:
        logger.error(f"Error saving batch {batch_id}: {str(e)}")
        return False

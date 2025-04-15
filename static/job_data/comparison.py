# """Save user settings for job sync and optionally trigger sync."""
@job_sync_bp.route('/save_settings', methods=['POST'])
def save_settings():
    for key in ["keywords", "location", "country", "remote_only"]:
        session.pop(key, None)
    try:
        job_sources = request.form.getlist('job_sources')
        keywords = request.form.get('keywords', '')
        keywords_list_data = request.form.get('keywordsListData', '[]')
        try:
            keywords_list = json.loads(keywords_list_data)
            session['keywords_list'] = keywords_list
        except Exception as e:
            logger.error(f"Error parsing keywords list: {str(e)}")
            keywords_list = []
        location = request.form.get('location', '')
        country = request.form.get('country', 'gb')
        remote_only = request.form.get('remote_only') == '1'
        sync_now = request.form.get('sync_now') == '1'
        session['job_search_keywords'] = keywords
        session['job_search_location'] = location
        session['job_search_country'] = country
        session['job_search_remote_only'] = '1' if remote_only else ''
        logger.info("Returning with redirect to %s", "index" if sync_now else "settings")
        logger.debug("Session keys at context generation: %s", list(session.keys()))
        return redirect(url_for('index' if sync_now else 'settings'))
    except Exception as e:
        logger.error(f"Error saving settings: {str(e)}")
        return redirect(url_for('settings'))
# """Configure Adzuna credentials in runtime environment."""
@job_sync_bp.route('/api/config/adzuna', methods=['POST'])
def config_adzuna():
    try:
        if not request.is_json:
            return jsonify({"success": False, "error": "Request must be JSON"}), 400
        data = request.json
        app_id = data.get('app_id')
        api_key = data.get('api_key')
        if app_id:
            os.environ['ADZUNA_APP_ID'] = app_id
            logger.info("Adzuna App ID configured")
        if api_key:
            os.environ['ADZUNA_API_KEY'] = api_key
            logger.info("Adzuna API Key configured")
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error configuring Adzuna API: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500










# Get parameters from request
data = request.json
keywords = data.get('keywords', '')
location = data.get('location', '')
country = data.get('country', 'gb')
max_pages = data.get('max_pages', 5)
max_days_old = data.get('max_days_old', 30)
remote_only = data.get('remote_only', False)

# Call search jobs function
results = search_jobs(
  keywords=keywords,
  location=location,
  country=country,
  max_days_old=max_days_old,
  page=1,
  results_per_page=50,
  full_time=None,
  permanent=None,
  category=None,
  distance=15
)


# jobSync.py - Handles syncing, storage, and indexing of Adzuna job data

# logic/b_jobs/jobSync.py - Consolidated Adzuna sync logic
import os
import logging
import json
import time
import requests
from datetime import datetime
from typing import List, Dict, Optional
from flask import Blueprint, request, jsonify, redirect, url_for, session

job_sync_bp = Blueprint('job_sync', __name__)
logger = logging.getLogger(__name__)

# === Paths and Constants ===
ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), '../../static/job_data/adzuna')
ADZUNA_INDEX_FILE = os.path.join(ADZUNA_DATA_DIR, 'index.json')
ADZUNA_API_BASE_URL = "https://api.adzuna.com/v1/api"

# === Utility Functions ===
def _get_api_credentials() -> Dict[str, str]:
    return {
        "app_id": os.environ.get("ADZUNA_APP_ID"),
        "app_key": os.environ.get("ADZUNA_API_KEY")
    }

def _load_index() -> Dict:
    if not os.path.exists(ADZUNA_INDEX_FILE):
        return {"batches": {}, "job_count": 0, "last_sync": None, "last_batch": None}
    with open(ADZUNA_INDEX_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def _save_index(index_data: Dict):
    with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, indent=2)

def _save_batch(batch_number: int, jobs: List[dict]):
    batch_path = os.path.join(ADZUNA_DATA_DIR, f"adzuna_batch_{batch_number}.json")
    with open(batch_path, 'w', encoding='utf-8') as f:
        json.dump(jobs, f, indent=2)

# === Public Routes ===
import os
import logging
import json
import time
import requests
from datetime import datetime
from typing import List, Dict, Optional
from flask import Blueprint, request, jsonify, redirect, url_for, session

job_sync_bp = Blueprint('job_sync', __name__)
logger = logging.getLogger(__name__)

# === Paths and Constants ===
ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), '../../static/job_data/adzuna')
ADZUNA_INDEX_FILE = os.path.join(ADZUNA_DATA_DIR, 'index.json')
ADZUNA_API_BASE_URL = "https://api.adzuna.com/v1/api"

# === Utility Functions ===
def _get_api_credentials() -> Dict[str, str]:
    return {
        "app_id": os.environ.get("ADZUNA_APP_ID"),
        "app_key": os.environ.get("ADZUNA_API_KEY")
    }

def _load_index() -> Dict:
    if not os.path.exists(ADZUNA_INDEX_FILE):
        return {"batches": {}, "job_count": 0, "last_sync": None, "last_batch": None}
    with open(ADZUNA_INDEX_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def _save_index(index_data: Dict):
    with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, indent=2)

def _save_batch(batch_number: int, jobs: List[dict]):
    batch_path = os.path.join(ADZUNA_DATA_DIR, f"adzuna_batch_{batch_number}.json")
    with open(batch_path, 'w', encoding='utf-8') as f:
        json.dump(jobs, f, indent=2)

# === Public Routes ===
@job_sync_bp.route('/api/jobs/sync', methods=['POST'])
def sync_jobs():
    try:
        if not request.is_json:
            return jsonify({"success": False, "error": "Request must be JSON"}), 400

        data = request.get_json()
        keywords = data.get('keywords', '')
        keywords_list = data.get('keywords_list', [])
        location = data.get('location', '')
        country = data.get('country', 'us')
        max_pages = data.get('max_pages', 5)
        max_days_old = data.get('max_days_old', 30)
        remote_only = data.get('remote_only', False)

        api = _get_api_credentials()
        if not api['app_id'] or not api['app_key']:
            return jsonify({"success": False, "error": "Missing Adzuna credentials"}), 403

        index_data = _load_index()
        last_batch = index_data.get("last_batch", 0)
        all_jobs = []
        keywords_to_run = keywords_list if keywords_list else [keywords] if keywords else []

        for keyword in keywords_to_run:
            for page in range(1, max_pages + 1):
                try:
                    params = {
                        "app_id": api['app_id'],
                        "app_key": api['app_key'],
                        "results_per_page": 50,
                        "what": keyword,
                        "where": location,
                        "max_days_old": max_days_old,
                        "distance": 15
                    }
                    if remote_only:
                        params['remote'] = 1

                    url = f"{ADZUNA_API_BASE_URL}/jobs/{country}/search/{page}"
                    response = requests.get(url, params=params)
                    response.raise_for_status()
                    payload = response.json()

                    results = payload.get("results", [])
                    if not results:
                        break

                    last_batch += 1
                    all_jobs.extend(results)
                    _save_batch(last_batch, results)
                    index_data['batches'][str(last_batch)] = {
                        "keyword": keyword,
                        "count": len(results),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    index_data['job_count'] += len(results)
                    index_data['last_batch'] = last_batch
                    time.sleep(3)

                except Exception as e:
                    logger.error(f"Error fetching jobs for keyword '{keyword}', page {page}: {str(e)}")
                    break

        index_data['last_sync'] = datetime.utcnow().isoformat()
        _save_index(index_data)

        logger.info(f"sync_jobs returning with {len(all_jobs)} jobs")
        return jsonify({
            "success": True,
            "message": f"Retrieved {len(all_jobs)} jobs",
            "jobs_count": len(all_jobs),
            "keywords_searched": keywords_to_run
        })

    except Exception as e:
        logger.error(f"Unexpected sync error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500




def sync_jobs_from_adzuna(
    keywords: Optional[str] = None,
    location: Optional[str] = None,
    country: str = "gb",
    max_pages: Optional[int] = None,
    max_days_old: int = 30,
    remote_only: bool = False
) -> Dict[str, Any]:
    """
    Sync jobs from Adzuna API, with pagination and a fixed delay between calls

    Args:
        keywords: Search keywords (optional)
        location: Location to search in (optional)
        country: Country code (default: "gb")
        max_pages: Maximum number of pages to fetch (default: None, fetch all)
        max_days_old: Maximum age of job listings in days (default: 30)

    Returns:
        dict: Results of the sync operation
    """
    try:
        call_delay = 3  # Fixed delay in seconds between API calls

        page = 1
        total_pages = 1
        total_count = 0
        new_jobs_count = 0
        pages_fetched = 0
        api_calls = 0
        start_time = time.time()

        while page <= total_pages and (max_pages is None or page <= max_pages):
            if call_delay > 0 and api_calls > 0:
                logger.info(f"Waiting {call_delay} seconds before next API call (fixed delay)")
                time.sleep(call_delay)

            api_calls += 1
            logger.info(f"Fetching page {page} of {total_pages if total_pages > 1 else 'unknown'}")

            try:
                jobs = search_jobs(
                    keywords=keywords,
                    location=location,
                    country=country,
                    page=page,
                    results_per_page=50,
                    max_days_old=max_days_old
                )

                if not jobs or len(jobs) == 0:
                    logger.info(f"No more jobs found on page {page}. Stopping pagination.")
                    break

                if page == 1 and hasattr(jobs, 'total_pages'):
                    total_pages = getattr(jobs, 'total_pages', 1)
                    total_count = getattr(jobs, 'total_count', 0)
                    logger.info(f"Found {total_count} jobs across {total_pages} pages")

                stored_count = _adzuna_storage.sync_jobs(
                    keywords=keywords,
                    location=location,
                    country=country,
                    max_days_old=max_days_old,
                    append=True
                )

                if isinstance(stored_count, int):
                    new_jobs_count += stored_count

                pages_fetched += 1
                page += 1

            except AdzunaAPIError as e:
                error_msg = f"Error fetching page {page}: {str(e)}"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "error": str(e),
                    "pages_fetched": pages_fetched,
                    "new_jobs": new_jobs_count,
                    "api_calls": api_calls
                }

            except Exception as e:
                error_msg = f"Unexpected error fetching page {page}: {str(e)}"
                logger.error(error_msg)
                return {
                    "status": "error",
                    "error": f"Unexpected error: {str(e)}",
                    "pages_fetched": pages_fetched,
                    "new_jobs": new_jobs_count,
                    "api_calls": api_calls
                }

        total_time = time.time() - start_time

        return {
            "status": "success",
            "pages_fetched": pages_fetched,
            "total_pages": total_pages,
            "new_jobs": new_jobs_count,
            "total_jobs": total_count,
            "api_calls": api_calls,
            "time_taken_seconds": round(total_time, 2),
            "message": f"Successfully fetched {pages_fetched} pages with {new_jobs_count} new jobs"
        }

    except Exception as e:
        error_msg = f"Error in sync_jobs_from_adzuna: {str(e)}"
        logger.error(error_msg)
        return {
            "status": "error",
            "error": str(e),
            "pages_fetched": 0,
            "new_jobs": 0,
            "api_calls": 0
        }
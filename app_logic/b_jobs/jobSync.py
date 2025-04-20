# jobSync.py - Syncs jobs from Adzuna API and stores them in batch files
import os
import json
import uuid
import time
import logging
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
import requests
from flask import Blueprint, request, jsonify, session
from logging.handlers import RotatingFileHandler
# === Adzuna API Constants ===
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
ADZUNA_DATA_DIR = os.path.join(PROJECT_ROOT, 'static', 'job_data', 'adzuna')
ADZUNA_INDEX_FILE = os.path.join(ADZUNA_DATA_DIR, 'index.json')
ADZUNA_API_BASE_URL = "https://api.adzuna.com/v1/api"
logger = logging.getLogger("job_sync")
# Setup logging
log_file_path = os.path.join(PROJECT_ROOT, "job_sync.log")
file_handler = RotatingFileHandler(log_file_path, maxBytes=1_000_000, backupCount=3)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s-%(name)s: [%(funcName)s] %(message)s'))
file_handler.setLevel(logging.INFO)
logger.addHandler(file_handler)
job_sync_bp = Blueprint('job_sync', __name__, url_prefix='/api/jobs')
# === Adzuna API Utilities ===
# Custom exception for Adzuna API errors
class AdzunaAPIError(Exception):
    pass
# Get Adzuna API credentials from environment variables
def get_api_credentials():
    app_id = os.environ.get('ADZUNA_APP_ID')
    api_key = os.environ.get('ADZUNA_API_KEY')
    if not app_id or not api_key:
        raise AdzunaAPIError("Missing Adzuna API credentials in environment variables")
    return app_id, api_key
# === Job Model for Adzuna Sync ===
class Job:
    """Class representing a job listing (self-contained in jobSync.py)"""
    def __init__(
        self,
        title: str,
        company: str,
        description: str,
        location: str,
        posted_date: Optional[str] = None,
        url: str = "",
        skills: Optional[List[str]] = None,
        salary_range: Optional[str] = None,
        is_remote: bool = False,
        matched_keywords: Optional[List[str]] = None
    ):
        self.title = title
        self.company = company
        self.description = description
        self.location = location
        self.posted_date = posted_date or datetime.now().isoformat()
        self.url = url
        self.skills = skills or []
        self.salary_range = salary_range or ""
        self.is_remote = is_remote
        self.matched_keywords = matched_keywords or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "company": self.company,
            "description": self.description,
            "location": self.location,
            "posted_date": self.posted_date,
            "url": self.url,
            "skills": self.skills,
            "salary_range": self.salary_range,
            "is_remote": self.is_remote,
            "matched_keywords": self.matched_keywords
        }

# Search for jobs using the Adzuna API
def search_jobs(
    keywords: Optional[List[str]] = None,
    location: Optional[str] = None,
    country: str = "gb",
    distance: int = 30,
    max_days_old: int = 30,
    page: int = 1,
    results_per_page: int = 50,
    category: Optional[str] = None,
    full_time: Optional[bool] = None,
    permanent: Optional[bool] = None
) -> Tuple[List[Job], int]:
    app_id, api_key = get_api_credentials()
    url = f"{ADZUNA_API_BASE_URL}/jobs/{country}/search/{page}"
    params = {
        "app_id": app_id,
        "app_key": api_key,
        "results_per_page": results_per_page,
        "max_days_old": max_days_old
    }
    logger.debug(f"Adzuna API Request: {url} with params: {params}")
    # If remote, requires remote keywords in search
    if keywords:
        remote_keywords = {"remote"}
        required_remotes = [kw for kw in keywords if kw in remote_keywords]
        job_keywords = [kw for kw in keywords if kw not in remote_keywords]
        # Remote keywords: Adzuna interprets space-separated terms with implicit OR
        if required_remotes:
            params["what"] = " ".join(required_remotes)
        # Title keywords: Adzuna interprets space-separated terms with implicit OR
        if job_keywords:
            params["what_or"] = " ".join(job_keywords)

    logger.debug(f"Search params: {params}")
    if location:
        params["where"] = location
    if distance:
        params["distance"] = distance
    if category:
        params["category"] = category
    if full_time is not None:
        params["full_time"] = int(full_time)
    if permanent is not None:
        params["permanent"] = int(permanent)
    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            raise AdzunaAPIError(f"Adzuna API error: {response.status_code} - {response.text}")
        data = response.json()
        results = parse_adzuna_results(data, page)
        total_pages = (data.get("count", 0) // results_per_page) + 1
        return results, total_pages
    except requests.exceptions.Timeout:
        raise AdzunaAPIError("Adzuna API request timed out")
    except requests.exceptions.RequestException as e:
        raise AdzunaAPIError(f"Request error: {str(e)}")
# Processes the raw Adzuna API response and converts it to a list of Job objects.
def parse_adzuna_results(data: Dict, page: int) -> List[Job]:
    results = []
    for item in data.get("results", []):
        try:
            job = Job(
                title=item.get("title", "Unknown"),
                company=item.get("company", {}).get("display_name", "Unknown Company"),
                description=item.get("description", ""),
                location=item.get("location", {}).get("display_name", ""),
                posted_date=item.get("created", datetime.now().isoformat()),
                url=item.get("redirect_url", ""),
                skills=[],
                salary_range=format_salary(item.get("salary_min"), item.get("salary_max"))
            )
            results.append(job)
        except Exception as e:
            logger.warning(f"Skipping job result due to error: {str(e)}")
    return results
# Converts raw numeric salary data into a readable range string, like "£40,000 - £60,000"
def format_salary(min_salary, max_salary):
    if min_salary and max_salary:
        return f"\u00a3{min_salary:,.0f} - \u00a3{max_salary:,.0f}"
    elif min_salary:
        return f"\u00a3{min_salary:,.0f}+"
    elif max_salary:
        return f"Up to \u00a3{max_salary:,.0f}"
    return None
# === Index and Batch Handling ===
def _load_index() -> Dict:
    if os.path.exists(ADZUNA_INDEX_FILE):
        try:
            with open(ADZUNA_INDEX_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load index: {str(e)}")
    return {"batches": {}, "job_count": 0, "last_sync": None, "last_batch": None}
# 
def _save_index(index: Dict) -> None:
    try:
        with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save index: {str(e)}")
#
def _save_batch(jobs: List[Dict], batch_id: str) -> bool:
    try:
        os.makedirs(ADZUNA_DATA_DIR, exist_ok=True)
        batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
        with open(batch_file, 'w', encoding='utf-8') as f:
            json.dump(jobs, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save batch {batch_id}: {str(e)}")
        logger.debug(f"Batch save failed for ID {batch_id}, data length: {len(jobs)}")
        return False
# 
def _load_demo_jobs(count=8) -> List[Dict]:
    jobs = []
    try:
        for filename in os.listdir(ADZUNA_DATA_DIR):
            if filename.startswith("batch_") and filename.endswith(".json"):
                with open(os.path.join(ADZUNA_DATA_DIR, filename), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for job in data:
                        job_copy = job.copy()
                        job_copy["posted_date"] = (
                            datetime.now() - timedelta(days=random.randint(0, 9))
                        ).isoformat()
                        job_copy["match_percentage"] = random.choice([65, 70, 75, 80, 85, 90])
                        jobs.append(job_copy)
        random.shuffle(jobs)
        return jobs[:count]
    except Exception as e:
        logger.error(f"[demo_sync] Failed to load demo jobs: {str(e)}")
        return []
# === Core Sync Function ===
# Pull jobs from Adzuna API and store them as batch
def sync_jobs_from_adzuna(
    keywords: Optional[List[str]] = None,
    location: Optional[str] = None,
    country: str = "us",
    max_pages: Optional[int] = None,
    max_days_old: int = 1,
    category: Optional[str] = None  # ← add this
) -> Dict[str, Any]:
    try:
        get_api_credentials()
    except AdzunaAPIError as e:
        return {"status": "error", "error": str(e)}
    # === Normalize Keywords & Remote Behavior ===
    keywords = list(set(filter(None, [kw.strip().lower() for kw in (keywords or [])])))
    keyword_counts = {kw: 0 for kw in keywords}
    location = location.strip().lower() if location else ""
    if location == "remote":
        logger.info("🌐 Interpreting 'remote' location as remote-style job filter")
        location = ""  # Avoid passing 'remote' as a geographic location
        remote_keywords = ["remote", "work from home", "telecommute", "virtual", "distributed"]
        keywords.extend(remote_keywords)
        keywords = list(set(keywords))
    logger.info(f"🔍 Starting job sync: location={location}, keywords={keywords}")
    dedupe_index = set()
    index = _load_index()
    for batch in index.get("batches", {}).values():
        for job in batch.get("jobs", []):
            if isinstance(job, dict) and "url" in job:
                dedupe_index.add(job["url"])
    exclusion_keywords = [
        "nurse", "rn", "lpn", "med/surg", "icu", "surgical", "hospital", "auditor",
        "classroom", "teacher", "clinical", "rehab", "pharmacy", "therapist", "case manager"
    ]
    # === Exclusion Keyword Filter -- TO BE MADE CONFIGURABLE ===
    page = 1
    total_fetched = 0
    total_jobs_kept = 0
    all_jobs: List[Job] = []
    seen_urls = set()
    total_pages = 1
    start_time = time.time()
    while page <= total_pages and (max_pages is None or page <= max_pages):
        try:
            result, total_pages = search_jobs(
                keywords=keywords,
                location=location,
                country=country,
                page=page,
                max_days_old=max_days_old,
                results_per_page=50,
                category=category
            )
            logger.info(f"📄 Fetched page {page}/{total_pages}, jobs returned: {len(result)}")
            page += 1
            total_fetched += len(result)
            for job in result:
                if job.url in dedupe_index or job.url in seen_urls:
                    continue
                seen_urls.add(job.url)
                fulltext = f"{job.title.lower()} {job.description.lower()}"
                # Skip if exclusion keywords found
                if any(ex_kw in fulltext for ex_kw in exclusion_keywords):
                    logger.debug(f"⛔ Excluding by EXCLUSION_KEYWORDS: {job.title}")
                    continue
                matched = [kw for kw in keyword_counts if kw in fulltext]
                if not matched:
                    logger.debug(f"⛔ Excluding job with 0 keyword matches: {job.title}")
                    continue
                for kw in matched:
                    keyword_counts[kw] += 1
                job.matched_keywords = matched
                all_jobs.append(job)
            time.sleep(3)
        except AdzunaAPIError as e:
            logger.error(f"Adzuna error: {str(e)}")
            break
        except Exception as e:
            logger.error(f"Unexpected error on page {page}: {str(e)}")
            break
    if not all_jobs:
        logger.warning("❌ No new jobs retrieved from Adzuna.")
        return {"status": "error", "error": "No new jobs retrieved from Adzuna"}
    job_dicts = []
    for job in all_jobs:
        try:
            job_dict = job.to_dict()
            job_dict["matched_keywords"] = getattr(job, "matched_keywords", [])
            job_dicts.append(job_dict)
        except Exception as e:
            logger.error(f"❌ Failed to convert job to dict: {str(e)} -- {repr(job)}")
    batch_id = str(uuid.uuid4())
    saved = _save_batch(job_dicts, batch_id)
    if not saved:
        return {"status": "error", "error": "Failed to write job batch"}
    index["batches"][batch_id] = {
        "id": batch_id,
        "timestamp": datetime.now().isoformat(),
        "keywords": sorted(keywords),
        "location": location,
        "country": country,
        "job_count": len(job_dicts),
        "max_days_old": max_days_old,
        "match_summary": dict(sorted(keyword_counts.items(), key=lambda item: item[1], reverse=True)),
        "jobs": job_dicts
    }
    index["job_count"] += len(job_dicts)
    index["last_sync"] = datetime.now().isoformat()
    index["last_batch"] = batch_id
    _save_index(index)
    logger.info(f"✅ Sync complete: {len(job_dicts)} new jobs kept (fetched {total_fetched} total) in {round(time.time() - start_time, 2)}s")
    logger.info(f"🧠 Keyword match summary: {json.dumps(dict(sorted(keyword_counts.items(), key=lambda item: item[1], reverse=True)), indent=2)}")
    logger.info(f"🗂️ Batch ID: {batch_id}")
    return {
        "status": "success",
        "pages_fetched": page - 1,
        "total_jobs": len(job_dicts),
        "batch_id": batch_id,
        "time_taken_seconds": round(time.time() - start_time, 2),
        "match_summary": dict(sorted(keyword_counts.items(), key=lambda item: item[1], reverse=True))
    }
# === API Endpoint Sync Route ===
@job_sync_bp.route('/sync', methods=['POST'])
def sync_jobs_api():
    if not request.is_json:
        return jsonify({"success": False, "error": "Request must be JSON"}), 400

    try:
        data = request.get_json()
        logger.debug(f"Received sync request payload: {json.dumps(data, indent=2)}")
        raw_keywords = data.get('keywords', '')
        keywords_list = data.get('keywords_list', [])
        # Start with any typed-in single keywords
        if raw_keywords:
            keywords_list.append(raw_keywords)
        # Clean and deduplicate all keywords
        keywords_list = list(set(filter(None, [kw.strip() for kw in keywords_list])))
        location = data.get('location', '')
        country = data.get('country', 'us')
        max_pages = data.get('max_pages', None)
        max_days_old = data.get('max_days_old', 1)
        category = data.get('category', None)
        # Check if demo mode is enabled to load demo jobs instead of real sync
        if session.get("demo", False):
            # Simulate demo job sync
            jobs = _load_demo_jobs(count=random.randint(6, 9))
            results = {
                "status": "success",
                "pages_fetched": 1,
                "total_jobs": len(jobs),
                "batch_id": "demo-mode",
                "time_taken_seconds": round(random.uniform(1.0, 2.5), 2),
                "match_summary": {kw: random.randint(1, 3) for kw in keywords_list}
            }
        else:
            results = sync_jobs_from_adzuna(
                keywords=keywords_list,
                location=location,
                country=country,
                max_pages=max_pages,
                max_days_old=max_days_old,
                category=category
            )
        if results.get('status') != 'success':
            return jsonify({
                "success": False,
                "error": results.get("error", "Unknown error during sync")
            }), 500

        return jsonify({
            "success": True,
            "results": results,
            "message": f"Successfully synced {results.get('total_jobs', 0)} jobs " +
                       f"across {results.get('pages_fetched', 0)} pages"
        })

    except Exception as e:
        logger.error(f"Unexpected sync error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
# API endpoint to save keyword list persistently in index.json
@job_sync_bp.route('/save_keywords_list', methods=['POST'])
def save_keywords_list():
    if not request.is_json:
        return jsonify({"success": False, "error": "Request must be JSON"}), 400

    # ✅ Check for demo mode BEFORE modifying the index
    if session.get("demo", False):
        data = request.get_json()
        keywords_list = data.get("keywords_list", [])
        return jsonify({
            "success": True,
            "message": "Settings saved (demo mode only, will reset after session).",
            "count": len(keywords_list)
        })

    try:
        data = request.get_json()
        keywords_list = data.get('keywords_list', [])

        if not isinstance(keywords_list, list):
            return jsonify({"success": False, "error": "Invalid keyword list"}), 400

        index = _load_index()
        index["saved_keywords"] = list(set(filter(None, [kw.strip() for kw in keywords_list])))
        _save_index(index)

        logger.info(f"✅ Saved keyword list with {len(index['saved_keywords'])} keywords to index")
        return jsonify({
            "success": True,
            "message": "Keywords list saved successfully",
            "count": len(index["saved_keywords"])
        })

    except Exception as e:
        logger.error(f"❌ Error saving keywords list: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Exception while saving keyword list",
            "details": str(e)
        }), 500


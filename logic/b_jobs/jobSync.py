# jobSync.py - Syncs jobs from Adzuna API and stores them in batch files
import os
import json
import uuid
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from adzuna_api import search_jobs, get_api_credentials, AdzunaAPIError
from models import Job
logger = logging.getLogger(__name__)
# Storage paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
ADZUNA_DATA_DIR = os.path.join(PROJECT_ROOT, 'static', 'job_data', 'adzuna')
ADZUNA_INDEX_FILE = os.path.join(ADZUNA_DATA_DIR, 'index.json')

# === Index and Batch Handling ===
def _load_index() -> Dict:
    if os.path.exists(ADZUNA_INDEX_FILE):
        try:
            with open(ADZUNA_INDEX_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load index: {str(e)}")
    return {
        "batches": {},
        "job_count": 0,
        "last_sync": None,
        "last_batch": None
    }
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
# === Core Sync Function ===
# Pull jobs from Adzuna API and store them as batch
def sync_jobs_from_adzuna(
    keywords: Optional[str] = None,
    location: Optional[str] = None,
    country: str = "gb",
    max_pages: Optional[int] = None,
    max_days_old: int = 30,
    remote_only: bool = False
) -> Dict[str, Any]:
    try:
        get_api_credentials()  # Validate credentials
    except AdzunaAPIError as e:
        return {"status": "error", "error": str(e)}
    page = 1
    total_fetched = 0
    total_pages = 1
    all_jobs: List[Job] = []
    start_time = time.time()
    while page <= total_pages and (max_pages is None or page <= max_pages):
        try:
            result = search_jobs(
                keywords=keywords,
                location=location,
                country=country,
                page=page,
                max_days_old=max_days_old,
                results_per_page=50
            )
            if not result or len(result) == 0:
                break
            if page == 1 and hasattr(result, "total_pages"):
                total_pages = result.total_pages
            all_jobs.extend(result)
            page += 1
            total_fetched += len(result)
            time.sleep(3)
        except AdzunaAPIError as e:
            logger.error(f"Adzuna error: {str(e)}")
            break
        except Exception as e:
            logger.error(f"Unexpected error on page {page}: {str(e)}")
            break
    if not all_jobs:
        return {"status": "error", "error": "No jobs retrieved from Adzuna"}
    job_dicts = []
    for job in all_jobs:
        try:
            job_dicts.append(job.to_dict())
        except Exception as e:
            logger.error(f"Failed to convert job to dict: {str(e)} -- {repr(job)}")
    batch_id = str(uuid.uuid4())
    saved = _save_batch(job_dicts, batch_id)
    if not saved:
        return {"status": "error", "error": "Failed to write job batch"}
    index = _load_index()
    index["batches"][batch_id] = {
        "id": batch_id,
        "timestamp": datetime.now().isoformat(),
        "keywords": keywords,
        "location": location,
        "country": country,
        "job_count": len(job_dicts),
        "max_days_old": max_days_old
    }
    index["job_count"] += len(job_dicts)
    index["last_sync"] = datetime.now().isoformat()
    index["last_batch"] = batch_id
    _save_index(index)
    return {
        "status": "success",
        "pages_fetched": page - 1,
        "total_jobs": total_fetched,
        "batch_id": batch_id,
        "time_taken_seconds": round(time.time() - start_time, 2)
    }
#
def get_adzuna_jobs(days: int = 30) -> List[Job]:
    """
    Load jobs from all batches within X days
    """
    jobs: List[Job] = []
    now = datetime.now()
    index = _load_index()
    for batch_id, meta in index.get("batches", {}).items():
        try:
            timestamp = datetime.fromisoformat(meta["timestamp"])
            if (now - timestamp).days > days:
                continue
            batch_path = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
            if os.path.exists(batch_path):
                with open(batch_path, 'r', encoding='utf-8') as f:
                    for job_dict in json.load(f):
                        jobs.append(Job(**job_dict))
        except Exception as e:
            logger.warning(f"Skipping batch {batch_id}: {str(e)}")
    return jobs
#
def get_adzuna_storage_status() -> Dict[str, Any]:
    """
    Retrieve current Adzuna job storage status
    """
    index = _load_index()
    return {
        "job_count": index.get("job_count", 0),
        "last_sync": index.get("last_sync"),
        "last_batch": index.get("last_batch"),
        "batches": index.get("batches", {})
    }

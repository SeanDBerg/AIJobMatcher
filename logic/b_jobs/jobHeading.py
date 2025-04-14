# logic/b_jobs/jobHeading.py - Isolated API routes for the Job Header controls (stats, cleanup, sync)
import os
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any
from flask import Blueprint, request, jsonify
from logic.b_jobs.jobUtils import save_index, get_index, ADZUNA_DATA_DIR
job_heading_bp = Blueprint('job_heading', __name__)
logger = logging.getLogger(__name__)
# Local copy of the Adzuna data directory path used for batch file storage
ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), '../../static', 'job_data', 'adzuna')
ADZUNA_INDEX_FILE = os.path.join(ADZUNA_DATA_DIR, 'index.json')
_index_cache = None
_index_cache_timestamp = None
INDEX_CACHE_TTL_SECONDS = 10
# === API Routes ===
# Remove job batches older than max_age days.
@job_heading_bp.route('/api/adzuna/cleanup', methods=['POST'])
def cleanup_old_jobs():
    try:
        data = request.get_json()
        max_age = data.get('max_age', 90)
        removed = cleanup_old_jobs_internal(max_age_days=max_age)
        return jsonify({"success": True, "jobs_removed": removed})
    except Exception as e:
        logger.error(f"Error cleaning up old jobs: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
# Return job storage summary status.
@job_heading_bp.route('/api/adzuna/status', methods=['GET'])
def get_adzuna_status():
    try:
        status = get_adzuna_status_internal()
        return jsonify({"success": True, "status": status})
    except Exception as e:
        logger.error(f"Error getting Adzuna status: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
# Remove job batches from disk and index that are older than the max_age_days threshold.
def cleanup_old_jobs_internal(max_age_days: int = 10) -> int:
    try:
        index = get_index(force_refresh=True)
        cutoff_date = (datetime.now() - timedelta(days=max_age_days)).isoformat()

        batches_to_remove = []
        job_count_removed = 0

        for batch_id, batch_info in index["batches"].items():
            if batch_info["timestamp"] < cutoff_date:
                batches_to_remove.append(batch_id)
                job_count_removed += batch_info["job_count"]

        for batch_id in batches_to_remove:
            batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
            if os.path.exists(batch_file):
                os.remove(batch_file)
            del index["batches"][batch_id]

        index["job_count"] = max(0, index["job_count"] - job_count_removed)

        if index["last_batch"] in batches_to_remove:
            index["last_batch"] = None
            if index["batches"]:
                index["last_batch"] = max(index["batches"].items(), key=lambda x: x[1]["timestamp"])[0]
        save_index(index)
        logger.info(f"Removed {job_count_removed} jobs from {len(batches_to_remove)} batches")
        return job_count_removed
    except Exception as e:
        logger.error(f"Error cleaning up old jobs: {str(e)}")
        return 0
# Generate a summary status dictionary from the job index.
def get_adzuna_status_internal() -> Dict[str, Any]:
    index = get_index()
    batch_count = len(index["batches"])
    job_count = index["job_count"]
    last_sync = index["last_sync"]
    last_batch = index["last_batch"]
    status = {
        "batch_count": batch_count,
        "total_jobs": job_count,
        "last_sync": last_sync,
        "last_batch": last_batch,
        "batches": index["batches"]
    }
    logger.debug(f"Storage status: {job_count} jobs in {batch_count} batches")
    return status
# === Index Management ===
# Load the Adzuna job index from disk with optional caching. Used for batch tracking, job count, last sync, and display.
def get_index(force_refresh=False) -> Dict:
    global _index_cache, _index_cache_timestamp
    if not force_refresh and _index_cache and _index_cache_timestamp:
        age = (datetime.now() - _index_cache_timestamp).total_seconds()
        if age < INDEX_CACHE_TTL_SECONDS:
            return _index_cache
    try:
        if not os.path.exists(ADZUNA_INDEX_FILE):
            logger.warning("Index file not found. Creating empty index.")
            _index_cache = {"batches": {}, "job_count": 0, "last_sync": None, "last_batch": None}
            save_index(_index_cache)
            _index_cache_timestamp = datetime.now()
            return _index_cache
        with open(ADZUNA_INDEX_FILE, 'r', encoding='utf-8') as f:
            index = json.load(f)
        index.setdefault("batches", {})
        index.setdefault("job_count", 0)
        index.setdefault("last_sync", None)
        index.setdefault("last_batch", None)
        _index_cache = index
        _index_cache_timestamp = datetime.now()
        return index
    except Exception as e:
        logger.error(f"Error loading job index: {str(e)}")
        _index_cache = {"batches": {}, "job_count": 0, "last_sync": None, "last_batch": None}
        _index_cache_timestamp = datetime.now()
        return _index_cache
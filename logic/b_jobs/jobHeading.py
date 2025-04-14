# logic/b_jobs/jobHeading.py - Isolated API routes for the Job Header controls (stats, cleanup, sync)
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from flask import Blueprint, request, jsonify
job_heading_bp = Blueprint('job_heading', __name__)
logger = logging.getLogger(__name__)

# Local copy of the Adzuna data directory path used for batch file storage
ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), 'static', 'job_data', 'adzuna')

@job_heading_bp.route('/api/adzuna/cleanup', methods=['POST'])
def cleanup_old_jobs():
    """Remove job batches older than max_age days."""
    try:
        data = request.get_json()
        max_age = data.get('max_age', 90)
        removed = cleanup_old_jobs_internal(max_age_days=max_age)
        return jsonify({"success": True, "jobs_removed": removed})
    except Exception as e:
        logger.error(f"Error cleaning up old jobs: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@job_heading_bp.route('/api/adzuna/status', methods=['GET'])
def get_adzuna_status():
    """Return job storage summary status."""
    try:
        status = get_adzuna_status_internal()
        return jsonify({"success": True, "status": status})
    except Exception as e:
        logger.error(f"Error getting Adzuna status: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

def cleanup_old_jobs_internal(max_age_days: int = 90) -> int:
    """Remove job batches from disk and index that are older than the max_age_days threshold."""
    try:
        index = job_manager.get_index(force_refresh=True)
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

        job_manager.save_index(index)
        job_manager._jobs_cache = None
        logger.info(f"Removed {job_count_removed} jobs from {len(batches_to_remove)} batches")
        return job_count_removed

    except Exception as e:
        logger.error(f"Error cleaning up old jobs: {str(e)}")
        return 0

def get_adzuna_status_internal() -> Dict[str, Any]:
    """Generate a summary status dictionary from the job index."""
    index = job_manager.get_index()

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

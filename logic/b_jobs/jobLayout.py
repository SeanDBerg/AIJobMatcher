# logic/b_jobs/jobLayout.py - Blueprint and logic for rendering job and batch data tables
import logging
import os
import json
from typing import List, Dict, Optional
from flask import Blueprint, jsonify, request
from logic.a_resume.resumeHistory import get_all_resumes
from logic.b_jobs.jobMatch import get_all_jobs
from logic.b_jobs.jobSync import save_index
from logic.b_jobs.jobHeading import get_index
logger = logging.getLogger(__name__)
# Define the blueprint
layout_bp = Blueprint("layout_bp", __name__)
# === Constants ===
ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), '../../static/job_data/adzuna')
ADZUNA_INDEX_FILE = os.path.join(ADZUNA_DATA_DIR, 'index.json')
# === Job Retrieval ===
# Load a batch of jobs from disk
def _load_job_batch(batch_id: str) -> List[Dict]:
    batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
    if not os.path.exists(batch_file):
        logger.warning(f"Batch file {batch_id} not found")
        return []
    try:
        with open(batch_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading batch {batch_id}: {str(e)}")
        return []
# Delete a specific batch of jobs
def delete_batch(batch_id):
    try:
        index = get_index(force_refresh=True)
        if batch_id not in index["batches"]:
            return False
        job_count = index["batches"][batch_id]["job_count"]
        batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
        if os.path.exists(batch_file):
            os.remove(batch_file)
        del index["batches"][batch_id]
        index["job_count"] = max(0, index["job_count"] - job_count)
        if index["last_batch"] == batch_id:
            index["last_batch"] = None
            if index["batches"]:
                index["last_batch"] = max(index["batches"].items(), key=lambda x: x[1]["timestamp"])[0]
        with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error deleting batch {batch_id}: {str(e)}")
        return False
# === Table Context Generation ===
# 
def _filter_remote_jobs(jobs):
    return [job for job in jobs if job.is_remote]
# Format salary range as a human-readable string
def format_salary_range(min_salary, max_salary) -> Optional[str]:
    if min_salary is None and max_salary is None:
        return None
    if min_salary and max_salary:
        if min_salary == max_salary:
            return f"£{min_salary:,.0f}"
        return f"£{min_salary:,.0f} - £{max_salary:,.0f}"
    elif min_salary:
        return f"£{min_salary:,.0f}+"
    elif max_salary:
        return f"Up to £{max_salary:,.0f}"
    return None
# Public function to assemble the context for index.html
def generate_table_context(session):
    try:
        keywords = session.get("job_search_keywords", "")
        location = session.get("job_search_location", "")
        country = session.get("job_search_country", "us")
        remote_only = session.get("job_search_remote_only", "") == "1"
        jobs = get_all_jobs(force_refresh=True)
        remote_jobs = _filter_remote_jobs(jobs)
        resume_id = session.get("resume_id")
        # Compute match percentages using centralized logic
        from logic.b_jobs.jobMatch import get_match_percentages
        match_map = {}
        if resume_id:
            match_map = get_match_percentages(resume_id, jobs)
            logger.debug("Match percentages applied to %d jobs", len(match_map))
        else:
            logger.warning("No resume ID provided, match percentages will be 0")
        for job in jobs:
            job.match_percentage = match_map.get(job.url, 0)
        jobs_dict = {i: job.to_dict() for i, job in enumerate(jobs)}
        remote_dict = {i: job.to_dict() for i, job in enumerate(remote_jobs)}
        return {
            "jobs": jobs_dict,
            "remote_jobs_list": remote_dict,
            "stored_resumes": get_all_resumes(),
            "total_jobs": len(jobs),
            "next_sync": "Manual sync only",
            "keywords": keywords,
            "location": location,
            "country": country,
            "remote_only": remote_only,
            "keywords_list": session.get("keywords_list", [])
        }
    except Exception as e:
        logger.error(f"Error generating table context: {str(e)}")
        return {}
# === API Routes ===
# API endpoint to get job listings
@layout_bp.route("/api/jobs", methods=["GET"])
def get_jobs():
    try:
        days = request.args.get("days", 30, type=int)
        jobs = get_all_jobs(force_refresh=True)
        logger.debug("Retrieved %d jobs for API", len(jobs))
        return jsonify({"success": True, "jobs": [job.to_dict() for job in jobs]})
    except Exception as e:
        logger.error(f"Error fetching jobs: {str(e)}")
        return jsonify({"success": False, "error": str(e)})
# API endpoint to delete a specific batch
@layout_bp.route("/api/adzuna/batch/<batch_id>", methods=["DELETE"])
def delete_adzuna_batch(batch_id):
    try:
        index = get_index(force_refresh=True)
        if batch_id not in index["batches"]:
            logger.warning(f"Batch {batch_id} not found or could not be deleted")
            return jsonify({"success": False, "error": f"Batch {batch_id} not found or could not be deleted"}), 404
        job_count = index["batches"][batch_id]["job_count"]
        batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
        if os.path.exists(batch_file):
            os.remove(batch_file)
        del index["batches"][batch_id]
        index["job_count"] = max(0, index["job_count"] - job_count)
        if index["last_batch"] == batch_id:
            index["last_batch"] = None
            if index["batches"]:
                index["last_batch"] = max(index["batches"].items(), key=lambda x: x[1]["timestamp"])[0]
        save_index(index)
        logger.debug(f"Successfully deleted batch {batch_id}")
        return jsonify({"success": True, "batch_id": batch_id, "status": index})
    except Exception as e:
        logger.error(f"Error deleting batch {batch_id}: {str(e)}")
        return jsonify({"success": False, "error": f"Error deleting batch {batch_id}: {str(e)}"}), 500
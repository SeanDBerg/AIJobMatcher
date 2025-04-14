# logic/b_jobs/jobSync.py - Consolidated Adzuna sync logic
import os
import logging
import json
from datetime import datetime
from typing import List, Dict
from flask import Blueprint, request, jsonify, redirect, url_for, session
job_sync_bp = Blueprint('job_sync', __name__)
logger = logging.getLogger(__name__)
# === Paths and Constants ===
ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), '../../static/job_data/adzuna')
ADZUNA_INDEX_FILE = os.path.join(ADZUNA_DATA_DIR, 'index.json')
ADZUNA_API_BASE_URL = "https://api.adzuna.com/v1/api"
# === Public Routes ===
# """Sync jobs from Adzuna using keywords or keyword list."""
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
        total_jobs_found = 0
        all_jobs = []
        return jsonify({
            "success": True,
            "message": f"Retrieved {total_jobs_found} jobs",
            "jobs_count": total_jobs_found,
            "keywords_searched": keywords_list if keywords_list else [keywords] if keywords else []
        })
    except Exception as e:
        logger.error(f"Unexpected sync error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
# """Save user settings for job sync and optionally trigger sync."""
@job_sync_bp.route('/save_settings', methods=['POST'])
def save_settings():
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
# """API endpoint to get jobs from storage"""
@job_sync_bp.route('/api/adzuna/jobs', methods=['GET'])
def get_adzuna_jobs_endpoint():
    try:
        jobs = get_all_jobs(force_refresh=True)
        return jsonify({
            "success": True,
            "jobs": [job.to_dict() for job in jobs],
            "count": len(jobs)
        })
    except Exception as e:
        logger.error(f"Error getting jobs: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
# === Internal Utilities ===
# Save job index to disk and update cache
def save_index(index: Dict) -> bool:
    global _index_cache, _index_cache_timestamp
    try:
        with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2)
        _index_cache = index
        _index_cache_timestamp = datetime.now()
        logger.debug("Saved job index to disk")
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
# """Create an empty job index file"""
def _create_empty_index(self) -> None:
    empty_index = {"batches": {}, "job_count": 0, "last_sync": None, "last_batch": None}
    try:
        with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(empty_index, f, indent=2)
        logger.debug("Created new empty index file")
    except Exception as e:
        logger.error(f"Error creating index file: {str(e)}")
# Retrieve Adzuna API credentials from environment variables
def get_api_credentials() -> tuple:
    app_id = os.environ.get('ADZUNA_APP_ID')
    api_key = os.environ.get('ADZUNA_API_KEY')
    if not app_id or not api_key:
        raise Exception("ADZUNA_APP_ID or ADZUNA_API_KEY is not set")
    return app_id, api_key
# Check if Adzuna API credentials are properly configured
def check_api_status() -> bool:
    try:
        get_api_credentials()
        return True
    except Exception:
        return False
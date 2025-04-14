# jobSync.py - Consolidated Adzuna sync logic (syncSection.html handler)
import os
import logging
import json
from typing import List
from flask import Blueprint, request, jsonify, redirect, url_for, session
from job_manager import JobManager, AdzunaAPIError
from logic.b_jobs.jobMatch import Job
job_sync_bp = Blueprint('job_sync', __name__)
logger = logging.getLogger(__name__)
job_manager = JobManager()

ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), 'static', 'job_data', 'adzuna')
# === Public Routes ===
@job_sync_bp.route('/api/jobs/sync', methods=['POST'])
def sync_jobs():
    """Sync jobs from Adzuna using keywords or keyword list."""
    try:
        if not request.is_json:
            return jsonify({"success": False, "error": "Request must be JSON"}), 400
        data = request.get_json()
        keywords = data.get('keywords', '')
        keywords_list = data.get('keywords_list', [])
        location = data.get('location', '')
        country = data.get('country', 'gb')
        max_days_old = data.get('max_days_old', 30)
        total_jobs_found = 0
        all_jobs = []
        if keywords_list and isinstance(keywords_list, list):
            for keyword in keywords_list:
                if not keyword:
                    continue
                try:
                    jobs = search_jobs_internal(keyword, location, country, max_days_old)
                    if jobs:
                        total_jobs_found += len(jobs)
                        all_jobs.extend(jobs)
                except Exception as keyword_error:
                    logger.error(f"Error syncing keyword '{keyword}': {str(keyword_error)}")

        if (not keywords_list or not all_jobs) and keywords:
            try:
                jobs = search_jobs_internal(keywords, location, country, max_days_old)
                if jobs:
                    total_jobs_found += len(jobs)
                    all_jobs.extend(jobs)
            except Exception as main_keyword_error:
                if not all_jobs:
                    raise main_keyword_error
        return jsonify({
            "success": True,
            "message": f"Retrieved {total_jobs_found} jobs",
            "jobs_count": total_jobs_found,
            "keywords_searched": keywords_list if keywords_list else [keywords] if keywords else []
        })
    except AdzunaAPIError as e:
        logger.error(f"API error during sync: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"Unexpected sync error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
"""Save user settings for job sync and optionally trigger sync."""
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
        max_days_old = int(request.form.get('max_days_old', 30))
        remote_only = request.form.get('remote_only') == '1'
        search_terms = request.form.getlist('search_terms')
        sync_now = request.form.get('sync_now') == '1'
        session['job_search_keywords'] = keywords
        session['job_search_location'] = location
        session['job_search_country'] = country
        session['job_search_max_days_old'] = str(max_days_old)
        session['job_search_remote_only'] = '1' if remote_only else ''
        if sync_now:
            logger.info("save_settings returning with redirect to index for sync")
            return redirect(url_for('index'))
        else:
            logger.info("save_settings returning with redirect to settings")
            return redirect(url_for('settings'))
    except Exception as e:
        logger.error(f"Error saving settings: {str(e)}")
        return redirect(url_for('settings'))
"""Configure Adzuna credentials in runtime environment."""
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
"""API endpoint to get jobs from storage"""
@job_sync_bp.route('/api/adzuna/jobs', methods=['GET'])
def get_adzuna_jobs_endpoint():
  try:
    days = request.args.get('days', 30, type=int)
    # Get jobs using JobManager
    jobs = job_manager.get_recent_jobs(days=days)
    # Convert to dictionaries for JSON response
    job_dicts = [job.to_dict() for job in jobs]
    logger.debug("Retrieved %d jobs for API", len(jobs))
    return jsonify({"success": True, "jobs": job_dicts, "count": len(job_dicts)})
  except Exception as e:
    logger.error(f"Error getting jobs: {str(e)}")
    return _handle_api_exception(e, "getting jobs")
# === Internal Utilities ===
"""Wrapper for job_manager.search_jobs to isolate and reuse the search logic."""
def search_jobs_internal(keywords=None, location=None, country="gb", max_days_old=30) -> List[Job]:
    all_jobs = []
    if keywords:
        jobs, _, _, _ = job_manager.search_jobs(
            keywords=keywords,
            location=location,
            country=country,
            max_days_old=max_days_old,
            page=1,
            results_per_page=50
        )
        all_jobs.extend(jobs)

    return all_jobs
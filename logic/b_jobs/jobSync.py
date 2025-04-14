# logic/b_jobs/jobSync.py - Consolidated Adzuna sync logic
import os
import logging
import json
from datetime import datetime
from typing import List, Dict
from flask import Blueprint, request, jsonify, redirect, url_for, session
from logic.b_jobs.jobUtils import save_index, get_index, ADZUNA_DATA_DIR
# Import this after jobUtils to avoid circular dependencies
from logic.b_jobs.jobMatch import get_all_jobs
job_sync_bp = Blueprint('job_sync', __name__)
logger = logging.getLogger(__name__)
# === Paths and Constants ===
# Using ADZUNA_DATA_DIR from jobUtils
ADZUNA_API_BASE_URL = "https://api.adzuna.com/v1/api"
# === Public Routes ===
# """Sync jobs from Adzuna using keywords or keyword list."""
@job_sync_bp.route('/api/jobs/sync', methods=['POST'])
def sync_jobs():
    try:
        if not request.is_json:
            return jsonify({"success": False, "error": "Request must be JSON"}), 400
        
        # Get request parameters
        data = request.get_json()
        keywords = data.get('keywords', '')
        keywords_list = data.get('keywords_list', [])
        location = data.get('location', '')
        country = data.get('country', 'gb')
        max_pages = int(data.get('max_pages', 1))
        remote_only = data.get('remote_only', False)
        
        # Make sure Adzuna credentials are available
        if not check_api_status():
            return jsonify({"success": False, "error": "Adzuna API credentials not configured"}), 400
            
        app_id, api_key = get_api_credentials()
        
        # Prepare search parameters
        search_terms = keywords_list if keywords_list else [keywords] if keywords else []
        if not search_terms:
            return jsonify({"success": False, "error": "No search keywords provided"}), 400
            
        # Load existing index
        import uuid
        import requests
        from datetime import datetime
        
        try:
            index = get_index(force_refresh=True)
        except Exception as e:
            logger.error(f"Error loading index: {str(e)}")
            index = {"batches": {}, "job_count": 0, "last_sync": None, "last_batch": None}
        
        # Create a new batch ID
        batch_id = str(uuid.uuid4())
        all_jobs = []
        total_jobs_found = 0
        
        # Process each keyword
        for keyword in search_terms:
            if not keyword.strip():
                continue
                
            # Build API request
            params = {
                "app_id": app_id,
                "app_key": api_key,
                "results_per_page": 20,
                "what": keyword
            }
            
            if location:
                params["where"] = location
                
            # Add remote filter if requested
            if remote_only:
                params["remote"] = 1
            
            # Request jobs for this keyword
            for page in range(1, max_pages + 1):
                params["page"] = page
                logger.info(f"Requesting page {page} for keyword '{keyword}'")
                
                try:
                    url = f"{ADZUNA_API_BASE_URL}/jobs/{country}/search/{page}"
                    response = requests.get(url, params=params)
                    
                    if response.status_code != 200:
                        logger.error(f"API error: {response.status_code} - {response.text}")
                        continue
                        
                    data = response.json()
                    jobs = data.get("results", [])
                    
                    # Process each job
                    for job in jobs:
                        # Extract job details
                        job_data = {
                            "title": job.get("title", "No Title"),
                            "company": job.get("company", {}).get("display_name", "Unknown Company"),
                            "description": job.get("description", "No description available"),
                            "location": job.get("location", {}).get("display_name", "Unknown Location"),
                            "is_remote": "remote" in job.get("title", "").lower() or "remote" in job.get("description", "").lower(),
                            "posted_date": job.get("created", datetime.now().isoformat()),
                            "url": job.get("redirect_url", ""),
                            "salary_range": "",
                            "skills": []
                        }
                        
                        # Process salary info if available
                        if "salary_min" in job and "salary_max" in job:
                            job_data["salary_range"] = f"{job.get('salary_min', 0):,.0f} - {job.get('salary_max', 0):,.0f} {job.get('salary_currency', 'GBP')}/year"
                        
                        all_jobs.append(job_data)
                        total_jobs_found += 1
                    
                except Exception as e:
                    logger.error(f"Error processing page {page} for {keyword}: {str(e)}")
                    continue
        
        # Save the jobs batch
        if all_jobs:
            if save_job_batch(all_jobs, batch_id):
                # Update the index
                timestamp = datetime.now().isoformat()
                index["batches"][batch_id] = {
                    "timestamp": timestamp,
                    "job_count": len(all_jobs),
                    "keywords": ", ".join(search_terms),
                    "location": location
                }
                index["job_count"] = sum(batch["job_count"] for batch in index["batches"].values())
                index["last_sync"] = timestamp
                index["last_batch"] = batch_id
                
                # Save updated index
                save_index(index)
                
                logger.info(f"Successfully synced {total_jobs_found} jobs in batch {batch_id}")
            else:
                logger.error(f"Failed to save batch {batch_id}")
        
        return jsonify({
            "success": True,
            "message": f"Retrieved {total_jobs_found} jobs",
            "jobs_count": total_jobs_found,
            "keywords_searched": search_terms,
            "batch_id": batch_id if all_jobs else None
        })
    except Exception as e:
        logger.error(f"Unexpected sync error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
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
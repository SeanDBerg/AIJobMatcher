# app.py
import os
import logging
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session, send_from_directory
import numpy as np
from datetime import datetime
from matching_engine import generate_dual_embeddings
from job_manager import JobManager
from client.resume.uploadResume import upload_resume_bp
from client.resume.resumeHistory import resume_history_bp, get_all_resumes
from resume_storage import resume_storage
from templates.jobs.jobHeading import job_heading_bp

job_manager = JobManager()
# Set up logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s-%(name)s: [%(funcName)s] %(message)s")
logger = logging.getLogger(__name__)

ADZUNA_SCRAPER_AVAILABLE = True
# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev_secret_key")
app.register_blueprint(upload_resume_bp)
app.register_blueprint(resume_history_bp)
app.register_blueprint(job_heading_bp)
#"""Log exception and return standardized error response"""
def _handle_api_exception(e, operation_name):
  logger.error(f"Error {operation_name}: {str(e)}")
  logger.info("_handle_api_exception returning with e=%s, operation_name=%s", e, operation_name)
  return jsonify({"success": False, "error": str(e)}), 500
# Route for the main page
@app.route('/')
def index():
  keywords = request.args.get('keywords', '')
  location = request.args.get('location', '')
  country = request.args.get('country', 'us')
  max_days_old = request.args.get('max_days_old', '1')
  remote_only = request.args.get('remote_only', '') == '1'
  
  # Initialize with empty keywords list
  keywords_list = []
  
  # Try to get keywords list from session if available
  if 'keywords_list' in session:
    try:
      keywords_list = session['keywords_list']
    except Exception as e:
      logger.error(f"Error loading keywords list from session: {str(e)}")
  
  status = {
    'keywords_list': keywords_list
  }
  
  if ADZUNA_SCRAPER_AVAILABLE:
    
    # Get jobs using the JobManager
    jobs = job_manager.get_recent_jobs(days=30)
    
    # Filter recent jobs (last 7 days)
    recent_jobs_list = []
    for job in jobs:
      if job.posted_date:
        try:
          job_date = datetime.fromisoformat(job.posted_date.split("T")[0]) if isinstance(job.posted_date, str) else job.posted_date
          if (datetime.now() - job_date).days <= 7:
            recent_jobs_list.append(job)
        except Exception:
          pass
          
    # Get remote jobs
    remote_jobs_list = [job for job in jobs if job.is_remote]
    
    # Get resume and embeddings if available
    resume_id = session.get('resume_id')
    resume_embeddings = None
    if resume_id:
      active_resume = resume_storage.get_resume(resume_id)
      if active_resume and "metadata" in active_resume:
        metadata = active_resume["metadata"]
        resume_embeddings = {"narrative": np.array(metadata["embedding_narrative"]), "skills": np.array(metadata["embedding_skills"])}
    
    # Calculate matching percentages if resume available
    if resume_embeddings:
      matches = job_manager.match_jobs_to_resume(resume_embeddings, jobs)
      job_id_to_match = {match.job.url: match for match in matches}
      for job in jobs:
        match = job_id_to_match.get(job.url)
        job.match_percentage = int(match.similarity_score * 100) if match else 0
    else:
      for job in jobs:
        job.match_percentage = 0  # Ensure numeric zero
    
    # Convert to dictionaries for template
    jobs_dict = {i: job.to_dict() for i, job in enumerate(jobs)}
    recent_jobs_dict = {i: job.to_dict() for i, job in enumerate(recent_jobs_list)}
    remote_jobs_dict = {i: job.to_dict() for i, job in enumerate(remote_jobs_list)}
    
    # Update status for template
    status.update({
      "jobs": jobs_dict,
      "recent_jobs_list": recent_jobs_dict,
      "remote_jobs_list": remote_jobs_dict,
      "total_jobs": len(jobs),
      "recent_jobs": len(recent_jobs_list),
      "next_sync": "Manual sync only",  # No scheduler, manual sync only
      "keywords": keywords,
      "location": location,
      "country": country,
      "max_days_old": max_days_old,
      "remote_only": remote_only
    })
    
  # Add stored resumes to status
  status["stored_resumes"] = get_all_resumes()
  
  logger.debug("Rendering index with %d jobs", status.get("total_jobs", 0))
  return render_template('index.html', **status)
#"""Serve resume files"""
@app.route('/resume_files/<resume_id>/<filename>')
def resume_files(resume_id, filename):
  # Get the path from the resume_storage module
  from resume_storage import RESUME_DIR
  logger.info("resume_files returning with resume_id=%s, filename=%s", resume_id, filename)
  return send_from_directory(RESUME_DIR, f"{resume_id}_{filename}")
#"""Save user settings for job search"""
@app.route('/save_settings', methods=['POST'])
def save_settings():
  try:
    # Extract settings from form
    job_sources = request.form.getlist('job_sources')
    keywords = request.form.get('keywords', '')
    keywords_list_data = request.form.get('keywordsListData', '[]')
    try:
      import json
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
    # Check if "Sync Now" was requested
    sync_now = request.form.get('sync_now') == '1'
    flash('Settings saved successfully!', 'success')
    # Redirect to job tracker page with sync form pre-filled if "Sync Now" was selected
    if sync_now:
      # Store search parameters in session for persistence
      session['job_search_keywords'] = keywords
      session['job_search_location'] = location
      session['job_search_country'] = country
      session['job_search_max_days_old'] = str(max_days_old)
      session['job_search_remote_only'] = '1' if remote_only else ''
      logger.info("save_settings returning with no parameters")

      return redirect(url_for('index'))
    else:
      logger.info("save_settings returning with no parameters")
      return redirect(url_for('settings'))

  except Exception as e:
    logger.error(f"Error saving settings: {str(e)}")
    flash(f'Error saving settings: {str(e)}', 'danger')
    logger.info("save_settings returning with no parameters")
    return redirect(url_for('settings'))

@app.route('/api/jobs', methods=['GET'])
def get_jobs():
  """API endpoint to get job listings"""
  try:
    days = request.args.get('days', 30, type=int)
    jobs = job_manager.get_recent_jobs(days=days)
    logger.debug("Retrieved %d jobs for API", len(jobs))
    return jsonify({"success": True, "jobs": [job.to_dict() for job in jobs]})
  except Exception as e:
    logger.error(f"Error fetching jobs: {str(e)}")
    return jsonify({"success": False, "error": str(e)})
@app.route('/api/match-jobs', methods=['POST'])
def match_jobs():
  """API endpoint to match resume to jobs"""
  try:
    # Check if we have a resume_id in the request
    if request.is_json:
      data = request.json
      resume_id = data.get('resume_id')
      resume_text = data.get('resume_text', '')
      filters = data.get('filters', {})
      # If resume_id is provided, get resume from storage
      if resume_id:
        try:
          resume_metadata = resume_storage.get_resume(resume_id)
          if not resume_metadata:
            logger.info("match_jobs returning with no parameters")
            return jsonify({"success": False, "error": f"Resume with ID {resume_id} not found"}), 404
          resume_text = resume_storage.get_resume_content(resume_id) or ''
          # Get embedding from metadata if available
          if resume_metadata.get('embedding_narrative') and resume_metadata.get('embedding_skills'):
            resume_embedding_narrative = np.array(resume_metadata['embedding_narrative'])
            resume_embedding_skills = np.array(resume_metadata['embedding_skills'])
          else:
            embeddings = generate_dual_embeddings(resume_text)
            resume_embedding_narrative = embeddings['narrative']
            resume_embedding_skills = embeddings['skills']
          # Use filters from metadata if not provided in request
          if not filters and resume_metadata.get('filters'):
            filters = resume_metadata['filters']
        except Exception as e:
          logger.error(f"Error retrieving resume {resume_id}: {str(e)}")
          logger.info("match_jobs returning with no parameters")
          return jsonify({"success": False, "error": f"Error retrieving resume: {str(e)}"}), 500
      else:
        # Use resume_text from request
        if not resume_text or len(resume_text.strip()) < 50:
          logger.info("match_jobs returning with no parameters")
          return jsonify({"success": False, "error": "Resume text is too short. Please provide a complete resume."}), 400
        # Generate embedding
        try:
          embeddings = generate_dual_embeddings(resume_text)
          resume_embedding_narrative = embeddings['narrative']
          resume_embedding_skills = embeddings['skills']
        except Exception as e:
          logger.error(f"Error generating embedding: {str(e)}")
          logger.info("match_jobs returning with no parameters")
          return jsonify({"success": False, "error": f"Error analyzing resume content: {str(e)}"}), 500
    else:
      logger.info("match_jobs returning with no parameters")
      return jsonify({"success": False, "error": "Request must be JSON"}), 400
    # Get job data using the JobManager
    try:
      days = data.get('days', 30)
      jobs = job_manager.get_recent_jobs(days=days)
      if not jobs:
        logger.warning("No job data available for matching")
        return jsonify({"success": False, "error": "No job data available to match against"}), 500
    except Exception as e:
      logger.error(f"Error retrieving job data: {str(e)}")
      return jsonify({"success": False, "error": f"Error retrieving job data: {str(e)}"}), 500
      
    # Find matching jobs using the JobManager
    try:
      resume_embeddings = {"narrative": resume_embedding_narrative, "skills": resume_embedding_skills}
      matching_jobs = job_manager.match_jobs_to_resume(resume_embeddings, jobs, filters, resume_text=resume_text)
      if not matching_jobs:
        logger.info("match_jobs returning with no parameters")
        return jsonify({"success": True, "matches": {}, "message": "No matching jobs found based on your filters. Try adjusting your search criteria."})
    except Exception as e:
      logger.error(f"Error matching jobs: {str(e)}")
      logger.info("match_jobs returning with no parameters")
      return jsonify({"success": False, "error": f"Error matching jobs: {str(e)}"}), 500
    # Create a dictionary with job IDs as keys and match percentages as values
    # This is the format needed by our JavaScript function
    matches_dict = {}
    for job_match in matching_jobs:
      job_id = job_match.job.id if hasattr(job_match.job, 'id') else str(id(job_match.job))
      match_percentage = int(job_match.similarity_score * 100)
      matches_dict[job_id] = match_percentage
    logger.info("match_jobs returning with no parameters")
    return jsonify({"success": True, "matches": matches_dict, "count": len(matching_jobs), "resume_id": resume_id if resume_id else None})
  except Exception as e:
    logger.error(f"Unexpected error in API: {str(e)}")
    logger.info("match_jobs returning with no parameters")
    return jsonify({"success": False, "error": f"Unexpected error: {str(e)}"}), 500
# API endpoint to configure Adzuna API credentials
@app.route('/api/config/adzuna', methods=['POST'])
def config_adzuna():
  try:
    if not request.is_json:
      logger.info("config_adzuna returning with no parameters")
      return jsonify({"success": False, "error": "Request must be JSON"}), 400
    data = request.json
    app_id = data.get('app_id')
    api_key = data.get('api_key')
    # Here we would normally save these to environment variables or a secure storage
    # For this example, we'll just set them in the current process environment
    if app_id:
      os.environ['ADZUNA_APP_ID'] = app_id
      logger.info("Adzuna App ID configured")
    if api_key:
      os.environ['ADZUNA_API_KEY'] = api_key
      logger.info("Adzuna API Key configured")
    logger.info("config_adzuna returning with no parameters")
    return jsonify({"success": True})
  except Exception as e:
    logger.error(f"Error configuring Adzuna API: {str(e)}")
    logger.info("config_adzuna returning with no parameters")
    return jsonify({"success": False, "error": str(e)}), 500    
"""API endpoint to get jobs from storage"""
@app.route('/api/adzuna/jobs', methods=['GET'])
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

@app.route('/api/adzuna/batch/<batch_id>', methods=['DELETE'])
def delete_adzuna_batch(batch_id):
  """API endpoint to delete a specific batch"""
  try:
    # Use JobManager to delete the batch
    success = job_manager.delete_batch(batch_id)
    
    if not success:
      logger.warning(f"Batch {batch_id} not found or could not be deleted")
      return jsonify({
        "success": False, 
        "error": f"Batch {batch_id} not found or could not be deleted"
      }), 404
    
    # Get updated status after deletion
    status = job_manager.get_storage_status()
    
    logger.debug(f"Successfully deleted batch {batch_id}")
    return jsonify({
      "success": True, 
      "batch_id": batch_id,
      "status": status
    })
  except Exception as e:
    logger.error(f"Error deleting batch {batch_id}: {str(e)}")
    return _handle_api_exception(e, f"deleting batch {batch_id}")
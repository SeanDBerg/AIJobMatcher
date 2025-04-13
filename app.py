# app.py
import os
import logging
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session, send_from_directory
from werkzeug.utils import secure_filename
import tempfile
import numpy as np
from datetime import datetime
from resume_parser import parse_resume, FileParsingError
from embedding_generator import generate_dual_embeddings
from job_data import get_job_data
from matching_engine import find_matching_jobs
from resume_storage import resume_storage
from adzuna_scraper import (sync_jobs_from_adzuna, get_adzuna_jobs, import_adzuna_jobs_to_main_storage, cleanup_old_adzuna_jobs, get_adzuna_storage_status)
# Set up logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s-%(name)s: [%(funcName)s] %(message)s")
logger = logging.getLogger(__name__)

ADZUNA_SCRAPER_AVAILABLE = True
# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev_secret_key")
#"""Log exception and return standardized error response"""
def _handle_api_exception(e, operation_name):
  logger.error(f"Error {operation_name}: {str(e)}")
  logger.info("_handle_api_exception returning with e=%s, operation_name=%s", e, operation_name)
  return jsonify({"success": False, "error": str(e)}), 500
#"""Check if request is JSON and return error response if not"""
def _require_json_request():
  if not request.is_json:
    logger.info("_require_json_request returning with no parameters")
    return jsonify({"success": False, "error": "Request must be JSON"}), 400
  logger.info("_require_json_request returning with no parameters")
  return None
# Route for the main page
@app.route('/')
def index():
  keywords = request.args.get('keywords', '')
  location = request.args.get('location', '')
  country = request.args.get('country', 'gb')
  max_days_old = request.args.get('max_days_old', '30')
  remote_only = request.args.get('remote_only', '') == '1'
  logger.debug(f"Job tracker parameters: keywords='{keywords}', location='{location}', country='{country}', max_days_old='{max_days_old}', remote_only='{remote_only}'")
  status = {}
  if ADZUNA_SCRAPER_AVAILABLE:
    storage_status = get_adzuna_storage_status()
    jobs = get_adzuna_jobs(days=30)
    recent_jobs_list = []
    for job in jobs:
      if job.posted_date:
        try:
          job_date = datetime.fromisoformat(job.posted_date.split("T")[0]) if isinstance(job.posted_date, str) else job.posted_date
          if (datetime.now() - job_date).days <= 7:
            recent_jobs_list.append(job)
        except Exception:
          pass
    remote_jobs_list = [job for job in jobs if job.is_remote]
    resume_id = session.get('resume_id')
    resume_embeddings = None
    if resume_id:
      active_resume = resume_storage.get_resume(resume_id)
      if active_resume and "metadata" in active_resume:
        metadata = active_resume["metadata"]
        resume_embeddings = {"narrative": np.array(metadata["embedding_narrative"]), "skills": np.array(metadata["embedding_skills"])}
    if resume_embeddings:
      matches = find_matching_jobs(resume_embeddings, jobs)
      for match in matches:
        match.job.match_percentage = int(match.similarity_score * 100)
    else:
      for job in jobs:
        job.match_percentage = None
    jobs_dict = {i: job.to_dict() for i, job in enumerate(jobs)}
    recent_jobs_dict = {i: job.to_dict() for i, job in enumerate(recent_jobs_list)}
    remote_jobs_dict = {i: job.to_dict() for i, job in enumerate(remote_jobs_list)}
    status.update({
      "storage_status": storage_status,
      "jobs": jobs_dict,
      "recent_jobs_list": recent_jobs_dict,
      "remote_jobs_list": remote_jobs_dict,
      "total_jobs": len(jobs),
      "recent_jobs": len(recent_jobs_list),
      "last_sync": storage_status.get("last_sync", "Never"),
      "next_sync": "Manual sync only", # No scheduler, manual sync only
      "keywords": keywords,
      "location": location,
      "country": country,
      "max_days_old": max_days_old,
      "remote_only": remote_only
    })
  status["stored_resumes"] = resume_storage.get_all_resumes()
  logger.info("index returning with no parameters")
  return render_template('index.html', **status)
#"""Serve resume files"""
@app.route('/resume_files/<resume_id>/<filename>')
def resume_files(resume_id, filename):
  # Get the path from the resume_storage module
  from resume_storage import RESUME_DIR
  logger.info("resume_files returning with resume_id=%s, filename=%s", resume_id, filename)
  return send_from_directory(RESUME_DIR, f"{resume_id}_{filename}")
#"""Delete a stored resume"""
@app.route('/delete_resume/<resume_id>', methods=['POST'])
def delete_resume(resume_id):
  try:
    if resume_storage.delete_resume(resume_id):
      flash('Resume deleted successfully', 'success')
    else:
      flash('Resume not found or could not be deleted', 'danger')
  except Exception as e:
    logger.error(f"Error deleting resume: {str(e)}")
    flash(f'Error deleting resume: {str(e)}', 'danger')
  logger.info("delete_resume returning with resume_id=%s", resume_id)
  return redirect(url_for('index'))
#"""Save user settings for job search"""
@app.route('/save_settings', methods=['POST'])
def save_settings():
  try:
    # Extract settings from form
    job_sources = request.form.getlist('job_sources')
    keywords = request.form.get('keywords', '')
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
@app.route('/upload_resume', methods=['POST'])
def upload_resume():
  ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}
  # Check if a file was uploaded
  if 'resume' not in request.files:
    flash('No file part', 'danger')
    logger.info("upload_resume returning with no parameters")
    return redirect(url_for('index'))

  file = request.files['resume']

  # If user doesn't select a file
  if file.filename == '':
    flash('No file selected', 'danger')
    logger.info("upload_resume returning with no parameters")
    return redirect(url_for('index'))

  # Check if the file is allowed
  def allowed_file(filename):
    logger.info("allowed_file returning with filename=%s", filename)
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

  if file and allowed_file(file.filename):
    # Save file temporarily
    filename = secure_filename(file.filename)
    TEMP_FOLDER = tempfile.gettempdir()
    filepath = os.path.join(TEMP_FOLDER, filename)
    file.save(filepath)

    try:
      # Parse resume
      logger.debug(f"Parsing resume from {filepath}")
      try:
        resume_text = parse_resume(filepath)
      except FileParsingError as e:
        logger.error(f"Resume parsing error: {str(e)}")
        flash(f'Resume parsing error: {str(e)}', 'danger')
        return redirect(url_for('index'))
      except Exception as e:
        logger.error(f"Unexpected error parsing resume: {str(e)}")
        flash(f'Error parsing resume: {str(e)}', 'danger')
        return redirect(url_for('index'))

      # Generate embedding
      logger.debug("Generating embedding for resume")
      try:
        embeddings = generate_dual_embeddings(resume_text)
        resume_embedding_narrative = embeddings["narrative"]
        resume_embedding_skills = embeddings["skills"]
      except Exception as e:
        logger.error(f"Error generating embedding: {str(e)}")
        flash(f'Error analyzing resume content: {str(e)}', 'danger')
        return redirect(url_for('index'))

      # Get filters from form
      filters = {'remote': request.form.get('remote', '') == 'on', 'location': request.form.get('location', ''), 'keywords': request.form.get('keywords', '')}

      # Store resume in persistent storage
      try:
        # Create metadata with embedding (convert NumPy array to list for JSON serialization)
        metadata = {"embedding_narrative": resume_embedding_narrative.tolist(), "embedding_skills": resume_embedding_skills.tolist(), "filters": filters}

        # Store in persistent storage
        resume_id = resume_storage.store_resume(temp_filepath=filepath, filename=filename, content=resume_text, metadata=metadata)

        flash(f'Resume "{filename}" successfully uploaded and stored', 'success')

        # Check if user wants to find matching jobs immediately
        find_matches = request.form.get('find_matches', '') == 'on'

        if find_matches:
          # Get all job data
          try:
            jobs = get_job_data()
            if not jobs:
              flash('No job data available to match against', 'warning')
              return redirect(url_for('index', resume_id=resume_id))
          except Exception as e:
            logger.error(f"Error retrieving job data: {str(e)}")
            flash(f'Error retrieving job data: {str(e)}', 'danger')
            return redirect(url_for('index', resume_id=resume_id))

          # Find matching jobs
          try:
            resume_embeddings = {"narrative": resume_embedding_narrative, "skills": resume_embedding_skills}
            matching_jobs = find_matching_jobs(resume_embeddings, jobs, filters, resume_text=resume_text)

            # Store resume text in session for display on results page
            session['resume_text'] = resume_text
            session['resume_id'] = resume_id

            # Clean up temp file
            if os.path.exists(filepath):
              os.remove(filepath)

            return render_template('results.html', jobs=matching_jobs, resume_text=resume_text, resume_id=resume_id)
          except Exception as e:
            logger.error(f"Error matching jobs: {str(e)}")
            flash(f'Error matching jobs: {str(e)}', 'danger')
            return redirect(url_for('index', resume_id=resume_id))
        else:
          # Clean up temp file
          if os.path.exists(filepath):
            os.remove(filepath)

          # Redirect to resume manager with this resume active
          return redirect(url_for('index', resume_id=resume_id))

      except Exception as e:
        logger.error(f"Error storing resume: {str(e)}")
        flash(f'Error storing resume: {str(e)}', 'danger')

        # Clean up temp file
        if os.path.exists(filepath):
          os.remove(filepath)

        return redirect(url_for('index'))

    except Exception as e:
      # Catch-all exception handler
      logger.error(f"Unexpected error processing resume: {str(e)}")
      flash(f'Unexpected error: {str(e)}', 'danger')

      # Make sure to clean up the temporary file
      try:
        if os.path.exists(filepath):
          os.remove(filepath)
      except Exception as cleanup_error:
        logger.error(f"Error removing temporary file: {str(cleanup_error)}")

      return redirect(url_for('index'))
  else:
    flash('Invalid file type. Please upload a PDF, DOCX, or TXT file.', 'danger')
    return redirect(url_for('index'))
@app.route('/api/jobs', methods=['GET'])
def get_jobs():
  """API endpoint to get job listings"""
  try:
    jobs = get_job_data()
    logger.info("get_jobs returning with no parameters")
    return jsonify({"success": True, "jobs": jobs})
  except Exception as e:
    logger.error(f"Error fetching jobs: {str(e)}")
    logger.info("get_jobs returning with no parameters")
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

    # Get job data
    try:
      jobs = get_job_data()
      if not jobs:
        logger.info("match_jobs returning with no parameters")
        return jsonify({"success": False, "error": "No job data available to match against"}), 500
    except Exception as e:
      logger.error(f"Error retrieving job data: {str(e)}")
      logger.info("match_jobs returning with no parameters")
      return jsonify({"success": False, "error": f"Error retrieving job data: {str(e)}"}), 500

    # Find matching jobs
    try:
      resume_embeddings = {"narrative": resume_embedding_narrative, "skills": resume_embedding_skills}
      matching_jobs = find_matching_jobs(resume_embeddings, jobs, filters, resume_text=resume_text)
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
@app.route('/api/adzuna/bulk-sync', methods=['POST'])
def bulk_sync_adzuna_jobs():
  """API endpoint to perform a bulk job sync from Adzuna with rate limiting"""
  try:
    if not request.is_json:
      logger.info("bulk_sync_adzuna_jobs returning with no parameters")
      return jsonify({"success": False, "error": "Request must be JSON"}), 400
    data = request.json
    keywords = data.get('keywords', '')
    location = data.get('location', '')
    country = data.get('country', 'gb')
    max_pages = data.get('max_pages', None)
    max_days_old = data.get('max_days_old', 30)

    # Perform bulk sync
    results = sync_jobs_from_adzuna(keywords=keywords, location=location, country=country, max_pages=max_pages, max_days_old=max_days_old)

    if results.get('status') != 'success':
      logger.info("bulk_sync_adzuna_jobs returning with no parameters")
      return jsonify({"success": False, "error": results.get('error', 'Unknown error occurred during sync')}), 500
    logger.info("bulk_sync_adzuna_jobs returning with no parameters")

    return jsonify({"success": True, "results": results, "message": f"Successfully synced {results.get('new_jobs', 0)} new jobs " + f"across {results.get('pages_fetched', 0)} pages"})

  except Exception as e:
    logger.info("bulk_sync_adzuna_jobs returning with no parameters")
    return _handle_api_exception(e, "during Adzuna bulk sync")
@app.route('/api/adzuna/jobs', methods=['GET'])
def get_adzuna_jobs_endpoint():
  """API endpoint to get Adzuna jobs from storage"""
  try:
    days = request.args.get('days', 30, type=int)
    import_to_main = request.args.get('import_to_main', 'false').lower() == 'true'
    # Get jobs
    jobs = get_adzuna_jobs(import_to_main=import_to_main, days=days)
    # Convert to dictionaries for JSON response
    job_dicts = [job.to_dict() for job in jobs]
    logger.info("get_adzuna_jobs_endpoint returning with no parameters")
    return jsonify({"success": True, "jobs": job_dicts, "count": len(job_dicts), "imported": import_to_main})
  except Exception as e:
    logger.info("get_adzuna_jobs_endpoint returning with no parameters")
    return _handle_api_exception(e, "getting Adzuna jobs")
@app.route('/api/adzuna/cleanup', methods=['POST'])
def cleanup_adzuna_jobs_endpoint():
  """API endpoint to clean up old Adzuna jobs"""
  try:
    # Check if request is JSON
    json_error = _require_json_request()
    if json_error:
      logger.info("cleanup_adzuna_jobs_endpoint returning with no parameters")
      return json_error
    data = request.json
    max_age_days = data.get('max_age_days', 90)
    # Clean up old jobs
    removed_count = cleanup_old_adzuna_jobs(max_age_days=max_age_days)
    logger.info("cleanup_adzuna_jobs_endpoint returning with no parameters")
    return jsonify({"success": True, "removed_count": removed_count, "message": f"Successfully removed {removed_count} old Adzuna jobs"})
  except Exception as e:
    logger.info("cleanup_adzuna_jobs_endpoint returning with no parameters")
    return _handle_api_exception(e, "cleaning up Adzuna jobs")
"""API endpoint to get Adzuna storage status"""
@app.route('/api/adzuna/status', methods=['GET'])
def get_adzuna_storage_status_endpoint():
  try:
    # Get status
    status = get_adzuna_storage_status()
    # Format datetime for JSON
    if status.get('last_sync'):
      status['last_sync'] = status['last_sync'].isoformat()
    logger.info("get_adzuna_storage_status_endpoint returning with no parameters")
    return jsonify({"success": True, "status": status})
  except Exception as e:
    logger.info("get_adzuna_storage_status_endpoint returning with no parameters")
    return _handle_api_exception(e, "getting Adzuna storage status")
@app.route('/api/adzuna/import', methods=['POST'])
def import_adzuna_jobs_endpoint():
  """API endpoint to import Adzuna jobs to main storage"""
  try:
    # Check if request is JSON
    json_error = _require_json_request()
    if json_error:
      logger.info("import_adzuna_jobs_endpoint returning with no parameters")
      return json_error
    data = request.json
    days = data.get('days', 30)
    # Import jobs
    count = import_adzuna_jobs_to_main_storage(days=days)
    logger.info("import_adzuna_jobs_endpoint returning with no parameters")
    return jsonify({"success": True, "count": count, "message": f"Successfully imported {count} Adzuna jobs to main storage"})
  except Exception as e:
    logger.info("import_adzuna_jobs_endpoint returning with no parameters")
    return _handle_api_exception(e, "importing Adzuna jobs")

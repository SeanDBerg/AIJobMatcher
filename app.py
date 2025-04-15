import os
import logging
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session, send_from_directory
from werkzeug.utils import secure_filename
import tempfile
from resume_parser import parse_resume, FileParsingError
from embedding_generator import generate_embedding
from job_data import get_job_data
from matching_engine import find_matching_jobs
from resume_storage import resume_storage
from logic.b_jobs.jobSync import sync_jobs_from_adzuna
from logic.b_jobs.jobLayout import generate_table_context
from logic.b_jobs.jobMatch import score_jobs
# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s-%(name)s: [%(funcName)s] %(message)s")
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev_secret_key")

@app.route('/api/adzuna/bulk-sync', methods=['POST'])
def bulk_sync_adzuna_jobs():
    """API endpoint to perform a bulk job sync from Adzuna with rate limiting"""
    try:
        # Check if Adzuna API is available
        error_response = _adzuna_api_check()
        if error_response:
            return error_response

        if not request.is_json:
            return jsonify({"success": False, "error": "Request must be JSON"}), 400

        data = request.json
        keywords = data.get('keywords', '')
        location = data.get('location', '')
        country = data.get('country', 'gb')
        max_pages = data.get('max_pages', None)
        max_days_old = data.get('max_days_old', 30)

        # Perform bulk sync
        results = sync_jobs_from_adzuna(
            keywords=keywords,
            location=location,
            country=country,
            max_pages=max_pages,
            max_days_old=max_days_old
        )

        if results.get('status') != 'success':
            return jsonify({
                "success": False,
                "error": results.get('error', 'Unknown error occurred during sync')
            }), 500

        return jsonify({
            "success": True,
            "results": results,
            "message": f"Successfully synced {results.get('new_jobs', 0)} new jobs " + 
                       f"across {results.get('pages_fetched', 0)} pages"
        })

    except Exception as e:
        return _handle_api_exception(e, "during Adzuna bulk sync")

@app.route('/job_tracker')
def job_tracker():
    context = generate_table_context(session)
    return render_template('job_tracker.html', **context)

@app.route('/match_resume/<resume_id>', methods=['GET'])
def match_resume(resume_id):
    try:
        resume_meta = resume_storage.get_resume(resume_id)
        if not resume_meta:
            flash(f'Resume with ID {resume_id} not found', 'danger')
            return redirect(url_for('resume_manager'))

        resume_text = resume_storage.get_resume_content(resume_id)
        filters = resume_meta.get("filters", {})

        # Use unified match logic
        jobs = get_job_data()
        job_matches = score_jobs(resume_id, jobs, filters)

        session['resume_text'] = resume_text
        session['resume_id'] = resume_id

        return render_template(
            'results.html',
            jobs=job_matches,
            resume_text=resume_text,
            resume_id=resume_id
        )

    except Exception as e:
        logger.error(f"Error in match_resume: {str(e)}")
        flash(f'Error matching resume: {str(e)}', 'danger')
        return redirect(url_for('resume_manager'))


# ======== Maybes =========
@app.route('/api/adzuna/jobs', methods=['GET'])
def get_adzuna_jobs_endpoint():
    """API endpoint to get Adzuna jobs from storage"""
    try:
        # Check if Adzuna API is available
        error_response = _adzuna_api_check()
        if error_response:
            return error_response

        days = request.args.get('days', 30, type=int)
        import_to_main = request.args.get('import_to_main', 'false').lower() == 'true'

        # Get jobs
        jobs = get_adzuna_jobs(import_to_main=import_to_main, days=days)

        # Convert to dictionaries for JSON response
        job_dicts = [job.to_dict() for job in jobs]

        return jsonify({
            "success": True,
            "jobs": job_dicts,
            "count": len(job_dicts),
            "imported": import_to_main
        })

    except Exception as e:
        return _handle_api_exception(e, "getting Adzuna jobs")

@app.route('/api/match', methods=['POST'])
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
                        return jsonify({
                            "success": False,
                            "error": f"Resume with ID {resume_id} not found"
                        }), 404

                    resume_text = resume_storage.get_resume_content(resume_id) or ''

                    # Get embedding from metadata if available
                    if resume_metadata.get('embedding'):
                        # Convert embedding from list back to numpy array if needed
                        import numpy as np
                        embedding_data = resume_metadata['embedding']
                        if isinstance(embedding_data, list):
                            resume_embedding = np.array(embedding_data)
                        else:
                            resume_embedding = embedding_data
                    else:
                        # Generate embedding if not in metadata
                        resume_embedding = generate_embedding(resume_text)

                    # Use filters from metadata if not provided in request
                    if not filters and resume_metadata.get('filters'):
                        filters = resume_metadata['filters']

                except Exception as e:
                    logger.error(f"Error retrieving resume {resume_id}: {str(e)}")
                    return jsonify({
                        "success": False,
                        "error": f"Error retrieving resume: {str(e)}"
                    }), 500
            else:
                # Use resume_text from request
                if not resume_text or len(resume_text.strip()) < 50:
                    return jsonify({
                        "success": False, 
                        "error": "Resume text is too short. Please provide a complete resume."
                    }), 400

                # Generate embedding
                try:
                    resume_embedding = generate_embedding(resume_text)
                except Exception as e:
                    logger.error(f"Error generating embedding: {str(e)}")
                    return jsonify({
                        "success": False,
                        "error": f"Error analyzing resume content: {str(e)}"
                    }), 500
        else:
            return jsonify({"success": False, "error": "Request must be JSON"}), 400

        # Get job data
        try:
            jobs = get_job_data()
            if not jobs:
                return jsonify({
                    "success": False,
                    "error": "No job data available to match against"
                }), 500
        except Exception as e:
            logger.error(f"Error retrieving job data: {str(e)}")
            return jsonify({
                "success": False,
                "error": f"Error retrieving job data: {str(e)}"
            }), 500

        # Find matching jobs
        try:
            matching_jobs = find_matching_jobs(resume_embedding, jobs, filters)
            if not matching_jobs:
                return jsonify({
                    "success": True,
                    "matches": [],
                    "message": "No matching jobs found based on your filters. Try adjusting your search criteria."
                })
        except Exception as e:
            logger.error(f"Error matching jobs: {str(e)}")
            return jsonify({
                "success": False,
                "error": f"Error matching jobs: {str(e)}"
            }), 500

        # Convert job matches to dictionaries
        job_matches_dict = [job_match.to_dict() for job_match in matching_jobs]

        return jsonify({
            "success": True, 
            "matches": job_matches_dict,
            "count": len(matching_jobs),
            "resume_id": resume_id if resume_id else None
        })

    except Exception as e:
        logger.error(f"Unexpected error in API: {str(e)}")
        return jsonify({
            "success": False, 
            "error": f"Unexpected error: {str(e)}"
        }), 500

@app.route('/resume_manager')
def resume_manager():
    # Get stored resumes
    stored_resumes = resume_storage.get_all_resumes()

    # Get active resume ID from query param if any
    active_resume_id = request.args.get('resume_id')

    # If resume_id is provided, redirect to match_resume
    if active_resume_id:
        active_resume = resume_storage.get_resume(active_resume_id)
        if active_resume:
            return redirect(url_for('match_resume', resume_id=active_resume_id))

    # Render the resume manager page (upload form)
    return render_template('resume_manager.html', 
                          stored_resumes=stored_resumes,
                          active_resume=None,
                          resume_content=None)

@app.route('/resume_files/<resume_id>/<filename>')
def resume_files(resume_id, filename):
    """Serve resume files"""
    # Get the path from the resume_storage module
    from resume_storage import RESUME_DIR
    return send_from_directory(RESUME_DIR, f"{resume_id}_{filename}")

@app.route('/delete_resume/<resume_id>', methods=['POST'])
def delete_resume(resume_id):
    """Delete a stored resume"""
    try:
        if resume_storage.delete_resume(resume_id):
            flash('Resume deleted successfully', 'success')
        else:
            flash('Resume not found or could not be deleted', 'danger')
    except Exception as e:
        logger.error(f"Error deleting resume: {str(e)}")
        flash(f'Error deleting resume: {str(e)}', 'danger')

    return redirect(url_for('resume_manager'))

# Optional import for Adzuna functionality
try:
    from adzuna_scraper import (
        get_adzuna_jobs, 
        cleanup_old_adzuna_jobs,
        get_adzuna_storage_status
    )
    ADZUNA_SCRAPER_AVAILABLE = True
except ImportError:
    logger.warning("Adzuna scraper module not available")
    ADZUNA_SCRAPER_AVAILABLE = False

# Optional import for Adzuna scheduler
try:
    from adzuna_scheduler import (
        get_scheduler_config,
        update_scheduler_config,
        start_scheduler,
        stop_scheduler,
        restart_scheduler,
        get_scheduler_status
    )
    ADZUNA_SCHEDULER_AVAILABLE = True
    # Start the scheduler automatically
    start_scheduler()
except ImportError:
    logger.warning("Adzuna scheduler module not available")
    ADZUNA_SCHEDULER_AVAILABLE = False

# Configure upload settings
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}
TEMP_FOLDER = tempfile.gettempdir()

# Helper functions for API endpoints
def _adzuna_api_check():
    """Check if Adzuna API is available and return error response if not"""
    if not ADZUNA_SCRAPER_AVAILABLE:
        return jsonify({
            "success": False,
            "error": "Adzuna scraper module is not available"
        }), 500
    return None

def _adzuna_scheduler_check():
    """Check if Adzuna scheduler is available and return error response if not"""
    if not ADZUNA_SCHEDULER_AVAILABLE:
        return jsonify({
            "success": False,
            "error": "Adzuna scheduler module is not available"
        }), 500
    return None

def _handle_api_exception(e, operation_name):
    """Log exception and return standardized error response"""
    logger.error(f"Error {operation_name}: {str(e)}")
    return jsonify({"success": False, "error": str(e)}), 500

def _require_json_request():
    """Check if request is JSON and return error response if not"""
    if not request.is_json:
        return jsonify({"success": False, "error": "Request must be JSON"}), 400
    return None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    # Get scheduler config if available
    config = None
    last_sync = "Never"
    total_jobs = 0
    next_sync = "Not scheduled"
    scraper_config = None
    
    if ADZUNA_SCHEDULER_AVAILABLE:
        config = get_scheduler_config()
    
    if ADZUNA_SCRAPER_AVAILABLE:
        storage_status = get_adzuna_storage_status()
        last_sync = storage_status.get("last_sync", "Never")
        total_jobs = storage_status.get("total_jobs", 0)
        
        # Get scraper config for API delay settings
        try:
            from adzuna_scraper import config as adzuna_config
            scraper_config = {
                "rate_limit_calls": adzuna_config.rate_limit_calls,
                "rate_limit_period": adzuna_config.rate_limit_period,
                "call_delay": adzuna_config.call_delay
            }
        except ImportError:
            logger.warning("Couldn't import adzuna_scraper config")
    
    if ADZUNA_SCHEDULER_AVAILABLE:
        scheduler_status = get_scheduler_status()
        next_sync = scheduler_status.get("next_run", "Not scheduled")
    
    # If config is None, initialize with defaults for the template
    if config is None:
        config = {
            'enabled': False,
            'daily_sync_time': '02:00',
            'keywords': '',
            'location': '',
            'country': 'gb',
            'max_days_old': 30,
            'cleanup_old_jobs': True,
            'cleanup_days': 90,
            'remote_only': False,
            'search_terms': []
        }
    
    return render_template('settings.html', 
                           config=config, 
                           last_sync=last_sync, 
                           total_jobs=total_jobs, 
                           next_sync=next_sync,
                           scraper_config=scraper_config)

@app.route('/save_settings', methods=['POST'])
def save_settings():
    """Save user settings for job search and scheduler"""
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
        
        # Scheduler settings
        scheduler_enabled = request.form.get('scheduler_enabled') == '1'
        daily_sync_time = request.form.get('daily_sync_time', '02:00')
        cleanup_old_jobs = request.form.get('cleanup_old_jobs') == '1'
        cleanup_days = int(request.form.get('cleanup_days', 90))
        
        # Update scheduler configuration if available
        if ADZUNA_SCHEDULER_AVAILABLE:
            config_updates = {
                'enabled': scheduler_enabled,
                'daily_sync_time': daily_sync_time,
                'keywords': keywords,
                'location': location,
                'country': country,
                'max_days_old': max_days_old,
                'cleanup_old_jobs': cleanup_old_jobs,
                'cleanup_days': cleanup_days,
                'remote_only': remote_only,
                'search_terms': search_terms
            }
            
            update_scheduler_config(config_updates)
            
            if scheduler_enabled:
                # Start or restart the scheduler if it's enabled
                restart_scheduler()
            else:
                # Stop the scheduler if it's disabled
                stop_scheduler()
        
        flash('Settings saved successfully!', 'success')
        
        # Redirect to job tracker page with sync form pre-filled if "Sync Now" was selected
        if sync_now:
            # Store search parameters in session for persistence
            session['job_search_keywords'] = keywords
            session['job_search_location'] = location
            session['job_search_country'] = country
            session['job_search_max_days_old'] = str(max_days_old)
            session['job_search_remote_only'] = '1' if remote_only else ''
            
            return redirect(url_for('job_tracker'))
        else:
            return redirect(url_for('settings'))
        
    except Exception as e:
        logger.error(f"Error saving settings: {str(e)}")
        flash(f'Error saving settings: {str(e)}', 'danger')
        return redirect(url_for('settings'))

@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    # Check if a file was uploaded
    if 'resume' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('resume_manager'))
    
    file = request.files['resume']
    
    # If user doesn't select a file
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('resume_manager'))
    
    # Check if the file is allowed
    if file and allowed_file(file.filename):
        # Save file temporarily
        filename = secure_filename(file.filename)
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
                return redirect(url_for('resume_manager'))
            except Exception as e:
                logger.error(f"Unexpected error parsing resume: {str(e)}")
                flash(f'Error parsing resume: {str(e)}', 'danger')
                return redirect(url_for('resume_manager'))
            
            # Generate embedding
            logger.debug("Generating embedding for resume")
            try:
                resume_embedding = generate_embedding(resume_text)
            except Exception as e:
                logger.error(f"Error generating embedding: {str(e)}")
                flash(f'Error analyzing resume content: {str(e)}', 'danger')
                return redirect(url_for('resume_manager'))
            
            # Get filters from form
            filters = {
                'remote': request.form.get('remote', '') == 'on',
                'location': request.form.get('location', ''),
                'keywords': request.form.get('keywords', '')
            }
            
            # Store resume in persistent storage
            try:
                # Create metadata with embedding (convert NumPy array to list for JSON serialization)
                metadata = {
                    "embedding": resume_embedding.tolist() if hasattr(resume_embedding, 'tolist') else resume_embedding,
                    "filters": filters
                }
                
                # Store in persistent storage
                resume_id = resume_storage.store_resume(
                    temp_filepath=filepath,
                    filename=filename,
                    content=resume_text,
                    metadata=metadata
                )
                
                flash(f'Resume "{filename}" successfully uploaded and stored', 'success')
                
                # Check if user wants to find matching jobs immediately
                find_matches = request.form.get('find_matches', '') == 'on'
                
                if find_matches:
                    # Get all job data
                    try:
                        jobs = get_job_data()
                        if not jobs:
                            flash('No job data available to match against', 'warning')
                            return redirect(url_for('resume_manager', resume_id=resume_id))
                    except Exception as e:
                        logger.error(f"Error retrieving job data: {str(e)}")
                        flash(f'Error retrieving job data: {str(e)}', 'danger')
                        return redirect(url_for('resume_manager', resume_id=resume_id))
                    
                    # Find matching jobs
                    try:
                        matching_jobs = find_matching_jobs(resume_embedding, jobs, filters)
                        
                        # Store resume text in session for display on results page
                        session['resume_text'] = resume_text
                        session['resume_id'] = resume_id
                        
                        # Clean up temp file
                        if os.path.exists(filepath):
                            os.remove(filepath)
                            
                        return render_template('results.html', 
                                            jobs=matching_jobs, 
                                            resume_text=resume_text,
                                            resume_id=resume_id)
                    except Exception as e:
                        logger.error(f"Error matching jobs: {str(e)}")
                        flash(f'Error matching jobs: {str(e)}', 'danger')
                        return redirect(url_for('resume_manager', resume_id=resume_id))
                else:
                    # Clean up temp file
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        
                    # Redirect to resume manager with this resume active
                    return redirect(url_for('resume_manager', resume_id=resume_id))
                
            except Exception as e:
                logger.error(f"Error storing resume: {str(e)}")
                flash(f'Error storing resume: {str(e)}', 'danger')
                
                # Clean up temp file
                if os.path.exists(filepath):
                    os.remove(filepath)
                    
                return redirect(url_for('resume_manager'))
            
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
            
            return redirect(url_for('resume_manager'))
    else:
        flash('Invalid file type. Please upload a PDF, DOCX, or TXT file.', 'danger')
        return redirect(url_for('resume_manager'))

@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    """API endpoint to get job listings"""
    try:
        jobs = get_job_data()
        return jsonify({"success": True, "jobs": jobs})
    except Exception as e:
        logger.error(f"Error fetching jobs: {str(e)}")
        return jsonify({"success": False, "error": str(e)})


        





# =========== Probably Nots ===========

@app.route('/api/adzuna/cleanup', methods=['POST'])
def cleanup_adzuna_jobs_endpoint():
    """API endpoint to clean up old Adzuna jobs"""
    try:
        # Check if Adzuna API is available
        error_response = _adzuna_api_check()
        if error_response:
            return error_response
        
        # Check if request is JSON
        json_error = _require_json_request()
        if json_error:
            return json_error
            
        data = request.json
        max_age_days = data.get('max_age_days', 90)
        
        # Clean up old jobs
        removed_count = cleanup_old_adzuna_jobs(max_age_days=max_age_days)
        
        return jsonify({
            "success": True,
            "removed_count": removed_count,
            "message": f"Successfully removed {removed_count} old Adzuna jobs"
        })
        
    except Exception as e:
        return _handle_api_exception(e, "cleaning up Adzuna jobs")

@app.route('/api/scrape/adzuna', methods=['POST'])
def scrape_adzuna_jobs():
    """API endpoint to scrape jobs from Adzuna with specific parameters"""
    try:
        if not request.is_json:
            return jsonify({"success": False, "error": "Request must be JSON"}), 400

        data = request.json
        keywords = data.get('keywords', '')
        location = data.get('location', '')

        # Import here to avoid circular imports
        try:
            from job_scraper import scrape_jobs_from_adzuna, save_scraped_jobs
        except ImportError:
            return jsonify({
                "success": False,
                "error": "Adzuna integration is not available"
            }), 500

        jobs = scrape_jobs_from_adzuna(keywords=keywords, location=location)

        if not jobs:
            return jsonify({
                "success": False,
                "error": "No jobs found or Adzuna API configuration is missing"
            }), 404

        saved_count = save_scraped_jobs(jobs)

        return jsonify({
            "success": True,
            "count": saved_count,
            "message": f"Successfully scraped {saved_count} jobs from Adzuna"
        })

    except Exception as e:
        logger.error(f"Error scraping Adzuna jobs: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/config/adzuna', methods=['POST'])
def config_adzuna():
    """API endpoint to configure Adzuna API credentials"""
    try:
        if not request.is_json:
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

        return jsonify({"success": True})

    except Exception as e:
        logger.error(f"Error configuring Adzuna API: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/admin/scrape', methods=['GET'])
def admin_scrape_page():
    """Admin page for job scraping"""
    return render_template('admin_scrape.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

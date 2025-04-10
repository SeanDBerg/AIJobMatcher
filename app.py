import os
import logging
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session
from werkzeug.utils import secure_filename
import tempfile
import json
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Import custom modules
from resume_parser import parse_resume, FileParsingError
from embedding_generator import generate_embedding
from job_data import get_job_data, add_job
from matching_engine import find_matching_jobs
from job_scraper import scrape_webpage_for_jobs, extract_skills_from_description, scrape_all_job_sources
from models import Job

# Optional import for Adzuna functionality
try:
    from adzuna_scraper import (
        sync_jobs_from_adzuna, 
        get_adzuna_jobs, 
        import_adzuna_jobs_to_main_storage,
        cleanup_old_adzuna_jobs,
        get_adzuna_storage_status
    )
    ADZUNA_SCRAPER_AVAILABLE = True
except ImportError:
    logger.warning("Adzuna scraper module not available")
    ADZUNA_SCRAPER_AVAILABLE = False

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev_secret_key")

# Configure upload settings
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}
TEMP_FOLDER = tempfile.gettempdir()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    # Check if a file was uploaded
    if 'resume' not in request.files:
        flash('No file part', 'danger')
        return redirect(request.url)
    
    file = request.files['resume']
    
    # If user doesn't select a file
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(request.url)
    
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
                return redirect(request.url)
            except Exception as e:
                logger.error(f"Unexpected error parsing resume: {str(e)}")
                flash(f'Error parsing resume: {str(e)}', 'danger')
                return redirect(request.url)
            
            # Generate embedding
            logger.debug("Generating embedding for resume")
            try:
                resume_embedding = generate_embedding(resume_text)
            except Exception as e:
                logger.error(f"Error generating embedding: {str(e)}")
                flash(f'Error analyzing resume content: {str(e)}', 'danger')
                return redirect(request.url)
            
            # Store resume text in session for display
            session['resume_text'] = resume_text
            
            # Get filters from form
            filters = {
                'remote': request.form.get('remote', '') == 'on',
                'location': request.form.get('location', ''),
                'keywords': request.form.get('keywords', '')
            }
            
            # Get all job data
            try:
                jobs = get_job_data()
                if not jobs:
                    flash('No job data available to match against', 'warning')
                    return redirect(request.url)
            except Exception as e:
                logger.error(f"Error retrieving job data: {str(e)}")
                flash(f'Error retrieving job data: {str(e)}', 'danger')
                return redirect(request.url)
            
            # Find matching jobs
            try:
                matching_jobs = find_matching_jobs(resume_embedding, jobs, filters)
            except Exception as e:
                logger.error(f"Error matching jobs: {str(e)}")
                flash(f'Error matching jobs: {str(e)}', 'danger')
                return redirect(request.url)
            
            # Remove the temporary file
            os.remove(filepath)
            
            return render_template('results.html', jobs=matching_jobs, resume_text=resume_text)
            
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
            
            return redirect(request.url)
    else:
        flash('Invalid file type. Please upload a PDF, DOCX, or TXT file.', 'danger')
        return redirect(request.url)

@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    """API endpoint to get job listings"""
    try:
        jobs = get_job_data()
        return jsonify({"success": True, "jobs": jobs})
    except Exception as e:
        logger.error(f"Error fetching jobs: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/match', methods=['POST'])
def match_jobs():
    """API endpoint to match resume to jobs"""
    try:
        # Validate request data
        if not request.is_json:
            return jsonify({"success": False, "error": "Request must be JSON"}), 400
            
        data = request.json
        resume_text = data.get('resume_text', '')
        
        # Validate resume text
        if not resume_text or len(resume_text.strip()) < 50:
            return jsonify({
                "success": False, 
                "error": "Resume text is too short. Please provide a complete resume."
            }), 400
            
        filters = data.get('filters', {})
        
        # Generate embedding for resume
        try:
            resume_embedding = generate_embedding(resume_text)
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            return jsonify({
                "success": False,
                "error": f"Error analyzing resume content: {str(e)}"
            }), 500
        
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
            "count": len(matching_jobs)
        })
        
    except Exception as e:
        logger.error(f"Unexpected error in API: {str(e)}")
        return jsonify({
            "success": False, 
            "error": f"Unexpected error: {str(e)}"
        }), 500

@app.route('/api/scrape/url', methods=['POST'])
def scrape_url():
    """API endpoint to scrape job information from a URL"""
    try:
        if not request.is_json:
            return jsonify({"success": False, "error": "Request must be JSON"}), 400
            
        data = request.json
        url = data.get('url', '')
        
        if not url:
            return jsonify({"success": False, "error": "URL is required"}), 400
        
        # Scrape the webpage
        job_text = scrape_webpage_for_jobs(url)
        
        if not job_text:
            return jsonify({
                "success": False,
                "error": "Unable to extract content from the provided URL"
            }), 400
        
        # Extract skills
        skills = extract_skills_from_description(job_text)
        
        # Create a job object
        job_title = data.get('title', 'Job Listing')
        job_company = data.get('company', 'Company')
        
        job = Job(
            title=job_title,
            company=job_company,
            description=job_text[:5000],  # Limit description length
            location=data.get('location', ''),
            is_remote=data.get('is_remote', False),
            posted_date=datetime.now(),
            url=url,
            skills=skills,
            salary_range=data.get('salary_range', '')
        )
        
        # Save to job data
        try:
            add_job(job.to_dict())
        except Exception as e:
            logger.error(f"Error saving scraped job: {str(e)}")
            return jsonify({
                "success": False,
                "error": f"Error saving job data: {str(e)}"
            }), 500
        
        return jsonify({
            "success": True,
            "job": job.to_dict(),
            "skills": skills,
            "message": "Job successfully scraped and saved"
        })
        
    except Exception as e:
        logger.error(f"Error scraping URL: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/scrape/all', methods=['POST'])
def scrape_all_jobs():
    """API endpoint to scrape jobs from all configured sources"""
    try:
        # This could be a long-running task, so we should ideally run it asynchronously
        # For simplicity, we'll run it synchronously here
        results = scrape_all_job_sources()
        
        return jsonify({
            "success": True,
            "results": results,
            "message": f"Successfully scraped {results.get('saved', 0)} jobs from {len(results) - 1} sources"
        })
        
    except Exception as e:
        logger.error(f"Error scraping jobs: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

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
        
@app.route('/api/config/adzuna/status', methods=['GET'])
def check_adzuna_status():
    """API endpoint to check Adzuna API status"""
    try:
        # Check if credentials are configured
        app_id = os.environ.get('ADZUNA_APP_ID')
        api_key = os.environ.get('ADZUNA_API_KEY')
        
        if not app_id or not api_key:
            return jsonify({
                "success": False,
                "error": "Adzuna API credentials not configured"
            }), 400
            
        # Make a test API call
        try:
            from adzuna_api import search_jobs
            jobs = search_jobs(results_per_page=1)  # Just get 1 job to test
            
            if jobs is None:
                return jsonify({
                    "success": False,
                    "error": "Adzuna API returned an invalid response"
                }), 500
                
            return jsonify({
                "success": True,
                "message": "Adzuna API is properly configured and working"
            })
            
        except Exception as e:
            logger.error(f"Error testing Adzuna API: {str(e)}")
            return jsonify({
                "success": False,
                "error": f"Adzuna API test failed: {str(e)}"
            }), 500
            
    except Exception as e:
        logger.error(f"Error checking Adzuna API status: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/adzuna/bulk-sync', methods=['POST'])
def bulk_sync_adzuna_jobs():
    """API endpoint to perform a bulk job sync from Adzuna with rate limiting"""
    try:
        if not ADZUNA_SCRAPER_AVAILABLE:
            return jsonify({
                "success": False,
                "error": "Adzuna bulk scraper is not available"
            }), 500
            
        if not request.is_json:
            return jsonify({"success": False, "error": "Request must be JSON"}), 400
            
        data = request.json
        keywords = data.get('keywords', '')
        location = data.get('location', '')
        country = data.get('country', 'gb')
        max_pages = data.get('max_pages', None)
        
        # Perform bulk sync
        results = sync_jobs_from_adzuna(
            keywords=keywords,
            location=location,
            country=country,
            max_pages=max_pages
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
        logger.error(f"Error during Adzuna bulk sync: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/adzuna/jobs', methods=['GET'])
def get_adzuna_jobs_endpoint():
    """API endpoint to get Adzuna jobs from storage"""
    try:
        if not ADZUNA_SCRAPER_AVAILABLE:
            return jsonify({
                "success": False,
                "error": "Adzuna bulk scraper is not available"
            }), 500
            
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
        logger.error(f"Error getting Adzuna jobs: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/adzuna/cleanup', methods=['POST'])
def cleanup_adzuna_jobs_endpoint():
    """API endpoint to clean up old Adzuna jobs"""
    try:
        if not ADZUNA_SCRAPER_AVAILABLE:
            return jsonify({
                "success": False,
                "error": "Adzuna bulk scraper is not available"
            }), 500
            
        if not request.is_json:
            return jsonify({"success": False, "error": "Request must be JSON"}), 400
            
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
        logger.error(f"Error cleaning up Adzuna jobs: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/adzuna/status', methods=['GET'])
def get_adzuna_storage_status_endpoint():
    """API endpoint to get Adzuna storage status"""
    try:
        if not ADZUNA_SCRAPER_AVAILABLE:
            return jsonify({
                "success": False,
                "error": "Adzuna bulk scraper is not available"
            }), 500
            
        # Get status
        status = get_adzuna_storage_status()
        
        # Format datetime for JSON
        if status.get('last_sync'):
            status['last_sync'] = status['last_sync'].isoformat()
        
        return jsonify({
            "success": True,
            "status": status
        })
        
    except Exception as e:
        logger.error(f"Error getting Adzuna storage status: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/adzuna/import', methods=['POST'])
def import_adzuna_jobs_endpoint():
    """API endpoint to import Adzuna jobs to main storage"""
    try:
        if not ADZUNA_SCRAPER_AVAILABLE:
            return jsonify({
                "success": False,
                "error": "Adzuna bulk scraper is not available"
            }), 500
            
        if not request.is_json:
            return jsonify({"success": False, "error": "Request must be JSON"}), 400
            
        data = request.json
        days = data.get('days', 30)
        
        # Import jobs
        count = import_adzuna_jobs_to_main_storage(days=days)
        
        return jsonify({
            "success": True,
            "count": count,
            "message": f"Successfully imported {count} Adzuna jobs to main storage"
        })
        
    except Exception as e:
        logger.error(f"Error importing Adzuna jobs: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/admin/scrape', methods=['GET'])
def admin_scrape_page():
    """Admin page for job scraping"""
    return render_template('admin_scrape.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

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

@app.route('/admin/scrape', methods=['GET'])
def admin_scrape_page():
    """Admin page for job scraping"""
    return render_template('admin_scrape.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

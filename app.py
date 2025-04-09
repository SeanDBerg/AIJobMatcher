import os
import logging
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session
from werkzeug.utils import secure_filename
import tempfile
import json

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Import custom modules
from resume_parser import parse_resume
from embedding_generator import generate_embedding
from job_data import get_job_data
from matching_engine import find_matching_jobs

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
        try:
            # Save file temporarily
            filename = secure_filename(file.filename)
            filepath = os.path.join(TEMP_FOLDER, filename)
            file.save(filepath)
            
            # Parse resume
            logger.debug(f"Parsing resume from {filepath}")
            resume_text = parse_resume(filepath)
            
            # Generate embedding
            logger.debug("Generating embedding for resume")
            resume_embedding = generate_embedding(resume_text)
            
            # Store embedding in session
            session['resume_text'] = resume_text
            
            # Get filters from form
            filters = {
                'remote': request.form.get('remote', '') == 'on',
                'location': request.form.get('location', ''),
                'keywords': request.form.get('keywords', '')
            }
            
            # Get all job data
            jobs = get_job_data()
            
            # Find matching jobs
            matching_jobs = find_matching_jobs(resume_embedding, jobs, filters)
            
            # Remove the temporary file
            os.remove(filepath)
            
            return render_template('results.html', jobs=matching_jobs, resume_text=resume_text)
            
        except Exception as e:
            logger.error(f"Error processing resume: {str(e)}")
            flash(f'Error processing resume: {str(e)}', 'danger')
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
        data = request.json
        resume_text = data.get('resume_text', '')
        filters = data.get('filters', {})
        
        # Generate embedding for resume
        resume_embedding = generate_embedding(resume_text)
        
        # Get job data
        jobs = get_job_data()
        
        # Find matching jobs
        matching_jobs = find_matching_jobs(resume_embedding, jobs, filters)
        
        return jsonify({"success": True, "matches": matching_jobs})
    except Exception as e:
        logger.error(f"Error matching jobs: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

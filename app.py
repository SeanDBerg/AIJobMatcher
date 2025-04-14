# app.py
import os
import logging
from flask import Flask, render_template, request, jsonify, session, send_from_directory
from job_manager import JobManager
from logic.a_resume.uploadResume import upload_resume_bp
from logic.a_resume.resumeHistory import resume_history_bp
from logic.b_jobs.jobHeading import job_heading_bp
from logic.b_jobs.jobLayout import generate_table_context
from logic.b_jobs.jobSync import job_sync_bp
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
app.register_blueprint(job_sync_bp)
# Route for the main page
@app.route('/')
def index():
    status = generate_table_context(session)
    logger.debug("Rendering index with %d jobs", status.get("total_jobs", 0))
    return render_template('index.html', **status)
# Serve resume files
@app.route('/resume_files/<resume_id>/<filename>')
def resume_files(resume_id, filename):
    from resume_storage import RESUME_DIR
    logger.info("resume_files returning with resume_id=%s, filename=%s", resume_id, filename)
    return send_from_directory(RESUME_DIR, f"{resume_id}_{filename}")

@app.route('/api/match-jobs', methods=['POST'])
def match_jobs():
    if not request.is_json:
        return jsonify({"success": False, "error": "Request must be JSON"}), 400
    response_json, status_code = match_jobs_api(request.json)
    return jsonify(response_json), status_code

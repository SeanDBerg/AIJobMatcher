# app.py - Main application file for job matching application
import os
import logging
from flask import Flask, render_template, session
from logic.b_jobs.jobLayout import generate_table_context
from logic.a_resume.uploadResume import upload_resume_bp
from logic.a_resume.resumeHistory import resume_history_bp
from logic.a_resume.resumeHistory import get_all_resumes
from logic.b_jobs.jobLayout import layout_bp
from logic.b_jobs.jobSync import job_sync_bp

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s-%(name)s: [%(funcName)s] %(message)s")
logger = logging.getLogger(__name__)
# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev_secret_key")
app.register_blueprint(upload_resume_bp)
app.register_blueprint(resume_history_bp)
app.register_blueprint(layout_bp)
app.register_blueprint(job_sync_bp)

@app.route('/')
def index():
    context = generate_table_context(session)
    context["stored_resumes"] = get_all_resumes()
    return render_template("index.html", **context)
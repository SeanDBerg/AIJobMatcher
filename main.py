# main.py - Main application file for job matching application
import os
import logging
from flask import Flask, render_template, session
from app_logic.b_jobs.jobLayout import generate_table_context
from app_logic.a_resume.uploadResume import upload_resume_bp
from app_logic.a_resume.resumeHistory import resume_history_bp
from app_logic.a_resume.resumeHistory import get_all_resumes
from app_logic.b_jobs.jobLayout import layout_bp
from app_logic.b_jobs.jobSync import job_sync_bp
from app_logic.c_user.userLogin import user_login_bp
# import Tools.call_tree_mapper  # Automatically runs at startup
# import Tools.js_tree_mapper  # This will auto-run on import
# import Tools.js_flask_bridge  # Automatically runs at startup
# import Tools.unified_tree_mapper
import Tools.diagnostic_tree_log


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
app.register_blueprint(user_login_bp)

@app.route('/')
def index():
    is_demo = not session.get("authenticated")
    session["demo"] = is_demo

    # ✅ Use real or demo resumes
    if is_demo:
        from app_logic.a_resume.resumeHistory import generate_demo_resumes
        resumes = generate_demo_resumes()
    else:
        resumes = get_all_resumes(user_id=session.get("user_id"))

    context = generate_table_context(session)
    context["stored_resumes"] = resumes
    context["is_demo"] = is_demo

    return render_template("index.html", **context)



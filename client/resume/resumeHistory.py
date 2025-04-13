# resumeHistory.py - Manages resume list and deletion logic
import os
import logging
from flask import Blueprint, redirect, url_for, flash
from resume_storage import resume_storage, RESUME_DIR
logger = logging.getLogger(__name__)
resume_history_bp = Blueprint("resume_history", __name__)
# Delete a resume
@resume_history_bp.route('/delete_resume/<resume_id>', methods=['POST'])
def delete_resume_route(resume_id):
    """
    Route for deleting a stored resume.
    """
    try:
        if delete_resume(resume_id):
            flash('Resume deleted successfully', 'success')
        else:
            flash('Resume not found or could not be deleted', 'danger')
    except Exception as e:
        logger.error(f"Error deleting resume: {str(e)}")
        flash(f'Error deleting resume: {str(e)}', 'danger')
    return redirect(url_for('index'))
# Get all stored resumes
def get_all_resumes():
    """
    Return a list of all stored resumes for display.
    """
    try:
        resume_storage._load_index()
        resumes = list(resume_storage._index["resumes"].values())
        resumes.sort(key=lambda r: r.get("upload_date", ""), reverse=True)
        logger.info("get_all_resumes returning with %d resumes", len(resumes))
        return resumes
    except Exception as e:
        logger.error(f"Error fetching all resumes: {str(e)}")
        return []
# Delete a resume
def delete_resume(resume_id: str) -> bool:
    """
    Delete a specific resume and update the index.
    """
    try:
        resume_storage._load_index()

        if resume_id not in resume_storage._index["resumes"]:
            logger.warning(f"Resume ID {resume_id} not found in index")
            return False

        metadata = resume_storage._index["resumes"][resume_id]
        stored_filename = metadata.get("stored_filename")
        content_filename = f"{resume_id}_content.txt"

        # Delete stored file
        if stored_filename:
            file_path = os.path.join(RESUME_DIR, stored_filename)
            if os.path.exists(file_path):
                os.remove(file_path)

        # Delete content file
        content_path = os.path.join(RESUME_DIR, content_filename)
        if os.path.exists(content_path):
            os.remove(content_path)

        # Remove from index
        del resume_storage._index["resumes"][resume_id]
        resume_storage._index["count"] -= 1

        # Update last_added if needed
        if resume_storage._index["last_added"] == resume_id:
            if resume_storage._index["resumes"]:
                newest = max(resume_storage._index["resumes"].values(), key=lambda r: r.get("upload_date", ""))
                resume_storage._index["last_added"] = newest["id"]
            else:
                resume_storage._index["last_added"] = None

        resume_storage._save_index()
        logger.info(f"Deleted resume ID {resume_id}")
        return True

    except Exception as e:
        logger.error(f"Error deleting resume {resume_id}: {str(e)}")
        return False

# logic/a_resume/resumeHistory.py - Manages resume listing, storage, access, and deletion
import os
import json
import uuid
import logging
import shutil
from datetime import datetime
from flask import Blueprint, redirect, url_for, flash, request, jsonify, session
from typing import Optional, List, Dict
# === Setup ===
logger = logging.getLogger(__name__)
resume_history_bp = Blueprint("resume_history", __name__)
# === Storage Paths ===
RESUME_DIR = os.path.join(os.path.dirname(__file__), '../../static/resumes')
RESUME_INDEX_FILE = os.path.join(RESUME_DIR, 'index.json')
# === Resume Access and Deletion ===
# """Load the resume index from file"""
def _load_index() -> Dict:
    try:
        if not os.path.exists(RESUME_INDEX_FILE):
            return {"resumes": {}, "count": 0, "last_added": None}
        with open(RESUME_INDEX_FILE, 'r', encoding='utf-8') as f:
            index = json.load(f)
        index.setdefault("resumes", {})
        index.setdefault("count", len(index["resumes"]))
        index.setdefault("last_added", None)
        return index
    except Exception as e:
        logger.error(f"Error loading resume index: {str(e)}")
        return {"resumes": {}, "count": 0, "last_added": None}
# """Save the resume index to file"""
def _save_index(index: Dict = None):
    try:
        if index is None:
            index = resume_storage._index
        with open(RESUME_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving resume index: {str(e)}")
# === Resume Access ===
# Get all stored resumes, sorted by upload date
def get_all_resumes() -> List[Dict]:
    try:
        index = _load_index()
        resumes = list(index["resumes"].values())
        resumes.sort(key=lambda r: r.get("upload_date", ""), reverse=True)
        logger.info("get_all_resumes returning with %d resumes", len(resumes))
        return resumes
    except Exception as e:
        logger.error(f"Error fetching all resumes: {str(e)}")
        return []
# Get a specific resume's metadata
def get_resume(resume_id: str) -> Optional[Dict]:
    try:
        index = _load_index()
        return index["resumes"].get(resume_id)
    except Exception as e:
        logger.error(f"Error getting resume {resume_id}: {str(e)}")
        return None
# Get the content of a resume
def get_resume_content(resume_id: str) -> Optional[str]:
    try:
        content_path = os.path.join(RESUME_DIR, f"{resume_id}_content.txt")
        if not os.path.exists(content_path):
            logger.warning(f"Content file for resume {resume_id} not found")
            return None
        with open(content_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error reading resume content for {resume_id}: {str(e)}")
        return None
# === Resume Deletion ===
# Delete a resume
def delete_resume(resume_id: str) -> bool:
    try:
        index = resume_storage._index  # ✅ Use the singleton directly

        if resume_id not in index["resumes"]:
            logger.warning(f"Resume ID {resume_id} not found in index")
            return False

        metadata = index["resumes"][resume_id]
        stored_filename = metadata.get("stored_filename")
        content_filename = f"{resume_id}_content.txt"

        # Delete the actual files
        if stored_filename:
            file_path = os.path.join(RESUME_DIR, stored_filename)
            if os.path.exists(file_path):
                os.remove(file_path)

        content_path = os.path.join(RESUME_DIR, content_filename)
        if os.path.exists(content_path):
            os.remove(content_path)

        # Update the in-memory index
        del index["resumes"][resume_id]
        index["count"] = max(0, len(index["resumes"]))  # Defensive

        if index.get("last_added") == resume_id:
            if index["resumes"]:
                newest = max(index["resumes"].values(), key=lambda r: r.get("upload_date", ""))
                index["last_added"] = newest["id"]
            else:
                index["last_added"] = None

        # ✅ Save the updated in-memory state
        resume_storage._save_index()

        logger.info(f"Deleted resume ID {resume_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting resume {resume_id}: {str(e)}")
        return False

# Delete a resume
@resume_history_bp.route('/delete_resume/<resume_id>', methods=['POST'])
def delete_resume_route(resume_id):
    try:
        if delete_resume(resume_id):
            flash('Resume deleted successfully', 'success')
        else:
            flash('Resume not found or could not be deleted', 'danger')
    except Exception as e:
        logger.error(f"Error deleting resume: {str(e)}")
        flash(f'Error deleting resume: {str(e)}', 'danger')
    return redirect(url_for('index'))
# Set the active resume
@resume_history_bp.route('/api/set_resume', methods=['POST'])
def set_active_resume():
    try:
        data = request.get_json()
        resume_id = data.get("resume_id")
        if not resume_id or not get_resume(resume_id):
            return jsonify({"success": False, "error": "Invalid or missing resume ID"}), 400
        session["resume_id"] = resume_id
        logger.info("Session updated with resume_id=%s", resume_id)
        return jsonify({"success": True, "resume_id": resume_id})
    except Exception as e:
        logger.error(f"Error setting active resume: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
# === Resume Storage Class ===
# """Initialize the storage object"""
class ResumeStorage:
    def __init__(self):
        self._index = {}
        self._initialize_resume_index()
    # """Ensure resume directory and index file exist"""
    def _initialize_resume_index(self):
        os.makedirs(RESUME_DIR, exist_ok=True)
        if not os.path.exists(RESUME_INDEX_FILE):
            self._index = {"resumes": {}, "count": 0, "last_added": None}
            self._save_index()
        else:
            self._load_index()
    # """Load resume index into memory"""
    def _load_index(self):
        try:
            with open(RESUME_INDEX_FILE, 'r', encoding='utf-8') as f:
                self._index = json.load(f)
        except Exception as e:
            logger.error(f"Error loading resume index: {str(e)}")
            self._index = {"resumes": {}, "count": 0, "last_added": None}
    # """Save resume index from memory to disk"""
    def _save_index(self):
        _save_index(self._index)
    # """Scan for content files not in index and restore them"""
    def _recover_missing_resumes(self):
        try:
            content_files = [f for f in os.listdir(RESUME_DIR) if f.endswith('_content.txt')]
            for content_file in content_files:
                resume_id = content_file.split('_')[0]
                if resume_id in self._index["resumes"]:
                    continue
                resume_files = [f for f in os.listdir(RESUME_DIR) if f.startswith(resume_id + '_') and not f.endswith('_content.txt')]
                if not resume_files:
                    continue
                original_filename = resume_files[0][len(resume_id) + 1:]
                content_path = os.path.join(RESUME_DIR, content_file)
                with open(content_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                resume_metadata = {
                    "id": resume_id,
                    "original_filename": original_filename,
                    "stored_filename": resume_files[0],
                    "upload_date": datetime.fromtimestamp(os.path.getctime(content_path)).isoformat(),
                    "content_preview": content[:200] + "..." if len(content) > 200 else content,
                    "file_extension": os.path.splitext(original_filename)[1].lower(),
                }
                self._index["resumes"][resume_id] = resume_metadata
                self._index["count"] = len(self._index["resumes"])
                if not self._index["last_added"] or os.path.getctime(content_path) > os.path.getctime(os.path.join(RESUME_DIR, f"{self._index['last_added']}_content.txt")):
                    self._index["last_added"] = resume_id
                logger.info(f"Recovered resume {original_filename} with ID {resume_id}")
        except Exception as e:
            logger.error(f"Error recovering missing resumes: {str(e)}")
    # """Store a resume permanently and update index"""
    def store_resume(self, temp_filepath: str, filename: str, content: str, metadata: Optional[Dict] = None) -> str:
        try:
            resume_id = str(uuid.uuid4())
            if metadata is None:
                metadata = {}
            resume_metadata = {
                "id": resume_id,
                "original_filename": filename,
                "stored_filename": f"{resume_id}_{filename}",
                "upload_date": datetime.now().isoformat(),
                "content_preview": content[:200] + "..." if len(content) > 200 else content,
                "file_extension": os.path.splitext(filename)[1].lower(),
                **metadata
            }
            dest_filepath = os.path.join(RESUME_DIR, resume_metadata["stored_filename"])
            shutil.copy2(temp_filepath, dest_filepath)
            content_filepath = os.path.join(RESUME_DIR, f"{resume_id}_content.txt")
            with open(content_filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            self._index["resumes"][resume_id] = resume_metadata
            self._index["count"] += 1
            self._index["last_added"] = resume_id
            self._save_index()
            logger.info(f"Resume {filename} stored with ID {resume_id}")
            return resume_id
        except Exception as e:
            logger.error(f"Error storing resume: {str(e)}")
            raise
# === Singleton Instance ===
resume_storage = ResumeStorage()
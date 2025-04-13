# resume_storage.py - Module for managing persistent resume storage
import os
import json
import uuid
import logging
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Any

# Set up logging
logger = logging.getLogger(__name__)

# Storage paths
RESUME_DIR = os.path.join(os.path.dirname(__file__), 'static', 'resumes')
RESUME_INDEX_FILE = os.path.join(RESUME_DIR, 'index.json')
# Class for managing resume storage
class ResumeStorage:
  def __init__(self):
    """Initialize the storage"""
    self._index = {}
    self._initialize_resume_index()

  def _initialize_resume_index(self):
    """Initialize the resume index file"""
    # Create directory if it doesn't exist
    os.makedirs(RESUME_DIR, exist_ok=True)

    # Create index file if it doesn't exist
    if not os.path.exists(RESUME_INDEX_FILE):
      self._index = {"resumes": {}, "count": 0, "last_added": None}
      self._save_index()
    else:
      self._load_index()
  """Load the resume index from file"""
  def _load_index(self) -> Dict:
    try:
      with open(RESUME_INDEX_FILE, 'r', encoding='utf-8') as f:
        self._index = json.load(f)
      # Ensure the index has all required keys
      if "resumes" not in self._index:
        self._index["resumes"] = {}
      if "count" not in self._index:
        self._index["count"] = 0
      if "last_added" not in self._index:
        self._index["last_added"] = None
      # Scan the resumes directory to find any resumes not in the index
      # This helps recover from any previous index save failures
      self._recover_missing_resumes()
      return self._index
    except Exception as e:
      logger.error(f"Error loading resume index: {str(e)}")
      # If index file is corrupted, create a new one
      self._index = {"resumes": {}, "count": 0, "last_added": None}
      # Scan the resumes directory to find and recover resumes
      self._recover_missing_resumes()
      self._save_index()
      logger.info("Resumes loaded from index")
      return self._index

  def _recover_missing_resumes(self):
    """Scan the resume directory to find any files not in the index"""
    try:
      # Get all content files in the resume directory
      content_files = [f for f in os.listdir(RESUME_DIR) if f.endswith('_content.txt')]
      # Extract resume IDs from the content file names
      for content_file in content_files:
        resume_id = content_file.split('_')[0]
        # Check if this resume is already in the index
        if resume_id in self._index["resumes"]:
          continue
        # Find the corresponding resume file
        resume_files = [f for f in os.listdir(RESUME_DIR) if f.startswith(resume_id + '_') and not f.endswith('_content.txt')]
        if not resume_files:
          continue
        # Get original filename (remove resume ID prefix)
        original_filename = resume_files[0][len(resume_id) + 1:]
        # Read content
        content_path = os.path.join(RESUME_DIR, content_file)
        with open(content_path, 'r', encoding='utf-8') as f:
          content = f.read()
        # Create metadata
        resume_metadata = {
          "id": resume_id,
          "original_filename": original_filename,
          "stored_filename": resume_files[0],
          "upload_date": datetime.fromtimestamp(os.path.getctime(content_path)).isoformat(),
          "content_preview": content[:200] + "..." if len(content) > 200 else content,
          "file_extension": os.path.splitext(original_filename)[1].lower(),
        }
        # Add to index
        self._index["resumes"][resume_id] = resume_metadata
        self._index["count"] = len(self._index["resumes"])
        if not self._index["last_added"] or os.path.getctime(content_path) > os.path.getctime(os.path.join(RESUME_DIR, f"{self._index['last_added']}_content.txt")):
          self._index["last_added"] = resume_id

        logger.info(f"Recovered resume {original_filename} with ID {resume_id}")
    except Exception as e:
      logger.error(f"Error recovering missing resumes: {str(e)}")

  def _save_index(self):
    """Save the resume index to file"""
    try:
      # Create a deep copy of the index to avoid modifying the original
      index_copy = {"resumes": {}, "count": self._index["count"], "last_added": self._index["last_added"]}

      # Convert any NumPy arrays to lists in the resume metadata
      for resume_id, resume_data in self._index["resumes"].items():
        resume_copy = resume_data.copy()

        # If there's an embedding, convert it to a list if it's a NumPy array
        if "embedding" in resume_copy and hasattr(resume_copy["embedding"], "tolist"):
          resume_copy["embedding"] = resume_copy["embedding"].tolist()

        index_copy["resumes"][resume_id] = resume_copy

      # Save the processed index to file
      with open(RESUME_INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index_copy, f, indent=2)

    except Exception as e:
      logger.error(f"Error saving resume index: {str(e)}")

  # Store a resume file in the permanent storage
  def store_resume(self, temp_filepath: str, filename: str, content: str, metadata: Optional[Dict] = None) -> str:
    try:
      # Generate unique ID
      resume_id = str(uuid.uuid4())
      # Create metadata dictionary
      if metadata is None:
        metadata = {}
      resume_metadata = {"id": resume_id, "original_filename": filename, "stored_filename": f"{resume_id}_{filename}", "upload_date": datetime.now().isoformat(), "content_preview": content[:200] + "..." if len(content) > 200 else content, "file_extension": os.path.splitext(filename)[1].lower(), **metadata}
      # Copy the file to permanent storage
      dest_filepath = os.path.join(RESUME_DIR, resume_metadata["stored_filename"])
      shutil.copy2(temp_filepath, dest_filepath)
      # Save content to a text file for full-text storage
      content_filepath = os.path.join(RESUME_DIR, f"{resume_id}_content.txt")
      with open(content_filepath, 'w', encoding='utf-8') as f:
        f.write(content)
      # Update index
      self._index["resumes"][resume_id] = resume_metadata
      self._index["count"] += 1
      self._index["last_added"] = resume_id
      self._save_index()
      logger.info(f"Resume {filename} stored with ID {resume_id}")
      logger.info("store_resume returning with self=%s, temp_filepath=%s, filename=%s, content=%s, metadata=%s", self, temp_filepath, filename, content, metadata)
      return resume_id
    except Exception as e:
      logger.error(f"Error storing resume: {str(e)}")
      raise

  # Get all stored resumes
  def get_all_resumes(self) -> List[Dict]:
    try:
      # Load index
      self._load_index()
      # Sort resumes by upload date (newest first)
      resumes = list(self._index["resumes"].values())
      resumes.sort(key=lambda r: r.get("upload_date", ""), reverse=True)
      logger.info("get_all_resumes returning with self=%s", self)
      return resumes
    except Exception as e:
      logger.error(f"Error getting all resumes: {str(e)}")
      logger.info("get_all_resumes returning with self=%s", self)
      return []

  # Get a specific resume's metadata
  def get_resume(self, resume_id: str) -> Optional[Dict]:
    try:
      # Load index
      self._load_index()
      logger.info("get_resume returning with self=%s, resume_id=%s", self, resume_id)
      # Return resume metadata
      return self._index["resumes"].get(resume_id)
    except Exception as e:
      logger.error(f"Error getting resume {resume_id}: {str(e)}")
      logger.info("get_resume returning with self=%s, resume_id=%s", self, resume_id)
      return None

  # Get the content of a resume
  def get_resume_content(self, resume_id: str) -> Optional[str]:
    try:
      # Get resume metadata
      resume = self.get_resume(resume_id)
      if not resume:
        logger.info("get_resume_content returning with self=%s, resume_id=%s", self, resume_id)
        return None
      # Load content from file
      content_filepath = os.path.join(RESUME_DIR, f"{resume_id}_content.txt")
      if not os.path.exists(content_filepath):
        logger.warning(f"Content file for resume {resume_id} not found")
        logger.info("get_resume_content returning with self=%s, resume_id=%s", self, resume_id)
        return None
      with open(content_filepath, 'r', encoding='utf-8') as f:
        logger.info("get_resume_content returning with self=%s, resume_id=%s", self, resume_id)
        return f.read()
    except Exception as e:
      logger.error(f"Error getting resume content for {resume_id}: {str(e)}")
      logger.info("get_resume_content returning with self=%s, resume_id=%s", self, resume_id)
      return None

  # Delete a resume
  def delete_resume(self, resume_id: str) -> bool:
    try:
      # Load index
      self._load_index()
      # Check if resume exists
      if resume_id not in self._index["resumes"]:
        logger.warning(f"Resume {resume_id} not found for deletion")
        logger.info("delete_resume returning with self=%s, resume_id=%s", self, resume_id)
        return False
      # Get resume metadata
      resume = self._index["resumes"][resume_id]
      # Delete files
      stored_filepath = os.path.join(RESUME_DIR, resume["stored_filename"])
      content_filepath = os.path.join(RESUME_DIR, f"{resume_id}_content.txt")
      if os.path.exists(stored_filepath):
        os.remove(stored_filepath)
      if os.path.exists(content_filepath):
        os.remove(content_filepath)
      # Update index
      del self._index["resumes"][resume_id]
      self._index["count"] -= 1
      # Update last_added if needed
      if self._index["last_added"] == resume_id:
        if self._index["resumes"]:
          # Set to most recent remaining resume
          newest = max(self._index["resumes"].values(), key=lambda r: r.get("upload_date", ""))
          self._index["last_added"] = newest["id"]
        else:
          self._index["last_added"] = None
      # Save index
      self._save_index()
      logger.info(f"Resume {resume_id} deleted")
      logger.info("delete_resume returning with self=%s, resume_id=%s", self, resume_id)
      return True
    except Exception as e:
      logger.error(f"Error deleting resume {resume_id}: {str(e)}")
      logger.info("delete_resume returning with self=%s, resume_id=%s", self, resume_id)
      return False
# Global instance
resume_storage = ResumeStorage()

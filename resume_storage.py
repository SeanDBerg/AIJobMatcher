"""
Module for managing persistent resume storage
"""
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

class ResumeStorage:
    """Class for managing resume storage"""
    
    def __init__(self):
        """Initialize the storage"""
        self._index = {}
        self._initialize_index()
    
    def _initialize_index(self):
        """Initialize the resume index file"""
        # Create directory if it doesn't exist
        os.makedirs(RESUME_DIR, exist_ok=True)
        
        # Create index file if it doesn't exist
        if not os.path.exists(RESUME_INDEX_FILE):
            self._index = {
                "resumes": {},
                "count": 0,
                "last_added": None
            }
            self._save_index()
        else:
            self._load_index()
    
    def _load_index(self) -> Dict:
        """Load the resume index from file"""
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
                
            return self._index
        except Exception as e:
            logger.error(f"Error loading resume index: {str(e)}")
            # If index file is corrupted, create a new one
            self._index = {
                "resumes": {},
                "count": 0,
                "last_added": None
            }
            self._save_index()
            return self._index
    
    def _save_index(self):
        """Save the resume index to file"""
        try:
            with open(RESUME_INDEX_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._index, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving resume index: {str(e)}")
    
    def store_resume(self, temp_filepath: str, filename: str, content: str, metadata: Optional[Dict] = None) -> str:
        """
        Store a resume file in the permanent storage
        
        Args:
            temp_filepath: Temporary file path
            filename: Original filename
            content: Text content of the resume
            metadata: Optional metadata dictionary
            
        Returns:
            resume_id: Unique ID for the saved resume
        """
        try:
            # Generate unique ID
            resume_id = str(uuid.uuid4())
            
            # Create metadata dictionary
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
            return resume_id
            
        except Exception as e:
            logger.error(f"Error storing resume: {str(e)}")
            raise
    
    def get_all_resumes(self) -> List[Dict]:
        """
        Get all stored resumes
        
        Returns:
            List of resume metadata dictionaries
        """
        try:
            # Load index
            self._load_index()
            
            # Sort resumes by upload date (newest first)
            resumes = list(self._index["resumes"].values())
            resumes.sort(key=lambda r: r.get("upload_date", ""), reverse=True)
            
            return resumes
            
        except Exception as e:
            logger.error(f"Error getting all resumes: {str(e)}")
            return []
    
    def get_resume(self, resume_id: str) -> Optional[Dict]:
        """
        Get a specific resume's metadata
        
        Args:
            resume_id: Resume ID
            
        Returns:
            Resume metadata dictionary or None if not found
        """
        try:
            # Load index
            self._load_index()
            
            # Return resume metadata
            return self._index["resumes"].get(resume_id)
            
        except Exception as e:
            logger.error(f"Error getting resume {resume_id}: {str(e)}")
            return None
    
    def get_resume_content(self, resume_id: str) -> Optional[str]:
        """
        Get the content of a resume
        
        Args:
            resume_id: Resume ID
            
        Returns:
            Resume content or None if not found
        """
        try:
            # Get resume metadata
            resume = self.get_resume(resume_id)
            if not resume:
                return None
                
            # Load content from file
            content_filepath = os.path.join(RESUME_DIR, f"{resume_id}_content.txt")
            if not os.path.exists(content_filepath):
                logger.warning(f"Content file for resume {resume_id} not found")
                return None
                
            with open(content_filepath, 'r', encoding='utf-8') as f:
                return f.read()
                
        except Exception as e:
            logger.error(f"Error getting resume content for {resume_id}: {str(e)}")
            return None
    
    def delete_resume(self, resume_id: str) -> bool:
        """
        Delete a resume
        
        Args:
            resume_id: Resume ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Load index
            self._load_index()
            
            # Check if resume exists
            if resume_id not in self._index["resumes"]:
                logger.warning(f"Resume {resume_id} not found for deletion")
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
                    newest = max(
                        self._index["resumes"].values(),
                        key=lambda r: r.get("upload_date", "")
                    )
                    self._index["last_added"] = newest["id"]
                else:
                    self._index["last_added"] = None
            
            # Save index
            self._save_index()
            
            logger.info(f"Resume {resume_id} deleted")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting resume {resume_id}: {str(e)}")
            return False

# Global instance
resume_storage = ResumeStorage()
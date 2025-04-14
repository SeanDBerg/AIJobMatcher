"""
JobManager - Unified interface for job data management.
Replaces redundant functions across different modules with a single, streamlined interface.
"""
import os
import json
import logging
import uuid
from typing import List, Dict, Optional, Set
from datetime import datetime
from logic.b_jobs.jobMatch import Job
# Set up logging
logger = logging.getLogger(__name__)

# Constants
ADZUNA_API_BASE_URL = "https://api.adzuna.com/v1/api"
# Custom exception for Adzuna API errors
class AdzunaAPIError(Exception):
  pass
# Unified manager for job data
class JobManager:
  # Singleton instance
  _instance = None

  def __new__(cls):
    """Ensure only one instance of JobManager exists (singleton pattern)"""
    if cls._instance is None:
      cls._instance = super(JobManager, cls).__new__(cls)
      cls._instance._initialized = False
    return cls._instance

  def _create_empty_index(self) -> None:
    """Create an empty index file"""
    empty_index = {"batches": {}, "job_count": 0, "last_sync": None, "last_batch": None}

    try:
      with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(empty_index, f, indent=2)

      logger.debug("Created new empty index file")
    except Exception as e:
      logger.error(f"Error creating index file: {str(e)}")

  def save_index(self, index: Dict) -> bool:
    """
        Save index to disk and update cache
        
        Args:
            index: Dictionary containing the job index
            
        Returns:
            True if successful, False otherwise
        """
    try:
      with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2)

      # Update cache
      self._index_cache = index
      self._index_cache_timestamp = datetime.now()

      logger.debug("Saved index to disk")
      return True

    except Exception as e:
      logger.error(f"Error saving index: {str(e)}")
      return False

  def _save_job_batch(self, jobs: List[Dict], batch_id: str) -> bool:
    """
        Save a batch of jobs to disk
        
        Args:
            jobs: List of job dictionaries
            batch_id: ID to use for the batch
            
        Returns:
            True if successful, False otherwise
        """
    batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")

    try:
      with open(batch_file, 'w', encoding='utf-8') as f:
        json.dump(jobs, f, indent=2)

      logger.debug(f"Saved batch {batch_id} with {len(jobs)} jobs")
      return True

    except Exception as e:
      logger.error(f"Error saving batch {batch_id}: {str(e)}")
      return False

  def get_api_credentials(self) -> tuple:
    """
        Get Adzuna API credentials from environment variables
        
        Returns:
            Tuple of (app_id, api_key)
            
        Raises:
            AdzunaAPIError: If credentials are not configured
        """
    app_id = os.environ.get('ADZUNA_APP_ID')
    api_key = os.environ.get('ADZUNA_API_KEY')

    if not app_id or not api_key:
      raise AdzunaAPIError("Adzuna API credentials are not configured. Please set ADZUNA_APP_ID and ADZUNA_API_KEY environment variables.")

    return app_id, api_key

  def check_api_status(self) -> bool:
    """
        Check if Adzuna API credentials are properly configured
        
        Returns:
            True if credentials are available, False otherwise
        """
    try:
      self.get_api_credentials()
      return True
    except AdzunaAPIError:
      return False

  def extract_skills_from_job(self, job_data: Dict, known_skills: Optional[Set[str]] = None) -> List[str]:
    """
        Extract skills from job data
        
        Args:
            job_data: Job data dictionary
            known_skills: Optional set of known skills to check against
            
        Returns:
            List of skills
        """
    skills = []

    # Try to use category tag from the API
    if "category" in job_data and "tag" in job_data["category"]:
      category = job_data["category"]["tag"].lower()

      # Extract programming languages and technologies from IT job categories
      if "it" in category or "software" in category or "developer" in category:
        tech_skills = ["python", "java", "javascript", "typescript", "ruby", "php", "c#", "c++", "go", "rust", "swift", "kotlin", "react", "angular", "vue", "node.js", "django", "flask", "spring", "aws", "azure", "gcp", "docker", "kubernetes", "sql", "mongodb", "postgresql", "mysql", "oracle", "redis", "elasticsearch"]

        description = job_data.get("description", "").lower()
        title = job_data.get("title", "").lower()

        # Check for skills in description
        for skill in tech_skills:
          if skill in description or skill in title:
            if skill not in skills:
              skills.append(skill)

    # Use matching_engine.extract_skills if no skills found and known_skills provided
    if not skills and known_skills:
      try:
        from matching_engine import extract_skills
        description = job_data.get("description", "")
        extracted_skills = extract_skills(description, known_skills)
        skills.extend(extracted_skills)
      except ImportError:
        logger.warning("Could not import extract_skills from matching_engine")

    return list(set(skills)) # Remove duplicates

  def store_jobs(self, jobs: List[Job], keywords: Optional[str] = None, location: Optional[str] = None, country: str = "gb", max_days_old: int = 30) -> int:
    """
        Store jobs in a new batch
        
        Args:
            jobs: List of Job objects
            keywords: Search keywords used
            location: Location used
            country: Country code
            max_days_old: Maximum age of jobs in days
            
        Returns:
            Number of jobs stored
        """
    try:
      # Convert Job objects to dictionaries
      job_dicts = [job.to_dict() for job in jobs]

      # Generate batch ID
      batch_id = str(uuid.uuid4())

      # Create batch info
      batch_info = {"id": batch_id, "timestamp": datetime.now().isoformat(), "keywords": keywords, "location": location, "country": country, "job_count": len(job_dicts), "max_days_old": max_days_old}

      # Save batch of jobs
      if self._save_job_batch(job_dicts, batch_id):
        # Update index
        index = self.get_index(force_refresh=True)
        index["batches"][batch_id] = batch_info
        index["job_count"] += len(job_dicts)
        index["last_sync"] = datetime.now().isoformat()
        index["last_batch"] = batch_id
        self.save_index(index)

        # Clear jobs cache
        self._jobs_cache = None

        logger.info(f"Saved {len(job_dicts)} jobs to batch {batch_id}")
        return len(job_dicts)
      else:
        logger.error(f"Failed to save job batch {batch_id}")
        return 0

    except Exception as e:
      logger.error(f"Error storing jobs: {str(e)}")
      return 0

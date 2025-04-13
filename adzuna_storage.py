# adzuna_storage.py - DEPRECATED - Use job_manager.py instead
# This file is kept for backwards compatibility only.
# All functionality has been consolidated into job_manager.py

import logging
import os
from datetime import datetime
from typing import Dict, List

from models import Job

logger = logging.getLogger(__name__)

# Storage paths
ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), 'static', 'job_data', 'adzuna')
ADZUNA_INDEX_FILE = os.path.join(ADZUNA_DATA_DIR, 'index.json')
"""Class for managing Adzuna job data storage"""
# Global cache to store loaded index and jobs
_GLOBAL_INDEX_CACHE = None
_GLOBAL_JOBS_CACHE = None
_GLOBAL_CACHE_TIMESTAMP = None

class AdzunaStorage:
  def __init__(self):
    """Initialize the storage - DEPRECATED, redirects to JobManager"""
    from job_manager import JobManager
    self._job_manager = JobManager()
    logger.warning("AdzunaStorage is deprecated - use JobManager instead")

  def _initialize_adzuna_index(self):
    """DEPRECATED: Initialize the job index file"""
    # Just delegate to the JobManager
    logger.debug("Using JobManager instead of AdzunaStorage._initialize_adzuna_index")
      
  def _load_index(self) -> Dict:
    """DEPRECATED: Load the index from JobManager"""
    logger.debug("Using JobManager instead of AdzunaStorage._load_index")
    self._index = self._job_manager.get_index()
    return self._index

  def _save_index(self):
    """DEPRECATED: Save the index with JobManager"""
    logger.debug("Using JobManager instead of AdzunaStorage._save_index")
    # Saves are now handled by JobManager

  def _save_job_batch(self, jobs: List[Dict], batch_id: str):
    """DEPRECATED: Save batch with JobManager"""
    logger.debug("Using JobManager instead of AdzunaStorage._save_job_batch")
    return self._job_manager._save_job_batch(jobs, batch_id)
    
  def _load_job_batch(self, batch_id: str) -> List[Dict]:
    """DEPRECATED: Load batch with JobManager"""
    logger.debug("Using JobManager instead of AdzunaStorage._load_job_batch")
    return self._job_manager._load_job_batch(batch_id)

  def store_jobs(self, jobs, keywords=None, location=None, country="gb", max_days_old=30):
    """
    DEPRECATED: Store job objects in a new batch - redirects to JobManager
        
    Args:
        jobs: List of Job objects
        keywords: Search keywords used
        location: Location used
        country: Country code
        max_days_old: Maximum age of jobs in days
            
    Returns:
        Number of jobs stored
    """
    logger.debug("Using JobManager instead of AdzunaStorage.store_jobs")
    return self._job_manager.store_jobs(jobs, keywords, location, country, max_days_old)
  # Get all stored jobs 
  def get_all_jobs(self) -> List[Job]:
    """DEPRECATED: Get all jobs - redirects to JobManager"""
    logger.debug("Using JobManager instead of AdzunaStorage.get_all_jobs")
    return self._job_manager.get_all_jobs()
      
  # Get recent jobs
  def get_recent_jobs(self, days: int = 30) -> List[Job]:
    """DEPRECATED: Get recent jobs - redirects to JobManager"""
    logger.debug("Using JobManager instead of AdzunaStorage.get_recent_jobs")
    return self._job_manager.get_recent_jobs(days)
  # Remove jobs older than a certain age
  def cleanup_old_jobs(self, max_age_days: int = 90) -> int:
    """DEPRECATED: Clean up old jobs - redirects to JobManager"""
    logger.debug("Using JobManager instead of AdzunaStorage.cleanup_old_jobs")
    return self._job_manager.cleanup_old_jobs(max_age_days)
    
  # Get the current sync status
  def get_sync_status(self) -> Dict:
    """DEPRECATED: Get storage status - redirects to JobManager"""
    logger.debug("Using JobManager instead of AdzunaStorage.get_sync_status")
    return self._job_manager.get_storage_status()

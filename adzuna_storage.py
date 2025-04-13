# adzuna_storage.py - DEPRECATED - Use job_manager.py instead
# This file is kept for backward compatibility only.
# All functionality has been consolidated into job_manager.py

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from models import Job
from job_manager import JobManager

logger = logging.getLogger(__name__)

class AdzunaStorage:
    """
    DEPRECATED: Use JobManager instead
    This class is kept for backward compatibility only.
    All methods forward calls to JobManager.
    """
    
    def __init__(self):
        """
        Initialize the AdzunaStorage with a JobManager instance
        """
        logger.warning("AdzunaStorage is deprecated - use JobManager instead")
        self.job_manager = JobManager()
    
    def get_recent_jobs(self, days: int = 30) -> List[Job]:
        """
        DEPRECATED: Get recent jobs - use JobManager.get_recent_jobs() instead
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of Job objects
        """
        logger.warning("AdzunaStorage.get_recent_jobs is deprecated - use JobManager.get_recent_jobs instead")
        return self.job_manager.get_recent_jobs(days)
    
    def store_jobs(self, jobs: List[Job], keywords: Optional[str] = None,
                  location: Optional[str] = None, country: str = "gb",
                  max_days_old: int = 30) -> int:
        """
        DEPRECATED: Store jobs - use JobManager.store_jobs() instead
        
        Args:
            jobs: List of Job objects
            keywords: Search keywords used
            location: Location used
            country: Country code
            max_days_old: Maximum age of jobs in days
            
        Returns:
            Number of jobs stored
        """
        logger.warning("AdzunaStorage.store_jobs is deprecated - use JobManager.store_jobs instead")
        return self.job_manager.store_jobs(
            jobs, 
            keywords=keywords, 
            location=location, 
            country=country, 
            max_days_old=max_days_old
        )
    
    def cleanup_old_jobs(self, max_age_days: int = 90) -> int:
        """
        DEPRECATED: Clean up old jobs - use JobManager.cleanup_old_jobs() instead
        
        Args:
            max_age_days: Maximum age of jobs to keep in days
            
        Returns:
            Number of jobs removed
        """
        logger.warning("AdzunaStorage.cleanup_old_jobs is deprecated - use JobManager.cleanup_old_jobs instead")
        return self.job_manager.cleanup_old_jobs(max_age_days)
    
    def get_sync_status(self) -> Dict[str, Any]:
        """
        DEPRECATED: Get storage status - use JobManager.get_storage_status() instead
        
        Returns:
            Dictionary with status information including job count, batch count, etc.
        """
        logger.warning("AdzunaStorage.get_sync_status is deprecated - use JobManager.get_storage_status instead")
        return self.job_manager.get_storage_status()
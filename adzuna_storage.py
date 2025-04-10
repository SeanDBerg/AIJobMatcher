"""
Module for managing Adzuna job data storage in JSON format with batch organization
"""
import os
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union

from models import Job

logger = logging.getLogger(__name__)

# Storage paths
ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), 'static', 'job_data', 'adzuna')
ADZUNA_INDEX_FILE = os.path.join(ADZUNA_DATA_DIR, 'index.json')

class AdzunaStorage:
    """Class for managing Adzuna job data storage"""
    
    def __init__(self):
        """Initialize the storage"""
        self._index = {}
        self._initialize_index()
    
    def _initialize_index(self):
        """Initialize the job index file"""
        # Create directory if it doesn't exist
        os.makedirs(ADZUNA_DATA_DIR, exist_ok=True)
        
        # Create index file if it doesn't exist
        if not os.path.exists(ADZUNA_INDEX_FILE):
            self._index = {
                "batches": {},
                "job_count": 0,
                "last_sync": None,
                "last_batch": None
            }
            self._save_index()
        else:
            self._load_index()
    
    def _load_index(self) -> Dict:
        """Load the job index from file"""
        try:
            with open(ADZUNA_INDEX_FILE, 'r', encoding='utf-8') as f:
                self._index = json.load(f)
            return self._index
        except Exception as e:
            logger.error(f"Error loading Adzuna index: {str(e)}")
            # If index file is corrupted, create a new one
            self._index = {
                "batches": {},
                "job_count": 0,
                "last_sync": None,
                "last_batch": None
            }
            self._save_index()
            return self._index
    
    def _save_index(self):
        """Save the job index to file"""
        try:
            with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._index, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving Adzuna index: {str(e)}")
    
    def _save_job_batch(self, jobs: List[Dict], batch_id: str):
        """Save a batch of jobs to a separate file"""
        try:
            batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
            with open(batch_file, 'w', encoding='utf-8') as f:
                json.dump(jobs, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving job batch {batch_id}: {str(e)}")
            return False
    
    def _load_job_batch(self, batch_id: str) -> List[Dict]:
        """Load a batch of jobs from a file"""
        try:
            batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
            if not os.path.exists(batch_file):
                logger.warning(f"Batch file {batch_id} not found")
                return []
                
            with open(batch_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading job batch {batch_id}: {str(e)}")
            return []
    
    def sync_jobs(
        self,
        keywords: Optional[str] = None,
        location: Optional[str] = None,
        country: str = "gb",
        max_days_old: int = 1,
        append: bool = True,
        max_pages: Optional[int] = None
    ) -> int:
        """
        Sync jobs from Adzuna API and store them locally
        
        Args:
            keywords: Optional keywords to search for
            location: Optional location to search in
            country: Country code (default: 'gb')
            max_days_old: Maximum age of job listings in days (default: 1)
            append: Whether to append to existing jobs or replace (default: True)
            max_pages: Maximum number of pages to fetch (default: None, fetch all)
            
        Returns:
            Number of new jobs added
        """
        try:
            # Import here to avoid circular imports
            from adzuna_api import search_jobs, AdzunaAPIError
            
            # Fetch jobs from API
            try:
                jobs = search_jobs(
                    keywords=keywords,
                    location=location,
                    country=country,
                    max_days_old=max_days_old,
                    page=1,
                    results_per_page=50
                )
                
                if not jobs:
                    logger.warning("No jobs returned from Adzuna API")
                    return 0
                    
            except AdzunaAPIError as e:
                logger.error(f"Adzuna API error: {str(e)}")
                return 0
                
            # Convert Job objects to dictionaries
            job_dicts = [job.to_dict() for job in jobs]
            
            # Generate batch ID
            batch_id = str(uuid.uuid4())
            
            # Create batch info
            batch_info = {
                "id": batch_id,
                "timestamp": datetime.now().isoformat(),
                "keywords": keywords,
                "location": location,
                "country": country,
                "job_count": len(job_dicts),
                "max_days_old": max_days_old
            }
            
            # Save batch of jobs
            if self._save_job_batch(job_dicts, batch_id):
                # Update index
                self._index["batches"][batch_id] = batch_info
                self._index["job_count"] += len(job_dicts)
                self._index["last_sync"] = datetime.now().isoformat()
                self._index["last_batch"] = batch_id
                self._save_index()
                
                logger.info(f"Saved {len(job_dicts)} jobs to batch {batch_id}")
                return len(job_dicts)
            else:
                logger.error(f"Failed to save job batch {batch_id}")
                return 0
                
        except Exception as e:
            logger.error(f"Error syncing jobs: {str(e)}")
            return 0
    
    def get_all_jobs(self) -> List[Job]:
        """
        Get all stored Adzuna jobs
        
        Returns:
            List of Job objects
        """
        try:
            all_jobs = []
            
            # Load index
            self._load_index()
            
            # Loop through batches
            for batch_id in self._index["batches"]:
                batch_jobs = self._load_job_batch(batch_id)
                
                # Convert dictionary to Job objects
                for job_dict in batch_jobs:
                    try:
                        job = Job(
                            title=job_dict["title"],
                            company=job_dict["company"],
                            description=job_dict["description"],
                            location=job_dict["location"],
                            is_remote=job_dict.get("is_remote", False),
                            posted_date=job_dict.get("posted_date"),
                            url=job_dict.get("url", ""),
                            skills=job_dict.get("skills", []),
                            salary_range=job_dict.get("salary_range")
                        )
                        all_jobs.append(job)
                    except Exception as e:
                        logger.error(f"Error creating Job object: {str(e)}")
                        continue
            
            return all_jobs
            
        except Exception as e:
            logger.error(f"Error getting all jobs: {str(e)}")
            return []
    
    def get_recent_jobs(self, days: int = 30) -> List[Job]:
        """
        Get jobs posted within the last X days
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of Job objects
        """
        try:
            all_jobs = self.get_all_jobs()
            
            if not all_jobs:
                return []
                
            # Calculate cutoff date
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            # Filter by posted date
            recent_jobs = []
            for job in all_jobs:
                if not job.posted_date:
                    continue
                    
                # Convert string to datetime if needed
                if isinstance(job.posted_date, str):
                    try:
                        job_date = job.posted_date
                        # No need to convert back since we're just comparing
                    except ValueError:
                        continue
                else:
                    job_date = job.posted_date  # Already a datetime or other type
                    
                try:
                    # Compare dates as strings (ISO format allows string comparison)
                    # This works because ISO format dates sort correctly as strings
                    if job_date >= cutoff_date:
                        recent_jobs.append(job)
                except Exception as e:
                    logger.error(f"Error comparing dates: {str(e)}")
                    # Include the job if comparison fails (better to include than exclude)
                    recent_jobs.append(job)
            
            return recent_jobs
            
        except Exception as e:
            logger.error(f"Error getting recent jobs: {str(e)}")
            return []
    
    def cleanup_old_jobs(self, max_age_days: int = 90) -> int:
        """
        Remove jobs older than a certain age
        
        Args:
            max_age_days: Maximum age in days
            
        Returns:
            Number of jobs removed
        """
        try:
            # Load index
            self._load_index()
            
            # Calculate cutoff date
            cutoff_date = (datetime.now() - timedelta(days=max_age_days)).isoformat()
            
            # Track batches and jobs to remove
            batches_to_remove = []
            job_count_removed = 0
            
            # Check each batch
            for batch_id, batch_info in self._index["batches"].items():
                # If batch is older than cutoff, mark for removal
                if batch_info["timestamp"] < cutoff_date:
                    batches_to_remove.append(batch_id)
                    job_count_removed += batch_info["job_count"]
            
            # Remove batches
            for batch_id in batches_to_remove:
                # Remove batch file
                batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
                if os.path.exists(batch_file):
                    os.remove(batch_file)
                
                # Remove from index
                del self._index["batches"][batch_id]
            
            # Update total job count
            self._index["job_count"] -= job_count_removed
            if self._index["job_count"] < 0:
                self._index["job_count"] = 0
            
            # Update last batch
            if self._index["last_batch"] in batches_to_remove:
                self._index["last_batch"] = None
                if self._index["batches"]:
                    # Set to most recent remaining batch
                    self._index["last_batch"] = max(
                        self._index["batches"].items(),
                        key=lambda x: x[1]["timestamp"]
                    )[0]
            
            # Save index
            self._save_index()
            
            logger.info(f"Removed {job_count_removed} jobs from {len(batches_to_remove)} batches")
            return job_count_removed
            
        except Exception as e:
            logger.error(f"Error cleaning up old jobs: {str(e)}")
            return 0
    
    def get_sync_status(self) -> Dict:
        """
        Get the current sync status
        
        Returns:
            Dict with status information
        """
        try:
            # Load index
            self._load_index()
            
            # Get batch and job counts
            batch_count = len(self._index["batches"])
            job_count = self._index["job_count"]
            
            # Get last sync date
            last_sync = self._index["last_sync"]
            
            # Get last batch info
            last_batch = None
            if self._index["last_batch"]:
                last_batch = self._index["last_batch"]
                
            return {
                "batch_count": batch_count,
                "total_jobs": job_count,
                "last_sync": last_sync,
                "last_batch": last_batch
            }
            
        except Exception as e:
            logger.error(f"Error getting sync status: {str(e)}")
            return {
                "batch_count": 0,
                "total_jobs": 0,
                "last_sync": None,
                "last_batch": None,
                "error": str(e)
            }
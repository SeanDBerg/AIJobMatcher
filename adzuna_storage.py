import json
import logging
import os
from datetime import datetime, timedelta
import time
from typing import List, Dict, Optional

from models import Job
from adzuna_api import search_jobs, AdzunaAPIError

logger = logging.getLogger(__name__)

# Path for Adzuna job data
ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), 'static', 'job_data', 'adzuna')
ADZUNA_INDEX_FILE = os.path.join(ADZUNA_DATA_DIR, 'index.json')

# Rate limiting
RATE_LIMIT_CALLS = 20  # API calls per minute
RATE_LIMIT_PERIOD = 60  # seconds

class AdzunaStorage:
    """Class for managing Adzuna job data storage"""
    
    def __init__(self):
        # Ensure directory exists
        os.makedirs(ADZUNA_DATA_DIR, exist_ok=True)
        
        # Initialize index if it doesn't exist
        if not os.path.exists(ADZUNA_INDEX_FILE):
            self._initialize_index()
        
        # Load index
        self.index = self._load_index()
    
    def _initialize_index(self):
        """Initialize the job index file"""
        index = {
            "last_sync": None,
            "total_jobs": 0,
            "jobs": []
        }
        with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2)
    
    def _load_index(self) -> Dict:
        """Load the job index from file"""
        try:
            with open(ADZUNA_INDEX_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error loading index: {str(e)}")
            self._initialize_index()
            return self._load_index()
    
    def _save_index(self):
        """Save the job index to file"""
        with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, indent=2)
    
    def _save_job_batch(self, jobs: List[Dict], batch_id: str):
        """Save a batch of jobs to a separate file"""
        batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
        with open(batch_file, 'w', encoding='utf-8') as f:
            json.dump(jobs, f, indent=2)
        return batch_file
    
    def _load_job_batch(self, batch_id: str) -> List[Dict]:
        """Load a batch of jobs from a file"""
        batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
        try:
            with open(batch_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.error(f"Job batch file not found or invalid: {batch_id}")
            return []
    
    def sync_jobs(self, keywords=None, location=None, country="gb", 
                  max_days_old=1, append=True, max_pages=None) -> Dict:
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
            Dict with sync results
        """
        results = {
            "status": "success",
            "total_jobs": 0,
            "new_jobs": 0,
            "pages_fetched": 0,
            "timestamp": datetime.now().isoformat()
        }
        
        # Rate limiting setup
        call_count = 0
        start_time = time.time()
        
        # Get existing job IDs if appending
        existing_job_ids = set()
        if append:
            for job_entry in self.index.get("jobs", []):
                job_id = job_entry.get("id")
                if job_id:
                    existing_job_ids.add(job_id)
        
        # Start with an empty job list if not appending
        if not append:
            self.index["jobs"] = []
        
        try:
            page = 1
            total_new_jobs = 0
            
            while True:
                # Rate limiting - enforce maximum 20 calls per minute
                call_count += 1
                if call_count >= RATE_LIMIT_CALLS:
                    elapsed = time.time() - start_time
                    if elapsed < RATE_LIMIT_PERIOD:
                        sleep_time = RATE_LIMIT_PERIOD - elapsed
                        logger.info(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
                        time.sleep(sleep_time)
                    call_count = 0
                    start_time = time.time()
                
                # Fetch jobs for current page
                logger.info(f"Fetching Adzuna jobs, page {page}")
                jobs = search_jobs(
                    keywords=keywords,
                    location=location,
                    country=country,
                    max_days_old=max_days_old,
                    page=page,
                    results_per_page=50
                )
                
                # Break if no jobs found
                if not jobs:
                    logger.info(f"No more jobs found, stopping at page {page}")
                    break
                
                # Get unique jobs
                batch_jobs = []
                for job in jobs:
                    job_dict = job.to_dict()
                    
                    # Generate a unique ID based on title, company and URL
                    job_id = f"{job.title}_{job.company}_{job.url}".replace(" ", "_")[:100]
                    
                    # Skip if job already exists and we're appending
                    if append and job_id in existing_job_ids:
                        continue
                    
                    # Add to batch and update existing set
                    job_dict["id"] = job_id
                    job_dict["fetched_date"] = datetime.now().isoformat()
                    batch_jobs.append(job_dict)
                    existing_job_ids.add(job_id)
                
                # If we have new jobs, save them to a batch file
                if batch_jobs:
                    batch_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{page}"
                    batch_file = self._save_job_batch(batch_jobs, batch_id)
                    
                    # Add batch reference to index
                    for job_dict in batch_jobs:
                        self.index["jobs"].append({
                            "id": job_dict["id"],
                            "title": job_dict["title"],
                            "company": job_dict["company"],
                            "batch": batch_id,
                            "posted_date": job_dict["posted_date"],
                            "fetched_date": job_dict["fetched_date"]
                        })
                    
                    total_new_jobs += len(batch_jobs)
                
                # Update index for each page
                self.index["last_sync"] = datetime.now().isoformat()
                self.index["total_jobs"] = len(self.index["jobs"])
                self._save_index()
                
                # Increment page and check limits
                page += 1
                results["pages_fetched"] = page - 1
                
                if max_pages and page > max_pages:
                    logger.info(f"Reached maximum number of pages ({max_pages}), stopping")
                    break
            
            # Final index update
            self.index["last_sync"] = datetime.now().isoformat()
            self.index["total_jobs"] = len(self.index["jobs"])
            self._save_index()
            
            results["total_jobs"] = self.index["total_jobs"]
            results["new_jobs"] = total_new_jobs
            
            return results
            
        except AdzunaAPIError as e:
            logger.error(f"Adzuna API error during sync: {str(e)}")
            results["status"] = "error"
            results["error"] = str(e)
            return results
        except Exception as e:
            logger.error(f"Error during job sync: {str(e)}")
            results["status"] = "error"
            results["error"] = str(e)
            return results
    
    def get_all_jobs(self) -> List[Job]:
        """
        Get all stored Adzuna jobs
        
        Returns:
            List of Job objects
        """
        all_jobs = []
        
        # Process index entries
        for job_entry in self.index.get("jobs", []):
            batch_id = job_entry.get("batch")
            if not batch_id:
                continue
            
            # Get all jobs from the batch
            batch_jobs = self._load_job_batch(batch_id)
            if not batch_jobs:
                continue
            
            # Find the matching job in the batch
            for job_dict in batch_jobs:
                if job_dict.get("id") == job_entry.get("id"):
                    # Convert to Job object
                    try:
                        # Parse the date
                        posted_date = None
                        if job_dict.get('posted_date'):
                            try:
                                posted_date = datetime.fromisoformat(job_dict['posted_date'])
                            except (ValueError, TypeError):
                                pass
                        
                        job = Job(
                            title=job_dict.get('title', ''),
                            company=job_dict.get('company', ''),
                            description=job_dict.get('description', ''),
                            location=job_dict.get('location', ''),
                            is_remote=job_dict.get('is_remote', False),
                            posted_date=posted_date,
                            url=job_dict.get('url', ''),
                            skills=job_dict.get('skills', []),
                            salary_range=job_dict.get('salary_range', '')
                        )
                        all_jobs.append(job)
                    except Exception as e:
                        logger.error(f"Error creating job object: {str(e)}")
                    
                    break
        
        return all_jobs
    
    def get_recent_jobs(self, days: int = 30) -> List[Job]:
        """
        Get jobs posted within the last X days
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of Job objects
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        recent_jobs = []
        for job in self.get_all_jobs():
            if job.posted_date and job.posted_date >= cutoff_date:
                recent_jobs.append(job)
        
        return recent_jobs
    
    def cleanup_old_jobs(self, max_age_days: int = 90) -> int:
        """
        Remove jobs older than a certain age
        
        Args:
            max_age_days: Maximum age in days
            
        Returns:
            Number of jobs removed
        """
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        cutoff_date_str = cutoff_date.isoformat()
        
        # Find entries to remove
        entries_to_remove = []
        for job_entry in self.index.get("jobs", []):
            posted_date_str = job_entry.get("posted_date")
            if posted_date_str and posted_date_str < cutoff_date_str:
                entries_to_remove.append(job_entry)
        
        # Remove entries
        for entry in entries_to_remove:
            self.index["jobs"].remove(entry)
        
        # Update index
        self.index["total_jobs"] = len(self.index["jobs"])
        self._save_index()
        
        return len(entries_to_remove)
    
    def get_sync_status(self) -> Dict:
        """
        Get the current sync status
        
        Returns:
            Dict with status information
        """
        last_sync = None
        if self.index.get("last_sync"):
            try:
                last_sync = datetime.fromisoformat(self.index["last_sync"])
            except (ValueError, TypeError):
                pass
        
        return {
            "last_sync": last_sync,
            "total_jobs": self.index.get("total_jobs", 0),
            "last_batch": self.index.get("jobs", [])[-1]["batch"] if self.index.get("jobs") else None
        }
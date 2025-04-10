"""
Adzuna job scraping module for bulk job retrieval with rate limiting
"""
import logging
import os
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Union, Tuple, Any

from adzuna_api import search_jobs, get_api_credentials, AdzunaAPIError, extract_skills_from_adzuna
from models import Job
from adzuna_storage import AdzunaStorage

logger = logging.getLogger(__name__)

# Initialize storage
_adzuna_storage = AdzunaStorage()

# Rate limiting constants
RATE_LIMIT_CALLS = 20  # 20 calls per minute
RATE_LIMIT_PERIOD = 60  # 60 seconds

def check_adzuna_api_status() -> bool:
    """
    Check if Adzuna API credentials are properly configured
    
    Returns:
        bool: True if credentials are available, False otherwise
    """
    try:
        get_api_credentials()
        return True
    except AdzunaAPIError:
        return False

def sync_jobs_from_adzuna(
    keywords: Optional[str] = None, 
    location: Optional[str] = None, 
    country: str = "gb", 
    max_pages: Optional[int] = None
) -> Dict[str, Any]:
    """
    Sync jobs from Adzuna API, with pagination and rate limiting
    
    Args:
        keywords: Search keywords (optional)
        location: Location to search in (optional)
        country: Country code (default: "gb")
        max_pages: Maximum number of pages to fetch (default: None, fetch all)
        
    Returns:
        dict: Results of the sync operation
    """
    try:
        # Check API credentials
        if not check_adzuna_api_status():
            return {
                "status": "error",
                "error": "Adzuna API credentials not configured",
                "pages_fetched": 0,
                "new_jobs": 0,
                "api_calls": 0
            }
        
        # Prepare rate limiting
        call_timestamps = []
        max_calls_per_period = RATE_LIMIT_CALLS
        period_seconds = RATE_LIMIT_PERIOD
        
        # Tracking variables
        page = 1
        total_pages = 1  # Will be updated after first call
        total_count = 0  # Will be updated after first call
        new_jobs_count = 0
        pages_fetched = 0
        api_calls = 0
        
        # Start time for overall process
        start_time = time.time()
        
        # Loop through pages
        while page <= total_pages and (max_pages is None or page <= max_pages):
            # Apply rate limiting
            current_time = time.time()
            
            # Remove timestamps older than the period
            call_timestamps = [ts for ts in call_timestamps if current_time - ts < period_seconds]
            
            # If we're at the rate limit, wait
            if len(call_timestamps) >= max_calls_per_period:
                # Calculate wait time
                oldest_timestamp = min(call_timestamps)
                wait_time = period_seconds - (current_time - oldest_timestamp) + 0.1  # Add a small buffer
                
                logger.info(f"Rate limit reached. Waiting {wait_time:.2f} seconds before next API call")
                time.sleep(wait_time)
                
                # Recalculate timestamps after waiting
                current_time = time.time()
                call_timestamps = [ts for ts in call_timestamps if current_time - ts < period_seconds]
            
            # Record this call
            call_timestamps.append(current_time)
            api_calls += 1
            
            # Log progress
            logger.info(f"Fetching page {page} of {total_pages if total_pages > 1 else 'unknown'}")
            
            try:
                # Fetch jobs for this page
                jobs = search_jobs(
                    keywords=keywords,
                    location=location,
                    country=country,
                    page=page,
                    results_per_page=50,  # Get maximum results per page
                    max_days_old=30  # Default to 30 days
                )
                
                # If no jobs returned, stop fetching
                if not jobs or len(jobs) == 0:
                    logger.info(f"No more jobs found on page {page}. Stopping pagination.")
                    break
                
                # Update total pages on first call
                if page == 1 and hasattr(jobs, 'total_pages'):
                    total_pages = getattr(jobs, 'total_pages', 1)
                    total_count = getattr(jobs, 'total_count', 0)
                    logger.info(f"Found {total_count} jobs across {total_pages} pages")
                
                # Store jobs for this page
                stored_count = _adzuna_storage.sync_jobs(keywords=keywords, location=location, country=country, append=True)
                # Ensure stored_count is an integer
                if isinstance(stored_count, int):
                    new_jobs_count += stored_count
                
                # Increment counters
                pages_fetched += 1
                page += 1
                
            except AdzunaAPIError as e:
                logger.error(f"Error fetching page {page}: {str(e)}")
                return {
                    "status": "error",
                    "error": str(e),
                    "pages_fetched": pages_fetched,
                    "new_jobs": new_jobs_count,
                    "api_calls": api_calls
                }
            except Exception as e:
                logger.error(f"Unexpected error fetching page {page}: {str(e)}")
                return {
                    "status": "error",
                    "error": f"Unexpected error: {str(e)}",
                    "pages_fetched": pages_fetched,
                    "new_jobs": new_jobs_count,
                    "api_calls": api_calls
                }
        
        # Calculate total time
        total_time = time.time() - start_time
        
        # Return results
        return {
            "status": "success",
            "pages_fetched": pages_fetched,
            "total_pages": total_pages,
            "new_jobs": new_jobs_count,
            "total_jobs": total_count,
            "api_calls": api_calls,
            "time_taken_seconds": round(total_time, 2),
            "message": f"Successfully fetched {pages_fetched} pages with {new_jobs_count} new jobs"
        }
        
    except Exception as e:
        logger.error(f"Error in sync_jobs_from_adzuna: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "pages_fetched": 0,
            "new_jobs": 0,
            "api_calls": 0
        }

def import_adzuna_jobs_to_main_storage(days: int = 30) -> int:
    """
    Import Adzuna jobs into the main job storage
    
    Args:
        days: Number of days to import (default: 30)
        
    Returns:
        int: Number of jobs imported
    """
    try:
        from job_data import add_job
        
        # Get recent jobs from Adzuna storage
        adzuna_jobs = _adzuna_storage.get_recent_jobs(days=days)
        
        logger.info(f"Importing {len(adzuna_jobs)} jobs from Adzuna storage")
        
        # Import each job
        imported_count = 0
        for job in adzuna_jobs:
            try:
                # Convert to dictionary and add to main storage
                job_dict = job.to_dict()
                add_job(job_dict)
                imported_count += 1
            except Exception as e:
                logger.error(f"Error importing job {job.title}: {str(e)}")
                continue
        
        logger.info(f"Successfully imported {imported_count} jobs")
        return imported_count
        
    except ImportError:
        logger.error("job_data module not available for import")
        return 0
    except Exception as e:
        logger.error(f"Error importing Adzuna jobs: {str(e)}")
        return 0

def get_adzuna_jobs(import_to_main: bool = False, days: int = 30) -> List[Job]:
    """
    Get Adzuna jobs from storage
    
    Args:
        import_to_main: Whether to also import to main storage
        days: Number of days to filter by
        
    Returns:
        List of Job objects
    """
    jobs = _adzuna_storage.get_recent_jobs(days=days)
    
    if import_to_main:
        import_adzuna_jobs_to_main_storage(days=days)
        
    return jobs

def cleanup_old_adzuna_jobs(max_age_days: int = 90) -> int:
    """
    Clean up old Adzuna jobs
    
    Args:
        max_age_days: Maximum age in days
        
    Returns:
        Number of jobs removed
    """
    return _adzuna_storage.cleanup_old_jobs(max_age_days=max_age_days)

def get_adzuna_storage_status() -> Dict[str, Any]:
    """
    Get status of Adzuna job storage
    
    Returns:
        Dict with status information
    """
    return _adzuna_storage.get_sync_status()

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Test the scraper
    result = sync_jobs_from_adzuna(
        keywords="python developer",
        location="london",
        country="gb",
        max_pages=1  # Just get one page for testing
    )
    
    print(f"Sync result: {result}")
    
    # Check storage status
    status = get_adzuna_storage_status()
    print(f"Storage status: {status}")
"""
Adzuna job scraping module for bulk job retrieval with rate limiting
"""
import logging
import os
import json
import time
from datetime import datetime, timedelta

from adzuna_storage import AdzunaStorage
from adzuna_api import AdzunaAPIError, get_api_credentials
from job_data import add_job
from models import Job

logger = logging.getLogger(__name__)

def check_adzuna_api_status():
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

def sync_jobs_from_adzuna(keywords=None, location=None, country="gb", max_pages=None):
    """
    Sync jobs from Adzuna API, with pagination and rate limiting
    
    Args:
        keywords: Search keywords (optional)
        location: Location to search in (optional)
        country: Country code (default: 'gb')
        max_pages: Maximum number of pages to fetch (default: None, fetch all)
        
    Returns:
        dict: Results of the sync operation
    """
    # Check if Adzuna API is available
    if not check_adzuna_api_status():
        logger.error("Adzuna API credentials not configured")
        return {
            "status": "error",
            "error": "Adzuna API credentials not configured"
        }
    
    logger.info(f"Starting Adzuna job sync with keywords={keywords}, location={location}")
    
    # Initialize storage
    storage = AdzunaStorage()
    
    # Sync all jobs
    results = storage.sync_jobs(
        keywords=keywords,
        location=location,
        country=country,
        max_days_old=1,  # Get jobs from last 24 hours
        append=True,
        max_pages=max_pages
    )
    
    logger.info(f"Adzuna job sync complete. Status: {results.get('status')}, " + 
                f"New jobs: {results.get('new_jobs')}, " +
                f"Total jobs: {results.get('total_jobs')}")
    
    return results

def import_adzuna_jobs_to_main_storage(days=30):
    """
    Import Adzuna jobs into the main job storage
    
    Args:
        days: Number of days to import (default: 30)
        
    Returns:
        int: Number of jobs imported
    """
    logger.info(f"Importing Adzuna jobs from last {days} days to main storage")
    
    # Initialize storage
    storage = AdzunaStorage()
    
    # Get recent jobs
    jobs = storage.get_recent_jobs(days=days)
    
    # Import to main storage
    count = 0
    for job in jobs:
        try:
            # Convert to dict and add to main storage
            add_job(job.to_dict())
            count += 1
        except Exception as e:
            logger.error(f"Error importing job: {str(e)}")
    
    logger.info(f"Successfully imported {count} jobs to main storage")
    return count

def get_adzuna_jobs(import_to_main=False, days=30):
    """
    Get Adzuna jobs from storage
    
    Args:
        import_to_main: Whether to also import to main storage
        days: Number of days to filter by
        
    Returns:
        List of Job objects
    """
    # Initialize storage
    storage = AdzunaStorage()
    
    # Get recent jobs
    jobs = storage.get_recent_jobs(days=days)
    
    # Import to main storage if requested
    if import_to_main and jobs:
        import_adzuna_jobs_to_main_storage(days=days)
    
    return jobs

def cleanup_old_adzuna_jobs(max_age_days=90):
    """
    Clean up old Adzuna jobs
    
    Args:
        max_age_days: Maximum age in days
        
    Returns:
        Number of jobs removed
    """
    # Initialize storage
    storage = AdzunaStorage()
    
    # Clean up old jobs
    removed_count = storage.cleanup_old_jobs(max_age_days=max_age_days)
    
    logger.info(f"Cleaned up {removed_count} old Adzuna jobs")
    return removed_count

def get_adzuna_storage_status():
    """
    Get status of Adzuna job storage
    
    Returns:
        Dict with status information
    """
    # Initialize storage
    storage = AdzunaStorage()
    
    # Get status
    status = storage.get_sync_status()
    
    return status

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Check if credentials are set
    if not os.environ.get('ADZUNA_APP_ID') or not os.environ.get('ADZUNA_API_KEY'):
        print("Adzuna API credentials not found in environment variables")
        print("Please set ADZUNA_APP_ID and ADZUNA_API_KEY environment variables")
        exit(1)
    
    # Sync jobs with rate limiting
    results = sync_jobs_from_adzuna(max_pages=5)  # Limit to 5 pages for testing
    print(f"Job sync results: {json.dumps(results, indent=2)}")
    
    # Get storage status
    status = get_adzuna_storage_status()
    print(f"Storage status: {status}")
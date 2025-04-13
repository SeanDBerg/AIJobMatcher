# adzuna_scraper.py - DEPRECATED - Use job_manager.py instead
# This file is kept for backwards compatibility only.
# All functionality has been consolidated into job_manager.py

from typing import List, Dict, Any
import logging
import os
from datetime import datetime
from models import Job

# Import the new, unified JobManager
from job_manager import JobManager, AdzunaAPIError

logger = logging.getLogger(__name__)

# API settings
ADZUNA_API_BASE_URL = "https://api.adzuna.com/v1/api"

# Initialize global JobManager instance
_job_manager = JobManager()

# Get Adzuna API credentials from environment variables
def get_api_credentials():
  """DEPRECATED: Use JobManager.get_api_credentials() instead"""
  logger.warning("get_api_credentials is deprecated - use JobManager.get_api_credentials instead")
  return _job_manager.get_api_credentials()

# Default rate limiting constants
DEFAULT_RATE_LIMIT_CALLS = 20 # 20 calls per minute
DEFAULT_RATE_LIMIT_PERIOD = 60 # 60 seconds
DEFAULT_CALL_DELAY = 3 # 3 seconds between API calls

# Configurable settings class
class ScraperConfig:
  rate_limit_calls = DEFAULT_RATE_LIMIT_CALLS
  rate_limit_period = DEFAULT_RATE_LIMIT_PERIOD
  call_delay = DEFAULT_CALL_DELAY
  
# Initialize config
config = ScraperConfig()

# Rate limiter class
class RateLimiter:
  """Manages API rate limiting with a sliding window approach"""
  def __init__(self, max_calls, period_seconds, call_delay):
    self.max_calls = max_calls
    self.period_seconds = period_seconds
    self.call_delay = call_delay
    self.call_timestamps = []
    
  def get_call_count(self):
    logger.info("get_call_count returning with self=%s", self)
    return len(self.call_timestamps)

def check_adzuna_api_status() -> bool:
  """
  DEPRECATED: Check if Adzuna API credentials are properly configured
  Use JobManager.check_api_status() instead
  
  Returns:
      bool: True if credentials are available, False otherwise
  """
  logger.warning("check_adzuna_api_status is deprecated - use JobManager.check_api_status instead")
  return _job_manager.check_api_status()

# Get jobs from storage
def get_adzuna_jobs(days: int = 30) -> List[Job]:
  """
  DEPRECATED: Get jobs from storage - use JobManager.get_recent_jobs() instead
  
  Args:
      days: Number of days to look back for recent jobs
      
  Returns:
      List of Job objects
  """
  logger.warning("get_adzuna_jobs is deprecated - use JobManager.get_recent_jobs instead")
  return _job_manager.get_recent_jobs(days)

# Clean up old jobs
def cleanup_old_adzuna_jobs(max_age_days: int = 90) -> int:
  """
  DEPRECATED: Clean up old jobs - use JobManager.cleanup_old_jobs() instead
  
  Args:
      max_age_days: Maximum age of jobs to keep in days
      
  Returns:
      Number of jobs removed
  """
  logger.warning("cleanup_old_adzuna_jobs is deprecated - use JobManager.cleanup_old_jobs instead")
  return _job_manager.cleanup_old_jobs(max_age_days)

# Get status of job storage
def get_adzuna_storage_status() -> Dict[str, Any]:
  """
  DEPRECATED: Get storage status - use JobManager.get_storage_status() instead
  
  Returns:
      Dictionary with status information including job count, batch count, etc.
  """
  logger.warning("get_adzuna_storage_status is deprecated - use JobManager.get_storage_status instead")
  return _job_manager.get_storage_status()

# Search for jobs using the Adzuna API
def search_jobs(keywords=None, location=None,
    country="gb", # Default to UK
    distance=15, # Default to 15 miles/km
    max_days_old=30,
    page=1,
    results_per_page=50,
    category=None,
    full_time=None,
    permanent=None):
  """
  DEPRECATED: Search jobs - use JobManager.search_jobs() instead
  
  Args:
      keywords: Job search keywords
      location: Job location
      country: Country code (default: "gb")
      distance: Search radius in miles/km (default: 15)
      max_days_old: Maximum age of jobs in days (default: 30)
      page: Page number for pagination (default: 1)
      results_per_page: Number of results per page (default: 50)
      category: Job category
      full_time: Filter for full-time jobs
      permanent: Filter for permanent jobs
      
  Returns:
      Jobs list with pagination metadata
  """
  logger.warning("search_jobs is deprecated - use JobManager.search_jobs instead")
  try:
    # Delegate to JobManager
    jobs, count, total_pages, current_page = _job_manager.search_jobs(
      keywords=keywords,
      location=location,
      country=country,
      distance=distance,
      max_days_old=max_days_old,
      page=page,
      results_per_page=results_per_page,
      category=category,
      full_time=full_time,
      permanent=permanent
    )
    
    # For backward compatibility, wrap the result in a custom list with metadata
    class JobResults(list):
      def __init__(self, jobs_list):
        super().__init__(jobs_list)
        self.total_count = 0
        self.total_pages = 0
        self.current_page = 0

    # Create our custom list with metadata
    job_results = JobResults(jobs)
    job_results.total_count = count
    job_results.total_pages = total_pages
    job_results.current_page = current_page
    
    return job_results
  except Exception as e:
    logger.error(f"Error searching jobs: {str(e)}")
    raise AdzunaAPIError(f"Error searching jobs: {str(e)}")

# Extract skills from job data
def extract_skills_from_adzuna(job_data):
  """
  DEPRECATED: Extract skills from job data - use JobManager.extract_skills_from_job instead
  
  Args:
      job_data: Job data from Adzuna API
      
  Returns:
      List of skills extracted from the job data
  """
  logger.warning("extract_skills_from_adzuna is deprecated - use JobManager.extract_skills_from_job instead")
  return _job_manager.extract_skills_from_job(job_data)

# Format salary range as a string
def format_salary_range(min_salary, max_salary):
  """
  DEPRECATED: Format salary range - use JobManager.format_salary_range instead
  
  Args:
      min_salary: Minimum salary amount
      max_salary: Maximum salary amount
      
  Returns:
      Formatted salary range string or None if no salary data
  """
  logger.warning("format_salary_range is deprecated - use JobManager.format_salary_range instead")
  return _job_manager.format_salary_range(min_salary, max_salary)
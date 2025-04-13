# adzuna_scraper.py - Adzuna job scraping module for bulk job retrieval with rate limiting
from typing import List, Dict, Any
import logging
from adzuna_api import get_api_credentials, AdzunaAPIError
from adzuna_storage import AdzunaStorage
from job_data import add_job
from models import Job
logger = logging.getLogger(__name__)

# Initialize storage
_adzuna_storage = AdzunaStorage()

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
#  Get the total number of calls tracked
  def get_call_count(self):
    logger.info("get_call_count returning with self=%s", self)
    return len(self.call_timestamps)
def check_adzuna_api_status() -> bool:
  """
    Check if Adzuna API credentials are properly configured
    
    Returns:
        bool: True if credentials are available, False otherwise
    """
  try:
    get_api_credentials()
    logger.info("check_adzuna_api_status returning with no parameters")
    return True
  except AdzunaAPIError:
    logger.info("check_adzuna_api_status returning with no parameters")
    return False
# Import Adzuna jobs into the main job storage
def import_adzuna_jobs_to_main_storage(days: int = 30) -> int:
  try:
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
# Get Adzuna jobs from storage
def get_adzuna_jobs(import_to_main: bool = False, days: int = 30) -> List[Job]:
  jobs = _adzuna_storage.get_recent_jobs(days=days)
  if import_to_main:
    import_adzuna_jobs_to_main_storage(days=days)
  logger.info("get_adzuna_jobs returning with import_to_main=%s, days=%s", import_to_main, days)
  return jobs
# Clean up old Adzuna jobs
def cleanup_old_adzuna_jobs(max_age_days: int = 10) -> int:
  logger.info("cleanup_old_adzuna_jobs returning with max_age_days=%s", max_age_days)
  return _adzuna_storage.cleanup_old_jobs(max_age_days=max_age_days)
# Get status of Adzuna job storage
def get_adzuna_storage_status() -> Dict[str, Any]:
  logger.info("get_adzuna_storage_status ran")
  return _adzuna_storage.get_sync_status()
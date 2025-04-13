# adzuna_scraper.py - Adzuna job scraping module for bulk job retrieval with rate limiting
from datetime import datetime
from typing import List, Dict, Optional, Any
import logging
import time
from adzuna_api import search_jobs, get_api_credentials, AdzunaAPIError
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

# Global variables for sync control
SYNC_RUNNING = False
SYNC_PAUSED = False
SYNC_STATUS = {"status": "idle", "progress": 0, "total_pages": 0, "current_page": 0, "jobs_found": 0, "start_time": None, "last_call_time": None, "estimated_completion": None, "error": None}
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

  def wait_if_needed(self):
    """
        Wait if rate limit would be exceeded
        
        Returns:
            bool: True if we should continue, False if operation was interrupted
        """
    current_time = time.time()

    # Remove timestamps older than our period
    self.call_timestamps = [ts for ts in self.call_timestamps if current_time - ts <= self.period_seconds]

    # Check if we've reached the rate limit
    if len(self.call_timestamps) >= self.max_calls:
      # Calculate time to wait - until oldest timestamp expires from window
      oldest_timestamp = min(self.call_timestamps)
      wait_time = oldest_timestamp + self.period_seconds - current_time

      if wait_time > 0:
        logger.info(f"Rate limit reached. Waiting {wait_time:.2f} seconds...")
        # Wait with check for interruption
        if not _wait_with_check(wait_time):
          logger.info("wait_if_needed returning with self=%s", self)
          return False

    # Add a small delay between calls anyway
    if self.call_delay > 0:
      if not _wait_with_check(self.call_delay):
        logger.info("wait_if_needed returning with self=%s", self)
        return False

    # Record this call
    self.call_timestamps.append(time.time())
    logger.info("wait_if_needed returning with self=%s", self)
    return True

  def get_call_count(self):
    """Get the total number of calls tracked"""
    logger.info("get_call_count returning with self=%s", self)
    return len(self.call_timestamps)
def update_scraper_config(new_config):
  """
    Update scraper configuration
    
    Args:
        new_config: Dictionary with configuration updates
    """
  if 'rate_limit_calls' in new_config:
    config.rate_limit_calls = int(new_config['rate_limit_calls'])
  if 'rate_limit_period' in new_config:
    config.rate_limit_period = int(new_config['rate_limit_period'])
  if 'call_delay' in new_config:
    config.call_delay = int(new_config['call_delay'])

  logger.info(f"Scraper config updated: calls={config.rate_limit_calls}, period={config.rate_limit_period}s, delay={config.call_delay}s")
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
def get_sync_status():
  """
    Get the current sync status
    
    Returns:
        dict: Current sync status
    """
  logger.info("get_sync_status returning with no parameters")
  # Make a copy to avoid external modifications
  return SYNC_STATUS.copy()
def pause_sync():
  """
    Pause the current sync operation
    """
  global SYNC_PAUSED

  if not SYNC_RUNNING:
    logger.info("pause_sync returning with no parameters")
    return {"status": "error", "message": "No sync operation is currently running"}

  SYNC_PAUSED = True
  SYNC_STATUS["status"] = "paused"
  logger.info("Sync operation paused")
  logger.info("pause_sync returning with no parameters")
  return {"status": "success", "message": "Sync operation paused"}
def resume_sync():
  """
    Resume a paused sync operation
    """
  global SYNC_PAUSED

  if not SYNC_RUNNING:
    logger.info("resume_sync returning with no parameters")
    return {"status": "error", "message": "No sync operation is currently running"}

  if not SYNC_PAUSED:
    logger.info("resume_sync returning with no parameters")
    return {"status": "error", "message": "Sync operation is not paused"}

  SYNC_PAUSED = False
  SYNC_STATUS["status"] = "running"
  logger.info("Sync operation resumed")
  logger.info("resume_sync returning with no parameters")
  return {"status": "success", "message": "Sync operation resumed"}
def stop_sync():
  """
    Stop the current sync operation
    """
  global SYNC_RUNNING, SYNC_PAUSED

  if not SYNC_RUNNING:
    logger.info("stop_sync returning with no parameters")
    return {"status": "error", "message": "No sync operation is currently running"}

  SYNC_RUNNING = False
  SYNC_PAUSED = False
  SYNC_STATUS["status"] = "stopped"
  logger.info("Sync operation stopped")
  logger.info("stop_sync returning with no parameters")
  return {"status": "success", "message": "Sync operation stopped"}
def sync_jobs_from_adzuna(keywords: Optional[str] = None, location: Optional[str] = None, country: str = "gb", max_pages: Optional[int] = None, max_days_old: int = 30, remote_only: bool = False) -> Dict[str, Any]:
  """
    Sync jobs from Adzuna API, with pagination and rate limiting
    """
  global SYNC_RUNNING, SYNC_PAUSED, SYNC_STATUS

  # Check if already running
  if SYNC_RUNNING:
    logger.info("sync_jobs_from_adzuna returning with keywords=%s, location=%s, country=%s, max_pages=%s, max_days_old=%s, remote_only=%s", keywords, location, country, max_pages, max_days_old, remote_only)
    return {"status": "error", "error": "A sync operation is already in progress", "current_status": get_sync_status()}

  # Initialize sync status
  _initialize_sync_status()

  try:
    # Check API credentials
    if not check_adzuna_api_status():
      _set_sync_error("Adzuna API credentials not configured")
      logger.info("sync_jobs_from_adzuna returning with keywords=%s, location=%s, country=%s, max_pages=%s, max_days_old=%s, remote_only=%s", keywords, location, country, max_pages, max_days_old, remote_only)
      return {"status": "error", "error": "Adzuna API credentials not configured", "pages_fetched": 0, "new_jobs": 0, "api_calls": 0}

    # Initialize rate limiter
    rate_limiter = RateLimiter(max_calls=config.rate_limit_calls, period_seconds=config.rate_limit_period, call_delay=config.call_delay)

    # Tracking variables
    page = 1
    total_pages = 1 # Will be updated after first call
    total_count = 0 # Will be updated after first call
    new_jobs_count = 0
    pages_fetched = 0
    api_calls = 0

    # Start time for overall process
    start_time = time.time()

    # Loop through pages
    while page <= total_pages and (max_pages is None or page <= max_pages):
      # Check if operation should continue
      if not _should_continue_sync():
        break

      # Apply rate limiting using our rate limiter class
      if not rate_limiter.wait_if_needed():
        break

      # Record API call information
      api_calls = rate_limiter.get_call_count()
      current_time = time.time()
      SYNC_STATUS["last_call_time"] = current_time
      SYNC_STATUS["current_page"] = page

      # Update progress information
      _update_sync_progress(page, total_pages, pages_fetched, start_time)

      # Log progress
      logger.info(f"Fetching page {page} of {total_pages if total_pages > 1 else 'unknown'}")

      try:
        SYNC_STATUS["status"] = "fetching"

        # Fetch jobs for this page
        jobs = search_jobs(
          keywords=keywords,
          location=location,
          country=country,
          page=page,
          results_per_page=50, # Get maximum results per page
          max_days_old=max_days_old
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
          SYNC_STATUS["total_pages"] = total_pages

        SYNC_STATUS["status"] = "storing"

        # Store jobs directly
        stored_count = _adzuna_storage.store_jobs(jobs, keywords=keywords, location=location, country=country, max_days_old=max_days_old)

        # Ensure stored_count is an integer
        if isinstance(stored_count, int):
          new_jobs_count += stored_count
          SYNC_STATUS["jobs_found"] = new_jobs_count

        # Increment counters
        pages_fetched += 1
        page += 1

        SYNC_STATUS["status"] = "running"

      except AdzunaAPIError as e:
        logger.info("sync_jobs_from_adzuna returning with keywords=%s, location=%s, country=%s, max_pages=%s, max_days_old=%s, remote_only=%s", keywords, location, country, max_pages, max_days_old, remote_only)
        return _handle_sync_error(f"Error fetching page {page}: {str(e)}", pages_fetched, new_jobs_count, api_calls)
      except Exception as e:
        logger.info("sync_jobs_from_adzuna returning with keywords=%s, location=%s, country=%s, max_pages=%s, max_days_old=%s, remote_only=%s", keywords, location, country, max_pages, max_days_old, remote_only)
        return _handle_sync_error(f"Unexpected error fetching page {page}: {str(e)}", pages_fetched, new_jobs_count, api_calls)

    # Calculate total time
    total_time = time.time() - start_time

    # Update final status
    SYNC_STATUS["status"] = "completed"
    SYNC_STATUS["progress"] = 100
    SYNC_RUNNING = False
    logger.info("sync_jobs_from_adzuna returning with keywords=%s, location=%s, country=%s, max_pages=%s, max_days_old=%s, remote_only=%s", keywords, location, country, max_pages, max_days_old, remote_only)

    # Return results
    return {"status": "success", "pages_fetched": pages_fetched, "total_pages": total_pages, "new_jobs": new_jobs_count, "total_jobs": total_count, "api_calls": api_calls, "time_taken_seconds": round(total_time, 2), "message": f"Successfully fetched {pages_fetched} pages with {new_jobs_count} new jobs"}

  except Exception as e:
    logger.info("sync_jobs_from_adzuna returning with keywords=%s, location=%s, country=%s, max_pages=%s, max_days_old=%s, remote_only=%s", keywords, location, country, max_pages, max_days_old, remote_only)
    return _handle_sync_error(f"Error in sync_jobs_from_adzuna: {str(e)}", 0, 0, 0)
def _initialize_sync_status():
  """Initialize the sync status for a new operation"""
  global SYNC_RUNNING, SYNC_PAUSED, SYNC_STATUS

  SYNC_RUNNING = True
  SYNC_PAUSED = False
  SYNC_STATUS = {
    "status": "running",
    "progress": 0,
    "total_pages": 0,
    "current_page": 0,
    "jobs_found": 0,
    "start_time": time.time(),
    "last_call_time": None,
    "estimated_completion": None,
    "error": None,
  }
def _set_sync_error(error_msg):
  """Set error status and disable sync running"""
  global SYNC_RUNNING, SYNC_STATUS

  SYNC_STATUS["status"] = "error"
  SYNC_STATUS["error"] = error_msg
  SYNC_RUNNING = False
def _should_continue_sync():
  """Check if sync should continue based on running/paused state"""
  global SYNC_RUNNING, SYNC_PAUSED

  # Check if operation has been stopped
  if not SYNC_RUNNING:
    logger.info("Sync operation stopped by user")
    logger.info("_should_continue_sync returning with no parameters")
    return False

  # Handle pause state
  while SYNC_PAUSED and SYNC_RUNNING:
    time.sleep(0.5) # Sleep briefly while paused
    continue
  logger.info("_should_continue_sync returning with no parameters")

  return SYNC_RUNNING
def _wait_with_check(seconds):
  """
    Wait for specified seconds with checks for stop/pause
    
    Returns:
        bool: True if waiting completed normally, False if operation should stop
    """
  global SYNC_RUNNING, SYNC_PAUSED

  wait_until = time.time() + seconds
  while time.time() < wait_until and SYNC_RUNNING and not SYNC_PAUSED:
    time.sleep(0.5)

  if not SYNC_RUNNING:
    logger.info("_wait_with_check returning with seconds=%s", seconds)
    return False

  if SYNC_PAUSED:
    logger.info("_wait_with_check returning with seconds=%s", seconds)
    return False
  logger.info("_wait_with_check returning with seconds=%s", seconds)

  return True
def _update_sync_progress(page, total_pages, pages_fetched, start_time):
  """Update progress information in sync status"""
  global SYNC_STATUS

  if total_pages > 1:
    SYNC_STATUS["progress"] = (page - 1) / total_pages * 100

    # Calculate estimated completion time
    if pages_fetched > 0:
      elapsed_time = time.time() - start_time
      avg_time_per_page = elapsed_time / pages_fetched
      remaining_pages = total_pages - page + 1
      estimated_remaining = avg_time_per_page * remaining_pages
      estimated_completion = time.time() + estimated_remaining
      SYNC_STATUS["estimated_completion"] = datetime.fromtimestamp(estimated_completion).isoformat()
def _handle_sync_error(error_msg, pages_fetched, new_jobs_count, api_calls):
  """Handle error during sync operation"""
  global SYNC_RUNNING, SYNC_STATUS

  logger.error(error_msg)
  SYNC_STATUS["status"] = "error"
  SYNC_STATUS["error"] = error_msg
  SYNC_RUNNING = False
  logger.info("_handle_sync_error returning with error_msg=%s, pages_fetched=%s, new_jobs_count=%s, api_calls=%s", error_msg, pages_fetched, new_jobs_count, api_calls)

  return {"status": "error", "error": error_msg, "pages_fetched": pages_fetched, "new_jobs": new_jobs_count, "api_calls": api_calls}
def import_adzuna_jobs_to_main_storage(days: int = 30) -> int:
  """
    Import Adzuna jobs into the main job storage
    
    Args:
        days: Number of days to import (default: 30)
        
    Returns:
        int: Number of jobs imported
    """
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
    logger.info("import_adzuna_jobs_to_main_storage returning with days=%s", days)
    return imported_count

  except ImportError:
    logger.error("job_data module not available for import")
    logger.info("import_adzuna_jobs_to_main_storage returning with days=%s", days)
    return 0
  except Exception as e:
    logger.error(f"Error importing Adzuna jobs: {str(e)}")
    logger.info("import_adzuna_jobs_to_main_storage returning with days=%s", days)
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
  logger.info("get_adzuna_jobs returning with import_to_main=%s, days=%s", import_to_main, days)

  return jobs
def cleanup_old_adzuna_jobs(max_age_days: int = 90) -> int:
  """
    Clean up old Adzuna jobs
    
    Args:
        max_age_days: Maximum age in days
        
    Returns:
        Number of jobs removed
    """
  logger.info("cleanup_old_adzuna_jobs returning with max_age_days=%s", max_age_days)
  return _adzuna_storage.cleanup_old_jobs(max_age_days=max_age_days)
def get_adzuna_storage_status() -> Dict[str, Any]:
  """
    Get status of Adzuna job storage
    
    Returns:
        Dict with status information
    """
  logger.info("get_adzuna_storage_status returning with no parameters")
  return _adzuna_storage.get_sync_status()
if __name__ == "__main__":
  # Configure logging
  logging.basicConfig(level=logging.INFO)

  # Test the scraper
  result = sync_jobs_from_adzuna(
    keywords="python developer",
    location="london",
    country="gb",
    max_pages=1 # Just get one page for testing
  )

  print(f"Sync result: {result}")

  # Check storage status
  status = get_adzuna_storage_status()
  print(f"Storage status: {status}")

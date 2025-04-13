# adzuna_scraper.py - Adzuna job scraping module for bulk job retrieval with API integration
from typing import List, Dict, Any
import os
import logging
import requests
from datetime import datetime
import time
from adzuna_storage import AdzunaStorage
from job_data import add_job
from models import Job

logger = logging.getLogger(__name__)

# API settings
ADZUNA_API_BASE_URL = "https://api.adzuna.com/v1/api"

# Custom exception for Adzuna API errors
class AdzunaAPIError(Exception):
  pass

# Get Adzuna API credentials from environment variables
def get_api_credentials():
  app_id = os.environ.get('ADZUNA_APP_ID')
  api_key = os.environ.get('ADZUNA_API_KEY')
  if not app_id or not api_key:
    raise AdzunaAPIError("Adzuna API credentials are not configured. Please set ADZUNA_APP_ID and ADZUNA_API_KEY environment variables.")
  logger.info("get_api_credentials returning with no parameters")
  return app_id, api_key

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

# Search for jobs using the Adzuna API
def search_jobs(keywords=None,location=None,
    country="gb", # Default to UK
    distance=15, # Default to 15 miles/km
    max_days_old=30,
    page=1,
    results_per_page=50,
    category=None,
    full_time=None,
    permanent=None):
  try:
    # Get API credentials
    app_id, api_key = get_api_credentials()
    # Build API URL
    url = f"{ADZUNA_API_BASE_URL}/jobs/{country}/search/{page}"
    # Prepare query parameters
    params = {"app_id": app_id, "app_key": api_key, "results_per_page": results_per_page, "max_days_old": max_days_old}
    # Add optional filters
    if keywords:
      params["what"] = keywords
    if location:
      params["where"] = location
    if distance:
      params["distance"] = distance
    if category:
      params["category"] = category
    if full_time is not None:
      params["full_time"] = 1 if full_time else 0
    if permanent is not None:
      params["permanent"] = 1 if permanent else 0
    # Make API request with timeout
    try:
      response = requests.get(url, params=params, timeout=30) # 30 second timeout
      # Check for API errors
      if response.status_code != 200:
        error_message = f"API request failed with status code {response.status_code}"
        try:
          error_data = response.json()
          if "error" in error_data:
            error_message = f"API error: {error_data['error']}"
        except:
          pass
        raise AdzunaAPIError(error_message)
    except requests.exceptions.Timeout:
      raise AdzunaAPIError("API request timed out. This might be due to heavy traffic or a large result set.")
    except requests.exceptions.ConnectionError:
      raise AdzunaAPIError("Failed to connect to the Adzuna API. Please check your network connection and try again.")
    except Exception as e:
      raise AdzunaAPIError(f"Unexpected error during API request: {str(e)}")
    # Parse response
    data = response.json()
    # Get total counts for pagination
    count = data.get("count", 0)
    total_pages = (count // results_per_page) + (1 if count % results_per_page > 0 else 0)
    # Process job listings
    jobs = []
    for job_data in data.get("results", []):
      try:
        # Extract job attributes
        company = job_data.get("company", {}).get("display_name", "Unknown Company")
        title = job_data.get("title", "Unknown Position")
        description = job_data.get("description", "")
        location = job_data.get("location", {}).get("display_name", "")
        # Extract salary range
        salary_min = job_data.get("salary_min")
        salary_max = job_data.get("salary_max")
        salary_range = format_salary_range(salary_min, salary_max)
        # Extract posting date
        created = job_data.get("created")
        if created:
          # Convert to ISO format
          created = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").isoformat()
        # Extract URL
        redirect_url = job_data.get("redirect_url", "")
        # Check if job is remote
        is_remote = False
        if "remote" in job_data.get("category", {}).get("tag", "").lower() or "remote" in title.lower():
          is_remote = True
        # Extract skills from description
        skills = extract_skills_from_adzuna(job_data)
        # Create Job object
        job = Job(title=title, company=company, description=description, location=location, is_remote=is_remote, posted_date=created, url=redirect_url, skills=skills, salary_range=salary_range)
        jobs.append(job)
      except Exception as e:
        logger.error(f"Error processing job data: {str(e)}")
        continue
    # Create a custom class to hold the list and metadata
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
    job_results.current_page = page
    return job_results
  except AdzunaAPIError:
    # Re-raise API errors
    raise
  except Exception as e:
    logger.error(f"Error searching jobs: {str(e)}")
    raise AdzunaAPIError(f"Error searching jobs: {str(e)}")

# Extract skills from Adzuna job data
def extract_skills_from_adzuna(job_data):
  skills = []
  # Try to use the Adzuna Category Tag Skill list
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
  # Fall back to extracting from title and description if no skills found
  if not skills:
    try:
      # Try to import the skill extractor from job_scraper
      from job_scraper import extract_skills_from_description
      description = job_data.get("description", "")
      extracted_skills = extract_skills_from_description(description)
      skills.extend(extracted_skills)
    except ImportError:
      logger.warning("Could not import extract_skills_from_description")
  logger.info("extract_skills_from_adzuna returning with job_data=%s", job_data)
  return list(set(skills)) # Remove duplicates

# Format salary range as a string
def format_salary_range(min_salary, max_salary):
  if min_salary is None and max_salary is None:
    logger.info("format_salary_range returning with min_salary=%s, max_salary=%s", min_salary, max_salary)
    return None
  # Format values
  if min_salary and max_salary:
    if min_salary == max_salary:
      logger.info("format_salary_range returning with min_salary=%s, max_salary=%s", min_salary, max_salary)
      return f"£{min_salary:,.0f}"
    logger.info("format_salary_range returning with min_salary=%s, max_salary=%s", min_salary, max_salary)
    return f"£{min_salary:,.0f} - £{max_salary:,.0f}"
  elif min_salary:
    logger.info("format_salary_range returning with min_salary=%s, max_salary=%s", min_salary, max_salary)
    return f"£{min_salary:,.0f}+"
  elif max_salary:
    logger.info("format_salary_range returning with min_salary=%s, max_salary=%s", min_salary, max_salary)
    return f"Up to £{max_salary:,.0f}"
  logger.info("format_salary_range returning with min_salary=%s, max_salary=%s", min_salary, max_salary)
  return None
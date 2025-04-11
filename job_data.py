#job_data.py
import json
import logging
import os
from datetime import datetime
from models import Job
from embedding_generator import generate_dual_embeddings

# Import Adzuna functions if available
try:
    from adzuna_scraper import get_adzuna_jobs
    ADZUNA_AVAILABLE = True
except ImportError:
    ADZUNA_AVAILABLE = False
    
logger = logging.getLogger(__name__)

# Path to the fallback job data file (only used if Adzuna not available)
FALLBACK_JOB_DATA_FILE = os.path.join(os.path.dirname(__file__), 'static', 'job_data', 'sample_jobs.json')

# Cache for job data with embeddings
_job_cache = None
_job_cache_last_updated = None

def load_job_data():
    """
    Load job data from Adzuna storage or fallback to JSON file
    
    Returns:
        List of Job objects
    """
    # First try to get jobs from Adzuna storage
    if ADZUNA_AVAILABLE:
        logger.debug("Loading job data from Adzuna storage")
        try:
            adzuna_jobs = get_adzuna_jobs(days=30)
            if adzuna_jobs and len(adzuna_jobs) > 0:
                logger.debug(f"Loaded {len(adzuna_jobs)} jobs from Adzuna storage")
                return adzuna_jobs
            else:
                logger.warning("No Adzuna jobs available, will use fallback")
        except Exception as e:
            logger.error(f"Error loading Adzuna jobs: {str(e)}")
    
    # Fallback to sample job data file
    logger.debug(f"Loading job data from {FALLBACK_JOB_DATA_FILE}")
    try:
        with open(FALLBACK_JOB_DATA_FILE, 'r', encoding='utf-8') as f:
            job_data = json.load(f)
        
        jobs = []
        for job_dict in job_data:
            # Convert posted_date string to datetime if it exists
            if 'posted_date' in job_dict and job_dict['posted_date']:
                try:
                    job_dict['posted_date'] = datetime.fromisoformat(job_dict['posted_date'])
                except (ValueError, TypeError):
                    job_dict['posted_date'] = datetime.now()
            
            # Create Job object
            job = Job(
                title=job_dict.get('title', ''),
                company=job_dict.get('company', ''),
                description=job_dict.get('description', ''),
                location=job_dict.get('location', ''),
                is_remote=job_dict.get('is_remote', False),
                posted_date=job_dict.get('posted_date', datetime.now()),
                url=job_dict.get('url', ''),
                skills=job_dict.get('skills', []),
                salary_range=job_dict.get('salary_range', '')
            )
            jobs.append(job)
        
        logger.debug(f"Loaded {len(jobs)} jobs")
        return jobs
    
    except FileNotFoundError:
        logger.warning(f"Job data file not found at {FALLBACK_JOB_DATA_FILE}")
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(FALLBACK_JOB_DATA_FILE), exist_ok=True)
        # Create empty job data file
        with open(FALLBACK_JOB_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
        return []
    
    except Exception as e:
        logger.error(f"Error loading job data: {str(e)}")
        return []


# Generate narrative and skills embeddings for job descriptions
def generate_job_embeddings(jobs):
    logger.debug(f"Generating dual embeddings for {len(jobs)} jobs")

    for job in jobs:
        job_text = f"{job.title}\n{job.company}\n{job.description}"
        if job.skills:
            job_text += "\nSkills: " + ", ".join(job.skills)

        embeddings = generate_dual_embeddings(job_text)
        job.embedding_narrative = embeddings["narrative"]
        job.embedding_skills = embeddings["skills"]

    return jobs


def get_job_data():
    """
    Get job data with embeddings, using cache if available
    
    Returns:
        List of Job objects with embeddings
    """
    global _job_cache, _job_cache_last_updated
    
    # Check if we need to refresh the cache
    current_time = datetime.now()
    cache_age = (current_time - _job_cache_last_updated).total_seconds() if _job_cache_last_updated else None
    
    if _job_cache is None or cache_age is None or cache_age > 3600:  # Refresh cache if older than 1 hour
        logger.debug("Refreshing job data cache")
        
        # Load job data
        jobs = load_job_data()
        
        # Generate embeddings
        jobs_with_embeddings = generate_job_embeddings(jobs)
        
        # Update cache
        _job_cache = jobs_with_embeddings
        _job_cache_last_updated = current_time
        
        return jobs_with_embeddings
    else:
        logger.debug("Using cached job data")
        return _job_cache

def add_job(job_dict):
    """
    Add a new job to the job data file
    
    Args:
        job_dict: Dictionary containing job details
        
    Returns:
        Newly added Job object
    """
    logger.debug(f"Adding new job: {job_dict.get('title')}")
    
    # Load existing jobs
    jobs = load_job_data()
    
    # Create new Job object
    new_job = Job(
        title=job_dict.get('title', ''),
        company=job_dict.get('company', ''),
        description=job_dict.get('description', ''),
        location=job_dict.get('location', ''),
        is_remote=job_dict.get('is_remote', False),
        posted_date=datetime.now(),
        url=job_dict.get('url', ''),
        skills=job_dict.get('skills', []),
        salary_range=job_dict.get('salary_range', '')
    )
    
    # Add to list
    jobs.append(new_job)
    
    # Convert to dictionary list for saving
    job_dicts = [job.to_dict() for job in jobs]
    
    # Save to file
    with open(FALLBACK_JOB_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(job_dicts, f, indent=2)
    
    # Invalidate cache
    global _job_cache, _job_cache_last_updated
    _job_cache = None
    _job_cache_last_updated = None
    
    return new_job

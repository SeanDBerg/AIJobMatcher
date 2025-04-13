"""
JobManager - Unified interface for job data management.
Replaces redundant functions across different modules with a single, streamlined interface.
"""
import os
import json
import logging
import uuid
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
import time
import requests
import numpy as np

from models import Job, JobMatch

# Set up logging
logger = logging.getLogger(__name__)

# Constants
ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), 'static', 'job_data', 'adzuna')
ADZUNA_INDEX_FILE = os.path.join(ADZUNA_DATA_DIR, 'index.json')
ADZUNA_API_BASE_URL = "https://api.adzuna.com/v1/api"

# Custom exception for Adzuna API errors
class AdzunaAPIError(Exception):
    pass

class JobManager:
    """
    Unified manager for job data - single interface to access all job data
    throughout the application, reducing redundancy and improving performance
    through caching.
    """
    
    # Singleton instance
    _instance = None
    
    # Class-level cache
    _index_cache = None
    _index_cache_timestamp = None
    _jobs_cache = None
    _jobs_cache_timestamp = None
    
    def __new__(cls):
        """Ensure only one instance of JobManager exists (singleton pattern)"""
        if cls._instance is None:
            cls._instance = super(JobManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the job manager (only runs once due to singleton pattern)"""
        if not self._initialized:
            # Initialize data directory
            os.makedirs(ADZUNA_DATA_DIR, exist_ok=True)
            
            # Initialize index if it doesn't exist
            if not os.path.exists(ADZUNA_INDEX_FILE):
                self._create_empty_index()
                
            self._initialized = True
    
    def _create_empty_index(self) -> None:
        """Create an empty index file"""
        empty_index = {
            "batches": {},
            "job_count": 0,
            "last_sync": None,
            "last_batch": None
        }
        
        try:
            with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
                json.dump(empty_index, f, indent=2)
                
            logger.debug("Created new empty index file")
        except Exception as e:
            logger.error(f"Error creating index file: {str(e)}")
    
    def get_index(self, force_refresh: bool = False) -> Dict:
        """
        Get the job index with caching
        
        Args:
            force_refresh: Force a refresh of the cache
            
        Returns:
            Dictionary containing the job index
        """
        current_time = datetime.now()
        cache_age = (current_time - self._index_cache_timestamp).total_seconds() if self._index_cache_timestamp else None
        
        # Use cache if available and not expired (5 second TTL)
        if not force_refresh and self._index_cache is not None and cache_age is not None and cache_age < 5:
            logger.debug(f"Using cached index (age: {cache_age:.2f}s)")
            return self._index_cache
        
        # Load fresh index from disk
        try:
            with open(ADZUNA_INDEX_FILE, 'r', encoding='utf-8') as f:
                index = json.load(f)
                
            # Ensure the index has all required keys
            if "batches" not in index:
                index["batches"] = {}
            if "job_count" not in index:
                index["job_count"] = 0
            if "last_sync" not in index:
                index["last_sync"] = None
            if "last_batch" not in index:
                index["last_batch"] = None
                
            # Update cache
            self._index_cache = index
            self._index_cache_timestamp = current_time
            
            logger.debug("Loaded fresh index from disk")
            return index
            
        except Exception as e:
            logger.error(f"Error loading index: {str(e)}")
            
            # If error, create a new empty index
            empty_index = {
                "batches": {},
                "job_count": 0,
                "last_sync": None,
                "last_batch": None
            }
            
            # Update cache
            self._index_cache = empty_index
            self._index_cache_timestamp = current_time
            
            return empty_index
    
    def save_index(self, index: Dict) -> bool:
        """
        Save index to disk and update cache
        
        Args:
            index: Dictionary containing the job index
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
                json.dump(index, f, indent=2)
                
            # Update cache
            self._index_cache = index
            self._index_cache_timestamp = datetime.now()
            
            logger.debug("Saved index to disk")
            return True
            
        except Exception as e:
            logger.error(f"Error saving index: {str(e)}")
            return False
    
    def _load_job_batch(self, batch_id: str) -> List[Dict]:
        """
        Load a batch of jobs from disk
        
        Args:
            batch_id: ID of the batch to load
            
        Returns:
            List of job dictionaries
        """
        batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
        
        if not os.path.exists(batch_file):
            logger.warning(f"Batch file {batch_id} not found")
            return []
            
        try:
            with open(batch_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading batch {batch_id}: {str(e)}")
            return []
    
    def _save_job_batch(self, jobs: List[Dict], batch_id: str) -> bool:
        """
        Save a batch of jobs to disk
        
        Args:
            jobs: List of job dictionaries
            batch_id: ID to use for the batch
            
        Returns:
            True if successful, False otherwise
        """
        batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
        
        try:
            with open(batch_file, 'w', encoding='utf-8') as f:
                json.dump(jobs, f, indent=2)
                
            logger.debug(f"Saved batch {batch_id} with {len(jobs)} jobs")
            return True
            
        except Exception as e:
            logger.error(f"Error saving batch {batch_id}: {str(e)}")
            return False
    
    def get_all_jobs(self, force_refresh: bool = False) -> List[Job]:
        """
        Get all jobs with caching
        
        Args:
            force_refresh: Force a refresh of the cache
            
        Returns:
            List of Job objects
        """
        current_time = datetime.now()
        cache_age = (current_time - self._jobs_cache_timestamp).total_seconds() if self._jobs_cache_timestamp else None
        
        # Use cache if available and not expired (10 second TTL)
        if not force_refresh and self._jobs_cache is not None and cache_age is not None and cache_age < 10:
            logger.debug(f"Using cached jobs (age: {cache_age:.2f}s)")
            return self._jobs_cache
        
        try:
            # Get the index (uses its own caching)
            index = self.get_index()
            all_jobs = []
            
            # Load all batches
            for batch_id in index["batches"]:
                batch_jobs = self._load_job_batch(batch_id)
                
                # Convert dictionaries to Job objects
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
            
            # Update cache
            self._jobs_cache = all_jobs
            self._jobs_cache_timestamp = current_time
            
            logger.debug(f"Loaded {len(all_jobs)} jobs from disk")
            return all_jobs
            
        except Exception as e:
            logger.error(f"Error getting all jobs: {str(e)}")
            return []
    
    def get_recent_jobs(self, days: int = 30, force_refresh: bool = False) -> List[Job]:
        """
        Get recent jobs with caching (uses get_all_jobs internally)
        
        Args:
            days: Number of days to look back
            force_refresh: Force a refresh of the cache
            
        Returns:
            List of Job objects from the last specified days
        """
        # Get all jobs (uses its own caching)
        all_jobs = self.get_all_jobs(force_refresh=force_refresh)
        
        if not all_jobs:
            return []
        
        # Calculate cutoff date
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        cutoff_datetime = datetime.fromisoformat(cutoff_date)
        
        # Filter by posted date
        recent_jobs = []
        
        for job in all_jobs:
            if not job.posted_date:
                continue
                
            try:
                job_date = None
                
                # Handle different date formats
                if isinstance(job.posted_date, str):
                    if 'T' in job.posted_date:
                        job_date = datetime.fromisoformat(job.posted_date.replace('Z', '+00:00'))
                    elif '-' in job.posted_date and len(job.posted_date) >= 10:
                        job_date = datetime.fromisoformat(job.posted_date[:10])
                    else:
                        try:
                            job_date = datetime.strptime(job.posted_date[:10], "%Y-%m-%d")
                        except:
                            # Last resort: use string comparison
                            if job.posted_date >= cutoff_date:
                                recent_jobs.append(job)
                            continue
                elif isinstance(job.posted_date, datetime):
                    job_date = job.posted_date
                else:
                    continue
                
                # Compare with cutoff date
                if job_date >= cutoff_datetime:
                    recent_jobs.append(job)
                    
            except Exception as e:
                logger.error(f"Error comparing dates for job {job.title}: {str(e)}")
                # Include jobs with date parsing errors to avoid excluding valid jobs
                recent_jobs.append(job)
        
        logger.debug(f"Filtered to {len(recent_jobs)} recent jobs (last {days} days)")
        return recent_jobs
    
    def get_storage_status(self) -> Dict[str, Any]:
        """
        Get status of the job storage
        
        Returns:
            Dictionary with status information including job count, batch count, etc.
        """
        index = self.get_index()
        
        batch_count = len(index["batches"])
        job_count = index["job_count"]
        last_sync = index["last_sync"]
        last_batch = index["last_batch"]
        
        status = {
            "batch_count": batch_count,
            "total_jobs": job_count,
            "last_sync": last_sync,
            "last_batch": last_batch,
            "batches": index["batches"]
        }
        
        logger.debug(f"Storage status: {job_count} jobs in {batch_count} batches")
        return status
    
    def cleanup_old_jobs(self, max_age_days: int = 90) -> int:
        """
        Remove jobs older than the specified age
        
        Args:
            max_age_days: Maximum age of jobs to keep in days
            
        Returns:
            Number of jobs removed
        """
        try:
            # Get the index
            index = self.get_index(force_refresh=True)
            
            # Calculate cutoff date
            cutoff_date = (datetime.now() - timedelta(days=max_age_days)).isoformat()
            
            # Track batches and jobs to remove
            batches_to_remove = []
            job_count_removed = 0
            
            # Check each batch
            for batch_id, batch_info in index["batches"].items():
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
                del index["batches"][batch_id]
            
            # Update total job count
            index["job_count"] -= job_count_removed
            if index["job_count"] < 0:
                index["job_count"] = 0
                
            # Update last batch if removed
            if index["last_batch"] in batches_to_remove:
                index["last_batch"] = None
                if index["batches"]:
                    # Set to most recent remaining batch
                    index["last_batch"] = max(index["batches"].items(), key=lambda x: x[1]["timestamp"])[0]
            
            # Save index
            self.save_index(index)
            
            # Clear cache to force refresh
            self._jobs_cache = None
            
            logger.info(f"Removed {job_count_removed} jobs from {len(batches_to_remove)} batches")
            return job_count_removed
            
        except Exception as e:
            logger.error(f"Error cleaning up old jobs: {str(e)}")
            return 0
    
    def get_api_credentials(self) -> tuple:
        """
        Get Adzuna API credentials from environment variables
        
        Returns:
            Tuple of (app_id, api_key)
            
        Raises:
            AdzunaAPIError: If credentials are not configured
        """
        app_id = os.environ.get('ADZUNA_APP_ID')
        api_key = os.environ.get('ADZUNA_API_KEY')
        
        if not app_id or not api_key:
            raise AdzunaAPIError("Adzuna API credentials are not configured. Please set ADZUNA_APP_ID and ADZUNA_API_KEY environment variables.")
            
        return app_id, api_key
    
    def check_api_status(self) -> bool:
        """
        Check if Adzuna API credentials are properly configured
        
        Returns:
            True if credentials are available, False otherwise
        """
        try:
            self.get_api_credentials()
            return True
        except AdzunaAPIError:
            return False
    
    def format_salary_range(self, min_salary, max_salary) -> Optional[str]:
        """
        Format salary range as a human-readable string
        
        Args:
            min_salary: Minimum salary amount
            max_salary: Maximum salary amount
            
        Returns:
            Formatted salary range string or None if no salary data
        """
        if min_salary is None and max_salary is None:
            return None
            
        if min_salary and max_salary:
            if min_salary == max_salary:
                return f"£{min_salary:,.0f}"
            return f"£{min_salary:,.0f} - £{max_salary:,.0f}"
        elif min_salary:
            return f"£{min_salary:,.0f}+"
        elif max_salary:
            return f"Up to £{max_salary:,.0f}"
            
        return None
    
    def extract_skills_from_job(self, job_data: Dict, known_skills: Optional[Set[str]] = None) -> List[str]:
        """
        Extract skills from job data
        
        Args:
            job_data: Job data dictionary
            known_skills: Optional set of known skills to check against
            
        Returns:
            List of skills
        """
        skills = []
        
        # Try to use category tag from the API
        if "category" in job_data and "tag" in job_data["category"]:
            category = job_data["category"]["tag"].lower()
            
            # Extract programming languages and technologies from IT job categories
            if "it" in category or "software" in category or "developer" in category:
                tech_skills = [
                    "python", "java", "javascript", "typescript", "ruby", "php", "c#", "c++", "go", 
                    "rust", "swift", "kotlin", "react", "angular", "vue", "node.js", "django", "flask", 
                    "spring", "aws", "azure", "gcp", "docker", "kubernetes", "sql", "mongodb", 
                    "postgresql", "mysql", "oracle", "redis", "elasticsearch"
                ]
                
                description = job_data.get("description", "").lower()
                title = job_data.get("title", "").lower()
                
                # Check for skills in description
                for skill in tech_skills:
                    if skill in description or skill in title:
                        if skill not in skills:
                            skills.append(skill)
        
        # Use matching_engine.extract_skills if no skills found and known_skills provided
        if not skills and known_skills:
            try:
                from matching_engine import extract_skills
                description = job_data.get("description", "")
                extracted_skills = extract_skills(description, known_skills)
                skills.extend(extracted_skills)
            except ImportError:
                logger.warning("Could not import extract_skills from matching_engine")
        
        return list(set(skills))  # Remove duplicates
    
    def search_jobs(self, keywords: Optional[str] = None, location: Optional[str] = None,
                   country: str = "gb", distance: int = 15, max_days_old: int = 30,
                   page: int = 1, results_per_page: int = 50,
                   category: Optional[str] = None, full_time: Optional[bool] = None,
                   permanent: Optional[bool] = None) -> tuple:
        """
        Search for jobs using the Adzuna API and store them
        
        Args:
            keywords: Job search keywords
            location: Job location
            country: Country code
            distance: Search radius in miles/km
            max_days_old: Maximum age of jobs in days
            page: Page number for pagination
            results_per_page: Number of results per page
            category: Job category
            full_time: Filter for full-time jobs
            permanent: Filter for permanent jobs
            
        Returns:
            Tuple of (jobs_list, total_count, total_pages, current_page)
            
        Raises:
            AdzunaAPIError: If API request fails
        """
        # Get API credentials
        app_id, api_key = self.get_api_credentials()
        
        # Build API URL
        url = f"{ADZUNA_API_BASE_URL}/jobs/{country}/search/{page}"
        
        # Prepare query parameters
        params = {
            "app_id": app_id,
            "app_key": api_key,
            "results_per_page": results_per_page,
            "max_days_old": max_days_old
        }
        
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
            response = requests.get(url, params=params, timeout=30)
            
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
                salary_range = self.format_salary_range(salary_min, salary_max)
                
                # Extract posting date
                created = job_data.get("created")
                if created:
                    created = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").isoformat()
                
                # Extract URL
                redirect_url = job_data.get("redirect_url", "")
                
                # Check if job is remote
                is_remote = False
                if "remote" in job_data.get("category", {}).get("tag", "").lower() or "remote" in title.lower():
                    is_remote = True
                
                # Extract skills
                skills = self.extract_skills_from_job(job_data)
                
                # Create Job object
                job = Job(
                    title=title,
                    company=company,
                    description=description,
                    location=location,
                    is_remote=is_remote,
                    posted_date=created,
                    url=redirect_url,
                    skills=skills,
                    salary_range=salary_range
                )
                jobs.append(job)
                
            except Exception as e:
                logger.error(f"Error processing job data: {str(e)}")
                continue
        
        # Store the jobs
        if jobs:
            self.store_jobs(jobs, keywords=keywords, location=location,
                          country=country, max_days_old=max_days_old)
        
        return jobs, count, total_pages, page
    
    def store_jobs(self, jobs: List[Job], keywords: Optional[str] = None,
                 location: Optional[str] = None, country: str = "gb",
                 max_days_old: int = 30) -> int:
        """
        Store jobs in a new batch
        
        Args:
            jobs: List of Job objects
            keywords: Search keywords used
            location: Location used
            country: Country code
            max_days_old: Maximum age of jobs in days
            
        Returns:
            Number of jobs stored
        """
        try:
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
                index = self.get_index(force_refresh=True)
                index["batches"][batch_id] = batch_info
                index["job_count"] += len(job_dicts)
                index["last_sync"] = datetime.now().isoformat()
                index["last_batch"] = batch_id
                self.save_index(index)
                
                # Clear jobs cache
                self._jobs_cache = None
                
                logger.info(f"Saved {len(job_dicts)} jobs to batch {batch_id}")
                return len(job_dicts)
            else:
                logger.error(f"Failed to save job batch {batch_id}")
                return 0
                
        except Exception as e:
            logger.error(f"Error storing jobs: {str(e)}")
            return 0
    
    def delete_batch(self, batch_id: str) -> bool:
        """
        Delete a specific batch of jobs
        
        Args:
            batch_id: ID of the batch to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get the index
            index = self.get_index(force_refresh=True)
            
            # Check if batch exists
            if batch_id not in index["batches"]:
                logger.warning(f"Batch {batch_id} not found")
                return False
            
            # Get job count
            job_count = index["batches"][batch_id]["job_count"]
            
            # Remove batch file
            batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
            if os.path.exists(batch_file):
                os.remove(batch_file)
            
            # Remove from index
            del index["batches"][batch_id]
            
            # Update job count
            index["job_count"] -= job_count
            if index["job_count"] < 0:
                index["job_count"] = 0
                
            # Update last batch if removed
            if index["last_batch"] == batch_id:
                index["last_batch"] = None
                if index["batches"]:
                    # Set to most recent remaining batch
                    index["last_batch"] = max(index["batches"].items(), key=lambda x: x[1]["timestamp"])[0]
            
            # Save index
            self.save_index(index)
            
            # Clear jobs cache
            self._jobs_cache = None
            
            logger.info(f"Deleted batch {batch_id} with {job_count} jobs")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting batch {batch_id}: {str(e)}")
            return False
    
    def match_jobs_to_resume(self, resume_embeddings: Dict[str, np.ndarray],
                            jobs: Optional[List[Job]] = None,
                            filters: Optional[Dict] = None,
                            resume_text: Optional[str] = None,
                            days: int = 30) -> List[JobMatch]:
        """
        Match jobs to a resume
        
        Args:
            resume_embeddings: Dict with 'narrative' and 'skills' embeddings
            jobs: Optional list of Job objects
            filters: Optional dictionary of filter criteria
            resume_text: Optional raw resume text
            days: Number of days to look back
            
        Returns:
            List of JobMatch objects sorted by similarity score
        """
        from matching_engine import calculate_similarity, apply_filters, boost_score_with_skills
        
        # Validate resume_embeddings
        if resume_embeddings is None or not isinstance(resume_embeddings, dict):
            logger.error("Invalid resume_embeddings - must be a dictionary")
            return []
            
        if "narrative" not in resume_embeddings or "skills" not in resume_embeddings:
            logger.error("Missing required keys in resume_embeddings ('narrative' and/or 'skills')")
            return []
        
        # Get jobs if not provided
        if jobs is None:
            jobs = self.get_recent_jobs(days=days)
            
        if not jobs:
            logger.warning("No jobs available for matching")
            return []
        
        # Apply filters if specified
        try:
            if filters:
                filtered_jobs = apply_filters(jobs, filters)
            else:
                filtered_jobs = jobs
        except Exception as e:
            logger.error(f"Error applying filters: {str(e)}")
            filtered_jobs = jobs
        
        # Match jobs to resume
        matches = []
        for job in filtered_jobs:
            try:
                # Skip jobs without embeddings and generate if needed
                if not hasattr(job, 'embedding_narrative') or not hasattr(job, 'embedding_skills'):
                    logger.warning(f"Job '{job.title}' missing embeddings")
                    from matching_engine import generate_dual_embeddings
                    
                    job_text = f"{job.title}\n{job.company}\n{job.description}"
                    if job.skills:
                        job_text += "\nSkills: " + ", ".join(job.skills)
                    
                    embeddings = generate_dual_embeddings(job_text)
                    job.embedding_narrative = embeddings["narrative"]
                    job.embedding_skills = embeddings["skills"]
                
                # Calculate similarity scores
                sim_narrative = calculate_similarity(resume_embeddings["narrative"], job.embedding_narrative)
                sim_skills = calculate_similarity(resume_embeddings["skills"], job.embedding_skills)
                
                # Weighted average
                similarity = (sim_narrative + sim_skills) / 2
                
                # Apply skill boost if resume text provided
                if resume_text:
                    job_text = f"{job.title} {job.description} {' '.join(job.skills)}"
                    similarity = boost_score_with_skills(similarity, resume_text, job_text)
                
                matches.append(JobMatch(job, similarity))
                
            except Exception as e:
                logger.error(f"Error matching job '{job.title}': {str(e)}")
                continue
        
        # Sort by similarity score
        try:
            matches.sort(key=lambda m: m.similarity_score, reverse=True)
        except Exception as e:
            logger.error(f"Error sorting matches: {str(e)}")
        
        logger.debug(f"Found {len(matches)} matching jobs")
        return matches

# Initialize global instance
job_manager = JobManager()
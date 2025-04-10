"""
Module for communicating with the Adzuna API
"""
import os
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Union

from models import Job

logger = logging.getLogger(__name__)

# API settings
ADZUNA_API_BASE_URL = "https://api.adzuna.com/v1/api"

class AdzunaAPIError(Exception):
    """Custom exception for Adzuna API errors"""
    pass

def get_api_credentials():
    """
    Get Adzuna API credentials from environment variables
    
    Returns:
        tuple: (app_id, api_key)
    
    Raises:
        AdzunaAPIError: If credentials are not set
    """
    app_id = os.environ.get('ADZUNA_APP_ID')
    api_key = os.environ.get('ADZUNA_API_KEY')
    
    if not app_id or not api_key:
        raise AdzunaAPIError("Adzuna API credentials are not configured. Please set ADZUNA_APP_ID and ADZUNA_API_KEY environment variables.")
        
    return app_id, api_key

def search_jobs(
    keywords=None,
    location=None,
    country="gb",  # Default to UK
    distance=15,   # Default to 15 miles/km
    max_days_old=30,
    page=1,
    results_per_page=50,
    category=None,
    full_time=None,
    permanent=None
):
    """
    Search for jobs using the Adzuna API
    
    Args:
        keywords: Search keywords (e.g. 'python developer')
        location: Location to search in (e.g. 'London')
        country: Country code (default: 'gb')
        distance: Distance in miles/km (default: 15)
        max_days_old: Maximum age of job listings in days (default: 30)
        page: Page number for pagination (default: 1)
        results_per_page: Number of results per page (default: 50)
        category: Job category (e.g. 'it-jobs')
        full_time: Filter for full-time jobs (True/False)
        permanent: Filter for permanent jobs (True/False)
    
    Returns:
        list: List of Job objects
    
    Raises:
        AdzunaAPIError: If API request fails
    """
    try:
        # Get API credentials
        app_id, api_key = get_api_credentials()
        
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
        
        # Make API request
        response = requests.get(url, params=params)
        
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

def extract_skills_from_adzuna(job_data):
    """
    Extract skills from Adzuna job data
    
    Args:
        job_data: Job data from Adzuna API
    
    Returns:
        list: List of skills
    """
    skills = []
    
    # Try to use the Adzuna Category Tag Skill list
    if "category" in job_data and "tag" in job_data["category"]:
        category = job_data["category"]["tag"].lower()
        
        # Extract programming languages and technologies from IT job categories
        if "it" in category or "software" in category or "developer" in category:
            tech_skills = [
                "python", "java", "javascript", "typescript", "ruby", "php", "c#", "c++", 
                "go", "rust", "swift", "kotlin", "react", "angular", "vue", "node.js",
                "django", "flask", "spring", "aws", "azure", "gcp", "docker", "kubernetes",
                "sql", "mongodb", "postgresql", "mysql", "oracle", "redis", "elasticsearch"
            ]
            
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
    
    return list(set(skills))  # Remove duplicates

def format_salary_range(min_salary, max_salary):
    """
    Format salary range as a string
    
    Args:
        min_salary: Minimum salary
        max_salary: Maximum salary
    
    Returns:
        str: Formatted salary range
    """
    if min_salary is None and max_salary is None:
        return None
    
    # Format values
    if min_salary and max_salary:
        if min_salary == max_salary:
            return f"£{min_salary:,.0f}"
        return f"£{min_salary:,.0f} - £{max_salary:,.0f}"
    elif min_salary:
        return f"£{min_salary:,.0f}+"
    elif max_salary:
        return f"Up to £{max_salary:,.0f}"
    
    return None

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Test the API
    try:
        jobs = search_jobs(
            keywords="python developer",
            location="London",
            country="gb",
            page=1,
            results_per_page=10
        )
        
        print(f"Found {len(jobs)} jobs")
        for job in jobs:
            print(f"- {job.title} at {job.company} ({job.location})")
            
    except AdzunaAPIError as e:
        print(f"API Error: {str(e)}")
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
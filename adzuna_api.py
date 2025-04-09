import os
import logging
import requests
from datetime import datetime, timedelta
from models import Job

logger = logging.getLogger(__name__)

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
        logger.error("Adzuna API credentials not found in environment variables")
        raise AdzunaAPIError(
            "Adzuna API credentials not configured. Please set ADZUNA_APP_ID and ADZUNA_API_KEY environment variables."
        )
    
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
        app_id, api_key = get_api_credentials()
        
        # Build base URL
        base_url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
        
        # Build query parameters
        params = {
            "app_id": app_id,
            "app_key": api_key,
            "results_per_page": results_per_page,
            "content-type": "application/json"
        }
        
        # Add optional parameters
        if keywords:
            params["what"] = keywords
        if location:
            params["where"] = location
            params["distance"] = distance
        if category:
            params["category"] = category
        if full_time is not None:
            params["full_time"] = 1 if full_time else 0
        if permanent is not None:
            params["permanent"] = 1 if permanent else 0
        
        # Add date filter
        if max_days_old:
            date_from = (datetime.now() - timedelta(days=max_days_old)).strftime("%Y-%m-%d")
            params["from_date"] = date_from
        
        # Make request
        logger.info(f"Making Adzuna API request: {base_url} with params: {params}")
        response = requests.get(base_url, params=params)
        
        # Check for errors
        if response.status_code != 200:
            logger.error(f"Adzuna API error: {response.status_code} - {response.text}")
            raise AdzunaAPIError(f"Adzuna API error: {response.status_code} - {response.text}")
        
        # Parse response
        data = response.json()
        
        # Check if we have results
        if data.get("count", 0) == 0:
            logger.info("No jobs found matching the criteria")
            return []
        
        # Extract jobs
        jobs = []
        for job_data in data.get("results", []):
            try:
                # Map Adzuna fields to our Job model
                job = Job(
                    title=job_data.get("title", ""),
                    company=job_data.get("company", {}).get("display_name", "Unknown"),
                    description=job_data.get("description", ""),
                    location=f"{job_data.get('location', {}).get('area', [''])[0]}, {job_data.get('location', {}).get('display_name', '')}".strip(", "),
                    is_remote="remote" in job_data.get("title", "").lower() or "remote" in job_data.get("description", "").lower(),
                    posted_date=datetime.strptime(job_data.get("created", "").split("T")[0], "%Y-%m-%d") if job_data.get("created") else None,
                    url=job_data.get("redirect_url", ""),
                    skills=extract_skills_from_adzuna(job_data),
                    salary_range=format_salary_range(job_data.get("salary_min"), job_data.get("salary_max")) if job_data.get("salary_min") or job_data.get("salary_max") else ""
                )
                jobs.append(job)
            except Exception as e:
                logger.warning(f"Error processing job listing: {str(e)}")
                continue
        
        logger.info(f"Found {len(jobs)} jobs from Adzuna")
        return jobs
        
    except Exception as e:
        if isinstance(e, AdzunaAPIError):
            raise
        logger.error(f"Error searching Adzuna jobs: {str(e)}")
        raise AdzunaAPIError(f"Error searching Adzuna jobs: {str(e)}")

def extract_skills_from_adzuna(job_data):
    """
    Extract skills from Adzuna job data
    
    Args:
        job_data: Job data from Adzuna API
    
    Returns:
        list: List of skills
    """
    skills = []
    
    # Check for category tags
    category = job_data.get("category", {}).get("tag", "")
    if category:
        skills.append(category.replace("-", " ").title())
    
    # Extract from title and description
    title = job_data.get("title", "")
    description = job_data.get("description", "")
    
    # Common programming languages and technologies
    tech_keywords = [
        "Python", "JavaScript", "Java", "C#", "C++", "Ruby", "PHP", "Swift", "Kotlin", 
        "TypeScript", "SQL", "NoSQL", "React", "Angular", "Vue", "Node.js", "Django",
        "Flask", "Spring", "ASP.NET", "Express", "TensorFlow", "PyTorch", "AWS", "Azure",
        "GCP", "Docker", "Kubernetes", "Git", "CI/CD", "Agile", "Scrum", "DevOps", "ML",
        "AI", "Data Science", "Big Data", "Hadoop", "Spark", "Scala", "Go", "Rust"
    ]
    
    # Check for tech keywords in title and description
    for keyword in tech_keywords:
        if (keyword.lower() in title.lower() or keyword.lower() in description.lower()) and keyword not in skills:
            skills.append(keyword)
    
    return skills[:10]  # Limit to 10 skills

def format_salary_range(min_salary, max_salary):
    """
    Format salary range as a string
    
    Args:
        min_salary: Minimum salary
        max_salary: Maximum salary
    
    Returns:
        str: Formatted salary range
    """
    if min_salary and max_salary:
        if min_salary == max_salary:
            return f"£{min_salary:,.0f}"
        return f"£{min_salary:,.0f} - £{max_salary:,.0f}"
    elif min_salary:
        return f"£{min_salary:,.0f}+"
    elif max_salary:
        return f"Up to £{max_salary:,.0f}"
    return ""
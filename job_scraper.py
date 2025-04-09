"""
Job scraper module for retrieving job listings from various job boards
"""
import logging
import os
import json
import re
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode, quote_plus
import trafilatura
import requests
from models import Job
from job_data import add_job

# Import Adzuna API module (will be used when credentials are available)
try:
    from adzuna_api import search_jobs as adzuna_search_jobs, AdzunaAPIError
    ADZUNA_AVAILABLE = True
except (ImportError, Exception) as e:
    logging.warning(f"Adzuna API not available: {str(e)}")
    ADZUNA_AVAILABLE = False

logger = logging.getLogger(__name__)

# Job board sources
JOB_SOURCES = {
    "github": {
        "name": "GitHub Jobs",
        "url": "https://jobs.github.com/positions.json",
        "params": {
            "description": "",
            "location": "",
            "full_time": "true"
        }
    },
    "remoteok": {
        "name": "RemoteOK",
        "url": "https://remoteok.io/api",
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
    }
}

def clean_text(text):
    """
    Clean HTML and extra whitespace from text
    
    Args:
        text: Text to clean
        
    Returns:
        Cleaned text
    """
    if not text:
        return ""
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Replace multiple whitespace with single space
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def scrape_jobs_from_github():
    """
    Scrape jobs from GitHub Jobs API
    
    Returns:
        List of Job objects
    """
    logger.info("Scraping jobs from GitHub Jobs")
    
    jobs = []
    
    try:
        # Build request URL with parameters
        params = JOB_SOURCES["github"]["params"].copy()
        url = JOB_SOURCES["github"]["url"]
        response = requests.get(url, params=params)
        
        if response.status_code != 200:
            logger.error(f"Error fetching jobs from GitHub: {response.status_code}")
            return jobs
        
        job_listings = response.json()
        
        for job_data in job_listings:
            # Extract job details
            title = job_data.get("title", "")
            company = job_data.get("company", "")
            description = clean_text(job_data.get("description", ""))
            location = job_data.get("location", "")
            is_remote = "remote" in location.lower() or "remote" in title.lower()
            url = job_data.get("url", "")
            
            # Parse created_at date
            try:
                posted_date = datetime.strptime(job_data.get("created_at", ""), "%a %b %d %H:%M:%S UTC %Y")
            except (ValueError, TypeError):
                posted_date = datetime.now()
            
            # Extract skills from description
            skills = extract_skills_from_description(description)
            
            # Create Job object
            job = Job(
                title=title,
                company=company,
                description=description,
                location=location,
                is_remote=is_remote,
                posted_date=posted_date,
                url=url,
                skills=skills,
                salary_range=""
            )
            
            jobs.append(job)
        
        logger.info(f"Scraped {len(jobs)} jobs from GitHub Jobs")
        
    except Exception as e:
        logger.error(f"Error scraping GitHub Jobs: {str(e)}")
    
    return jobs

def scrape_jobs_from_remoteok():
    """
    Scrape jobs from RemoteOK API
    
    Returns:
        List of Job objects
    """
    logger.info("Scraping jobs from RemoteOK")
    
    jobs = []
    
    try:
        url = JOB_SOURCES["remoteok"]["url"]
        headers = JOB_SOURCES["remoteok"]["headers"].copy()
        
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"Error fetching jobs from RemoteOK: {response.status_code}")
            return jobs
        
        job_listings = response.json()
        
        # Skip the first item which is usually metadata
        if job_listings and isinstance(job_listings, list) and len(job_listings) > 0:
            job_listings = job_listings[1:]
        
        for job_data in job_listings:
            # Extract job details
            title = job_data.get("position", "")
            company = job_data.get("company", "")
            description = clean_text(job_data.get("description", ""))
            location = "Remote"  # RemoteOK jobs are all remote
            is_remote = True
            url = f"https://remoteok.io/l/{job_data.get('id', '')}"
            
            # Parse date
            try:
                posted_date = datetime.fromtimestamp(int(job_data.get("date", 0)))
            except (ValueError, TypeError):
                posted_date = datetime.now()
            
            # Extract skills from tags
            skills = job_data.get("tags", [])
            if not skills and description:
                skills = extract_skills_from_description(description)
            
            # Create Job object
            job = Job(
                title=title,
                company=company,
                description=description,
                location=location,
                is_remote=is_remote,
                posted_date=posted_date,
                url=url,
                skills=skills,
                salary_range=job_data.get("salary", "")
            )
            
            jobs.append(job)
        
        logger.info(f"Scraped {len(jobs)} jobs from RemoteOK")
        
    except Exception as e:
        logger.error(f"Error scraping RemoteOK: {str(e)}")
    
    return jobs

def scrape_webpage_for_jobs(url):
    """
    Scrape a webpage directly for job content
    
    Args:
        url: URL of the webpage to scrape
        
    Returns:
        Text content of the webpage
    """
    logger.info(f"Scraping webpage: {url}")
    
    try:
        # Use trafilatura to extract content
        downloaded = trafilatura.fetch_url(url)
        text = trafilatura.extract(downloaded)
        
        if not text:
            logger.warning(f"No text extracted from {url}")
            return ""
        
        logger.info(f"Successfully extracted {len(text)} characters from {url}")
        return text
        
    except Exception as e:
        logger.error(f"Error scraping webpage: {str(e)}")
        return ""

def extract_skills_from_description(description):
    """
    Extract skills from job description
    
    Args:
        description: Job description text
        
    Returns:
        List of skills
    """
    # Common tech skills to look for
    common_skills = [
        "python", "javascript", "typescript", "java", "c++", "c#", "go", "ruby", "php", "swift", "kotlin",
        "react", "angular", "vue", "node.js", "express", "django", "flask", "spring", "rails",
        "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "jenkins", "git",
        "postgresql", "mysql", "mongodb", "sql", "nosql", "redis", "elasticsearch",
        "machine learning", "deep learning", "ai", "data science", "nlp", "computer vision",
        "agile", "scrum", "devops", "ci/cd", "test driven development", "restful api"
    ]
    
    skills = []
    description_lower = description.lower()
    
    for skill in common_skills:
        if skill in description_lower:
            # Avoid duplicates with different casing
            if skill not in [s.lower() for s in skills]:
                # Use the skill name with proper formatting
                if skill == "javascript":
                    skills.append("JavaScript")
                elif skill == "typescript":
                    skills.append("TypeScript")
                elif skill == "python":
                    skills.append("Python")
                elif skill == "java":
                    skills.append("Java")
                elif skill == "node.js":
                    skills.append("Node.js")
                elif skill == "react":
                    skills.append("React")
                elif skill == "angular":
                    skills.append("Angular")
                elif skill == "vue":
                    skills.append("Vue.js")
                elif skill == "aws":
                    skills.append("AWS")
                elif skill == "azure":
                    skills.append("Azure")
                elif skill == "gcp":
                    skills.append("GCP")
                elif skill == "devops":
                    skills.append("DevOps")
                elif skill == "ci/cd":
                    skills.append("CI/CD")
                elif skill == "machine learning":
                    skills.append("Machine Learning")
                elif skill == "deep learning":
                    skills.append("Deep Learning")
                elif skill == "ai":
                    skills.append("AI")
                elif skill == "nlp":
                    skills.append("NLP")
                else:
                    # Capitalize first letter of each word
                    skills.append(skill.title())
    
    return skills

def save_scraped_jobs(jobs):
    """
    Save scraped jobs to the job data file
    
    Args:
        jobs: List of Job objects
        
    Returns:
        Number of jobs saved
    """
    logger.info(f"Saving {len(jobs)} scraped jobs")
    
    count = 0
    for job in jobs:
        try:
            add_job(job.to_dict())
            count += 1
        except Exception as e:
            logger.error(f"Error saving job: {str(e)}")
    
    logger.info(f"Successfully saved {count} jobs")
    return count

def scrape_jobs_from_adzuna(keywords=None, location=None):
    """
    Scrape jobs from Adzuna API
    
    Args:
        keywords: Optional keywords to search for
        location: Optional location to search in
        
    Returns:
        List of Job objects
    """
    logger.info(f"Scraping jobs from Adzuna API with keywords={keywords}, location={location}")
    
    if not ADZUNA_AVAILABLE:
        logger.warning("Adzuna API not available")
        return []
    
    try:
        # Check if Adzuna credentials are available
        if not os.environ.get('ADZUNA_APP_ID') or not os.environ.get('ADZUNA_API_KEY'):
            logger.warning("Adzuna API credentials not found in environment variables")
            return []
        
        # Call Adzuna API
        jobs = adzuna_search_jobs(
            keywords=keywords,
            location=location,
            country="gb",  # Default to UK
            max_days_old=30,
            results_per_page=50
        )
        
        logger.info(f"Scraped {len(jobs)} jobs from Adzuna")
        return jobs
        
    except Exception as e:
        if isinstance(e, AdzunaAPIError):
            logger.error(f"Adzuna API error: {str(e)}")
        else:
            logger.error(f"Error scraping Adzuna: {str(e)}")
        return []

def scrape_all_job_sources():
    """
    Scrape jobs from all configured sources
    
    Returns:
        Dictionary with results per source
    """
    logger.info("Starting job scraping from all sources")
    
    results = {}
    all_jobs = []
    
    # GitHub Jobs
    github_jobs = scrape_jobs_from_github()
    results["github"] = len(github_jobs)
    all_jobs.extend(github_jobs)
    
    # RemoteOK
    remoteok_jobs = scrape_jobs_from_remoteok()
    results["remoteok"] = len(remoteok_jobs)
    all_jobs.extend(remoteok_jobs)
    
    # Adzuna (if available)
    if ADZUNA_AVAILABLE:
        try:
            adzuna_jobs = scrape_jobs_from_adzuna()
            results["adzuna"] = len(adzuna_jobs)
            all_jobs.extend(adzuna_jobs)
        except Exception as e:
            logger.error(f"Error scraping Adzuna: {str(e)}")
            results["adzuna"] = 0
    else:
        results["adzuna"] = "Not available"
    
    # Save all jobs
    saved_count = save_scraped_jobs(all_jobs)
    results["total"] = len(all_jobs)
    results["saved"] = saved_count
    
    return results

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Run job scraper
    results = scrape_all_job_sources()
    print(f"Job scraping results: {json.dumps(results, indent=2)}")
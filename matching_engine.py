# matching_engine.py
import logging
import math
import numpy as np
from models import JobMatch
from embedding_generator import boost_score_with_skills, DEFAULT_SKILLS

logger = logging.getLogger(__name__)
# Calculate cosine similarity between resume and job embeddings
def calculate_similarity(resume_embedding, job_embedding):
    """
    Calculate cosine similarity between resume and job embeddings
    """
    # Convert to arrays if needed
    resume_vec = np.array(resume_embedding)
    job_vec = np.array(job_embedding)

    # Compute cosine similarity
    dot_product = np.dot(resume_vec, job_vec)
    norm_a = np.linalg.norm(resume_vec)
    norm_b = np.linalg.norm(job_vec)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    similarity = dot_product / (norm_a * norm_b)
    return (similarity + 1) / 2  # normalize to [0, 1]


def apply_filters(jobs, filters):
    """
    Apply filters to job listings
    
    Args:
        jobs: List of Job objects
        filters: Dictionary of filter criteria
            - remote: Boolean indicating preference for remote jobs
            - location: String with preferred location
            - keywords: String with comma-separated keywords
        
    Returns:
        List of filtered Job objects
    """
    logger.debug(f"Applying filters: {filters}")
    
    filtered_jobs = jobs.copy()
    
    # Filter for remote jobs if specified
    if filters.get('remote'):
        filtered_jobs = [job for job in filtered_jobs if job.is_remote]
    
    # Filter by location if specified
    location = filters.get('location', '').strip().lower()
    if location:
        filtered_jobs = [job for job in filtered_jobs if location in job.location.lower()]
    
    # Filter by keywords if specified
    keywords = filters.get('keywords', '').strip()
    if keywords:
        keyword_list = [kw.strip().lower() for kw in keywords.split(',')]
        filtered_jobs = []
        
        for job in jobs:
            job_text = (job.title + ' ' + job.description + ' ' + 
                         job.company + ' ' + ' '.join(job.skills)).lower()
            
            # Check if any keyword is present
            if any(kw in job_text for kw in keyword_list):
                filtered_jobs.append(job)
    
    logger.debug(f"Filtered jobs from {len(jobs)} to {len(filtered_jobs)}")
    
    return filtered_jobs
# Find jobs that match a resume based on embedding similarity and filters
def find_matching_jobs(resume_embedding, jobs, filters=None, resume_text=None):
    logger.debug("Finding matching jobs")

    if filters:
        filtered_jobs = apply_filters(jobs, filters)
    else:
        filtered_jobs = jobs

    job_matches = []
    for job in filtered_jobs:
        if job.embedding is None:
            logger.warning(f"Job '{job.title}' has no embedding")
            continue

        similarity = calculate_similarity(resume_embedding, job.embedding)

        # ⬇️ BOOST: Apply skill overlap if resume_text is provided
        if resume_text:
            job_text = f"{job.title} {job.description} {' '.join(job.skills)}"
            similarity = boost_score_with_skills(similarity, resume_text, job_text, DEFAULT_SKILLS)

        job_match = JobMatch(job, similarity)
        job_matches.append(job_match)

    job_matches.sort(key=lambda x: x.similarity_score, reverse=True)
    logger.debug(f"Found {len(job_matches)} matching jobs")

    return job_matches


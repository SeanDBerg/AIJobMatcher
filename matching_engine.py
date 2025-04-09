import logging
import math
import util_np as np
from models import JobMatch

logger = logging.getLogger(__name__)

def calculate_similarity(resume_embedding, job_embedding):
    """
    Calculate cosine similarity between resume and job embeddings
    
    Args:
        resume_embedding: NumpyArray of resume embedding
        job_embedding: NumpyArray of job embedding
        
    Returns:
        Float representing similarity score (0-1)
    """
    # Implement cosine similarity manually
    # Formula: cos(θ) = (A·B) / (||A||·||B||)
    
    # Get the vectors from the NumpyArray objects
    if hasattr(resume_embedding, 'data'):
        resume_vec = resume_embedding.data
    else:
        resume_vec = resume_embedding
        
    if hasattr(job_embedding, 'data'):
        job_vec = job_embedding.data
    else:
        job_vec = job_embedding
    
    # Calculate dot product A·B
    dot_product = sum(a * b for a, b in zip(resume_vec, job_vec))
    
    # Calculate magnitudes
    resume_magnitude = math.sqrt(sum(a * a for a in resume_vec))
    job_magnitude = math.sqrt(sum(b * b for b in job_vec))
    
    # Avoid division by zero
    if resume_magnitude == 0 or job_magnitude == 0:
        return 0.0
    
    # Calculate cosine similarity
    similarity = dot_product / (resume_magnitude * job_magnitude)
    
    # Ensure result is in range [-1, 1] and convert to [0, 1] range
    similarity = max(min(similarity, 1.0), -1.0)
    
    # This will map from [-1, 1] to [0, 1]
    # But for embeddings, the similarity is typically in [0, 1] already
    # so this is just a safeguard
    normalized_similarity = (similarity + 1) / 2
    
    return normalized_similarity

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

def find_matching_jobs(resume_embedding, jobs, filters=None):
    """
    Find jobs that match a resume based on embedding similarity and filters
    
    Args:
        resume_embedding: Numpy array of resume embedding
        jobs: List of Job objects with embeddings
        filters: Dictionary of filter criteria (optional)
        
    Returns:
        List of JobMatch objects sorted by similarity score
    """
    logger.debug("Finding matching jobs")
    
    # Apply filters if specified
    if filters:
        filtered_jobs = apply_filters(jobs, filters)
    else:
        filtered_jobs = jobs
    
    # Calculate similarity for each job
    job_matches = []
    for job in filtered_jobs:
        # Skip jobs without embeddings
        if job.embedding is None:
            logger.warning(f"Job '{job.title}' has no embedding")
            continue
        
        # Calculate similarity
        similarity = calculate_similarity(resume_embedding, job.embedding)
        
        # Create JobMatch object
        job_match = JobMatch(job, similarity)
        job_matches.append(job_match)
    
    # Sort by similarity score (descending)
    job_matches.sort(key=lambda x: x.similarity_score, reverse=True)
    
    logger.debug(f"Found {len(job_matches)} matching jobs")
    
    return job_matches

# matching_engine.py
# Merged file containing functionality from:
# - matching_engine.py (job matching functionality)
# - embedding_generator.py (text embedding generation)

import logging
import os
import json
import numpy as np
import re
from datetime import datetime
from models import Job, JobMatch
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import HashingVectorizer

logger = logging.getLogger(__name__)

################################################################################
# EMBEDDING GENERATOR SECTION (originally from embedding_generator.py)
################################################################################

# Set up the vectorizer once
vectorizer = HashingVectorizer(n_features=384, alternate_sign=False, norm='l2', 
                             stop_words='english', lowercase=True)

def clean_text(text: str) -> str:
    """
    Normalize text for embedding:
    - Lowercase
    - Remove non-alphanumerics
    - Collapse whitespace
    """
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    logger.info("clean_text returning with text=%s", text)
    return text

# Default embedding dimension for the all-MiniLM-L6-v2 model
EMBEDDING_DIM = 384

# Get the API token from environment variable
def get_api_token():
    api_token = os.environ.get("API_TOKEN")
    if not api_token:
        logger.warning("API_TOKEN environment variable not found")
        logger.info("get_api_token returning with no parameters")
        return None
    logger.info("get_api_token returning with no parameters")
    return api_token

# Generate embedding vector for the input text using deterministic hashing
def generate_embedding(text: str) -> np.ndarray:
    cleaned = clean_text(text)
    if not cleaned or len(cleaned) < 10:
        logger.info("generate_embedding returning with text=%s", text)
        return np.zeros(384)

    try:
        embedding_sparse: csr_matrix = vectorizer.transform([cleaned])
        logger.info("generate_embedding returning with text=%s", text)
        return embedding_sparse.toarray()[0]
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Embedding generation failed: {e}")
        logger.info("generate_embedding returning with text=%s", text)
        return np.zeros(384)

def batch_generate_embeddings(texts):
    """
    Generate embeddings for a batch of texts
    
    Args:
        texts: List of input texts to embed
        
    Returns:
        List of arrays containing the embedding vectors
    """
    logger.debug(f"Generating embeddings for {len(texts)} texts")

    embeddings = [generate_embedding(text) for text in texts]

    logger.debug(f"Generated {len(embeddings)} embeddings")
    logger.info("batch_generate_embeddings returning with texts=%s", texts)

    return embeddings

def chunk_text(text, max_length=512, overlap=50):
    """
    Sentence-aware chunking that splits text into chunks close to max_length.
    """
    logger.debug(f"Chunking text of length {len(text)}")

    # Split into sentences using punctuation
    sentences = re.split(r'(?<=[.!?]) +', text)
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk.strip())

            if overlap > 0 and len(current_chunk) > overlap:
                overlap_text = current_chunk[-overlap:]
                current_chunk = overlap_text + " " + sentence
            else:
                current_chunk = sentence
        else:
            current_chunk += " " + sentence

    if current_chunk:
        chunks.append(current_chunk.strip())

    logger.debug(f"Chunked text into {len(chunks)} chunks")
    logger.info("chunk_text returning with text=%s, max_length=%s, overlap=%s", text, max_length, overlap)
    return chunks

def generate_embedding_for_long_text(text, max_length=512, overlap=50):
    cleaned = clean_text(text)

    if len(cleaned) <= max_length:
        logger.info("generate_embedding_for_long_text returning with text=%s, max_length=%s, overlap=%s", text, max_length, overlap)
        return generate_embedding(cleaned)

    chunks = chunk_text(cleaned, max_length, overlap)
    embeddings = []

    for chunk in chunks:
        if len(chunk.strip()) < 10:
            continue # skip meaningless or empty chunks
        emb = generate_embedding(chunk)
        if np.linalg.norm(emb) > 0:
            embeddings.append(emb)

    if not embeddings:
        logger.warning("No valid chunks found for embedding")
        logger.info("generate_embedding_for_long_text returning with text=%s, max_length=%s, overlap=%s", text, max_length, overlap)
        return np.zeros(384)
    logger.info("generate_embedding_for_long_text returning with text=%s, max_length=%s, overlap=%s", text, max_length, overlap)

    return np.mean(embeddings, axis=0)

DEFAULT_SKILLS = {"python", "java", "c++", "c#", "javascript", "typescript", "react", "node", "sql", "postgresql", "mysql", "mongodb", "aws", "azure", "gcp", "docker", "kubernetes", "git", "flask", "django", "linux", "pandas", "numpy", "tensorflow", "scikit", "html", "css", "bash", "redis", "graphql"}
# Extract matching skills from text using a known skills list.
def extract_skills(text: str, known_skills: set) -> set:
    tokens = text.lower().split()
    found = set()
    for token in tokens:
        if token in known_skills:
            found.add(token)
    logger.info("ran")
    return found
# Boost similarity score based on skill overlap
def boost_score_with_skills(similarity: float, resume_text: str, job_text: str, known_skills=DEFAULT_SKILLS) -> float:
    # Safety check for None or invalid inputs
    if similarity is None or not isinstance(similarity, (int, float)):
        logger.warning("Invalid similarity value in boost_score_with_skills")
        return 0.0
    if resume_text is None or job_text is None:
        logger.warning("Missing text in boost_score_with_skills")
        return similarity
    try:
        # Extract skills from both texts
        resume_skills = extract_skills(resume_text, known_skills)
        job_skills = extract_skills(job_text, known_skills)
        # Find overlapping skills
        overlap = resume_skills & job_skills
        if not overlap:
            logger.debug("No overlapping skills found")
            return similarity
        # Apply boost based on number of overlapping skills
        boost = 0.05 * len(overlap)
        boosted_score = min(similarity + boost, 1.0)
        logger.debug(f"Skill boost: {similarity:.2f} → {boosted_score:.2f} (overlapping skills: {len(overlap)})")
        return boosted_score
    except Exception as e:
        logger.error(f"Error in boost_score_with_skills: {str(e)}")
        return similarity
# Generate two embeddings: one for the full narrative, one for just the skills section.
def generate_dual_embeddings(text: str) -> dict:
    cleaned = clean_text(text)

    # Try to extract relevant "skills sections"
    # This is heuristic-based: finds common headers like 'skills' or 'technologies'
    skill_blocks = []
    skill_keywords = ['skills', 'technologies', 'tools', 'languages', 'proficiencies']
    lines = text.splitlines()
    collecting = False

    for line in lines:
        line_lower = line.strip().lower()
        if any(k in line_lower for k in skill_keywords):
            collecting = True
            continue
        if collecting:
            if line.strip() == "" or len(skill_blocks) > 5:
                break
            skill_blocks.append(line.strip())

    skill_text = " ".join(skill_blocks) if skill_blocks else cleaned # fallback to cleaned
    logger.info("generate_dual_embeddings returning with text=%s", text)

    return {"narrative": generate_embedding(cleaned), "skills": generate_embedding(clean_text(skill_text))}

################################################################################
# JOB DATA & MATCHING ENGINE SECTION (simplified)
################################################################################

# Cache for job data with embeddings
_job_cache = None
_job_cache_last_updated = None
_job_manager = None

# Get job data with embeddings, using cache if available
def get_job_data(days=30, refresh=False):
    """
    Get job data with embeddings from storage.
    
    Args:
        days: Number of days to look back for recent jobs
        refresh: Force refresh the cache
        
    Returns:
        List of Job objects with embeddings
    """
    global _job_cache, _job_cache_last_updated, _job_manager
    
    # Check if we need to refresh the cache
    current_time = datetime.now()
    cache_age = (current_time - _job_cache_last_updated).total_seconds() if _job_cache_last_updated else None
    
    if refresh or _job_cache is None or cache_age is None or cache_age > 3600:  # Refresh if forced or cache older than 1 hour
        logger.debug("Refreshing job data cache")
        
        # Get jobs from JobManager
        if _job_manager is None:
            from job_manager import JobManager
            _job_manager = JobManager()
            
        jobs = _job_manager.get_recent_jobs(days=days)
        
        if not jobs:
            logger.warning("No jobs available from storage")
            return []
        
        # Generate embeddings for jobs
        for job in jobs:
            if not hasattr(job, 'embedding_narrative') or not hasattr(job, 'embedding_skills'):
                job_text = f"{job.title}\n{job.company}\n{job.description}"
                if job.skills:
                    job_text += "\nSkills: " + ", ".join(job.skills)
                
                embeddings = generate_dual_embeddings(job_text)
                job.embedding_narrative = embeddings["narrative"]
                job.embedding_skills = embeddings["skills"]
        
        # Update cache
        _job_cache = jobs
        _job_cache_last_updated = current_time
        
        logger.debug(f"Refreshed job cache with {len(jobs)} jobs")
        return jobs
    else:
        logger.debug(f"Using cached job data ({len(_job_cache) if _job_cache else 0} jobs)")
        return _job_cache
# Calculate cosine similarity between resume and job embeddings
def calculate_similarity(resume_embedding, job_embedding):

    # Check for None values
    if resume_embedding is None or job_embedding is None:
        logger.warning("Cannot calculate similarity - one of the embeddings is None")
        return 0.0
    try:
        # Convert to arrays if needed
        resume_vec = np.array(resume_embedding)
        job_vec = np.array(job_embedding)
        # Verify dimensions are valid
        if resume_vec.size == 0 or job_vec.size == 0:
            logger.warning("Cannot calculate similarity - empty vector(s)")
            return 0.0
        # Check for NaN or inf values
        if np.isnan(resume_vec).any() or np.isnan(job_vec).any() or \
           np.isinf(resume_vec).any() or np.isinf(job_vec).any():
            logger.warning("Cannot calculate similarity - invalid values in vectors")
            return 0.0
        # Compute cosine similarity
        dot_product = np.dot(resume_vec, job_vec)
        norm_a = np.linalg.norm(resume_vec)
        norm_b = np.linalg.norm(job_vec)
        if norm_a == 0 or norm_b == 0:
            logger.warning("Cannot calculate similarity - zero norm vector(s)")
            return 0.0
        similarity = dot_product / (norm_a * norm_b)
        # Handle any invalid results
        if np.isnan(similarity) or np.isinf(similarity):
            logger.warning("Invalid similarity result - using default 0.0")
            return 0.0
        # Normalize to [0, 1]
        normalized = (similarity + 1) / 2
        return normalized
    except Exception as e:
        logger.error(f"Error calculating similarity: {str(e)}")
        return 0.0
# Apply filters to job listings
def apply_filters(jobs, filters):
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
            job_text = (job.title + ' ' + job.description + ' ' + job.company + ' ' + ' '.join(job.skills)).lower()
            # Check if any keyword is present
            if any(kw in job_text for kw in keyword_list):
                filtered_jobs.append(job)
    logger.debug(f"Filtered jobs from {len(jobs)} to {len(filtered_jobs)}")

    return filtered_jobs

# Match jobs to resume using narrative + skill embeddings.
def find_matching_jobs(resume_embeddings, jobs=None, filters=None, resume_text=None, days=30):
    """
    Find jobs matching a resume using embeddings
    
    Args:
        resume_embeddings: Dict with 'narrative' and 'skills' embeddings
        jobs: Optional list of Job objects (if None, will load from storage)
        filters: Optional dictionary of filter criteria
        resume_text: Optional raw resume text for skill boosting
        days: Number of days to look back for jobs (if jobs not provided)
        
    Returns:
        List of JobMatch objects sorted by similarity score
    """
    logger.debug("Finding matching jobs (dual embeddings)")
    
    # Use the JobManager directly for matching
    global _job_manager
    if _job_manager is None:
        from job_manager import JobManager
        _job_manager = JobManager()
        
    # Use the consolidated matching function in JobManager
    return _job_manager.match_jobs_to_resume(
        resume_embeddings=resume_embeddings,
        jobs=jobs,
        filters=filters,
        resume_text=resume_text,
        days=days
    )
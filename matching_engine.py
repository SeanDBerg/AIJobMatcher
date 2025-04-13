# matching_engine.py
# Merged file containing functionality from:
# - matching_engine.py (job matching functionality)
# - embedding_generator.py (text embedding generation)
# - job_data.py (job data management)

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

def extract_skills(text: str, known_skills: set) -> set:
    """
    Extract matching skills from text using a known skills list.
    Args:
        text: Cleaned text input
        known_skills: A set of lowercase skill keywords
    Returns:
        Set of skills found in the text
    """
    tokens = text.lower().split()
    found = set()

    for token in tokens:
        if token in known_skills:
            found.add(token)
    logger.info("extract_skills returning with text=%s, known_skills=%s", text, known_skills)

    return found

def boost_score_with_skills(similarity: float, resume_text: str, job_text: str, known_skills=DEFAULT_SKILLS) -> float:
    resume_skills = extract_skills(resume_text, known_skills)
    job_skills = extract_skills(job_text, known_skills)
    overlap = resume_skills & job_skills

    if not overlap:
        logger.info("boost_score_with_skills returning with similarity=%s, resume_text=%s, job_text=%s, known_skills=%s", similarity, resume_text, job_text, known_skills)
        return similarity

    boost = 0.05 * len(overlap)
    logger.info("boost_score_with_skills returning with similarity=%s, resume_text=%s, job_text=%s, known_skills=%s", similarity, resume_text, job_text, known_skills)
    return min(similarity + boost, 1.0)

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
# JOB DATA SECTION (originally from job_data.py)
################################################################################

# Import Adzuna functions if available
try:
    from adzuna_scraper import get_adzuna_jobs
    ADZUNA_AVAILABLE = True
except ImportError:
    ADZUNA_AVAILABLE = False

# Cache for job data with embeddings
_job_cache = None
_job_cache_last_updated = None

# Load job data from Adzuna storage
def load_job_data():
    if ADZUNA_AVAILABLE:
        logger.debug("Loading job data from Adzuna storage")
        try:
            adzuna_jobs = get_adzuna_jobs(days=30)
            if adzuna_jobs and len(adzuna_jobs) > 0:
                logger.debug(f"Loaded {len(adzuna_jobs)} jobs from Adzuna storage")
                logger.info("load_job_data returning with no parameters")
                return adzuna_jobs
            else:
                logger.warning("No Adzuna jobs available")
                logger.info("load_job_data returning with no parameters")
                return []
        except Exception as e:
            logger.error(f"Error loading Adzuna jobs: {str(e)}")
            logger.info("load_job_data returning with no parameters")
            return []
    else:
        logger.warning("Adzuna API not available")
        logger.info("load_job_data returning with no parameters")
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
    logger.info("generate_job_embeddings returning with jobs=%s", jobs)

    return jobs

def get_job_data():
    """
    Get job data with embeddings, using cache if available
    """
    global _job_cache, _job_cache_last_updated

    # Check if we need to refresh the cache
    current_time = datetime.now()
    cache_age = (current_time - _job_cache_last_updated).total_seconds() if _job_cache_last_updated else None

    if _job_cache is None or cache_age is None or cache_age > 3600: # Refresh cache if older than 1 hour
        logger.debug("Refreshing job data cache")

        # Load job data
        jobs = load_job_data()

        # Generate embeddings
        jobs_with_embeddings = generate_job_embeddings(jobs)

        # Update cache
        _job_cache = jobs_with_embeddings
        _job_cache_last_updated = current_time
        logger.info("get_job_data returning with no parameters")

        return jobs_with_embeddings
    else:
        logger.debug("Using cached job data")
        logger.info("get_job_data returning with no parameters")
        return _job_cache

def add_job(job_dict):
    """
    Add a new job to the job data file
    """
    logger.debug(f"Adding new job: {job_dict.get('title')}")

    # Load existing jobs
    jobs = load_job_data()

    # Create new Job object
    new_job = Job(title=job_dict.get('title', ''), company=job_dict.get('company', ''), 
                 description=job_dict.get('description', ''), location=job_dict.get('location', ''), 
                 is_remote=job_dict.get('is_remote', False), posted_date=datetime.now(), 
                 url=job_dict.get('url', ''), skills=job_dict.get('skills', []), 
                 salary_range=job_dict.get('salary_range', ''))

    # Add to list
    jobs.append(new_job)

    # Invalidate cache
    global _job_cache, _job_cache_last_updated
    _job_cache = None
    _job_cache_last_updated = None
    logger.info("add_job returning with job_dict=%s", job_dict)

    return new_job

################################################################################
# MATCHING ENGINE SECTION (originally from matching_engine.py)
################################################################################

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
        logger.info("calculate_similarity returning with resume_embedding=%s, job_embedding=%s", resume_embedding, job_embedding)
        return 0.0

    similarity = dot_product / (norm_a * norm_b)
    logger.info("calculate_similarity returning with resume_embedding=%s, job_embedding=%s", resume_embedding, job_embedding)
    return (similarity + 1) / 2 # normalize to [0, 1]

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
            job_text = (job.title + ' ' + job.description + ' ' + job.company + ' ' + ' '.join(job.skills)).lower()

            # Check if any keyword is present
            if any(kw in job_text for kw in keyword_list):
                filtered_jobs.append(job)

    logger.debug(f"Filtered jobs from {len(jobs)} to {len(filtered_jobs)}")
    logger.info("apply_filters returning with jobs=%s, filters=%s", jobs, filters)

    return filtered_jobs

# Match jobs to resume using narrative + skill embeddings.
def find_matching_jobs(resume_embeddings, jobs, filters=None, resume_text=None):
    logger.debug("Finding matching jobs (dual embeddings)")

    if filters:
        filtered_jobs = apply_filters(jobs, filters)
    else:
        filtered_jobs = jobs

    matches = []
    for job in filtered_jobs:
        if job.embedding_narrative is None or job.embedding_skills is None:
            logger.warning(f"Job '{job.title}' missing dual embeddings")
            continue

        sim_narrative = calculate_similarity(resume_embeddings["narrative"], job.embedding_narrative)
        sim_skills = calculate_similarity(resume_embeddings["skills"], job.embedding_skills)

        similarity = (sim_narrative + sim_skills) / 2 # Weighted average
        logger.debug(f"{job.title}: sim_narrative={sim_narrative:.3f}, sim_skills={sim_skills:.3f}, final={similarity:.3f}")

        if resume_text:
            job_text = f"{job.title} {job.description} {' '.join(job.skills)}"
            similarity = boost_score_with_skills(similarity, resume_text, job_text, DEFAULT_SKILLS)

        matches.append(JobMatch(job, similarity))

    matches.sort(key=lambda m: m.similarity_score, reverse=True)
    logger.info("find_matching_jobs returning with resume_embeddings=%s, jobs=%s, filters=%s, resume_text=%s", resume_embeddings, jobs, filters, resume_text)
    return matches
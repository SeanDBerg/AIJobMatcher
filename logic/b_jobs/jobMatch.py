# jobMatch.py - Comprehensive matching logic
import logging
import numpy as np
import re
from datetime import datetime
from typing import List, Dict, Optional
from sklearn.feature_extraction.text import HashingVectorizer
logger = logging.getLogger(__name__)
class Job:
    def __init__(self, title, company, description, location, is_remote=False,
                 posted_date=None, url="", skills=None, salary_range=None, match_percentage=None):
        self.title = title
        self.company = company
        self.description = description
        self.location = location
        self.is_remote = is_remote
        self.posted_date = posted_date or datetime.now()
        self.url = url
        self.skills = skills or []
        self.salary_range = salary_range or ""
        self.match_percentage = match_percentage
    def to_dict(self, include_embeddings=False):
        return {
            'title': self.title,
            'company': self.company,
            'description': self.description,
            'location': self.location,
            'is_remote': self.is_remote,
            'posted_date': self.posted_date.isoformat() if isinstance(self.posted_date, datetime) else self.posted_date,
            'url': self.url,
            'skills': self.skills,
            'salary_range': self.salary_range,
            'match_percentage': self.match_percentage
        }
# === Embedding Utilities ===
EMBEDDING_DIM = 384 # Default embedding dimension for the all-MiniLM-L6-v2 model
vectorizer = HashingVectorizer(n_features=384, alternate_sign=False, norm='l2', stop_words='english', lowercase=True)
# Normalize text for embedding: Lowercase, Remove non-alphanumerics, Collapse whitespace
def clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text
# Generate embedding vector for the input text using deterministic hashing
def generate_embedding(text: str) -> np.ndarray:
    cleaned = clean_text(text)
    if not cleaned or len(cleaned) < 10:
        return np.zeros(EMBEDDING_DIM)
    try:
        return vectorizer.transform([cleaned]).toarray()[0]
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return np.zeros(EMBEDDING_DIM)
# Generate embeddings for a batch of texts
def batch_generate_embeddings(texts):
    return [generate_embedding(text) for text in texts]
# Sentence-aware chunking that splits text into chunks close to max_length.
def chunk_text(text, max_length=512, overlap=50):
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
    return chunks
# 
def generate_embedding_for_long_text(text, max_length=512, overlap=50):
    cleaned = clean_text(text)
    if len(cleaned) <= max_length:
        return generate_embedding(cleaned)
    chunks = chunk_text(cleaned, max_length, overlap)
    embeddings = [generate_embedding(chunk) for chunk in chunks if len(chunk.strip()) >= 10]
    if not embeddings:
        return np.zeros(EMBEDDING_DIM)
    return np.mean(embeddings, axis=0)
# Generate two embeddings: one for the full narrative, one for just the skills section.
def generate_dual_embeddings(text: str) -> dict:
    cleaned = clean_text(text)
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
    skill_text = " ".join(skill_blocks) if skill_blocks else cleaned
    return {
        "narrative": generate_embedding(cleaned),
        "skills": generate_embedding(clean_text(skill_text))
    }
# === Scoring and Filtering ===
DEFAULT_SKILLS = {"python", "java", "c++", "c#", "javascript", "typescript", "react", "node", "sql", "postgresql", "mysql", "mongodb", "aws", "azure", "gcp", "docker", "kubernetes", "git", "flask", "django", "linux", "pandas", "numpy", "tensorflow", "scikit", "html", "css", "bash", "redis", "graphql"}
# Extract matching skills from text using a known skills list.
def extract_skills(text: str, known_skills: set) -> set:
    tokens = text.lower().split()
    return {token for token in tokens if token in known_skills}
# Boost similarity score based on skill overlap
def boost_score_with_skills(similarity: float, resume_text: str, job_text: str, known_skills=DEFAULT_SKILLS) -> float:
    if similarity is None or not isinstance(similarity, (int, float)):
        return 0.0
    if resume_text is None or job_text is None:
        return similarity
    try:
        resume_skills = extract_skills(resume_text, known_skills)
        job_skills = extract_skills(job_text, known_skills)
        overlap = resume_skills & job_skills
        if not overlap:
            return similarity
        boost = 0.05 * len(overlap)
        return min(similarity + boost, 1.0)
    except Exception as e:
        logger.error(f"Error in boost_score_with_skills: {str(e)}")
        return similarity
# Calculate cosine similarity between resume and job embeddings
def calculate_similarity(resume_embedding, job_embedding):
    if resume_embedding is None or job_embedding is None:
        return 0.0
    try:
        resume_vec = np.array(resume_embedding)
        job_vec = np.array(job_embedding)
        if resume_vec.size == 0 or job_vec.size == 0:
            return 0.0
        if np.isnan(resume_vec).any() or np.isinf(resume_vec).any() or np.isnan(job_vec).any() or np.isinf(job_vec).any():
            return 0.0
        dot_product = np.dot(resume_vec, job_vec)
        norm_a = np.linalg.norm(resume_vec)
        norm_b = np.linalg.norm(job_vec)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        similarity = dot_product / (norm_a * norm_b)
        normalized = (similarity + 1) / 2
        return normalized
    except Exception as e:
        logger.error(f"Error calculating similarity: {str(e)}")
        return 0.0
# Apply filters to job listings
def apply_filters(jobs, filters):
    filtered_jobs = jobs.copy()
    if filters.get('remote'):
        filtered_jobs = [job for job in filtered_jobs if job.is_remote]
    location = filters.get('location', '').strip().lower()
    if location:
        filtered_jobs = [job for job in filtered_jobs if location in job.location.lower()]
    keywords = filters.get('keywords', '').strip()
    if keywords:
        keyword_list = [kw.strip().lower() for kw in keywords.split(',')]
        filtered_jobs = [job for job in filtered_jobs if any(kw in f"{job.title} {job.description} {job.company} {' '.join(job.skills)}".lower() for kw in keyword_list)]
    return filtered_jobs
# Assigns match percentage to each job based on resume embeddings
def get_resume_embeddings(resume_id):
    try:
        active_resume = resume_storage.get_resume(resume_id)
        if active_resume and "metadata" in active_resume:
            metadata = active_resume["metadata"]
            return {
                "narrative": np.array(metadata["embedding_narrative"]),
                "skills": np.array(metadata["embedding_skills"])
            }
        return None
    except Exception as e:
        logger.error(f"Error retrieving resume embeddings for ID {resume_id}: {str(e)}")
        return None
# === Resume Matching Pipeline ===
# Class representing a match between a resume and job
class JobMatch:
  def __init__(self, job, similarity_score):
    self.job = job
    self.similarity_score = similarity_score

  def to_dict(self):
    return {'job': self.job.to_dict(), 'similarity_score': self.similarity_score}
# Match jobs to a resume
def match_jobs_to_resume(resume_embeddings: Dict[str, np.ndarray], jobs: Optional[List[Job]] = None, filters: Optional[Dict] = None, resume_text: Optional[str] = None, days: int = 30) -> List[JobMatch]:
    if resume_embeddings is None or not isinstance(resume_embeddings, dict):
        return []
    if "narrative" not in resume_embeddings or "skills" not in resume_embeddings:
        return []
    if jobs is None:
        jobs = job_manager.get_recent_jobs(days=days)
    if not jobs:
        return []
    try:
        filtered_jobs = apply_filters(jobs, filters) if filters else jobs
    except Exception as e:
        logger.error(f"Error applying filters: {str(e)}")
        filtered_jobs = jobs
    matches = []
    for job in filtered_jobs:
        try:
            if not hasattr(job, 'embedding_narrative') or not hasattr(job, 'embedding_skills'):
                job_text = f"{job.title}\n{job.company}\n{job.description}"
                if job.skills:
                    job_text += "\nSkills: " + ", ".join(job.skills)
                embeddings = generate_dual_embeddings(job_text)
                job.embedding_narrative = embeddings["narrative"]
                job.embedding_skills = embeddings["skills"]
            sim_narrative = calculate_similarity(resume_embeddings["narrative"], job.embedding_narrative)
            sim_skills = calculate_similarity(resume_embeddings["skills"], job.embedding_skills)
            similarity = (sim_narrative + sim_skills) / 2
            if resume_text:
                job_text = f"{job.title} {job.description} {' '.join(job.skills)}"
                similarity = boost_score_with_skills(similarity, resume_text, job_text)
            matches.append(JobMatch(job, similarity))
        except Exception as e:
            logger.error(f"Error matching job '{job.title}': {str(e)}")
            continue
    try:
        matches.sort(key=lambda m: m.similarity_score, reverse=True)
    except Exception as e:
        logger.error(f"Error sorting matches: {str(e)}")
    return matches
# API endpoint to match resume to jobs
def match_jobs(data: dict) -> tuple[dict, int]:
    try:
        resume_id = data.get('resume_id')
        resume_text = data.get('resume_text', '')
        filters = data.get('filters', {})
        days = data.get('days', 30)
        if resume_id:
            try:
                resume_metadata = resume_storage.get_resume(resume_id)
                if not resume_metadata:
                    return {"success": False, "error": f"Resume with ID {resume_id} not found"}, 404
                resume_text = resume_storage.get_resume_content(resume_id) or ''
                if resume_metadata.get('embedding_narrative') and resume_metadata.get('embedding_skills'):
                    resume_embedding_narrative = np.array(resume_metadata['embedding_narrative'])
                    resume_embedding_skills = np.array(resume_metadata['embedding_skills'])
                else:
                    embeddings = generate_dual_embeddings(resume_text)
                    resume_embedding_narrative = embeddings['narrative']
                    resume_embedding_skills = embeddings['skills']
                if not filters and resume_metadata.get('filters'):
                    filters = resume_metadata['filters']
            except Exception as e:
                logger.error(f"Error retrieving resume {resume_id}: {str(e)}")
                return {"success": False, "error": f"Error retrieving resume: {str(e)}"}, 500
        else:
            if not resume_text or len(resume_text.strip()) < 50:
                return {"success": False, "error": "Resume text is too short. Please provide a complete resume."}, 400
            try:
                embeddings = generate_dual_embeddings(resume_text)
                resume_embedding_narrative = embeddings['narrative']
                resume_embedding_skills = embeddings['skills']
            except Exception as e:
                logger.error(f"Error generating embedding: {str(e)}")
                return {"success": False, "error": f"Error analyzing resume content: {str(e)}"}, 500
        try:
            jobs = job_manager.get_recent_jobs(days=days)
            if not jobs:
                return {"success": False, "error": "No job data available to match against"}, 500
        except Exception as e:
            logger.error(f"Error retrieving job data: {str(e)}")
            return {"success": False, "error": f"Error retrieving job data: {str(e)}"}, 500
        try:
            resume_embeddings = {
                "narrative": resume_embedding_narrative,
                "skills": resume_embedding_skills
            }
            matching_jobs = match_jobs_to_resume(
                resume_embeddings, jobs, filters, resume_text=resume_text
            )
            if not matching_jobs:
                return {
                    "success": True,
                    "matches": {},
                    "message": "No matching jobs found based on your filters. Try adjusting your search criteria."
                }, 200
        except Exception as e:
            logger.error(f"Error matching jobs: {str(e)}")
            return {"success": False, "error": f"Error matching jobs: {str(e)}"}, 500
        matches_dict = {}
        for job_match in matching_jobs:
            job_id = job_match.job.id if hasattr(job_match.job, 'id') else str(id(job_match.job))
            match_percentage = int(job_match.similarity_score * 100)
            matches_dict[job_id] = match_percentage
        return {
            "success": True,
            "matches": matches_dict,
            "count": len(matching_jobs),
            "resume_id": resume_id if resume_id else None
        }, 200
    except Exception as e:
        logger.error(f"Unexpected error in match_jobs: {str(e)}")
        return {"success": False, "error": f"Unexpected error: {str(e)}"}, 500
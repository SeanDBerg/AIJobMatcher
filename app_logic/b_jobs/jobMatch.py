# logic/b_jobs/jobMatch.py - Comprehensive matching logic
import os
import json
import logging
import numpy as np
import re
import hashlib
import time
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
from datetime import datetime
from typing import List, Dict, Optional
from sklearn.feature_extraction.text import HashingVectorizer
from sentence_transformers import SentenceTransformer
from app_logic.a_resume.resumeHistory import get_resume_content, get_resume, resume_storage
logger = logging.getLogger(__name__)
ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), '../../static/job_data/adzuna')
model = SentenceTransformer('all-MiniLM-L6-v2')
MATCH_CACHE_PATH = os.path.join(ADZUNA_DATA_DIR, 'match_cache.json')
# === Job Model ===
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
        self.embedding_narrative: Optional[np.ndarray] = None
        self.embedding_skills: Optional[np.ndarray] = None
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
# === Resume-to-Job Matching Engine ===
class JobMatch:
    def __init__(self, job, similarity_score: float, breakdown: Optional[Dict] = None):
        self.job = job
        self.similarity_score = similarity_score
        self.breakdown = breakdown or {}

    def to_dict(self):
        return {
            'job': self.job.to_dict(),
            'similarity_score': self.similarity_score,
            'breakdown': self.breakdown
        }
# === Title Normalization ===
def normalize_title(title: str, title_map: Dict[str, str]) -> str:
    return title_map.get(title.lower().strip(), title)
# === Guess resume title from the first role-like line in resume text ===
def extract_resume_title(text: str) -> str:
    lines = text.lower().splitlines()
    for line in lines:
        if any(term in line for term in ["developer", "engineer", "manager", "scientist", "analyst", "designer", "consultant"]):
            return line.strip()
    return "unknown"
# === Boost Similarity with Skill and Title Matching ===
def boost_score_with_skills(
    similarity: float,
    resume_text: str,
    job_text: str,
    skill_map: Optional[Dict[str, str]] = None,
    resume_title: Optional[str] = None,
    job_title: Optional[str] = None,
    title_map: Optional[Dict[str, str]] = None
) -> tuple[float, Dict]:
    breakdown = {
        "raw_similarity": similarity,
        "matched_tokens": [],
        "matched_categories": [],
        "bonus_breakdown": {},
        "title_match": False,
        "normalized_resume_title": resume_title,
        "normalized_job_title": job_title
    }
    score = similarity
    try:
        resume_tokens = tokenize_clean(resume_text)
        job_tokens = tokenize_clean(job_text)
        token_overlap = resume_tokens & job_tokens
        if token_overlap:
            bonus = min(0.02 * len(token_overlap), 0.10)
            score += bonus
            breakdown["matched_tokens"] = sorted(token_overlap)
            breakdown["bonus_breakdown"]["token_overlap_bonus"] = round(bonus, 4)
        if skill_map:
            resume_categories = find_skill_categories_in_text(resume_text, skill_map)
            job_categories = find_skill_categories_in_text(job_text, skill_map)
            category_overlap = resume_categories & job_categories
            if category_overlap:
                cat_bonus = min(0.05 * len(category_overlap), 0.20)
                score += cat_bonus
                breakdown["matched_categories"] = sorted(category_overlap)
                breakdown["bonus_breakdown"]["category_overlap_bonus"] = round(cat_bonus, 4)
        if resume_title and job_title and title_map:
            norm_resume_title = normalize_title(resume_title, title_map)
            norm_job_title = normalize_title(job_title, title_map)
            breakdown["normalized_resume_title"] = norm_resume_title
            breakdown["normalized_job_title"] = norm_job_title
            if norm_resume_title == norm_job_title:
                score += 0.05
                breakdown["title_match"] = True
                breakdown["bonus_breakdown"]["title_match_bonus"] = 0.05
        final_score = min(score, 1.0)
        return final_score, breakdown
    except Exception as e:
        logger.error(f"Error in boost_score_with_skills: {str(e)}")
        return similarity, breakdown
# === Match Caching Utilities ===
def _load_match_cache() -> dict:
    if os.path.exists(MATCH_CACHE_PATH):
        try:
            with open(MATCH_CACHE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[cache] Failed to load match cache: {e}")
    return {}

def _save_match_cache(cache: dict) -> None:
    try:
        with open(MATCH_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.warning(f"[cache] Failed to save match cache: {e}")

def _hash_jobs(jobs: List[Job]) -> str:
    job_data = "".join(sorted(job.url for job in jobs if job.url))
    return hashlib.sha256(job_data.encode('utf-8')).hexdigest()

def _hash_filters(filters: Optional[dict]) -> str:
    if not filters:
        return "nofilters"
    return hashlib.sha256(json.dumps(filters, sort_keys=True).encode('utf-8')).hexdigest()
# === Embedding Utilities ===
EMBEDDING_DIM = 384 # Default embedding dimension for the all-MiniLM-L6-v2 model
vectorizer = HashingVectorizer(n_features=384, alternate_sign=False, norm='l2', stop_words='english', lowercase=True)
# Get all jobs from all batches
def get_all_jobs(force_refresh=False) -> List[Job]:
    all_jobs = []
    try:
        for filename in os.listdir(ADZUNA_DATA_DIR):
            if filename.startswith("batch_") and filename.endswith(".json"):
                batch_path = os.path.join(ADZUNA_DATA_DIR, filename)
                with open(batch_path, 'r', encoding='utf-8') as f:
                    job_dicts = json.load(f)
                    for job_dict in job_dicts:
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
                        except Exception as job_err:
                            logger.warning(f"Could not parse job in {filename}: {job_err}")
        logger.debug("Loaded %d jobs from disk", len(all_jobs))
        return all_jobs
    except Exception as e:
        logger.error(f"[get_all_jobs] Error retrieving all jobs: {str(e)}")
        return []
# Normalize text for embedding: Lowercase, Remove non-alphanumerics, Collapse whitespace
def clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text
# Tokenize text into a set of words, excluding stop words from matching
def tokenize_clean(text: str) -> set:
    words = re.findall(r'\b[a-zA-Z0-9\-]{3,}\b', text.lower())
    return {w for w in words if w not in ENGLISH_STOP_WORDS}
# Generate embedding vector for the input text using deterministic hashing
def generate_embedding(text: str) -> np.ndarray:
    cleaned = clean_text(text)
    if not cleaned or len(cleaned) < 10:
        return np.zeros((EMBEDDING_DIM,), dtype=np.float32)
    try:
        encoded = model.encode(cleaned)
        return np.asarray(encoded, dtype=np.float32)
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return np.zeros((EMBEDDING_DIM,), dtype=np.float32)
# Sentence-aware chunking that splits text into chunks close to max_length.
def chunk_text(text, max_length=512, overlap=50):
    sentences = re.split(r'(?<=[.!?]) +', text)
    chunks = []
    current_chunk = ""
    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence if overlap <= 0 else current_chunk[-overlap:] + " " + sentence
        else:
            current_chunk += " " + sentence
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks
# Generate an averaged embedding over multiple text chunks using SentenceTransformer
def generate_embedding_for_long_text(text: str, max_length: int = 512, overlap: int = 50) -> np.ndarray:
    cleaned = clean_text(text)
    if len(cleaned) <= max_length:
        return generate_embedding(cleaned)

    chunks = chunk_text(cleaned, max_length, overlap)
    try:
        embeddings = model.encode(chunks)
        if isinstance(embeddings, list):  # sometimes model.encode returns list
            embeddings = np.asarray(embeddings, dtype=np.float32)
        return np.mean(embeddings, axis=0)
    except Exception as e:
        logger.error(f"Embedding generation failed for long text: {e}")
        return np.zeros((EMBEDDING_DIM,), dtype=np.float32)
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
        if collecting and (line.strip() == "" or len(skill_blocks) > 5):
            break
        skill_blocks.append(line.strip())
    skill_text = " ".join(skill_blocks) if skill_blocks else cleaned
    return {
        "narrative": generate_embedding_for_long_text(cleaned),
        "skills": generate_embedding_for_long_text(skill_text)
    }
# Extract matching skills from text using a known skills list.
def extract_skills(text: str, skill_map: Dict[str, str]) -> set:
    tokens = text.lower().split()
    known_skills = set(skill_map.keys())
    return {token for token in tokens if token in known_skills}

def find_skill_categories_in_text(text: str, skill_map: Dict[str, str]) -> set:
    found_categories = set()
    lower_text = text.lower()
    for skill, category in skill_map.items():
        if skill.lower() in lower_text:
            found_categories.add(category)
    return found_categories




# Calculate cosine similarity between resume and job embeddings
def calculate_similarity(resume_embedding, job_embedding):
    if resume_embedding is None or job_embedding is None:
        return 0.0
    try:
        a = np.array(resume_embedding)
        b = np.array(job_embedding)
        if np.any(np.isnan(a)) or np.any(np.isinf(a)) or np.any(np.isnan(b)) or np.any(np.isinf(b)):
            return 0.0
        similarity = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        return (similarity + 1) / 2  # normalize to 0–1
    except Exception as e:
        logger.error(f"Error calculating similarity: {str(e)}")
        return 0.0
# Apply filters to job listings
def apply_filters(jobs, filters):
    filtered = jobs.copy()
    if filters.get('remote'):
        filtered = [job for job in filtered if job.is_remote]
    loc = filters.get('location', '').strip().lower()
    if loc:
        filtered = [job for job in filtered if loc in job.location.lower()]
    keywords = filters.get('keywords', '').strip()
    if keywords:
        kw_list = [k.strip().lower() for k in keywords.split(',')]
        filtered = [job for job in filtered if any(kw in f"{job.title} {job.description} {job.company} {' '.join(job.skills)}".lower() for kw in kw_list)]
    return filtered
# Assigns match percentage to each job based on resume embeddings
def get_resume_embeddings(resume_id):
    try:
        metadata = get_resume_content(resume_id)
        if isinstance(metadata, dict) and "metadata" in metadata:
            inner = metadata.get("metadata", {})
            if isinstance(inner, dict) and "embedding_narrative" in inner and "embedding_skills" in inner:
                return {
                    "narrative": np.array(inner["embedding_narrative"], dtype=np.float32),
                    "skills": np.array(inner["embedding_skills"], dtype=np.float32)
                }
        return None
    except Exception as e:
        logger.error(f"Error retrieving resume embeddings for ID {resume_id}: {str(e)}")
        return None

# Match jobs to a resume
def match_jobs_to_resume(
    resume_embeddings: Dict[str, np.ndarray],
    jobs: Optional[List[Job]],
    filters: Optional[Dict] = None,
    resume_text: Optional[str] = None,
    skill_map: Optional[Dict[str, str]] = None,
    title_map: Optional[Dict[str, str]] = None,
    resume_title: Optional[str] = None
) -> List[JobMatch]:
    if not resume_embeddings or not all(k in resume_embeddings for k in ["narrative", "skills"]):
        return []
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
            normalized_title = normalize_title(job.title, title_map) if title_map else job.title
            job_text = f"{normalized_title}\n{job.company}\n{job.description}"
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
                similarity = boost_score_with_skills(
                    similarity,
                    resume_text,
                    job_text,
                    skill_map=skill_map,
                    resume_title=resume_title,
                    job_title=job.title,
                    title_map=title_map
                )

            matches.append(JobMatch(job, similarity))
        except Exception as e:
            logger.error(f"Error matching job '{job.title}': {str(e)}")

    return sorted(matches, key=lambda m: m.similarity_score, reverse=True)

# Extract skills from job data
def extract_skills_from_job(job_data: Dict, skill_map: Optional[Dict[str, str]] = None) -> List[str]:
    skills = []
    # Fallback to empty dict if none provided
    if skill_map is None:
        skill_map = {}
    all_possible_skills = set(skill_map.keys())
    # Simple skill detection based on job category and text
    if "category" in job_data and "tag" in job_data["category"]:
        category = job_data["category"]["tag"].lower()
        if any(k in category for k in ["it", "software", "developer"]):
            description = job_data.get("description", "").lower()
            title = job_data.get("title", "").lower()
            combined = f"{title} {description}"
            skills += [skill for skill in all_possible_skills if skill in combined]
    return list(set(skills))
# 
def match_jobs(data: dict) -> tuple[dict, int]:
    try:
        resume_id = data.get('resume_id')
        resume_text = data.get('resume_text', '')
        filters = data.get('filters', {})

        if resume_id:
            resume_metadata = get_resume(resume_id)
            if not resume_metadata:
                return {"success": False, "error": f"Resume with ID {resume_id} not found"}, 404
            resume_text = get_resume_content(resume_id) or ''
            if resume_metadata.get('embedding_narrative') and resume_metadata.get('embedding_skills'):
                resume_embedding_narrative = np.array(resume_metadata['embedding_narrative'])
                resume_embedding_skills = np.array(resume_metadata['embedding_skills'])
            else:
                embeddings = generate_dual_embeddings(resume_text)
                resume_embedding_narrative = embeddings['narrative']
                resume_embedding_skills = embeddings['skills']
            if not filters and resume_metadata.get('filters'):
                filters = resume_metadata['filters']
        else:
            if not resume_text or len(resume_text.strip()) < 50:
                return {"success": False, "error": "Resume text is too short. Please provide a complete resume."}, 400
            embeddings = generate_dual_embeddings(resume_text)
            resume_embedding_narrative = embeddings['narrative']
            resume_embedding_skills = embeddings['skills']

        resume_title_raw = extract_resume_title(resume_text)

        jobs = get_all_jobs(force_refresh=True)
        logger.debug(f"get_all_jobs returned {len(jobs)} jobs")
        if not jobs:
            return {"success": False, "error": "No job data available to match against"}, 500

        resume_embeddings = {
            "narrative": resume_embedding_narrative,
            "skills": resume_embedding_skills
        }

        skill_map = load_skill_map()
        title_map = load_title_map()
        resume_title_raw = extract_resume_title(resume_text)

        matching_jobs = match_jobs_to_resume(
            resume_embeddings,
            jobs,
            filters=filters,
            resume_text=resume_text,
            skill_map=skill_map,
            title_map=title_map,
            resume_title=resume_title_raw  # ✅ Pass it here
        )

        if not matching_jobs:
            return {
                "success": True,
                "matches": {},
                "message": "No matching jobs found based on your filters. Try adjusting your search criteria."
            }, 200

        matches_dict = {}
        for job_match in matching_jobs:
            job_id = getattr(job_match.job, 'id', str(id(job_match.job)))
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
# Returns {job.url: match_percentage} mapping for a given resume and job list
def get_match_percentages(resume_id: str, jobs: List[Job]) -> Dict[str, int]:
    try:
        resume_text = get_resume_content(resume_id)
        if not resume_text:
            logger.warning(f"No resume content found for ID {resume_id}")
            return {}

        resume_metadata = resume_storage._index["resumes"].get(resume_id)
        if not resume_metadata:
            logger.warning(f"No metadata found for resume ID {resume_id}")
            return {}

        if not isinstance(resume_metadata, dict):
            logger.warning(f"resume_metadata is not a dict for ID {resume_id}")
            return {}

        emb_narr = resume_metadata.get("embedding_narrative")
        emb_skill = resume_metadata.get("embedding_skills")

        if (
            isinstance(emb_narr, list)
            and isinstance(emb_skill, list)
            and len(emb_narr) == 384
            and len(emb_skill) == 384
        ):
            resume_embeddings = {
                "narrative": np.array(emb_narr, dtype=np.float32),
                "skills": np.array(emb_skill, dtype=np.float32)
            }
        else:
            logger.warning(f"[get_match_percentages] No valid embeddings for resume ID {resume_id}, generating...")
            embeddings = generate_dual_embeddings(resume_text)
            resume_embeddings = {
                "narrative": embeddings["narrative"],
                "skills": embeddings["skills"]
            }
            resume_metadata["embedding_narrative"] = embeddings["narrative"].tolist()
            resume_metadata["embedding_skills"] = embeddings["skills"].tolist()
            resume_storage._index["resumes"][resume_id] = resume_metadata
            resume_storage._save_index()
            logger.info(f"[get_match_percentages] Stored regenerated embeddings for resume ID {resume_id}")

        resume_title_raw = extract_resume_title(resume_text)

        job_hash = _hash_jobs(jobs)
        filters_hash = "nofilters"
        cache = _load_match_cache()
        cached = cache.get(resume_id, {}).get(job_hash, {}).get(filters_hash)

        if cached and "matches" in cached:
            logger.info(f"[cache] Using cached match results for resume {resume_id}")
            return cached["matches"]

        skill_map = load_skill_map()
        title_map = load_title_map()
        resume_title_raw = extract_resume_title(resume_text)

        matches = match_jobs_to_resume(
            resume_embeddings,
            jobs,
            resume_text=resume_text,
            skill_map=skill_map,
            title_map=title_map,
            resume_title=resume_title_raw  # ✅ Pass it here too
        )

        match_result = {m.job.url: int(m.similarity_score * 100) for m in matches}

        cache.setdefault(resume_id, {}).setdefault(job_hash, {})[filters_hash] = {
            "timestamp": time.time(),
            "matches": match_result
        }
        _save_match_cache(cache)

        return match_result

    except Exception as e:
        logger.error(f"Error computing match percentages: {str(e)}")
        return {}
# === Skill Mapping Utility ===
def load_skill_map() -> Dict[str, str]:
    path = os.path.join(os.path.dirname(__file__), '../../skills.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[load_skill_map] Failed to load skills.json: {e}")
        return {}
# === Title Mapping Utility ===
def load_title_map() -> Dict[str, str]:
    path = os.path.join(os.path.dirname(__file__), '../../title_map.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[load_title_map] Failed to load title_map.json: {e}")
        return {}


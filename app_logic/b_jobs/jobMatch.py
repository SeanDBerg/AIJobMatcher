# logic/b_jobs/jobMatch.py - Comprehensive matching logic
import os
import re
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, HashingVectorizer
from sentence_transformers import SentenceTransformer
from app_logic.a_resume.resumeHistory import get_resume_content, get_resume, resume_storage
logger = logging.getLogger(__name__)
ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), '../../static/job_data/adzuna')
MATCH_CACHE_PATH = os.path.join(ADZUNA_DATA_DIR, 'match_cache.json')
SKILLS_PATH = os.path.join(os.path.dirname(__file__), '../../skills.json')
TITLE_MAP_PATH = os.path.join(os.path.dirname(__file__), '../../title_map.json')
EMBEDDING_DIM = 384
model = SentenceTransformer('all-MiniLM-L6-v2')
vectorizer = HashingVectorizer(n_features=384, alternate_sign=False, norm='l2', stop_words='english', lowercase=True)
# === Job Model ===
class Job:
    def __init__(self, title, company, description, location, is_remote=False,
                 posted_date=None, url="", skills=None, salary_range=None, match_percentage=None, **kwargs):
        if kwargs:
            logger.debug(f"Ignoring extra job fields: {list(kwargs.keys())}")
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
# === Resume-to-Job Matching Model ===
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
# === Skill Mapping Utility ===
def load_skill_map() -> Dict[str, str]:
    try:
        with open(SKILLS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[load_skill_map] Failed: {e}")
        return {}
# === Title Mapping Utility ===
def load_title_map() -> Dict[str, str]:
    try:
        with open(TITLE_MAP_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[load_title_map] Failed: {e}")
        return {}
# Normalize text for embedding: Lowercase, Remove non-alphanumerics, Collapse whitespace
def clean_text(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9\s]', ' ', text.lower())).strip()
# Tokenize text into a set of words, excluding stop words from matching
def tokenize_clean(text: str) -> set:
    return {w for w in re.findall(r'\b[a-zA-Z0-9\-]{3,}\b', text.lower()) if w not in ENGLISH_STOP_WORDS}
# Generate embedding vector for the input text using deterministic hashing
def generate_embedding(text: str) -> np.ndarray:
    try:
        return np.asarray(model.encode(clean_text(text)), dtype=np.float32)
    except Exception as e:
        logger.error(f"[embedding] Failed: {e}")
        return np.zeros((EMBEDDING_DIM,), dtype=np.float32)
# Sentence-aware chunking that splits text into chunks close to max_length.
def chunk_text(text, max_length=512, overlap=50):
    sentences = re.split(r'(?<=[.!?]) +', text)
    chunks, current_chunk = [], ""
    for sentence in sentences:
        if len(current_chunk) + len(sentence) > max_length:
            chunks.append(current_chunk.strip())
            current_chunk = sentence
        else:
            current_chunk += " " + sentence
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks
# Generate an averaged embedding over multiple text chunks using SentenceTransformer
def generate_embedding_for_long_text(text: str) -> np.ndarray:
    cleaned = clean_text(text)
    if len(cleaned) < 10:
        return np.zeros((EMBEDDING_DIM,), dtype=np.float32)
    chunks = chunk_text(cleaned)
    try:
        embeddings = model.encode(chunks)
        return np.mean(np.asarray(embeddings, dtype=np.float32), axis=0)
    except Exception as e:
        logger.error(f"[embedding_long] Failed: {e}")
        return np.zeros((EMBEDDING_DIM,), dtype=np.float32)
# Generate two embeddings: one for the full narrative, one for just the skills section.
def generate_dual_embeddings(text: str) -> Dict[str, np.ndarray]:
    skill_lines = []
    skill_keywords = ['skills', 'technologies', 'tools']
    collecting = False
    for line in text.splitlines():
        if any(k in line.lower() for k in skill_keywords):
            collecting = True
            continue
        if collecting and (line.strip() == "" or len(skill_lines) > 5):
            break
        skill_lines.append(line.strip())
    skill_text = " ".join(skill_lines)
    return {
        "narrative": generate_embedding_for_long_text(text),
        "skills": generate_embedding_for_long_text(skill_text)
    }
# === Guess resume title from the first role-like line in resume text ===
def extract_resume_title(text: Optional[str]) -> str:
    if not text:
        return "unknown"
    for line in text.lower().splitlines():
        if any(role in line for role in ["developer", "engineer", "manager"]):
            return line.strip()
    return "unknown"
# === Title Normalization ===
def normalize_title(title: str, title_map: Dict[str, str]) -> str:
    return title_map.get(title.lower().strip(), title)
# === Skill Category Matching ===
def find_skill_categories_in_text(text: str, skill_map: Dict[str, str]) -> set:
    return {cat for skill, cat in skill_map.items() if skill in text.lower()}
# === Boost Similarity with Skill and Title Matching ===
def boost_score_with_skills(similarity: float, resume_text: str, job_text: str, skill_map, resume_title, job_title, title_map) -> Tuple[float, Dict]:
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
    resume_tokens = tokenize_clean(resume_text)
    job_tokens = tokenize_clean(job_text)
    token_overlap = resume_tokens & job_tokens
    if token_overlap:
        bonus = min(0.02 * len(token_overlap), 0.10)
        score += bonus
        breakdown["matched_tokens"] = sorted(token_overlap)
        breakdown["bonus_breakdown"]["token_overlap"] = round(bonus, 4)
    resume_cats = find_skill_categories_in_text(resume_text, skill_map)
    job_cats = find_skill_categories_in_text(job_text, skill_map)
    if resume_cats & job_cats:
        cat_bonus = min(0.05 * len(resume_cats & job_cats), 0.20)
        score += cat_bonus
        breakdown["matched_categories"] = sorted(resume_cats & job_cats)
        breakdown["bonus_breakdown"]["category_overlap"] = round(cat_bonus, 4)
    if resume_title and job_title:
        norm_resume = normalize_title(resume_title, title_map)
        norm_job = normalize_title(job_title, title_map)
        breakdown["normalized_resume_title"] = norm_resume
        breakdown["normalized_job_title"] = norm_job
        if norm_resume == norm_job:
            score += 0.05
            breakdown["title_match"] = True
            breakdown["bonus_breakdown"]["title_match"] = 0.05
    return min(score, 1.0), breakdown
# Calculate cosine similarity between resume and job embeddings
def calculate_similarity(a, b):
    try:
        if a is None or b is None:
            return 0.0
        a, b = np.array(a), np.array(b)
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        if denom == 0:
            logger.warning("[similarity] Invalid vector norm product (zero); returning 0.0")
            return 0.0
        similarity = float((np.dot(a, b) / denom + 1) / 2)
        if np.isnan(similarity):
            logger.warning("[similarity] NaN similarity result encountered; returning 0.0")
            return 0.0
        return similarity
    except Exception as e:
        logger.error(f"[similarity] Error: {str(e)}")
        return 0.0
# Get all jobs from all batches
def get_all_jobs() -> List[Job]:
    jobs = []
    try:
        for file in os.listdir(ADZUNA_DATA_DIR):
            if file.startswith("batch_") and file.endswith(".json"):
                with open(os.path.join(ADZUNA_DATA_DIR, file), 'r', encoding='utf-8') as f:
                    for job in json.load(f):
                        try:
                            jobs.append(Job(**job))
                        except Exception as err:
                            logger.warning(f"[get_all_jobs] Failed to parse job: {err}")
    except Exception as e:
        logger.error(f"[get_all_jobs] {e}")
    return jobs
# Resolve resume embeddings (narrative + skills) and text   
def resolve_resume_embeddings(resume_id: str) -> Tuple[Optional[Dict[str, np.ndarray]], Optional[str], Optional[Dict]]:
  try:
      metadata = get_resume(resume_id)
      if not metadata or not isinstance(metadata, dict):
          return None, None, {"error": f"Missing metadata for resume ID {resume_id}"}

      resume_text = get_resume_content(resume_id)
      if not resume_text:
          return None, None, {"error": f"Missing resume text for ID {resume_id}"}

      inner = metadata.get("metadata", {}) or metadata
      emb_narr = inner.get("embedding_narrative")
      emb_skill = inner.get("embedding_skills")

      if (
          isinstance(emb_narr, list)
          and isinstance(emb_skill, list)
          and len(emb_narr) == 384
          and len(emb_skill) == 384
      ):
          return {
              "narrative": np.array(emb_narr, dtype=np.float32),
              "skills": np.array(emb_skill, dtype=np.float32)
          }, resume_text, None

      # Fall back to regeneration
      logger.info(f"[resolve_resume_embeddings] Regenerating embeddings for resume ID {resume_id}")
      embeddings = generate_dual_embeddings(resume_text)
      resume_storage._index["resumes"][resume_id].setdefault("metadata", {})
      resume_storage._index["resumes"][resume_id]["metadata"]["embedding_narrative"] = embeddings["narrative"].tolist()
      resume_storage._index["resumes"][resume_id]["metadata"]["embedding_skills"] = embeddings["skills"].tolist()
      resume_storage._save_index()

      return embeddings, resume_text, None
  except Exception as e:
      logger.error(f"Error resolving embeddings for resume ID {resume_id}: {str(e)}")
      return None, None, {"error": str(e)}
# Match jobs to a resume
def match_jobs_to_resume(embeddings, resume_text, jobs, skill_map, title_map, resume_title) -> List[JobMatch]:
    matches = []
    for job in jobs:
        job_text = f"{job.title} {job.company} {job.description} {' '.join(job.skills)}"
        job_embeds = generate_dual_embeddings(job_text)
        job.embedding_narrative = job_embeds["narrative"]
        job.embedding_skills = job_embeds["skills"]
        sim_narr = calculate_similarity(embeddings["narrative"], job.embedding_narrative)
        sim_skill = calculate_similarity(embeddings["skills"], job.embedding_skills)
        raw_similarity = (sim_narr + sim_skill) / 2
        final_score, breakdown = boost_score_with_skills(
            raw_similarity, resume_text, job_text, skill_map, resume_title, job.title, title_map)
        matches.append(JobMatch(job, final_score, breakdown))
    return sorted(matches, key=lambda m: m.similarity_score, reverse=True)
# === Main Matching Function ===
def match_jobs(data: dict) -> Tuple[dict, int]:
    resume_id = data.get("resume_id")
    resume_text = data.get("resume_text")
    filters = data.get("filters", {})
    embeddings, resume_text, err = resolve_resume_embeddings(resume_id, resume_text)
    if err:
        return {"success": False, "error": err["error"]}, 400
    jobs = get_all_jobs()
    if not jobs:
        return {"success": False, "error": "No jobs available."}, 500
    resume_title = extract_resume_title(resume_text)
    skill_map = load_skill_map()
    title_map = load_title_map()
    matches = match_jobs_to_resume(embeddings, resume_text, jobs, skill_map, title_map, resume_title)
    return {
        "success": True,
        "matches": {getattr(m.job, 'url', str(id(m.job))): int(m.similarity_score * 100) for m in matches},
        "count": len(matches),
        "resume_id": resume_id
    }, 200
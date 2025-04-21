# logic/b_jobs/jobMatch.py - Comprehensive matching logic
import re
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, HashingVectorizer
import os
os.environ["TRANSFORMERS_NO_TQDM"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
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
    # Track ignored field occurrences for batch logging
    _ignored_field_counts: Dict[str, int] = {}
    def __init__(self, title, company, description, location, is_remote=False,
                 posted_date=None, url="", skills=None, salary_range=None, match_percentage=None, **kwargs):
        if kwargs:
            for key in kwargs.keys():
                Job._ignored_field_counts[key] = Job._ignored_field_counts.get(key, 0) + 1
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
    # Serialize job object to dictionary
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
    # Log summary of ignored fields
    @classmethod
    def log_ignored_field_summary(cls):
        if cls._ignored_field_counts:
            summary = ", ".join(f"{k} ({v}x)" for k, v in cls._ignored_field_counts.items())
            logger.debug(f"[Job] Ignored extra fields: {summary}")
            cls._ignored_field_counts.clear()
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
        embeddings = model.encode(chunks, show_progress_bar=False)
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
# === Aggregates boost_score_with_skills logs ===
class BoostScoreLogCounter:
    count = 0
    max_logs = 5
    # Log individual breakdowns
    @classmethod
    def log_breakdown(cls, breakdown: dict):
        cls.count += 1
        if cls.count <= cls.max_logs:
            logger.debug(f"[boost_score_with_skills] Breakdown calculated: {json.dumps(breakdown, indent=2)}")
    # Log summary of boost score calculations
    @classmethod
    def log_summary(cls):
        if cls.count > cls.max_logs:
            logger.info(f"[boost_score_with_skills] Breakdown suppressed for {cls.count - cls.max_logs} jobs")
        logger.info(f"[boost_score_with_skills] Total jobs scored: {cls.count}")
        cls.count = 0
# === Boost Similarity with Skill and Title Matching ===
def boost_score_with_skills(similarity, resume_text, job_text, skill_map, resume_title, job_title, title_map):
    breakdown = {
        "raw_similarity": similarity,
        "matched_tokens": [],
        "matched_categories": [],
        "similarity_score": 0.0,
        "token_bonus": 0.0,
        "category_bonus": 0.0,
        "title_bonus": 0.0,
        "total_bonus": 0.0,
        "title_match": False,
        "normalized_resume_title": resume_title,
        "normalized_job_title": job_title
    }
    similarity_score = similarity if not np.isnan(similarity) else 0.0
    total_bonus = 0.0

    # Token matching
    resume_tokens = tokenize_clean(resume_text)
    job_tokens = tokenize_clean(job_text)
    token_overlap = resume_tokens & job_tokens
    token_bonus = 0.0
    if token_overlap:
        token_bonus = min(0.02 * len(token_overlap), 0.10)
        breakdown["matched_tokens"] = sorted(token_overlap)

    # Category matching
    resume_cats = find_skill_categories_in_text(resume_text, skill_map)
    job_cats = find_skill_categories_in_text(job_text, skill_map)
    category_overlap = resume_cats & job_cats
    category_bonus = 0.0
    if category_overlap:
        category_bonus = min(0.05 * len(category_overlap), 0.20)
        breakdown["matched_categories"] = sorted(category_overlap)

    # Title matching
    title_bonus = 0.0
    if resume_title and job_title:
        norm_resume = normalize_title(resume_title, title_map)
        norm_job = normalize_title(job_title, title_map)
        breakdown["normalized_resume_title"] = norm_resume
        breakdown["normalized_job_title"] = norm_job
        if norm_resume == norm_job:
            title_bonus = 0.05
            breakdown["title_match"] = True

    # Calculate total bonus and update breakdown safely
    total_bonus = token_bonus + category_bonus + title_bonus
    breakdown.update({
        "similarity_score": round(similarity_score * 100, 2),
        "token_bonus": round(token_bonus * 100, 2),
        "category_bonus": round(category_bonus * 100, 2),
        "title_bonus": round(title_bonus * 100, 2),
        "total_bonus": round(total_bonus * 100, 2)
    })
    BoostScoreLogCounter.log_breakdown(breakdown)
    final_score = min(similarity_score + total_bonus, 1.0)

    return final_score, breakdown

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
        Job.log_ignored_field_summary()
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
    BoostScoreLogCounter.log_summary()
    return sorted(matches, key=lambda m: m.similarity_score, reverse=True)
# Match jobs to resume and cache results to avoid recomputation in future runs
def match_and_cache_jobs(jobs: List[Job], resume_id: str, resume_text: str) -> Dict[str, JobMatch]:
    logger.info(f"🟢 Starting job match and caching for resume {resume_id}")

    cache_file = os.path.join(ADZUNA_DATA_DIR, f"matchcache_{resume_id}.json")

    # Try to load cache
    cached = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
                cached = {
                    url: JobMatch(Job(**data['job']), data['similarity_score'], data.get('breakdown', {}))
                    for url, data in raw.items()
                }
            logger.info(f"📂 Loaded cache with {len(cached)} entries for resume {resume_id}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load cache for resume {resume_id}: {e}")

    # Only calculate matches for uncached jobs
    cached_urls = set(cached.keys())
    job_urls = [job.url for job in jobs if job.url]
    new_jobs = [job for job in jobs if job.url not in cached_urls]

    logger.debug(f"[match_and_cache_jobs] {len(cached_urls)} cached URLs loaded")
    logger.debug(f"[match_and_cache_jobs] Job URLs in request: {len(job_urls)}")
    logger.debug(f"[match_and_cache_jobs] Uncached jobs: {len(new_jobs)}")

    if not new_jobs:
        logger.info("✅ All jobs found in cache, skipping match calculations")
        return cached

    logger.info(f"🧠 Matching {len(new_jobs)} new jobs for resume {resume_id}")

    # Generate embeddings for resume
    embeddings, _, err = resolve_resume_embeddings(resume_id)
    if err:
        logger.error(f"❌ Could not resolve resume embeddings: {err}")
        return cached

    skill_map = load_skill_map()
    title_map = load_title_map()
    resume_title = extract_resume_title(resume_text)

    new_matches = match_jobs_to_resume(
        embeddings, resume_text, new_jobs, skill_map, title_map, resume_title
    )

    for i, match in enumerate(new_matches[:10]):
        logger.debug(f"📝 Cached: {match.job.title} ({match.job.url}) [{int(match.similarity_score * 100)}%]")

    for match in new_matches:
        cached[match.job.url] = match

    logger.info(f"📦 Cached {len(new_matches)} new matches (Total: {len(cached)}) for resume {resume_id}")

    # Save updated cache
    try:
        serializable = {
            url: {
                "job": match.job.to_dict(),
                "similarity_score": match.similarity_score,
                "breakdown": match.breakdown
            }
            for url, match in cached.items()
        }
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(serializable, f, indent=2)
        logger.info("💾 Match cache saved successfully")
    except Exception as e:
        logger.error(f"❌ Failed to save cache: {e}")

    return cached

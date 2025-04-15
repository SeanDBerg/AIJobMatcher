# jobMatch.py - Applies resume-to-job match scoring logic
import logging
import numpy as np
from typing import List, Dict
from models import Job, JobMatch
from resume_storage import resume_storage
from embedding_generator import generate_embedding_for_long_text
from matching_engine import find_matching_jobs
logger = logging.getLogger(__name__)
# Retrieve or generate embedding for a stored resume
def get_resume_embedding(resume_id: str) -> np.ndarray:
    resume_meta = resume_storage.get_resume(resume_id)
    if not resume_meta:
        raise ValueError(f"Resume ID {resume_id} not found")
    content = resume_storage.get_resume_content(resume_id)
    if not content:
        raise ValueError(f"Resume content missing for ID {resume_id}")
    embedding = resume_meta.get("embedding")
    if embedding is None:
        embedding = generate_embedding_for_long_text(content)
        resume_meta["embedding"] = embedding.tolist()
        resume_storage._index["resumes"][resume_id] = resume_meta
        resume_storage._save_index()
    if isinstance(embedding, list):
        embedding = np.array(embedding)
    return embedding
# Run full resume-to-jobs matching process and return scored matches
def score_jobs(resume_id: str, jobs: List[Job], filters: Dict = None) -> List[JobMatch]:
    try:
        resume_embedding = get_resume_embedding(resume_id)
        job_matches = find_matching_jobs(resume_embedding, jobs, filters or {})
        return job_matches
    except Exception as e:
        logger.error(f"[score_jobs] Error matching resume to jobs: {str(e)}")
        return []

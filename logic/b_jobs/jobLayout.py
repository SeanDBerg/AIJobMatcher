# jobLayout.py - Prepares job table context from stored Adzuna batches
import logging
from typing import Dict, Any
from logic.b_jobs.jobSync import get_adzuna_jobs
logger = logging.getLogger(__name__)
# Public function to assemble the context for index.html
def generate_table_context(session) -> Dict[str, Any]:
    try:
        keywords = session.get("keywords", "")
        location = session.get("location", "")
        country = session.get("country", "us")
        max_days_old = int(session.get("max_days_old", 7))
        remote_only = session.get("remote_only", "") == "1"
        jobs = get_adzuna_jobs(days=max_days_old)
        if remote_only:
            jobs = [job for job in jobs if job.is_remote]
        logger.debug(f"[generate_table_context] Loaded {len(jobs)} jobs (filtered)")
        jobs_dict = {i: job.to_dict() for i, job in enumerate(jobs)}
        return {
            "keywords": keywords,
            "location": location,
            "country": country,
            "max_days_old": max_days_old,
            "remote_only": remote_only,
            "jobs": jobs_dict,
            "job_count": len(jobs_dict),
            "recent_jobs_list": jobs_dict,
            "remote_jobs_list": {i: job for i, job in jobs_dict.items() if job.get("is_remote")},
        }
    except Exception as e:
        logger.error(f"[generate_table_context] Error: {str(e)}")
        return {
            "keywords": "",
            "location": "",
            "country": "us",
            "max_days_old": 7,
            "remote_only": False,
            "jobs": {},
            "job_count": 0
        }
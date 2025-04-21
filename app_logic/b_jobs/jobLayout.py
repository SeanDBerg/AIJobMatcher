# logic/b_jobs/jobLayout.py - Blueprint and logic for rendering job and batch data tables
import logging
import os
import json
import random
import numpy as np
from datetime import datetime, timedelta
from flask import Blueprint, jsonify
from app_logic.a_resume.resumeHistory import get_all_resumes, get_resume_content
from app_logic.b_jobs.jobMatch import Job, get_all_jobs, resolve_resume_embeddings, extract_resume_title, load_skill_map, load_title_map, match_jobs_to_resume
logger = logging.getLogger(__name__)
# Define the blueprint
layout_bp = Blueprint("layout_bp", __name__)
# === Constants ===
ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), '../../static/job_data/adzuna')
ADZUNA_INDEX_FILE = os.path.join(ADZUNA_DATA_DIR, 'index.json')
# === Helpers ===
# Generate a random date within the last N days
def _random_date_within(days: int) -> str:
    return (datetime.now() - timedelta(days=random.randint(0, days))).isoformat()
# Load a fixed number of jobs from demo batches
def _load_jobs_from_batches(count=25):
    jobs = []
    try:
        for filename in os.listdir(ADZUNA_DATA_DIR):
            if filename.startswith("batch_") and filename.endswith(".json"):
                path = os.path.join(ADZUNA_DATA_DIR, filename)
                with open(path, "r", encoding="utf-8") as f:
                    for job in json.load(f):
                        try:
                            job_obj = Job(**job)
                            job_obj.posted_date = _random_date_within(10)
                            jobs.append(job_obj)
                            if len(jobs) >= count:
                                return jobs
                        except Exception as e:
                            logger.warning(f"[demo job load] Failed to parse job: {e}")
    except Exception as e:
        logger.error(f"Error loading demo batch jobs: {str(e)}")
    return jobs[:count]
# Normalize any job to a dictionary (Job object or dict)
def normalize_job(job):
    try:
        if isinstance(job, dict):
            return job
        if hasattr(job, "to_dict"):
            return job.to_dict()
    except Exception as e:
        logger.error(f"[normalize_job] Failed to convert job: {e}")
    return {"title": "Unknown", "url": "", "match_percentage": 0}
# === Table Context Generation ===
# Public function to assemble the context for index.html
def generate_table_context(session):
    try:
        is_demo = session.get("demo", False)
        keywords = session.get("job_search_keywords", "")
        location = session.get("job_search_location", "")
        country = session.get("job_search_country", "us")
        remote_only = session.get("job_search_remote_only", "") == "1"

        jobs = _load_jobs_from_batches() if is_demo else get_all_jobs()
        stored_resumes = get_all_resumes()
        resume_id = session.get("resume_id")

        if resume_id and not any(r["id"] == resume_id for r in stored_resumes):
            logger.warning(f"Session resume_id {resume_id} is invalid. Clearing it.")
            session.pop("resume_id", None)
            resume_id = None

        if not resume_id and stored_resumes:
            resume_id = stored_resumes[0]["id"]
            session["resume_id"] = resume_id
            logger.info(f"No resume_id in session. Defaulting to: {resume_id}")

        match_map = {}
        if resume_id:
            resume_embeddings, resume_text, err = resolve_resume_embeddings(resume_id=resume_id)
            if not err and resume_embeddings and "narrative" in resume_embeddings and "skills" in resume_embeddings:
                original_count = len(jobs)
                jobs = [j for j in jobs if isinstance(j, Job)]
                filtered_count = len(jobs)
                if filtered_count < original_count:
                    logger.debug(f"Filtered out {original_count - filtered_count} non-Job entries before matching")

                resume_title = extract_resume_title(resume_text or "")
                skill_map = load_skill_map()
                title_map = load_title_map()
                matches = match_jobs_to_resume(
                    embeddings=resume_embeddings,
                    jobs=jobs,
                    resume_text=resume_text or "",
                    skill_map=skill_map,
                    title_map=title_map,
                    resume_title=resume_title
                )
                match_map = {
                    getattr(m.job, 'url', str(id(m.job))): int(m.similarity_score * 100)
                    for m in matches if not np.isnan(m.similarity_score)
                }
                logger.debug("Match percentages applied to %d jobs", len(match_map))
            else:
                logger.warning(f"[generate_table_context] Embedding error: {err['error'] if err else 'unknown'}")
        else:
            logger.warning("No resume ID provided, skipping match percentages")

        jobs = [
            {
                **normalize_job(job),
                "match_percentage": match_map.get(normalize_job(job).get("url") or "", 0),
                "posted_date": str(normalize_job(job).get("posted_date") or "")
            }
            for job in jobs
        ]

        remote_jobs = [job for job in jobs if job.get("is_remote")]
        jobs_dict = {job["url"]: job for job in jobs if job.get("url")}
        remote_dict = {job["url"]: job for job in remote_jobs if job.get("url")}

        return {
            "jobs": jobs_dict,
            "remote_jobs_list": remote_dict,
            "stored_resumes": stored_resumes,
            "total_jobs": len(jobs),
            "next_sync": "Manual sync only",
            "keywords": keywords,
            "location": location,
            "country": country,
            "remote_only": remote_only,
            "keywords_list": session.get("keywords_list", []),
            "storage_status": get_storage_status()
        }
    except Exception as e:
        logger.error(f"Error generating table context: {str(e)}")
        return {}
# === API Routes ===
# API endpoint to get job listings
@layout_bp.route("/api/jobs", methods=["GET"])
def get_jobs():
    try:
        jobs = get_all_jobs()
        logger.debug("Retrieved %d jobs for API", len(jobs))
        return jsonify({"success": True, "jobs": [normalize_job(job) for job in jobs]})
    except Exception as e:
        logger.error(f"Error fetching jobs: {str(e)}")
        return jsonify({"success": False, "error": str(e)})
# API endpoint to delete a specific batch
@layout_bp.route("/api/adzuna/batch/<batch_id>", methods=["DELETE"])
def delete_batch(batch_id):
    try:
        filename = f"batch_{batch_id}.json"
        path = os.path.join(ADZUNA_DATA_DIR, filename)
        if not os.path.exists(path):
            return jsonify({"success": False, "error": f"Batch file '{filename}' not found"}), 404
        os.remove(path)
        logger.info(f"Deleted batch file: {filename}")
        return jsonify({"success": True, "batch_id": batch_id})
    except Exception as e:
        logger.error(f"Error deleting batch {batch_id}: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
# API endpoint to get match percentages for a specific resume
@layout_bp.route("/api/match_percentages/<resume_id>", methods=["GET"])
def get_match_percentages_for_resume(resume_id):
    try:
        resume_text = get_resume_content(resume_id)
        embeddings, resume_text, err = resolve_resume_embeddings(resume_id=resume_id)
        if err:
            return jsonify({"success": False, "error": err["error"]}), 400
        jobs = get_all_jobs()
        resume_title = extract_resume_title(resume_text or "")
        skill_map = load_skill_map()
        title_map = load_title_map()
        matches = match_jobs_to_resume(
            embeddings, resume_text, jobs, skill_map, title_map, resume_title
        )
        return jsonify({
            "success": True,
            "matches": {
                getattr(m.job, 'url', str(id(m.job))): int(m.similarity_score * 100)
                for m in matches
            }
        })
    except Exception as e:
        logger.error(f"Error fetching matches for resume {resume_id}: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
# Batch metadata summarization for frontend display
def get_storage_status() -> dict:
    batches = {}
    try:
        for filename in os.listdir(ADZUNA_DATA_DIR):
            if not filename.startswith("batch_") or not filename.endswith(".json"):
                continue
            batch_id = filename.removeprefix("batch_").removesuffix(".json")
            path = os.path.join(ADZUNA_DATA_DIR, filename)
            try:
                file_ctime = os.path.getctime(path)
                timestamp_str = datetime.fromtimestamp(file_ctime).strftime("%Y-%m-%d %I:%M %p")
            except Exception:
                timestamp_str = "Unknown"
            with open(path, 'r', encoding='utf-8') as f:
                jobs = json.load(f)
                job_count = len(jobs)
                first_job = jobs[0] if jobs else {}
                batches[batch_id] = {
                    "timestamp": timestamp_str,
                    "job_count": job_count,
                    "keywords": ", ".join(first_job.get("skills", [])) if first_job.get("skills") else "",
                    "location": first_job.get("location", "")
                }
    except Exception as e:
        logger.error(f"[get_storage_status] Failed to generate batch summary: {str(e)}")
    return {"batches": batches}
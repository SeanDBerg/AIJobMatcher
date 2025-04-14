# logic/b_jobs/jobLayout.py - Blueprint and logic for rendering job and batch data tables
import logging
import os
import json
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
import numpy as np
from logic.a_resume.resumeHistory import get_all_resumes, get_resume
from logic.b_jobs.jobMatch import match_jobs_to_resume, Job
logger = logging.getLogger(__name__)
# Define the blueprint
layout_bp = Blueprint("layout_bp", __name__)
# === Constants ===
ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), '../../static/job_data/adzuna')
ADZUNA_INDEX_FILE = os.path.join(ADZUNA_DATA_DIR, 'index.json')
# === Index and Batch Utilities ===
# Get the job index with caching
def get_index(force_refresh=False):
  if not hasattr(get_index, "_cache"):
    get_index._cache = None
    get_index._timestamp = None
  if not force_refresh and get_index._cache and get_index._timestamp:
    age = (datetime.now() - get_index._timestamp).total_seconds()
    if age < 5:
      return get_index._cache
  try:
    with open(ADZUNA_INDEX_FILE, 'r', encoding='utf-8') as f:
      index = json.load(f)
    index.setdefault("batches", {})
    index.setdefault("job_count", 0)
    index.setdefault("last_sync", None)
    index.setdefault("last_batch", None)
    get_index._cache = index
    get_index._timestamp = datetime.now()
    return index
  except Exception as e:
    logger.error(f"Error loading index: {str(e)}")
    index = {"batches": {}, "job_count": 0, "last_sync": None, "last_batch": None}
    get_index._cache = index
    get_index._timestamp = datetime.now()
    return index
# Load a batch of jobs from disk
def _load_job_batch(self, batch_id: str) -> List[Dict]:
  batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")

  if not os.path.exists(batch_file):
    logger.warning(f"Batch file {batch_id} not found")
    return []

  try:
    with open(batch_file, 'r', encoding='utf-8') as f:
      return json.load(f)
  except Exception as e:
    logger.error(f"Error loading batch {batch_id}: {str(e)}")
    return []
# Delete a specific batch of jobs
def delete_batch(batch_id):
  try:
    index = get_index(force_refresh=True)
    if batch_id not in index["batches"]:
      return False
    job_count = index["batches"][batch_id]["job_count"]
    batch_file = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
    if os.path.exists(batch_file):
      os.remove(batch_file)
    del index["batches"][batch_id]
    index["job_count"] = max(0, index["job_count"] - job_count)

    if index["last_batch"] == batch_id:
      index["last_batch"] = None
      if index["batches"]:
        index["last_batch"] = max(index["batches"].items(), key=lambda x: x[1]["timestamp"])[0]
    with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
      json.dump(index, f, indent=2)
    get_index._cache = index
    get_index._timestamp = datetime.now()
    return True
  except Exception as e:
    logger.error(f"Error deleting batch {batch_id}: {str(e)}")
    return False
# === Job Retrieval ===
# Get all jobs with caching
def get_all_jobs(force_refresh=False):
  if not hasattr(get_all_jobs, "_cache"):
    get_all_jobs._cache = None
    get_all_jobs._timestamp = None
  if not force_refresh and get_all_jobs._cache and get_all_jobs._timestamp:
    age = (datetime.now() - get_all_jobs._timestamp).total_seconds()
    if age < 10:
      return get_all_jobs._cache
  try:
    index = get_index()
    all_jobs = []
    for batch_id in index["batches"]:
      path = os.path.join(ADZUNA_DATA_DIR, f"batch_{batch_id}.json")
      if not os.path.exists(path):
        continue
      try:
        with open(path, 'r', encoding='utf-8') as f:
          job_dicts = json.load(f)
          for job_dict in job_dicts:
            job = Job(title=job_dict["title"], company=job_dict["company"], description=job_dict["description"], location=job_dict["location"], is_remote=job_dict.get("is_remote", False), posted_date=job_dict.get("posted_date"), url=job_dict.get("url", ""), skills=job_dict.get("skills", []), salary_range=job_dict.get("salary_range"))
            all_jobs.append(job)
      except Exception as e:
        logger.error(f"Error loading batch {batch_id}: {str(e)}")
        continue
    get_all_jobs._cache = all_jobs
    get_all_jobs._timestamp = datetime.now()
    return all_jobs
  except Exception as e:
    logger.error(f"Error retrieving all jobs: {str(e)}")
    return []
# Get recent jobs with caching
def get_recent_jobs(days=30, force_refresh=False):
  all_jobs = get_all_jobs(force_refresh=force_refresh)
  if not all_jobs:
    return []

  cutoff = datetime.now() - timedelta(days=days)
  recent_jobs = []
  for job in all_jobs:
    try:
      if isinstance(job.posted_date, str):
        job_date = datetime.fromisoformat(job.posted_date[:10])
      else:
        job_date = job.posted_date
      if job_date >= cutoff:
        recent_jobs.append(job)
    except Exception as e:
      logger.warning(f"Date parsing error for job {job.title}: {str(e)}")
      continue
  return recent_jobs
# === Table Context Generation ===
# Utility to filter jobs by recent and remote
def _filter_recent_jobs(jobs, days=7):
  recent = []
  for job in jobs:
    if job.posted_date:
      try:
        job_date = datetime.fromisoformat(job.posted_date.split("T")[0]) if isinstance(job.posted_date, str) else job.posted_date
        if (datetime.now() - job_date).days <= days:
          recent.append(job)
      except Exception:
        continue
  return recent
# 
def _filter_remote_jobs(jobs):
  return [job for job in jobs if job.is_remote]
# Format salary range as a human-readable string
def format_salary_range(self, min_salary, max_salary) -> Optional[str]:
  if min_salary is None and max_salary is None:
    return None
  if min_salary and max_salary:
    if min_salary == max_salary:
      return f"£{min_salary:,.0f}"
    return f"£{min_salary:,.0f} - £{max_salary:,.0f}"
  elif min_salary:
    return f"£{min_salary:,.0f}+"
  elif max_salary:
    return f"Up to £{max_salary:,.0f}"
  return None
# Public function to assemble the context for index.html
# Public function to assemble the context for index.html
def generate_table_context(session):
  try:
    keywords = session.get("keywords", "")
    location = session.get("location", "")
    country = session.get("country", "us")
    max_days_old = session.get("max_days_old", "1")
    remote_only = session.get("remote_only", "") == "1"

    jobs = get_recent_jobs(days=30)
    recent_jobs = _filter_recent_jobs(jobs)
    remote_jobs = _filter_remote_jobs(jobs)

    resume_id = session.get("resume_id")
    resume_embeddings = None

    if resume_id:
      active_resume = get_resume(resume_id)
      if not active_resume:
        logger.warning(f"Resume ID {resume_id} not found in storage")
      else:
        metadata = active_resume.get("metadata", {})
        if "embedding_narrative" in metadata and "embedding_skills" in metadata:
          resume_embeddings = {
            "narrative": np.array(metadata["embedding_narrative"]),
            "skills": np.array(metadata["embedding_skills"])
          }
          logger.debug(f"Loaded embeddings from metadata for resume_id {resume_id}")
        else:
          logger.warning(f"Missing embeddings in metadata for resume_id {resume_id}")
          from logic.b_jobs.jobMatch import generate_dual_embeddings
          from logic.a_resume.resumeHistory import resume_storage
          resume_text = resume_storage.get_resume_content(resume_id)
          if resume_text:
            embeddings = generate_dual_embeddings(resume_text)
            resume_embeddings = {
              "narrative": embeddings["narrative"],
              "skills": embeddings["skills"]
            }
            logger.debug(f"Generated new embeddings from resume text for resume_id {resume_id}")
          else:
            logger.warning(f"Could not load resume text for resume_id {resume_id}")

    if resume_embeddings:
      matches = match_jobs_to_resume(resume_embeddings, jobs=jobs)
      match_map = {m.job.url: int(m.similarity_score * 100) for m in matches}
      logger.debug("Assigned match percentages for %d jobs", len(match_map))
    else:
      logger.warning("No resume embeddings available, match percentages will be 0")
      match_map = {}

    for job in jobs:
      job.match_percentage = match_map.get(job.url, 0)

    jobs_dict = {i: job.to_dict() for i, job in enumerate(jobs)}
    recent_dict = {i: job.to_dict() for i, job in enumerate(recent_jobs)}
    remote_dict = {i: job.to_dict() for i, job in enumerate(remote_jobs)}

    return {
      "jobs": jobs_dict,
      "recent_jobs_list": recent_dict,
      "remote_jobs_list": remote_dict,
      "stored_resumes": get_all_resumes(),
      "total_jobs": len(jobs),
      "recent_jobs": len(recent_jobs),
      "next_sync": "Manual sync only",
      "keywords": keywords,
      "location": location,
      "country": country,
      "max_days_old": max_days_old,
      "remote_only": remote_only,
      "keywords_list": session.get("keywords_list", [])
    }

  except Exception as e:
    logger.error(f"Error generating table context: {str(e)}")
    return {}

# === API Routes ===
# API endpoint to get job listings
@layout_bp.route("/api/jobs", methods=["GET"])
def get_jobs():
  try:
    days = request.args.get("days", 30, type=int)
    jobs = get_recent_jobs(days=days)
    logger.debug("Retrieved %d jobs for API", len(jobs))
    return jsonify({"success": True, "jobs": [job.to_dict() for job in jobs]})
  except Exception as e:
    logger.error(f"Error fetching jobs: {str(e)}")
    return jsonify({"success": False, "error": str(e)})
# API endpoint to delete a specific batch
@layout_bp.route("/api/adzuna/batch/<batch_id>", methods=["DELETE"])
def delete_adzuna_batch(batch_id):
  try:
    success = delete_batch(batch_id)
    if not success:
      logger.warning(f"Batch {batch_id} not found or could not be deleted")
      return jsonify({"success": False, "error": f"Batch {batch_id} not found or could not be deleted"}), 404

    status = get_index()
    logger.debug(f"Successfully deleted batch {batch_id}")
    return jsonify({"success": True, "batch_id": batch_id, "status": status})

  except Exception as e:
    logger.error(f"Error deleting batch {batch_id}: {str(e)}")
    return jsonify({"success": False, "error": f"Error deleting batch {batch_id}: {str(e)}"}), 500


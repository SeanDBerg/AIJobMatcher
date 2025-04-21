




















# Maybe from jobLayout.py
def _filter_remote_jobs(jobs):
  return [job for job in jobs if job.get("is_remote")]
# Format salary range as a human-readable string
def format_salary_range(min_salary, max_salary) -> Optional[str]:
  if min_salary is None and max_salary is None:
      return None
  if min_salary and max_salary:
      if min_salary == max_salary:
          return f"${min_salary:,.0f}"
      return f"${min_salary:,.0f} - £{max_salary:,.0f}"
  elif min_salary:
      return f"${min_salary:,.0f}+"
  elif max_salary:
      return f"Up to ${max_salary:,.0f}"
  return None
@layout_bp.route("/api/match_percentages/<resume_id>", methods=["GET"])
def get_match_percentages_for_resume(resume_id):
  try:
      jobs = get_all_jobs(force_refresh=True)
      matches = get_match_percentages(resume_id, jobs)
      return jsonify({"success": True, "matches": matches})
  except Exception as e:
      logger.error(f"Error fetching matches for resume {resume_id}: {str(e)}")
      return jsonify({"success": False, "error": str(e)})




# Maybes from JobMatch.py

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
# Extract matching skills from text using a known skills list.
def extract_skills(text: str, skill_map: Dict[str, str]) -> set:
    tokens = text.lower().split()
    known_skills = set(skill_map.keys())
    return {token for token in tokens if token in known_skills}
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
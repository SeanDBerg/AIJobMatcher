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
        return 0.0

    similarity = dot_product / (norm_a * norm_b)
    return (similarity + 1) / 2  # normalize to [0, 1]


# Find jobs that match a resume based on embedding similarity and filters
def find_matching_jobs(resume_embedding, jobs, filters=None, resume_text=None):
    logger.debug("Finding matching jobs")

    if filters:
        filtered_jobs = apply_filters(jobs, filters)
    else:
        filtered_jobs = jobs

    job_matches = []
    for job in filtered_jobs:
        if job.embedding is None:
            logger.warning(f"Job '{job.title}' has no embedding")
            continue

        similarity = calculate_similarity(resume_embedding, job.embedding)

        # ⬇️ BOOST: Apply skill overlap if resume_text is provided
        if resume_text:
            job_text = f"{job.title} {job.description} {' '.join(job.skills)}"
            similarity = boost_score_with_skills(similarity, resume_text, job_text, DEFAULT_SKILLS)

        job_match = JobMatch(job, similarity)
        job_matches.append(job_match)

    job_matches.sort(key=lambda x: x.similarity_score, reverse=True)
    logger.debug(f"Found {len(job_matches)} matching jobs")

    return job_matches
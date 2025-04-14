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





















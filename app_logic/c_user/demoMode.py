# demoMode.py - Generates fake job entries using real historical data
import os
import json
import random
from datetime import datetime, timedelta
from app_logic.b_jobs.jobLayout import ADZUNA_DATA_DIR

def _load_all_jobs_from_batches(max_count=32):
    jobs = []
    for filename in os.listdir(ADZUNA_DATA_DIR):
        if filename.startswith("batch_") and filename.endswith(".json"):
            path = os.path.join(ADZUNA_DATA_DIR, filename)
            with open(path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    for job in data:
                        if "title" in job and "company" in job:
                            jobs.append(job)
                            if len(jobs) >= max_count:
                                return jobs
                except Exception:
                    continue
    return jobs

def _random_date_within(days: int) -> str:
    return (datetime.now() - timedelta(days=random.randint(0, days))).isoformat()

def get_demo_jobs(initial=True):
    raw_jobs = _load_all_jobs_from_batches()
    count = 25 if initial else 7
    demo_jobs = []
    for job in raw_jobs[:count]:
        demo = job.copy()
        demo["posted_date"] = _random_date_within(10 if initial else 1)
        demo["match_percentage"] = random.choice([60, 70, 80, 90])
        demo_jobs.append(demo)
    return demo_jobs





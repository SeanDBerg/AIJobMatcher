# logic/b_jobs/jobUtils.py - Common utility functions for job-related operations
import os
import json
import logging
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)

# === Constants ===
ADZUNA_DATA_DIR = os.path.join(os.path.dirname(__file__), '../../static/job_data/adzuna')
ADZUNA_INDEX_FILE = os.path.join(ADZUNA_DATA_DIR, 'index.json')

# Global caching mechanism for job index to avoid repeated disk reads
_index_cache = None
_index_cache_timestamp = None
INDEX_CACHE_TTL_SECONDS = 10

# Save job index to disk and update cache
def save_index(index: Dict) -> bool:
    global _index_cache, _index_cache_timestamp
    try:
        with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2)
        _index_cache = index
        _index_cache_timestamp = datetime.now()
        logger.debug("Saved job index to disk")
        return True
    except Exception as e:
        logger.error(f"Error saving job index: {str(e)}")
        return False

# Load the Adzuna job index from disk with optional caching.
def get_index(force_refresh=False) -> Dict:
    global _index_cache, _index_cache_timestamp
    if not force_refresh and _index_cache and _index_cache_timestamp:
        age = (datetime.now() - _index_cache_timestamp).total_seconds()
        if age < INDEX_CACHE_TTL_SECONDS:
            return _index_cache
    try:
        if not os.path.exists(ADZUNA_INDEX_FILE):
            logger.warning("Index file not found. Creating empty index.")
            _index_cache = {"batches": {}, "job_count": 0, "last_sync": None, "last_batch": None}
            save_index(_index_cache)
            _index_cache_timestamp = datetime.now()
            return _index_cache
        with open(ADZUNA_INDEX_FILE, 'r', encoding='utf-8') as f:
            index = json.load(f)
        index.setdefault("batches", {})
        index.setdefault("job_count", 0)
        index.setdefault("last_sync", None)
        index.setdefault("last_batch", None)
        _index_cache = index
        _index_cache_timestamp = datetime.now()
        return index
    except Exception as e:
        logger.error(f"Error loading job index: {str(e)}")
        _index_cache = {"batches": {}, "job_count": 0, "last_sync": None, "last_batch": None}
        _index_cache_timestamp = datetime.now()
        return _index_cache

# Create an empty job index file
def create_empty_index() -> None:
    empty_index = {"batches": {}, "job_count": 0, "last_sync": None, "last_batch": None}
    try:
        with open(ADZUNA_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(empty_index, f, indent=2)
        logger.debug("Created new empty index file")
    except Exception as e:
        logger.error(f"Error creating index file: {str(e)}")
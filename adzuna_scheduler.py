# adzuna_scheduler.py = Scheduling module for Adzuna job synchronization
import logging
import os
import time
import threading
from datetime import datetime, timedelta
import json
import traceback

from adzuna_scraper import sync_jobs_from_adzuna, get_adzuna_storage_status, cleanup_old_adzuna_jobs
from adzuna_api import get_api_credentials, AdzunaAPIError

logger = logging.getLogger(__name__)

# Scheduler configuration
SCHEDULER_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'static', 'job_data', 'adzuna', 'scheduler_config.json')
DEFAULT_CONFIG = {
    'enabled': False,
    'daily_sync_time': '02:00',  # 2 AM in 24-hour format
    'keywords': '',
    'location': '',
    'country': 'gb',
    'cleanup_old_jobs': True,
    'cleanup_days': 90,
    'last_run': None,
    'next_run': None
}

# Global scheduler thread
_scheduler_thread = None
_stop_scheduler = False

def _load_scheduler_config():
    """
    Load scheduler configuration from file
    
    Returns:
        dict: Scheduler configuration
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(SCHEDULER_CONFIG_FILE), exist_ok=True)
        
        # Load config if it exists
        if os.path.exists(SCHEDULER_CONFIG_FILE):
            with open(SCHEDULER_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # Fill in any missing keys with defaults
                for key, value in DEFAULT_CONFIG.items():
                    if key not in config:
                        config[key] = value
                return config
        
        # Create default config if it doesn't exist
        with open(SCHEDULER_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        
        return DEFAULT_CONFIG.copy()
        
    except Exception as e:
        logger.error(f"Error loading scheduler config: {str(e)}")
        return DEFAULT_CONFIG.copy()

def _save_scheduler_config(config):
    """
    Save scheduler configuration to file
    
    Args:
        config: Configuration dictionary
    """
    try:
        with open(SCHEDULER_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving scheduler config: {str(e)}")

def update_scheduler_config(config_updates):
    """
    Update scheduler configuration
    
    Args:
        config_updates: Dictionary of configuration updates
        
    Returns:
        dict: Updated configuration
    """
    config = _load_scheduler_config()
    
    # Update configuration
    for key, value in config_updates.items():
        if key in config:
            config[key] = value
    
    # Calculate next run time
    if 'daily_sync_time' in config_updates or 'enabled' in config_updates:
        if config['enabled']:
            config['next_run'] = _calculate_next_run_time(config['daily_sync_time'])
        else:
            config['next_run'] = None
    
    # Save updated config
    _save_scheduler_config(config)
    
    # Restart scheduler if it's already running
    restart_scheduler()
    
    return config

def get_scheduler_config():
    """
    Get current scheduler configuration
    
    Returns:
        dict: Scheduler configuration
    """
    return _load_scheduler_config()

def _calculate_next_run_time(time_str):
    """
    Calculate the next run time based on the daily sync time
    
    Args:
        time_str: Time string in HH:MM format
        
    Returns:
        str: Next run time as ISO format string
    """
    try:
        # Parse time string
        hour, minute = map(int, time_str.split(':'))
        
        # Get current time
        now = datetime.now()
        
        # Calculate target time for today
        target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If target time is in the past, set it for tomorrow
        if target_time <= now:
            target_time += timedelta(days=1)
        
        return target_time.isoformat()
        
    except Exception as e:
        logger.error(f"Error calculating next run time: {str(e)}")
        # Default to 24 hours from now
        return (datetime.now() + timedelta(days=1)).isoformat()

def _scheduler_loop():
    """
    Main scheduler loop that runs in a separate thread
    """
    global _stop_scheduler
    
    logger.info("Adzuna job scheduler started")
    
    while not _stop_scheduler:
        try:
            # Load current config
            config = _load_scheduler_config()
            
            # Skip if scheduler is disabled
            if not config['enabled']:
                time.sleep(60)  # Check again in 1 minute
                continue
            
            # Check if it's time to run
            now = datetime.now()
            next_run = datetime.fromisoformat(config['next_run']) if config['next_run'] else None
            
            if next_run and now >= next_run:
                logger.info("Starting scheduled Adzuna job sync")
                
                try:
                    # Verify API credentials are available
                    get_api_credentials()
                    
                    # Run the sync
                    result = sync_jobs_from_adzuna(
                        keywords=config['keywords'],
                        location=config['location'],
                        country=config['country'],
                        max_pages=None  # No limit on pages for scheduled sync
                    )
                    
                    logger.info(f"Scheduled sync completed: {result.get('new_jobs', 0)} new jobs added")
                    
                    # Cleanup old jobs if enabled
                    if config['cleanup_old_jobs']:
                        removed_count = cleanup_old_adzuna_jobs(max_age_days=config['cleanup_days'])
                        logger.info(f"Cleaned up {removed_count} old jobs")
                    
                    # Update last run and next run times
                    config['last_run'] = now.isoformat()
                    config['next_run'] = _calculate_next_run_time(config['daily_sync_time'])
                    _save_scheduler_config(config)
                    
                except AdzunaAPIError as e:
                    logger.error(f"Adzuna API error during scheduled sync: {str(e)}")
                except Exception as e:
                    logger.error(f"Error during scheduled sync: {str(e)}")
                    logger.error(traceback.format_exc())
            
            # Sleep for a minute before checking again
            time.sleep(60)
            
        except Exception as e:
            logger.error(f"Error in scheduler loop: {str(e)}")
            logger.error(traceback.format_exc())
            time.sleep(300)  # Sleep for 5 minutes on error

def start_scheduler():
    """
    Start the Adzuna job scheduler
    """
    global _scheduler_thread, _stop_scheduler
    
    # Don't start if already running
    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.info("Scheduler already running")
        return False
    
    # Load config and make sure next run time is set
    config = _load_scheduler_config()
    if config['enabled'] and not config['next_run']:
        config['next_run'] = _calculate_next_run_time(config['daily_sync_time'])
        _save_scheduler_config(config)
    
    # Reset stop flag
    _stop_scheduler = False
    
    # Start scheduler thread
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    _scheduler_thread.start()
    
    logger.info("Adzuna job scheduler started")
    return True

def stop_scheduler():
    """
    Stop the Adzuna job scheduler
    """
    global _scheduler_thread, _stop_scheduler
    
    if not _scheduler_thread or not _scheduler_thread.is_alive():
        logger.info("Scheduler not running")
        return False
    
    _stop_scheduler = True
    
    # Wait for thread to exit
    _scheduler_thread.join(timeout=5.0)
    
    logger.info("Adzuna job scheduler stopped")
    return True

def restart_scheduler():
    """
    Restart the Adzuna job scheduler
    """
    stop_scheduler()
    return start_scheduler()

def get_scheduler_status():
    """
    Get the current status of the scheduler
    
    Returns:
        dict: Scheduler status information
    """
    config = _load_scheduler_config()
    
    # Get storage status
    storage_status = get_adzuna_storage_status()
    
    status = {
        'enabled': config['enabled'],
        'is_running': bool(_scheduler_thread and _scheduler_thread.is_alive()),
        'daily_sync_time': config['daily_sync_time'],
        'last_run': config['last_run'],
        'next_run': config['next_run'],
        'cleanup_old_jobs': config['cleanup_old_jobs'],
        'cleanup_days': config['cleanup_days'],
        'job_count': storage_status.get('total_jobs', 0),
        'last_sync': storage_status.get('last_sync')
    }
    
    return status

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Test the scheduler
    config = _load_scheduler_config()
    print(f"Current config: {json.dumps(config, indent=2)}")
    
    # Update config for testing
    test_config = update_scheduler_config({
        'enabled': True,
        'daily_sync_time': '12:00',  # Noon
        'keywords': 'python',
        'location': 'london',
        'country': 'gb'
    })
    
    print(f"Updated config: {json.dumps(test_config, indent=2)}")
    
    # Start the scheduler
    start_scheduler()
    
    # Keep main thread alive for testing
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping scheduler...")
        stop_scheduler()
        print("Scheduler stopped")
"""
Databricks API Utilities
Fetch detailed job run information from Databricks REST API
"""
import os
import logging
import requests
from typing import Optional, Dict

logger = logging.getLogger("databricks_api_utils")

# Load Databricks credentials from environment
DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", "")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")

def fetch_databricks_run_details(run_id: str) -> Optional[Dict]:
    """
    Fetch detailed run information from Databricks Jobs API.

    Args:
        run_id: The Databricks job run ID

    Returns:
        Dictionary containing run details including error messages, or None if fetch fails

    API Response structure:
    {
        "job_id": 123,
        "run_id": 456,
        "run_name": "job-name",
        "state": {
            "life_cycle_state": "TERMINATED",
            "state_message": "...",
            "result_state": "FAILED",
            "user_cancelled_or_timedout": false
        },
        "tasks": [
            {
                "task_key": "task1",
                "state": {
                    "life_cycle_state": "INTERNAL_ERROR",
                    "result_state": "FAILED",
                    "state_message": "Detailed error message here"
                }
            }
        ],
        "cluster_instance": {
            "cluster_id": "...",
            "spark_context_id": "..."
        }
    }
    """
    if not DATABRICKS_HOST or not DATABRICKS_TOKEN:
        logger.error("=" * 80)
        logger.error("CRITICAL: Databricks API credentials NOT configured!")
        logger.error("Cannot fetch detailed error messages from Databricks Jobs API")
        logger.error("RCA will only have generic error info from webhook")
        logger.error("")
        logger.error("TO FIX: Set these environment variables:")
        logger.error(f"DATABRICKS_HOST={DATABRICKS_HOST or '(not set)'}")
        logger.error(f"DATABRICKS_TOKEN={DATABRICKS_TOKEN or '(not set)'}")
        logger.error("")
        logger.error("Example:")
        logger.error("   export DATABRICKS_HOST='https://adb-1234567890123456.7.azuredatabricks.net'")
        logger.error("   export DATABRICKS_TOKEN='dapi1234567890abcdef...'")
        logger.error("=" * 80)
        return None
    
    # Remove trailing slash from host
    host = DATABRICKS_HOST.rstrip('/')
    
    # Databricks Jobs API endpoint
    url = f"{host}/api/2.1/jobs/runs/get"
    
    headers = {
        "Authorization": f"Bearer {DATABRICKS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    params = {"run_id": run_id}
    
    try:
        logger.info(f"Fetching Databricks run details for run_id: {run_id}")
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Successfully fetched run details for {run_id}")
            
            # **ENHANCEMENT: Fetch task outputs for real error messages**
            tasks = data.get("tasks", [])
            for task in tasks:
                if task.get("state", {}).get("result_state") == "FAILED":
                    task_run_id = task.get("run_id")
                    if task_run_id:
                        try:
                            task_output = fetch_task_output(task_run_id)
                            if task_output:
                                task["run_output"] = task_output
                                logger.info(f"Fetched run output for task {task.get('task_key')}")
                        except Exception as e:
                            logger.warning(f"Could not fetch task output for {task_run_id}: {e}")
            
            # Extract the most relevant error message
            error_message = extract_error_message(data)
            if error_message:
                logger.info(f"Extracted error message: {error_message[:200]}...")
            
            return data
        else:
            logger.error(f"Failed to fetch Databricks run details. Status: {response.status_code}, Response: {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Exception while fetching Databricks run details: {e}")
        return None


def fetch_task_output(task_run_id: str) -> Optional[Dict]:
    """
    Fetch the output of a specific task run, which contains the actual error details.
    Args:
        task_run_id: The task run ID (different from job run ID)
    Returns:
        Dictionary containing task output including error traces
    """
    if not DATABRICKS_HOST or not DATABRICKS_TOKEN:
        return None
    
    host = DATABRICKS_HOST.rstrip('/')
    url = f"{host}/api/2.1/jobs/runs/get-output"
    
    headers = {
        "Authorization": f"Bearer {DATABRICKS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    params = {"run_id": task_run_id}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"Could not fetch task output. Status: {response.status_code}")
            return None
    except Exception as e:
        logger.warning(f"Exception fetching task output: {e}")
        return None


def extract_error_message(run_data: Dict) -> Optional[str]:
    """
    Extract the most detailed error message from Databricks run data.
    Tries to get task-level errors first, then job-level errors.

    Args:
        run_data: The complete run data from Databricks API

    Returns:
        The most detailed error message available
    """
    error_messages = []

    logger.info("🔍 Extracting error message from Databricks API response...")

    # 1. Try to get task-level errors (most detailed) - CHECK RUN OUTPUT FIRST
    tasks = run_data.get("tasks", [])
    logger.info(f"   Found {len(tasks)} task(s) in run data")

    for task in tasks:
        task_state = task.get("state", {})
        task_key = task.get("task_key", "unknown")
        result_state = task_state.get("result_state")

        logger.info(f"Task '{task_key}': result_state={result_state}")

        if result_state == "FAILED":
            logger.info(f"Task '{task_key}' has FAILED state, extracting error...")

            # PRIORITY 1: Check run_output for actual exception (REAL ERROR)
            run_output = task.get("run_output", {})
            real_error = (
                run_output.get("error") or
                run_output.get("error_trace") or
                run_output.get("logs")
            )

            if real_error:
                logger.info(f"Found error in run_output for task '{task_key}'")

            # PRIORITY 2: Check exception fields
            if not real_error:
                real_error = (
                    task.get("exception", {}).get("message") or
                    task.get("error_message")
                )
                if real_error:
                    logger.info(f"Found error in exception field for task '{task_key}'")

            # PRIORITY 3: Fallback to state message (generic)
            if not real_error:
                real_error = (
                    task_state.get("state_message") or
                    task_state.get("error_message")
                )
                if real_error:
                    logger.info(f"Only found generic state_message for task '{task_key}'")

            if real_error:
                # Clean up the error message
                if isinstance(real_error, str):
                    # Remove excessive whitespace and newlines
                    real_error = " ".join(real_error.split())
                    error_messages.append(f"[Task: {task_key}] {real_error}")
                    logger.info(f" Added error for task '{task_key}': {real_error[:100]}...")
            else:
                logger.warning(f"Task '{task_key}' failed but no error message found in any field!")

    # 2. Try to get job-level error (only if no task errors found)
    if not error_messages:
        logger.info("No task-level errors found, checking job-level state...")
        state = run_data.get("state", {})
        job_error = (
            state.get("state_message") or
            state.get("error_message") or
            run_data.get("error_message")
        )

        if job_error:
            logger.info(f"Found job-level error: {job_error[:100]}...")
            error_messages.append(f"[Job-level error] {job_error}")
        else:
            logger.warning("No job-level error found either!")

    # 3. Return combined errors or None
    if error_messages:
        combined = " | ".join(error_messages)
        logger.info(f"Successfully extracted {len(error_messages)} error message(s)")
        return combined
    else:
        logger.error("Could not extract any error messages from Databricks API response")
        logger.error(f"Run state was: {run_data.get('state', {})}")
        return None


def get_cluster_logs_url(run_data: Dict) -> Optional[str]:
    """
    Extract cluster logs URL from run data if available.
    
    Args:
        run_data: The complete run data from Databricks API
        
    Returns:
        URL to cluster logs or None
    """
    cluster_instance = run_data.get("cluster_instance", {})
    cluster_id = cluster_instance.get("cluster_id")
    
    if cluster_id and DATABRICKS_HOST:
        host = DATABRICKS_HOST.rstrip('/')
        return f"{host}/#/setting/clusters/{cluster_id}/sparkUi"
    
    return None


def get_run_page_url(run_data: Dict) -> Optional[str]:
    """
    Generate the Databricks UI URL for this run.
    Args:
        run_data: The complete run data from Databricks API
    Returns:
        URL to the run page in Databricks UI
    """
    run_id = run_data.get("run_id")
    if run_id and DATABRICKS_HOST:
        host = DATABRICKS_HOST.rstrip('/')
        return f"{host}/#job/{run_data.get('job_id')}/run/{run_id}"
    return None
# Example usage and testing
if __name__ == "__main__":
    # Test with a sample run_id
    import sys 
    if len(sys.argv) > 1:
        test_run_id = sys.argv[1]
        print(f"Testing with run_id: {test_run_id}")
        
        result = fetch_databricks_run_details(test_run_id)
        if result:
            print("\n=== Run Details ===")
            print(f"Job ID: {result.get('job_id')}")
            print(f"Run ID: {result.get('run_id')}")
            print(f"Run Name: {result.get('run_name')}")
            print(f"State: {result.get('state', {}).get('life_cycle_state')}")
            print(f"Result: {result.get('state', {}).get('result_state')}")
            
            error = extract_error_message(result)
            if error:
                print(f"\n=== Error Message ===\n{error}")
            
            run_url = get_run_page_url(result)
            if run_url:
                print(f"\n=== Run URL ===\n{run_url}")
        else:
            print("Failed to fetch run details")
    else:
        print("Usage: python databricks_api_utils.py <run_id>")
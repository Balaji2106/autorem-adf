# 🤖 AUTO-REMEDIATION OPPORTUNITIES

## Overview

This document identifies errors that can be automatically remediated and provides implementation strategies.

---

## 📊 AUTO-REMEDIATION CAPABILITY MATRIX

### Azure Data Factory Errors

| Error Type | Auto-Remediation Possible? | Strategy | Risk Level | Implementation Complexity |
|------------|---------------------------|----------|------------|--------------------------|
| **UserErrorSourceBlobNotExists** | ✅ YES | Retry after checking if upstream created the file | 🟢 Low | Easy |
| **GatewayTimeout** | ✅ YES | Retry with exponential backoff | 🟢 Low | Easy |
| **HttpConnectionFailed** | ✅ YES | Retry with connection pool reset | 🟢 Low | Easy |
| **ThrottlingError** | ✅ YES | Retry with delay based on Retry-After header | 🟢 Low | Easy |
| **UserErrorInvalidDataType** | ⚠️ PARTIAL | Auto-cast if types are compatible | 🟡 Medium | Medium |
| **UserErrorColumnNameInvalid** | ❌ NO | Requires schema change | 🔴 High | Complex |
| **AuthenticationError** | ⚠️ PARTIAL | Refresh token if expired | 🟡 Medium | Medium |
| **InternalServerError** | ✅ YES | Retry after delay | 🟢 Low | Easy |

---

### Databricks Errors

| Error Type | Auto-Remediation Possible? | Strategy | Risk Level | Implementation Complexity |
|------------|---------------------------|----------|------------|--------------------------|
| **DatabricksClusterStartFailure** | ✅ YES | Retry cluster start, fallback to different node type | 🟢 Low | Medium |
| **DatabricksJobExecutionError** | ⚠️ DEPENDS | Depends on root cause | 🟡 Medium | Complex |
| **DatabricksLibraryInstallationError** | ✅ YES | Retry with version fallback | 🟢 Low | Easy |
| **DatabricksPermissionDenied** | ❌ NO | Requires manual access grant | 🔴 High | N/A |
| **DatabricksResourceExhausted** | ✅ YES | Scale up cluster or retry with smaller batch | 🟡 Medium | Medium |
| **DatabricksTableNotFound** | ⚠️ PARTIAL | Check if table exists, create if missing (only if DDL available) | 🟡 Medium | Medium |
| **DatabricksDriverNotResponding** | ✅ YES | Restart driver/cluster | 🟢 Low | Easy |
| **DatabricksSparkException** | ⚠️ DEPENDS | Depends on exception type | 🟡 Medium | Complex |
| **DatabricksTimeoutError** | ✅ YES | Retry with increased timeout | 🟢 Low | Easy |
| **Cluster Unexpected Termination** | ✅ YES | Restart cluster automatically | 🟢 Low | Easy |
| **Library Install Failed** | ✅ YES | Retry with previous working version | 🟢 Low | Easy |

---

## 🎯 PRIORITY 1: EASY WINS (Implement First)

### 1. Retry-Based Auto-Remediation

**Applicable Errors:**
- GatewayTimeout
- HttpConnectionFailed
- ThrottlingError
- InternalServerError
- DatabricksClusterStartFailure
- DatabricksTimeoutError

**Implementation:**

```python
# In main.py

RETRY_ELIGIBLE_ERRORS = {
    # ADF Errors
    "GatewayTimeout": {
        "max_retries": 3,
        "backoff_seconds": [10, 30, 60],
        "playbook_url": os.getenv("PLAYBOOK_RETRY_PIPELINE")
    },
    "HttpConnectionFailed": {
        "max_retries": 3,
        "backoff_seconds": [5, 15, 30],
        "playbook_url": os.getenv("PLAYBOOK_RETRY_PIPELINE")
    },
    "ThrottlingError": {
        "max_retries": 5,
        "backoff_seconds": [30, 60, 120, 300, 600],
        "playbook_url": os.getenv("PLAYBOOK_RETRY_PIPELINE")
    },
    "InternalServerError": {
        "max_retries": 2,
        "backoff_seconds": [30, 60],
        "playbook_url": os.getenv("PLAYBOOK_RETRY_PIPELINE")
    },

    # Databricks Errors
    "DatabricksClusterStartFailure": {
        "max_retries": 2,
        "backoff_seconds": [60, 120],
        "playbook_url": os.getenv("PLAYBOOK_RESTART_CLUSTER")
    },
    "DatabricksTimeoutError": {
        "max_retries": 2,
        "backoff_seconds": [30, 60],
        "playbook_url": os.getenv("PLAYBOOK_RETRY_JOB")
    },
    "DatabricksDriverNotResponding": {
        "max_retries": 1,
        "backoff_seconds": [60],
        "playbook_url": os.getenv("PLAYBOOK_RESTART_CLUSTER")
    },
}

async def attempt_auto_remediation(ticket_id: str, error_type: str, metadata: dict) -> bool:
    """
    Attempt auto-remediation for eligible error types

    Returns:
        True if remediation was attempted, False otherwise
    """
    if error_type not in RETRY_ELIGIBLE_ERRORS:
        logger.info(f"No auto-remediation available for error type: {error_type}")
        return False

    config = RETRY_ELIGIBLE_ERRORS[error_type]
    playbook_url = config.get("playbook_url")

    if not playbook_url:
        logger.warning(f"Playbook URL not configured for {error_type}")
        return False

    max_retries = config.get("max_retries", 1)
    backoff_seconds = config.get("backoff_seconds", [30])

    # Check if we've already retried this run_id
    run_id = metadata.get("run_id")
    if run_id:
        retry_count = db_query(
            "SELECT COUNT(*) as count FROM audit_trail WHERE run_id = :run_id AND action = 'Auto-Remediation Attempted'",
            {"run_id": run_id},
            one=True
        ).get("count", 0)

        if retry_count >= max_retries:
            logger.warning(f"Max retries ({max_retries}) reached for run_id {run_id}. Giving up.")
            log_audit(
                ticket_id=ticket_id,
                action="Auto-Remediation Max Retries Reached",
                run_id=run_id,
                details=f"Attempted {retry_count} times. Manual intervention required."
            )
            return False

    # Determine backoff delay
    current_attempt = retry_count if run_id else 0
    delay = backoff_seconds[min(current_attempt, len(backoff_seconds) - 1)]

    logger.info(f"AUTO-REMEDIATION: Attempting remediation for {error_type} (attempt {current_attempt + 1}/{max_retries})")
    logger.info(f"AUTO-REMEDIATION: Waiting {delay} seconds before retry...")

    # Log the attempt
    log_audit(
        ticket_id=ticket_id,
        action="Auto-Remediation Attempted",
        run_id=run_id,
        details=f"Error: {error_type}, Attempt: {current_attempt + 1}/{max_retries}, Backoff: {delay}s"
    )

    # Wait for backoff period (in real scenario, schedule this)
    await asyncio.sleep(delay)

    # Call the playbook
    playbook_payload = {
        "ticket_id": ticket_id,
        "error_type": error_type,
        "metadata": metadata,
        "retry_attempt": current_attempt + 1,
        "max_retries": max_retries
    }

    try:
        response = await asyncio.to_thread(
            _http_post_with_retries,
            playbook_url,
            playbook_payload,
            timeout=60,
            retries=3,
            backoff=1.5
        )

        if response.status_code == 200:
            result = response.json()
            new_run_id = result.get("new_run_id") or result.get("run_id")

            logger.info(f"✅ AUTO-REMEDIATION: Playbook executed successfully. New run: {new_run_id}")

            log_audit(
                ticket_id=ticket_id,
                action="Auto-Remediation Succeeded",
                run_id=new_run_id,
                details=f"Successfully triggered retry playbook. New run ID: {new_run_id}"
            )

            # Update ticket with new run_id if available
            if new_run_id and run_id != new_run_id:
                db_execute(
                    "UPDATE tickets SET run_id = :new_run_id WHERE id = :ticket_id",
                    {"new_run_id": new_run_id, "ticket_id": ticket_id}
                )

            return True
        else:
            logger.error(f"❌ AUTO-REMEDIATION: Playbook failed. Status: {response.status_code}, Response: {response.text}")
            log_audit(
                ticket_id=ticket_id,
                action="Auto-Remediation Failed",
                run_id=run_id,
                details=f"Playbook returned {response.status_code}: {response.text}"
            )
            return False

    except Exception as e:
        logger.error(f"❌ AUTO-REMEDIATION: Exception during playbook execution: {e}")
        log_audit(
            ticket_id=ticket_id,
            action="Auto-Remediation Failed",
            run_id=run_id,
            details=f"Exception: {str(e)}"
        )
        return False
```

**Usage in Endpoints:**

```python
# In /azure-monitor endpoint, after RCA generation:

if AUTO_REMEDIATION_ENABLED and rca.get("auto_heal_possible"):
    error_type = rca.get("error_type")
    remediation_metadata = {
        "run_id": runid,
        "pipeline": pipeline,
        "error_type": error_type,
        "source": "adf"
    }

    try:
        await attempt_auto_remediation(tid, error_type, remediation_metadata)
    except Exception as e:
        logger.error(f"Auto-remediation failed for {tid}: {e}")

# Similar for /databricks-monitor endpoint
```

---

### 2. Upstream Dependency Check

**Applicable Error:**
- UserErrorSourceBlobNotExists

**Strategy:**
Check if upstream pipeline has completed successfully before retrying.

**Implementation:**

```python
async def check_upstream_and_retry(ticket_id: str, pipeline_name: str, run_id: str) -> bool:
    """
    Check if upstream dependencies are ready before retrying
    """
    # Extract upstream pipeline name from naming convention
    # Example: "Pipeline_CopyFromStaging" depends on "Pipeline_LoadToStaging"

    upstream_pipeline = extract_upstream_pipeline_name(pipeline_name)

    if not upstream_pipeline:
        logger.info(f"No upstream pipeline identified for {pipeline_name}")
        return False

    # Check last run status of upstream pipeline using ADF REST API
    upstream_status = await check_adf_pipeline_status(upstream_pipeline)

    if upstream_status == "Succeeded":
        logger.info(f"✅ Upstream pipeline {upstream_pipeline} succeeded. Retrying {pipeline_name}")

        # Trigger retry
        playbook_url = os.getenv("PLAYBOOK_RETRY_PIPELINE")
        if playbook_url:
            await trigger_pipeline_retry(playbook_url, {
                "ticket_id": ticket_id,
                "pipeline": pipeline_name,
                "run_id": run_id
            })
            return True
    else:
        logger.warning(f"⚠️ Upstream pipeline {upstream_pipeline} status: {upstream_status}. Cannot retry yet.")
        log_audit(
            ticket_id=ticket_id,
            action="Waiting for Upstream",
            details=f"Upstream pipeline {upstream_pipeline} not ready. Status: {upstream_status}"
        )
        return False

def extract_upstream_pipeline_name(pipeline_name: str) -> Optional[str]:
    """
    Extract upstream pipeline name based on naming convention

    Examples:
        "ETL_Step2_Transform" -> "ETL_Step1_Load"
        "Copy_From_Bronze" -> "Load_To_Bronze"
    """
    # Implement your naming convention logic here
    patterns = {
        "Step2": "Step1",
        "Step3": "Step2",
        "Copy": "Load",
        "Transform": "Extract",
    }

    for pattern, upstream in patterns.items():
        if pattern in pipeline_name:
            return pipeline_name.replace(pattern, upstream)

    return None

async def check_adf_pipeline_status(pipeline_name: str) -> str:
    """
    Check the status of an ADF pipeline using Azure REST API
    """
    # Get Azure credentials
    subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    resource_group = os.getenv("AZURE_RESOURCE_GROUP")
    adf_name = os.getenv("ADF_NAME")
    access_token = os.getenv("AZURE_ACCESS_TOKEN")  # Or use Azure SDK to get token

    if not all([subscription_id, resource_group, adf_name, access_token]):
        logger.warning("Azure credentials not configured for ADF status check")
        return "Unknown"

    url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.DataFactory/factories/{adf_name}/pipelineruns"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Get last run of the pipeline
    params = {
        "api-version": "2018-06-01",
        "$filter": f"pipelineName eq '{pipeline_name}'",
        "$top": 1,
        "$orderby": "RunStart desc"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            runs = data.get("value", [])
            if runs:
                return runs[0].get("status", "Unknown")
        return "Unknown"
    except Exception as e:
        logger.error(f"Failed to check ADF pipeline status: {e}")
        return "Unknown"
```

---

### 3. Databricks Library Version Fallback

**Applicable Error:**
- DatabricksLibraryInstallationError

**Strategy:**
If library installation fails, try installing the previous stable version.

**Implementation:**

```python
LIBRARY_VERSION_FALLBACKS = {
    "pandas": ["2.1.0", "2.0.3", "1.5.3"],
    "numpy": ["1.24.3", "1.23.5", "1.22.4"],
    "pyspark": ["3.4.0", "3.3.2", "3.3.1"],
    # Add more libraries as needed
}

async def retry_library_installation_with_fallback(cluster_id: str, library_name: str, failed_version: str) -> bool:
    """
    Retry library installation with fallback versions
    """
    # Parse library name (e.g., "pandas==2.2.0" -> "pandas")
    lib_base_name = library_name.split("==")[0].split(">=")[0].split("<=")[0].strip()

    fallback_versions = LIBRARY_VERSION_FALLBACKS.get(lib_base_name, [])

    if not fallback_versions:
        logger.info(f"No fallback versions configured for {lib_base_name}")
        return False

    # Try each fallback version
    for version in fallback_versions:
        if version == failed_version:
            continue  # Skip the version that just failed

        logger.info(f"Attempting to install {lib_base_name}=={version} as fallback")

        success = await install_databricks_library(cluster_id, lib_base_name, version)

        if success:
            logger.info(f"✅ Successfully installed {lib_base_name}=={version}")
            return True

    logger.error(f"❌ All fallback versions failed for {lib_base_name}")
    return False

async def install_databricks_library(cluster_id: str, library_name: str, version: str) -> bool:
    """
    Install a library on a Databricks cluster using REST API
    """
    host = os.getenv("DATABRICKS_HOST", "").rstrip('/')
    token = os.getenv("DATABRICKS_TOKEN", "")

    if not host or not token:
        logger.error("Databricks credentials not configured")
        return False

    url = f"{host}/api/2.0/libraries/install"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "cluster_id": cluster_id,
        "libraries": [
            {"pypi": {"package": f"{library_name}=={version}"}}
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Failed to install library: {e}")
        return False
```

---

## 🚀 PRIORITY 2: MEDIUM COMPLEXITY

### 4. Resource Scaling

**Applicable Errors:**
- DatabricksResourceExhausted
- Out of Memory errors
- Cluster capacity exceeded

**Strategy:**
Automatically scale up cluster resources or retry with optimized settings.

**Implementation:**

```python
async def auto_scale_cluster(cluster_id: str, current_config: dict) -> bool:
    """
    Automatically scale up a Databricks cluster
    """
    host = os.getenv("DATABRICKS_HOST", "").rstrip('/')
    token = os.getenv("DATABRICKS_TOKEN", "")

    if not host or not token:
        return False

    # Determine scaling strategy
    current_workers = current_config.get("num_workers", 2)
    max_workers = current_config.get("autoscale", {}).get("max_workers", current_workers * 2)

    # Increase workers by 50% or max_workers, whichever is lower
    new_workers = min(int(current_workers * 1.5), max_workers)

    if new_workers <= current_workers:
        logger.info("Cluster already at max capacity")
        return False

    logger.info(f"Scaling cluster from {current_workers} to {new_workers} workers")

    url = f"{host}/api/2.0/clusters/edit"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "cluster_id": cluster_id,
        "num_workers": new_workers
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            logger.info(f"✅ Successfully scaled cluster to {new_workers} workers")
            return True
        else:
            logger.error(f"Failed to scale cluster: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Exception during cluster scaling: {e}")
        return False
```

---

### 5. Databricks Cluster Auto-Restart

**Applicable Errors:**
- Cluster unexpected termination
- Driver not responding
- Cluster failed to start

**Implementation:**

```python
async def auto_restart_cluster(cluster_id: str, ticket_id: str) -> bool:
    """
    Automatically restart a Databricks cluster
    """
    host = os.getenv("DATABRICKS_HOST", "").rstrip('/')
    token = os.getenv("DATABRICKS_TOKEN", "")

    if not host or not token:
        return False

    # Check current cluster state
    state = await get_cluster_state(cluster_id)

    if state in ["RUNNING", "PENDING"]:
        logger.info(f"Cluster {cluster_id} is already {state}")
        return False

    logger.info(f"Attempting to restart cluster {cluster_id} (current state: {state})")

    url = f"{host}/api/2.0/clusters/start"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {"cluster_id": cluster_id}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code == 200:
            logger.info(f"✅ Successfully initiated cluster restart for {cluster_id}")

            log_audit(
                ticket_id=ticket_id,
                action="Cluster Auto-Restarted",
                details=f"Cluster {cluster_id} restart initiated"
            )

            # Wait for cluster to start (with timeout)
            for i in range(60):  # Wait up to 10 minutes
                await asyncio.sleep(10)
                state = await get_cluster_state(cluster_id)

                if state == "RUNNING":
                    logger.info(f"✅ Cluster {cluster_id} is now RUNNING")
                    return True
                elif state == "ERROR":
                    logger.error(f"❌ Cluster {cluster_id} failed to start")
                    return False

            logger.warning(f"⚠️ Cluster restart timeout for {cluster_id}")
            return False
        else:
            logger.error(f"Failed to restart cluster: {response.text}")
            return False

    except Exception as e:
        logger.error(f"Exception during cluster restart: {e}")
        return False

async def get_cluster_state(cluster_id: str) -> str:
    """Get current state of a Databricks cluster"""
    host = os.getenv("DATABRICKS_HOST", "").rstrip('/')
    token = os.getenv("DATABRICKS_TOKEN", "")

    url = f"{host}/api/2.0/clusters/get"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"cluster_id": cluster_id}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("state", "UNKNOWN")
        return "UNKNOWN"
    except Exception:
        return "UNKNOWN"
```

---

## 🔴 PRIORITY 3: NOT RECOMMENDED FOR AUTO-REMEDIATION

These errors require manual intervention:

1. **UserErrorColumnNameInvalid** - Requires schema changes
2. **DatabricksPermissionDenied** - Requires access control changes
3. **Data corruption errors** - Risk of data integrity issues
4. **Schema mismatch errors** - May need business logic updates
5. **Authentication failures** - Security risk if automated

---

## 🧪 TESTING AUTO-REMEDIATION

### Test Plan

```bash
#!/bin/bash
# test_auto_remediation.sh

# Test 1: Retry-based remediation
echo "Test 1: Simulating GatewayTimeout error"
curl -X POST "http://localhost:8000/azure-monitor?api_key=test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "essentials": {"alertRule": "Test_Pipeline"},
      "alertContext": {
        "properties": {
          "PipelineName": "Test_Retry_Pipeline",
          "PipelineRunId": "test-run-retry-001",
          "ErrorCode": "GatewayTimeout",
          "ErrorMessage": "Gateway timeout after 30 seconds"
        }
      }
    }
  }'

# Expected: System should schedule a retry after 10 seconds

# Test 2: Databricks cluster restart
echo "Test 2: Simulating cluster termination"
curl -X POST "http://localhost:8000/databricks-monitor" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "cluster.terminated",
    "cluster": {
      "cluster_id": "test-cluster-123",
      "cluster_name": "Test Cluster",
      "state": "TERMINATED",
      "state_message": "Driver not responding",
      "termination_reason": {
        "code": "DRIVER_NOT_RESPONDING",
        "type": "ERROR"
      }
    }
  }'

# Expected: System should attempt to restart cluster

# Test 3: Library version fallback
echo "Test 3: Simulating library installation failure"
curl -X POST "http://localhost:8000/databricks-monitor" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "library.install_failed",
    "cluster": {
      "cluster_id": "test-cluster-123",
      "cluster_name": "Test Cluster"
    },
    "library": {
      "pypi": {"package": "pandas==2.2.0"}
    },
    "error_message": "Could not find a version that satisfies the requirement pandas==2.2.0"
  }'

# Expected: System should try fallback versions
```

---

## 📈 MONITORING AUTO-REMEDIATION

### Key Metrics

1. **Auto-remediation Success Rate**
   - % of attempts that succeeded
   - Target: > 80%

2. **Time to Resolution**
   - Average time from error to resolution
   - Compare manual vs automated

3. **Retry Attempts**
   - Average number of retries before success
   - Identify errors that need max retries adjustment

4. **Cost Impact**
   - Compute cost of retries
   - Compare to manual intervention cost

### Dashboard Query

```sql
-- Auto-remediation success rate by error type
SELECT
    action,
    COUNT(*) as total_attempts,
    SUM(CASE WHEN action = 'Auto-Remediation Succeeded' THEN 1 ELSE 0 END) as successes,
    ROUND(100.0 * SUM(CASE WHEN action = 'Auto-Remediation Succeeded' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM audit_trail
WHERE action LIKE 'Auto-Remediation%'
    AND timestamp >= datetime('now', '-7 days')
GROUP BY action
ORDER BY total_attempts DESC;
```

---

## ⚙️ CONFIGURATION

Add to `.env`:

```bash
# Auto-Remediation Settings
AUTO_REMEDIATION_ENABLED=true

# ADF Playbook URLs
PLAYBOOK_RETRY_PIPELINE=https://your-logic-app.azure.com/retry-pipeline
PLAYBOOK_RERUN_UPSTREAM=https://your-logic-app.azure.com/rerun-upstream

# Databricks Playbook URLs
PLAYBOOK_RESTART_CLUSTER=https://your-logic-app.azure.com/restart-cluster
PLAYBOOK_RETRY_JOB=https://your-logic-app.azure.com/retry-job
PLAYBOOK_REINSTALL_LIBRARIES=https://your-logic-app.azure.com/reinstall-libraries

# Auto-Remediation Limits
AUTO_REMEDIATION_MAX_RETRIES=3
AUTO_REMEDIATION_MAX_COST_USD=100  # Max cost per day for auto-remediation

# Azure Credentials for ADF Status Checks
AZURE_SUBSCRIPTION_ID=your-subscription-id
AZURE_RESOURCE_GROUP=rg_techdemo_2025_Q4
ADF_NAME=your-adf-name
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
```

---

## 🚦 ROLLOUT STRATEGY

### Phase 1: Read-Only Mode (Week 1-2)
- ✅ Identify eligible errors
- ✅ Log what WOULD be done
- ✅ Monitor false positives
- ❌ Don't actually retry anything

### Phase 2: Pilot (Week 3-4)
- ✅ Enable for non-production pipelines
- ✅ Enable for low-risk error types (GatewayTimeout, HttpConnectionFailed)
- ✅ Manual approval required for each remediation
- ✅ Monitor success rate

### Phase 3: Production (Week 5+)
- ✅ Enable for production pipelines
- ✅ Add more error types gradually
- ✅ Automated remediation with notifications
- ✅ Continuous monitoring and tuning

---

## 📝 SUMMARY

**Easy Wins (Implement Now):**
1. ✅ Retry-based remediation (GatewayTimeout, HttpConnectionFailed, etc.)
2. ✅ Databricks cluster restart
3. ✅ Library version fallback

**Medium Complexity (Implement Next):**
4. ⚠️ Upstream dependency checks
5. ⚠️ Resource scaling
6. ⚠️ Token refresh for auth errors

**Not Recommended:**
- ❌ Schema changes
- ❌ Permission changes
- ❌ Data integrity fixes

**Expected Impact:**
- 🎯 Reduce MTTR by 60-80% for retry-eligible errors
- 💰 Save 20-30 engineering hours per month
- 📉 Reduce alert fatigue by 40%

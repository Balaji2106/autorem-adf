# Auto-Remediation Matrix

This document shows which errors can be auto-remediated and which Logic App handles each error type.

## Auto-Remediable Errors

### Azure Data Factory (ADF)

| Error Type | Auto-Heal? | Logic App | Remediation Action | Max Retries | Backoff (seconds) |
|------------|-----------|-----------|-------------------|-------------|-------------------|
| **GatewayTimeout** | ✅ Yes | ADF Logic App | retry_pipeline | 3 | 30, 60, 120 |
| **HttpConnectionFailed** | ✅ Yes | ADF Logic App | retry_pipeline | 3 | 30, 60, 120 |
| **ThrottlingError** | ✅ Yes | ADF Logic App | retry_pipeline | 5 | 60, 120, 180, 300, 600 |
| **InternalServerError** | ✅ Yes | ADF Logic App | retry_pipeline | 3 | 30, 60, 120 |
| UserErrorSourceBlobNotExists | ❌ No | N/A | Manual investigation | - | - |
| UserErrorColumnNameInvalid | ❌ No | N/A | Fix schema | - | - |
| UserErrorInvalidDataType | ❌ No | N/A | Fix data quality | - | - |
| UserErrorSqlOperationFailed | ❌ No | N/A | Fix SQL query | - | - |
| AuthenticationError | ❌ No | N/A | Fix credentials | - | - |
| UnknownError | ❌ No | N/A | Manual investigation | - | - |

### Databricks

| Error Type | Auto-Heal? | Logic App | Remediation Action | Max Retries | Backoff (seconds) |
|------------|-----------|-----------|-------------------|-------------|-------------------|
| **DatabricksClusterStartFailure** | ✅ Yes | Databricks Logic App | restart_cluster | 3 | 30, 60, 120 |
| **DatabricksResourceExhausted** | ✅ Yes | Databricks Logic App | restart_cluster | 3 | 30, 60, 120 |
| **DatabricksLibraryInstallationError** | ✅ Yes | Databricks Logic App | reinstall_libraries | 3 | 30, 60, 120 |
| **DatabricksDriverNotResponding** | ✅ Yes | Databricks Logic App | restart_cluster | 3 | 30, 60, 120 |
| **DatabricksTimeoutError** | ✅ Yes | Databricks Logic App | retry_job | 3 | 30, 60, 120 |
| **DatabricksJobExecutionError** | ✅ Yes* | Databricks Logic App | retry_job | 3 | 30, 60, 120 |
| DatabricksPermissionDenied | ❌ No | N/A | Grant permissions | - | - |
| DatabricksTableNotFound | ❌ No | N/A | Create/fix table | - | - |
| DatabricksSparkException | ❌ No | N/A | Fix Spark code | - | - |
| DatabricksAuthenticationError | ❌ No | N/A | Refresh token | - | - |
| DatabricksNotebookExecutionError | ❌ No | N/A | Fix notebook code | - | - |
| UnknownError | ❌ No | N/A | Manual investigation | - | - |

\* DatabricksJobExecutionError is only auto-healed if it's a transient error (e.g., timeout, resource issue). Code errors require manual fix.

---

## How Auto-Remediation Works

### Flow for Auto-Remediable Errors

```
1. Pipeline/Job Fails (e.g., GatewayTimeout)
   ↓
2. Azure Monitor sends alert to Python API
   ↓
3. AI generates RCA with auto_heal_possible=true
   ↓
4. Python API calls appropriate Logic App
   ├─ ADF errors → ADF Logic App (retry_pipeline)
   └─ Databricks errors → Databricks Logic App (retry_job/restart_cluster/reinstall_libraries)
   ↓
5. Logic App performs remediation action
   ├─ Calls ADF/Databricks REST API
   └─ Returns new run_id/status
   ↓
6. Python API monitors remediation run (polls every 30s)
   ↓
7. Success/Failure Handling
   ├─ ✅ Success: Close ticket, post to Slack/Jira, update dashboard
   ├─ ❌ Failed but retries left: Wait backoff_seconds, retry (step 4)
   └─ ❌ Failed and max retries exceeded: Escalate to manual intervention
```

### Flow for Non-Auto-Remediable Errors

```
1. Pipeline/Job Fails (e.g., UserErrorSourceBlobNotExists)
   ↓
2. Azure Monitor sends alert to Python API
   ↓
3. AI generates RCA with auto_heal_possible=false
   ↓
4. Create ticket in DB
   ↓
5. Send to Jira (assigned to on-call team)
   ↓
6. Post to Slack with recommendations
   ↓
7. Wait for manual resolution
```

---

## RCA Auto-Heal Decision Logic

The AI uses these rules to determine `auto_heal_possible`:

### Rule 1: Transient/Infrastructure Issues → Auto-Heal ✅

- Network timeouts
- Service unavailable (5xx errors)
- Rate limiting/throttling
- Cluster startup failures
- Resource exhaustion

### Rule 2: Code/Data/Permission Issues → Manual Fix ❌

- Missing data files
- Schema mismatches
- SQL query errors
- Permission denied
- Code execution errors
- Missing tables/resources

---

## Logic App Payloads

### ADF Logic App Payload

```json
{
  "pipeline_name": "ETL_Pipeline",
  "ticket_id": "ADF-20251203T123456-abc123",
  "error_type": "GatewayTimeout",
  "original_run_id": "run-abc-123",
  "retry_attempt": 1,
  "max_retries": 3,
  "remediation_action": "retry_pipeline",
  "timestamp": "2025-12-03T12:34:56Z"
}
```

### Databricks Logic App Payload (Job Retry)

```json
{
  "job_name": "DataProcessingJob",
  "job_id": "123456",
  "ticket_id": "DBR-20251203T123456-xyz789",
  "error_type": "DatabricksTimeoutError",
  "original_run_id": "789",
  "retry_attempt": 1,
  "max_retries": 3,
  "remediation_action": "retry_job",
  "timestamp": "2025-12-03T12:34:56Z"
}
```

### Databricks Logic App Payload (Cluster Restart)

```json
{
  "cluster_id": "0123-456789-abc123",
  "ticket_id": "DBR-20251203T123456-xyz789",
  "error_type": "DatabricksClusterStartFailure",
  "retry_attempt": 1,
  "max_retries": 3,
  "remediation_action": "restart_cluster",
  "timestamp": "2025-12-03T12:34:56Z"
}
```

---

## Expected Logic App Responses

### Success Response

```json
{
  "status": "success",
  "run_id": "new-run-id-456",
  "message": "ADF pipeline re-run triggered successfully",
  "pipeline_name": "ETL_Pipeline",
  "ticket_id": "ADF-20251203T123456-abc123",
  "retry_attempt": 1
}
```

### Failure Response

```json
{
  "status": "failed",
  "message": "Failed to trigger ADF pipeline re-run",
  "error": "Detailed error message from Azure API",
  "pipeline_name": "ETL_Pipeline",
  "ticket_id": "ADF-20251203T123456-abc123"
}
```

---

## Monitoring Remediation

### Python API Monitoring

After Logic App returns `run_id`, Python API monitors the remediation run:

- **Polling Interval:** 30 seconds
- **Timeout:** 60 minutes (configurable)
- **Status Checks:**
  - ADF: `GET /subscriptions/.../pipelineruns/{run_id}` → Check `status`
  - Databricks: `GET /api/2.1/jobs/runs/get?run_id={run_id}` → Check `state.life_cycle_state`

### Success Criteria

- **ADF:** `status == "Succeeded"`
- **Databricks:** `state.result_state == "SUCCESS"`

### Failure Criteria

- **ADF:** `status == "Failed"`
- **Databricks:** `state.result_state == "FAILED"`

### Retry Decision

```python
if remediation_failed:
    if retry_attempt < max_retries:
        wait(backoff_seconds[retry_attempt])
        trigger_auto_remediation(retry_attempt + 1)
    else:
        escalate_to_manual_intervention()
```

---

## Configuration Summary

### Required Environment Variables

```bash
# Enable auto-remediation
AUTO_REMEDIATION_ENABLED=true

# ADF configuration
AZURE_SUBSCRIPTION_ID=...
AZURE_RESOURCE_GROUP=...
AZURE_DATA_FACTORY_NAME=...

# Azure auth (for monitoring)
AZURE_TENANT_ID=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...

# Databricks (for monitoring)
DATABRICKS_HOST=https://adb-...azuredatabricks.net
DATABRICKS_TOKEN=dapi...

# Logic App URLs
PLAYBOOK_RETRY_PIPELINE=https://prod-XX.logic.azure.com/...
PLAYBOOK_RETRY_JOB=https://prod-YY.logic.azure.com/...
PLAYBOOK_RESTART_CLUSTER=https://prod-YY.logic.azure.com/...
PLAYBOOK_REINSTALL_LIBRARIES=https://prod-YY.logic.azure.com/...
```

---

## MTTR Targets

| Error Type | Target MTTR | Typical MTTR with Auto-Heal |
|------------|-------------|------------------------------|
| GatewayTimeout | 15 min | **3-5 min** ✅ |
| HttpConnectionFailed | 15 min | **3-5 min** ✅ |
| ThrottlingError | 30 min | **10-15 min** ✅ |
| ClusterStartFailure | 30 min | **5-10 min** ✅ |
| ResourceExhausted | 30 min | **5-10 min** ✅ |
| Manual errors | 2-4 hours | 2-4 hours (no change) |

---

## Dashboard Indicators

### Ticket Status Icons

- 🟢 **Auto-Remediated**: Ticket closed automatically by AI
- 🟡 **Remediation In Progress**: Currently attempting auto-heal
- 🔴 **Remediation Failed**: Escalated to manual intervention
- ⚫ **Manual Resolution Required**: Not auto-remediable

### Metrics Tracked

- **Auto-Heal Success Rate:** % of remediable errors successfully resolved
- **MTTR Improvement:** Average time saved by auto-remediation
- **Retry Distribution:** How many attempts before success (1st, 2nd, 3rd)
- **Remediation Actions:** Distribution of retry_pipeline vs restart_cluster vs retry_job

---

## Troubleshooting

### Auto-Remediation Not Triggering

1. **Check:** Is `AUTO_REMEDIATION_ENABLED=true`?
2. **Check:** Does RCA show `auto_heal_possible: true`?
3. **Check:** Is error type in `REMEDIABLE_ERRORS` config?
4. **Check:** Are Logic App URLs configured correctly?

### Logic App Failing

1. **ADF Logic App:** Check Managed Identity has Contributor role on ADF
2. **Databricks Logic App:** Check Databricks token is valid
3. **Both:** View Logic App run history for detailed error
4. **Both:** Check Azure API quotas and throttling

### Remediation Monitoring Timeout

1. **Check:** ADF/Databricks API connectivity
2. **Check:** Run ID returned by Logic App is valid
3. **Increase:** Monitoring timeout in code (default 60 min)

---

## Summary

- **4 ADF errors** can be auto-remediated → Use ADF Logic App
- **5-6 Databricks errors** can be auto-remediated → Use Databricks Logic App
- **All others** require manual intervention
- **AI determines** auto_heal_possible based on error type
- **Logic Apps** perform the actual remediation
- **Python API** monitors and handles success/failure

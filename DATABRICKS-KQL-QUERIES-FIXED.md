# Databricks KQL Queries - Schema Discovery & Fixed Queries

## 🔍 Step 1: Discover Your Databricks Log Schema

Before creating alert rules, you need to identify the actual column names in your Databricks diagnostic logs.

### A. Find Available Databricks Tables

Run this query in Azure Log Analytics to see what Databricks tables you have:

```kusto
search *
| where TimeGenerated > ago(24h)
| where _ResourceId contains "databricks"
| distinct $table
```

**Expected tables:**
- `AzureDiagnostics` (most common - all Databricks logs go here)
- `DatabricksJobs`
- `DatabricksClusters`
- `DatabricksNotebook`
- `DatabricksWorkspace`

---

### B. Discover Column Names in AzureDiagnostics

**Most Databricks workspaces send logs to `AzureDiagnostics` table, not dedicated tables.**

Run this to see all available columns:

```kusto
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| take 10
| project *
```

**Key columns to look for:**
- `Category` - Type of log (clusters, jobs, notebook, etc.)
- `OperationName` - Action performed
- `ResultType` - Success/Failure
- `properties_s` - JSON string with detailed info
- `Level` - Error, Warning, Info

---

### C. Inspect Properties Column (JSON Parsing)

Databricks often stores detailed info in a JSON column called `properties_s`:

```kusto
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| where Category == "clusters" or Category == "jobs"
| take 10
| extend ParsedProperties = parse_json(properties_s)
| project TimeGenerated, Category, OperationName, ResultType, ParsedProperties
```

**Look for these fields inside `ParsedProperties`:**
- Cluster logs: `cluster_id`, `cluster_name`, `state`, `state_message`, `termination_code`
- Job logs: `job_id`, `run_id`, `result_state`, `state_message`, `error_code`

---

## ✅ Step 2: Fixed KQL Queries (Schema-Agnostic Approach)

These queries work with the standard **AzureDiagnostics** table structure.

---

### Query 1: Databricks Cluster Start Failures

```kusto
// Databricks Cluster Start Failures
AzureDiagnostics
| where TimeGenerated > ago(5m)
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| where Category == "clusters"
| where OperationName has_any ("clusterStart", "createCluster", "editCluster")
| where ResultType != "Success" or Level == "Error"
| extend ClusterDetails = parse_json(properties_s)
| extend
    ClusterId = tostring(ClusterDetails.cluster_id),
    ClusterName = tostring(ClusterDetails.cluster_name),
    State = tostring(ClusterDetails.state),
    TerminationCode = tostring(ClusterDetails.termination_code),
    TerminationReason = tostring(ClusterDetails.state_message),
    ErrorCode = tostring(ClusterDetails.error_code)
| where State in ("TERMINATING", "TERMINATED", "ERROR")
    or TerminationCode has_any (
        "CLUSTER_START_FAILURE",
        "CLOUD_PROVIDER_LAUNCH_FAILURE",
        "CLOUD_PROVIDER_SHUTDOWN",
        "INSTANCE_POOL_CLUSTER_FAILURE",
        "DRIVER_UNREACHABLE",
        "AZURE_QUOTA_EXCEEDED"
    )
| project
    TimeGenerated,
    ClusterId,
    ClusterName,
    State,
    TerminationCode,
    TerminationReason,
    ErrorCode,
    ResourceGroup,
    SubscriptionId = _SubscriptionId,
    Workspace = _ResourceId
| order by TimeGenerated desc
```

**Use this for Azure Monitor Alert:**
- Alert if: `ResultCount > 0`
- Webhook: Your RCA API `/webhook/databricks`

---

### Query 2: Databricks Job Failures

```kusto
// Databricks Job Run Failures
AzureDiagnostics
| where TimeGenerated > ago(5m)
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| where Category == "jobs"
| where OperationName has_any ("runSubmit", "runNow", "jobRun")
| where ResultType != "Success" or Level == "Error"
| extend JobDetails = parse_json(properties_s)
| extend
    JobId = tostring(JobDetails.job_id),
    RunId = tostring(JobDetails.run_id),
    JobName = tostring(JobDetails.job_name),
    ResultState = tostring(JobDetails.result_state),
    StateMessage = tostring(JobDetails.state_message),
    ErrorCode = tostring(JobDetails.error_code),
    ErrorMessage = tostring(JobDetails.error_message),
    TaskKey = tostring(JobDetails.task_key)
| where ResultState in ("FAILED", "TIMEDOUT", "CANCELED", "INTERNAL_ERROR")
| project
    TimeGenerated,
    JobId,
    RunId,
    JobName,
    TaskKey,
    ResultState,
    ErrorCode,
    ErrorMessage,
    StateMessage,
    ResourceGroup,
    SubscriptionId = _SubscriptionId,
    Workspace = _ResourceId
| order by TimeGenerated desc
```

**Use this for Azure Monitor Alert:**
- Alert if: `ResultCount > 0` and `ErrorCode` is auto-remediable
- Webhook: Your RCA API `/webhook/databricks`

---

### Query 3: Databricks Library Installation Failures

```kusto
// Databricks Library Installation Failures
AzureDiagnostics
| where TimeGenerated > ago(5m)
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| where Category == "clusters" or Category == "libraries"
| where OperationName has_any ("installLibrary", "clusterLibraries")
| where ResultType != "Success" or Level == "Error"
| extend LibDetails = parse_json(properties_s)
| extend
    ClusterId = tostring(LibDetails.cluster_id),
    ClusterName = tostring(LibDetails.cluster_name),
    LibraryName = tostring(LibDetails.library),
    LibraryStatus = tostring(LibDetails.status),
    ErrorMessage = tostring(LibDetails.messages)
| where LibraryStatus in ("FAILED", "SKIPPED")
    or ErrorMessage contains "Failed to install"
| project
    TimeGenerated,
    ClusterId,
    ClusterName,
    LibraryName,
    LibraryStatus,
    ErrorMessage,
    ResourceGroup,
    SubscriptionId = _SubscriptionId,
    Workspace = _ResourceId
| order by TimeGenerated desc
```

---

### Query 4: Combined Databricks Failures (All Types)

```kusto
// Comprehensive Databricks Failure Detection
// Combines cluster, job, and library failures

// Cluster failures
let ClusterFailures = AzureDiagnostics
| where TimeGenerated > ago(5m)
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| where Category == "clusters"
| where ResultType != "Success" or Level == "Error"
| extend Details = parse_json(properties_s)
| extend
    FailureType = "Cluster",
    EntityId = tostring(Details.cluster_id),
    EntityName = tostring(Details.cluster_name),
    ErrorCode = coalesce(tostring(Details.termination_code), tostring(Details.error_code)),
    ErrorMessage = tostring(Details.state_message),
    State = tostring(Details.state)
| where State in ("TERMINATED", "ERROR", "TERMINATING")
    or ErrorCode != ""
| project
    TimeGenerated,
    FailureType,
    EntityId,
    EntityName,
    ErrorCode,
    ErrorMessage,
    ResourceGroup,
    SubscriptionId = _SubscriptionId,
    Workspace = _ResourceId;

// Job failures
let JobFailures = AzureDiagnostics
| where TimeGenerated > ago(5m)
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| where Category == "jobs"
| where ResultType != "Success" or Level == "Error"
| extend Details = parse_json(properties_s)
| extend
    FailureType = "Job",
    EntityId = strcat(tostring(Details.job_id), "-", tostring(Details.run_id)),
    EntityName = tostring(Details.job_name),
    ErrorCode = tostring(Details.error_code),
    ErrorMessage = coalesce(tostring(Details.error_message), tostring(Details.state_message)),
    State = tostring(Details.result_state)
| where State in ("FAILED", "TIMEDOUT", "INTERNAL_ERROR")
| project
    TimeGenerated,
    FailureType,
    EntityId,
    EntityName,
    ErrorCode,
    ErrorMessage,
    ResourceGroup,
    SubscriptionId = _SubscriptionId,
    Workspace = _ResourceId;

// Library failures
let LibraryFailures = AzureDiagnostics
| where TimeGenerated > ago(5m)
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| where Category has_any ("clusters", "libraries")
| where OperationName has "library" or properties_s has "library"
| where ResultType != "Success" or Level == "Error"
| extend Details = parse_json(properties_s)
| extend
    FailureType = "Library",
    EntityId = tostring(Details.cluster_id),
    EntityName = tostring(Details.cluster_name),
    ErrorCode = "LIBRARY_INSTALL_FAILED",
    ErrorMessage = tostring(Details.messages),
    State = tostring(Details.status)
| where State == "FAILED" or ErrorMessage contains "Failed"
| project
    TimeGenerated,
    FailureType,
    EntityId,
    EntityName,
    ErrorCode,
    ErrorMessage,
    ResourceGroup,
    SubscriptionId = _SubscriptionId,
    Workspace = _ResourceId;

// Combine all failures
union ClusterFailures, JobFailures, LibraryFailures
| order by TimeGenerated desc
```

---

## 🛠️ Step 3: Customize Queries for YOUR Schema

### Option A: If You Have Dedicated Tables (DatabricksClusters, DatabricksJobs)

Run this to check schema:

```kusto
DatabricksClusters
| take 10
| project *
```

**Common column mappings:**

| Expected Column | Possible Actual Names |
|----------------|----------------------|
| `State` | `state`, `cluster_state`, `Status`, `ClusterState` |
| `TerminationCode` | `termination_code`, `TerminationReason`, `StateMessage` |
| `ClusterId` | `cluster_id`, `ClusterId`, `id` |
| `ClusterName` | `cluster_name`, `ClusterName`, `name` |

**Example fix:**
```kusto
// If column is "cluster_state" instead of "State"
DatabricksClusters
| where cluster_state == "TERMINATED"  // Changed from "State"
```

---

### Option B: If Everything is in AzureDiagnostics

Use the queries from **Step 2** above - they parse the `properties_s` JSON column.

---

## 🔧 Step 4: Test Your Query Before Creating Alert

1. **Open Azure Portal** → Log Analytics Workspace
2. **Run this test query:**

```kusto
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| summarize count() by Category, OperationName, ResultType
```

3. **Verify you see data:**
   - If `count > 0` → You have Databricks logs ✅
   - If `count = 0` → Check diagnostic settings

4. **Enable Databricks Diagnostic Logs:**

```bash
# Enable diagnostic logs for Databricks workspace
az monitor diagnostic-settings create \
  --resource /subscriptions/{sub-id}/resourceGroups/{rg}/providers/Microsoft.Databricks/workspaces/{workspace-name} \
  --name databricks-diagnostics \
  --workspace /subscriptions/{sub-id}/resourceGroups/{rg}/providers/Microsoft.OperationalInsights/workspaces/{log-analytics-workspace} \
  --logs '[
    {"category": "jobs", "enabled": true},
    {"category": "clusters", "enabled": true},
    {"category": "notebook", "enabled": true},
    {"category": "accounts", "enabled": true}
  ]'
```

---

## 🚨 Step 5: Create Azure Monitor Alert Rule

Once you've verified the query works, create the alert:

### Using Azure Portal:

1. **Navigate to:** Azure Monitor → Alerts → Create → Alert Rule
2. **Scope:** Select your Log Analytics Workspace
3. **Condition:** Custom log search
4. **Query:** Paste one of the queries above (e.g., Cluster Failures)
5. **Alert logic:**
   - Based on: Number of results
   - Operator: Greater than
   - Threshold: 0
   - Evaluation frequency: 5 minutes
6. **Actions:**
   - Select Action Group
   - Add Webhook: `https://your-api.azurewebsites.net/webhook/databricks`
7. **Alert Details:**
   - Name: `Databricks-Cluster-Start-Failure`
   - Severity: Sev 2 (Warning)

---

### Using Azure CLI:

```bash
# Create alert rule for Databricks failures
az monitor scheduled-query create \
  --name "databricks-cluster-failures" \
  --resource-group YOUR_RESOURCE_GROUP \
  --scopes /subscriptions/{sub-id}/resourceGroups/{rg}/providers/Microsoft.OperationalInsights/workspaces/{workspace} \
  --condition "count > 0" \
  --query-time-range 5 \
  --evaluation-frequency 5 \
  --action-groups /subscriptions/{sub-id}/resourceGroups/{rg}/providers/microsoft.insights/actionGroups/{action-group-name} \
  --description "Alert on Databricks cluster start failures" \
  --query '
AzureDiagnostics
| where TimeGenerated > ago(5m)
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| where Category == "clusters"
| where ResultType != "Success"
| extend Details = parse_json(properties_s)
| extend TerminationCode = tostring(Details.termination_code)
| where TerminationCode in ("CLUSTER_START_FAILURE", "CLOUD_PROVIDER_LAUNCH_FAILURE")
'
```

---

## 🧪 Step 6: Test the Alert

### Trigger a Test Failure:

**Option 1: Cluster Failure (Safe Test)**
```python
# In Databricks notebook - request invalid instance type
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
cluster = w.clusters.create(
    cluster_name="test-failure-cluster",
    spark_version="13.3.x-scala2.12",
    node_type_id="INVALID_INSTANCE_TYPE",  # This will fail
    num_workers=1
)
```

**Option 2: Job Failure (Safe Test)**
```python
# Create a job that fails immediately
w.jobs.run_now(
    job_id=YOUR_JOB_ID,
    notebook_params={"test_failure": "true"}  # Your notebook should fail on this
)
```

**Option 3: Manual Log Entry (Not Recommended)**
- Better to test with real failures

---

## 📊 Expected Webhook Payload

When the alert fires, your RCA API will receive:

```json
{
  "schemaId": "azureMonitorCommonAlertSchema",
  "data": {
    "essentials": {
      "alertId": "/subscriptions/.../alertId",
      "alertRule": "databricks-cluster-failures",
      "severity": "Sev2",
      "firedDateTime": "2025-12-04T10:30:00Z"
    },
    "alertContext": {
      "SearchQuery": "AzureDiagnostics | where...",
      "SearchResults": {
        "tables": [{
          "rows": [
            [
              "2025-12-04T10:28:00Z",
              "cluster-abc123",
              "prod-etl-cluster",
              "TERMINATED",
              "CLOUD_PROVIDER_LAUNCH_FAILURE",
              "Azure quota exceeded for Standard_DS4_v2",
              "quota_exceeded"
            ]
          ],
          "columns": [
            {"name": "TimeGenerated", "type": "datetime"},
            {"name": "ClusterId", "type": "string"},
            {"name": "ClusterName", "type": "string"},
            {"name": "State", "type": "string"},
            {"name": "TerminationCode", "type": "string"},
            {"name": "TerminationReason", "type": "string"},
            {"name": "ErrorCode", "type": "string"}
          ]
        }]
      }
    }
  }
}
```

---

## 🔍 Troubleshooting

### Issue 1: "Invalid column name 'State'"
**Solution:** The table doesn't have that column. Use `AzureDiagnostics` with JSON parsing instead.

### Issue 2: Query returns no results
**Cause:** Diagnostic logs not enabled or wrong time range
**Solution:**
```kusto
// Check if ANY Databricks logs exist
AzureDiagnostics
| where TimeGenerated > ago(7d)
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| summarize count()
```

### Issue 3: Webhook not triggered
**Cause:** Alert rule misconfigured or action group issue
**Solution:**
```bash
# Test action group manually
az monitor action-group test-notifications create \
  --action-group-name YOUR_ACTION_GROUP \
  --resource-group YOUR_RESOURCE_GROUP \
  --notification-type webhook
```

### Issue 4: Wrong error details in webhook
**Cause:** Query `project` statement missing required columns
**Solution:** Ensure query projects these columns:
- `ClusterId` or `RunId` (for deduplication)
- `ErrorCode` (for auto-remediation decision)
- `ErrorMessage` (for RCA generation)
- `TimeGenerated` (for MTTR calculation)

---

## 📝 Summary: Quick Start Checklist

- [ ] **Step 1:** Run schema discovery query to find column names
- [ ] **Step 2:** Customize one of the provided queries for your schema
- [ ] **Step 3:** Test query in Log Analytics → verify it returns data
- [ ] **Step 4:** Create Azure Monitor Alert Rule with the query
- [ ] **Step 5:** Configure webhook action to point to your RCA API
- [ ] **Step 6:** Trigger test failure and verify webhook received
- [ ] **Step 7:** Check RCA dashboard for new ticket
- [ ] **Step 8:** Monitor auto-remediation in action

---

## 🎯 Next Steps

1. **Run schema discovery queries** in your Log Analytics workspace
2. **Copy the actual column names** you find
3. **Customize the queries** with your column names
4. **Test in Log Analytics** before creating alerts
5. **Share the working query** if you need help troubleshooting

Would you like me to help customize a query once you share the schema output? Just paste the result of the schema discovery query and I'll fix it! 🚀

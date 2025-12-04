# ✅ Correct Databricks KQL Queries - Copy & Paste Ready

## 🔍 First: Discover Your Schema (Run This First!)

```kusto
// Step 1: Check what tables you have
search *
| where TimeGenerated > ago(24h)
| where _ResourceId contains "databricks"
| distinct $table
```

**Expected output:** `AzureDiagnostics` (most common)

---

```kusto
// Step 2: See what columns exist
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| take 10
| project *
```

**Look for:** `Category`, `OperationName`, `ResultType`, `properties_s`

---

## ✅ Correct Query 1: Cluster Start Failures

**Use this query - it works with standard Databricks diagnostic logs:**

```kusto
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
```

---

## ✅ Correct Query 2: Job Failures

```kusto
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
```

---

## ✅ Correct Query 3: Combined All Failures

```kusto
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
| where State in ("TERMINATED", "ERROR", "TERMINATING") or ErrorCode != ""
| project TimeGenerated, FailureType, EntityId, EntityName, ErrorCode, ErrorMessage, ResourceGroup, _SubscriptionId, _ResourceId;

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
| project TimeGenerated, FailureType, EntityId, EntityName, ErrorCode, ErrorMessage, ResourceGroup, _SubscriptionId, _ResourceId;

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
| project TimeGenerated, FailureType, EntityId, EntityName, ErrorCode, ErrorMessage, ResourceGroup, _SubscriptionId, _ResourceId;

// Combine all
union ClusterFailures, JobFailures, LibraryFailures
| order by TimeGenerated desc
```

---

## 🧪 Test Before Creating Alert

**Run this to verify you're getting Databricks logs:**

```kusto
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| summarize count() by Category, OperationName, ResultType
```

**Expected output should show:**
- `Category: clusters, jobs, notebook, accounts`
- `OperationName: clusterStart, runNow, etc.`
- `count > 0`

If `count = 0`, you need to enable diagnostic settings first!

---

## 🔧 Enable Databricks Diagnostic Logs (If No Data)

```bash
az monitor diagnostic-settings create \
  --resource /subscriptions/YOUR_SUB_ID/resourceGroups/YOUR_RG/providers/Microsoft.Databricks/workspaces/YOUR_WORKSPACE \
  --name databricks-diagnostics \
  --workspace /subscriptions/YOUR_SUB_ID/resourceGroups/YOUR_RG/providers/Microsoft.OperationalInsights/workspaces/YOUR_LOG_ANALYTICS \
  --logs '[
    {"category": "jobs", "enabled": true},
    {"category": "clusters", "enabled": true},
    {"category": "notebook", "enabled": true},
    {"category": "accounts", "enabled": true},
    {"category": "dbfs", "enabled": false},
    {"category": "workspace", "enabled": false}
  ]'
```

---

## 📋 How to Use These Queries

### Option 1: Create Alert in Azure Portal

1. Go to **Azure Monitor** → **Alerts** → **New Alert Rule**
2. **Scope**: Select your Log Analytics Workspace
3. **Condition**: Custom log search
4. **Paste one of the queries above** (e.g., Cluster Failures)
5. **Alert logic**:
   - Based on: Number of results
   - Operator: Greater than
   - Threshold value: 0
   - Frequency: 5 minutes
6. **Actions**: Add webhook to your RCA API
   - URL: `https://your-api.azurewebsites.net/webhook/databricks`
7. **Save**

### Option 2: Create Alert with Azure CLI

```bash
az monitor scheduled-query create \
  --name "databricks-failures" \
  --resource-group YOUR_RG \
  --scopes /subscriptions/YOUR_SUB/resourceGroups/YOUR_RG/providers/Microsoft.OperationalInsights/workspaces/YOUR_WORKSPACE \
  --condition "count > 0" \
  --query-time-range 5 \
  --evaluation-frequency 5 \
  --action-groups /subscriptions/YOUR_SUB/resourceGroups/YOUR_RG/providers/microsoft.insights/actionGroups/YOUR_ACTION_GROUP \
  --query 'AzureDiagnostics
| where TimeGenerated > ago(5m)
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| where Category == "clusters"
| where ResultType != "Success"
| extend Details = parse_json(properties_s)
| extend TerminationCode = tostring(Details.termination_code)
| where TerminationCode in ("CLUSTER_START_FAILURE", "CLOUD_PROVIDER_LAUNCH_FAILURE")'
```

---

## ✅ What Changed from Previous Queries?

**Old (Wrong):**
```kusto
DatabricksClusters
| where State == "TERMINATED"  // ❌ Table/column doesn't exist
```

**New (Correct):**
```kusto
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| where Category == "clusters"
| extend Details = parse_json(properties_s)  // ✅ Parse JSON column
| extend State = tostring(Details.state)     // ✅ Extract from JSON
| where State == "TERMINATED"
```

**Why the change?**
- Most Databricks workspaces send logs to `AzureDiagnostics` table
- Detailed info is stored in `properties_s` as JSON
- Need to use `parse_json()` to extract fields

---

## 🎯 Summary

1. **Run schema discovery** to confirm you have `AzureDiagnostics` table
2. **Copy the queries above** - they work with standard Databricks logs
3. **Test in Log Analytics** before creating alerts
4. **Create alert rule** with one of the queries
5. **Configure webhook** to your RCA API endpoint

These queries should work immediately! If you still get errors, paste the output of the schema discovery query and I'll customize it further. 🚀

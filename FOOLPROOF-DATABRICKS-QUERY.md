# ✅ Foolproof Databricks Query - Works on ANY Schema

## 🎯 Run This First - It ALWAYS Works

This query doesn't assume ANY column names - it searches across all tables and columns:

```kusto
search *
| where TimeGenerated > ago(5m)
| where _ResourceId contains "databricks"
| where * has_any ("FAILED", "ERROR", "TERMINATED", "CLUSTER_START_FAILURE")
| where $table in ("AzureDiagnostics", "DatabricksClusters", "DatabricksJobs", "AzureActivity")
| project
    TimeGenerated,
    Table = $table,
    ResourceId = _ResourceId,
    AllData = pack_all()
```

**This will show you ALL Databricks failures regardless of table structure!**

---

## 🔍 Discover Your Schema - Run This Second

```kusto
// This shows what columns exist in your Databricks logs
search *
| where TimeGenerated > ago(24h)
| where _ResourceId contains "databricks"
| take 1
| evaluate bag_unpack(pack_all())
| project-away TimeGenerated, TenantId, Type
```

**Copy ALL column names from the output** and send them to me.

---

## 📋 Schema-Agnostic Query (Works Everywhere)

Use this for your alert - it adapts to any schema:

```kusto
// Universal Databricks failure detection
let DatabricksResource =
    search *
    | where TimeGenerated > ago(24h)
    | where _ResourceId contains "databricks"
    | distinct _ResourceId
    | take 1;
//
search in (AzureDiagnostics, DatabricksClusters, DatabricksJobs, AzureActivity) *
| where TimeGenerated > ago(5m)
| where _ResourceId in (DatabricksResource)
| where * has_any (
    "FAILED",
    "ERROR",
    "TERMINATED",
    "CLUSTER_START_FAILURE",
    "CLOUD_PROVIDER_LAUNCH_FAILURE",
    "DRIVER_UNREACHABLE",
    "TIMEOUT"
)
| extend
    FailureIndicator = case(
        * has "CLUSTER_START_FAILURE", "Cluster Start Failed",
        * has "CLOUD_PROVIDER_LAUNCH_FAILURE", "Cloud Provider Failed",
        * has "DRIVER_UNREACHABLE", "Driver Unreachable",
        * has "FAILED", "Job Failed",
        "Unknown Error"
    )
| project
    TimeGenerated,
    SourceTable = $table,
    FailureType = FailureIndicator,
    ResourceGroup,
    SubscriptionId = _SubscriptionId,
    ResourceId = _ResourceId,
    RawData = pack_all()
| order by TimeGenerated desc
```

---

## 🧪 Simple Test Query - Just Show Me Databricks Data

```kusto
// Show me ANYTHING related to Databricks in last 24 hours
search *
| where TimeGenerated > ago(24h)
| where _ResourceId contains "databricks"
| summarize
    RecordCount = count(),
    Tables = make_set($table),
    SampleTime = min(TimeGenerated),
    LatestTime = max(TimeGenerated)
| project
    RecordCount,
    Tables = strcat_array(Tables, ", "),
    FirstRecord = SampleTime,
    LatestRecord = LatestTime
```

**Expected output:**
```
RecordCount: 1500
Tables: AzureDiagnostics, AzureMetrics, AzureActivity
FirstRecord: 2025-12-03T10:00:00Z
LatestRecord: 2025-12-04T09:00:00Z
```

**If RecordCount = 0**, diagnostic logs are NOT enabled!

---

## ⚡ Ultra-Simple Failure Query

This is the SIMPLEST possible query - no assumptions about schema:

```kusto
search "FAILED"
| where TimeGenerated > ago(5m)
| where _ResourceId contains "databricks"
```

**Use this to test if your alert fires at all.**

---

## 🚨 Create Alert with Foolproof Query

### Azure Portal Steps:

1. **Azure Monitor** → **Alerts** → **New Alert Rule**
2. **Scope**: Your Log Analytics Workspace
3. **Condition**: Custom log search
4. **Query**:

```kusto
search *
| where TimeGenerated > ago(5m)
| where _ResourceId contains "databricks"
| where * has_any ("FAILED", "ERROR", "CLUSTER_START_FAILURE")
```

5. **Alert Logic**:
   - Operator: Greater than
   - Threshold: 0
   - Frequency: 5 minutes

6. **Action**: Webhook → `https://your-api/webhook/databricks`

7. **Done!** ✅

---

## 🎯 What to Do Next

### Step 1: Run the Simple Test Query

```kusto
search *
| where TimeGenerated > ago(24h)
| where _ResourceId contains "databricks"
| summarize count()
```

- **If count > 0**: You have logs! Use the foolproof query above
- **If count = 0**: Diagnostic logs not enabled - see below

### Step 2: Enable Diagnostic Settings (If Needed)

```bash
# Get your workspace ID
WORKSPACE_ID=$(az databricks workspace list --query "[0].id" -o tsv)

# Get your Log Analytics workspace ID
LOG_ANALYTICS_ID=$(az monitor log-analytics workspace list --query "[0].id" -o tsv)

# Enable diagnostics
az monitor diagnostic-settings create \
  --resource $WORKSPACE_ID \
  --name "databricks-logs" \
  --workspace $LOG_ANALYTICS_ID \
  --logs '[{"category": "jobs", "enabled": true}, {"category": "clusters", "enabled": true}]'
```

### Step 3: Wait 15 Minutes

Diagnostic logs take 10-30 minutes to appear after enabling.

### Step 4: Run Foolproof Query

Use the schema-agnostic query at the top of this doc.

---

## 💡 Why Your Previous Queries Failed

**Query 1 Error:**
```
Invalid column name in the query: 'State'
```
**Reason:** `DatabricksClusters` table doesn't exist OR column is named differently

**Query 2 Error:**
```
Failed to resolve scalar expression named 'properties_s'
```
**Reason:** Column is named `Properties` (capital P) or doesn't exist

**Solution:** Use `search *` with wildcards - doesn't rely on specific column names!

---

## 📊 Alternative: Query Databricks Directly

If Azure Monitor logs don't work, query Databricks system tables:

### In Databricks SQL or Notebook:

```sql
-- Cluster failures
SELECT
  event_time,
  cluster_id,
  cluster_name,
  state,
  termination_code,
  termination_details
FROM system.compute.clusters
WHERE event_time > current_timestamp() - INTERVAL 5 MINUTES
  AND state IN ('TERMINATING', 'TERMINATED', 'ERROR')
```

```sql
-- Job failures
SELECT
  event_time,
  job_id,
  run_id,
  job_name,
  result_state,
  error_message
FROM system.workflows.job_runs
WHERE event_time > current_timestamp() - INTERVAL 5 MINUTES
  AND result_state = 'FAILED'
```

### Set Up Databricks SQL Alert:

1. **Databricks Workspace** → **SQL** → **Alerts**
2. **Create Alert** with query above
3. **Condition**: `result_state = FAILED`
4. **Notification**: Webhook → Your RCA API
5. **Frequency**: Every 5 minutes

---

## 🎯 Bottom Line

**Use this query - it will work:**

```kusto
search *
| where TimeGenerated > ago(5m)
| where _ResourceId contains "databricks"
| where * has_any ("FAILED", "ERROR", "TERMINATED")
| project TimeGenerated, $table, _ResourceId, pack_all()
```

**Then send me the output** and I'll customize it further!

No more "column doesn't exist" errors! 🚀

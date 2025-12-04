# Databricks Schema Discovery - Find Your Actual Columns

## 🔍 Step 1: Discover What Columns You Have

Run these queries **one by one** in your Log Analytics workspace:

### Query A: Find All Databricks Tables

```kusto
search *
| where TimeGenerated > ago(7d)
| where _ResourceId contains "databricks"
| distinct $table
| project TableName = $table
```

**Copy the output here** → You should see table names like:
- `AzureDiagnostics`
- `DatabricksJobs`
- `DatabricksClusters`
- `AzureActivity`
- `AzureMetrics`

---

### Query B: See ALL Columns in AzureDiagnostics

```kusto
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where _ResourceId contains "databricks"
| take 1
| project *
```

**Look for columns with these patterns:**
- `properties*` (properties, Properties, properties_s, properties_d)
- `cluster*` (cluster_id, cluster_name, cluster_state)
- `job*` (job_id, job_name, run_id)
- `state*` (state, State, result_state)
- `error*` (error_code, error_message)

**Common possibilities:**
- Capital P: `Properties` instead of `properties_s`
- No suffix: `properties` instead of `properties_s`
- Direct columns: Data is NOT in JSON, but in separate columns

---

### Query C: Check for Dedicated Databricks Tables

```kusto
// If you have DatabricksClusters table
DatabricksClusters
| take 1
| project *
```

```kusto
// If you have DatabricksJobs table
DatabricksJobs
| take 1
| project *
```

**If these return results**, then you DO have dedicated tables! We'll use a different query.

---

### Query D: Show Raw Sample Data

```kusto
AzureDiagnostics
| where TimeGenerated > ago(24h)
| where _ResourceId contains "databricks"
| take 5
```

**Copy the entire output** and I'll tell you exactly what query to use.

---

## ✅ Alternative Queries Based on Common Schemas

### Option 1: If You Have `Properties` (Capital P)

```kusto
AzureDiagnostics
| where TimeGenerated > ago(5m)
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| where Category == "clusters"
| where ResultType != "Success"
| extend ClusterDetails = parse_json(Properties)  // Changed to capital P
| extend
    ClusterId = tostring(ClusterDetails.cluster_id),
    ClusterName = tostring(ClusterDetails.cluster_name),
    State = tostring(ClusterDetails.state),
    TerminationCode = tostring(ClusterDetails.termination_code)
| where State in ("TERMINATED", "ERROR")
| project TimeGenerated, ClusterId, ClusterName, State, TerminationCode
```

---

### Option 2: If Columns Are Directly in the Table (No JSON)

```kusto
AzureDiagnostics
| where TimeGenerated > ago(5m)
| where ResourceProvider == "MICROSOFT.DATABRICKS"
| where Category == "clusters"
| where ResultType != "Success"
| project
    TimeGenerated,
    ClusterId = cluster_id,           // Direct column
    ClusterName = cluster_name,       // Direct column
    State = cluster_state,            // Direct column
    TerminationCode = termination_code,
    ErrorCode = error_code,
    ResourceGroup
```

---

### Option 3: If You Have Dedicated DatabricksClusters Table

```kusto
DatabricksClusters
| where TimeGenerated > ago(5m)
| where cluster_state == "TERMINATED" or cluster_state == "ERROR"
| project
    TimeGenerated,
    ClusterId = cluster_id,
    ClusterName = cluster_name,
    State = cluster_state,
    TerminationCode = termination_code,
    TerminationReason = state_message
```

---

### Option 4: If Using AzureActivity Table

```kusto
AzureActivity
| where TimeGenerated > ago(5m)
| where ResourceProvider == "Microsoft.Databricks/workspaces"
| where ActivityStatusValue == "Failed" or ActivityStatusValue == "Error"
| extend Details = parse_json(Properties)
| extend
    OperationType = OperationNameValue,
    ErrorCode = tostring(Details.statusCode),
    ErrorMessage = tostring(Details.statusMessage)
| project
    TimeGenerated,
    OperationType,
    ErrorCode,
    ErrorMessage,
    Caller,
    ResourceGroup
```

---

### Option 5: Generic Query That Works Everywhere

This query tries to find errors across ALL tables:

```kusto
union AzureDiagnostics, DatabricksClusters, DatabricksJobs, AzureActivity
| where TimeGenerated > ago(5m)
| where _ResourceId contains "databricks"
| where * contains "FAILED" or * contains "ERROR" or * contains "TERMINATED"
| project TimeGenerated, $table, *
```

---

## 🎯 Quick Diagnostic Script

**Copy-paste this entire script** - it will show you everything:

```kusto
// === DATABRICKS SCHEMA DIAGNOSTIC REPORT ===

print "=== Step 1: Available Tables ==="
| union (
    search *
    | where TimeGenerated > ago(7d)
    | where _ResourceId contains "databricks"
    | distinct $table
    | summarize Tables = make_list($table)
    | project ReportSection = "Available Tables", Details = tostring(Tables)
)
| union (
    print "=== Step 2: AzureDiagnostics Column Names ==="
)
| union (
    AzureDiagnostics
    | where TimeGenerated > ago(24h)
    | where _ResourceId contains "databricks"
    | take 1
    | project ReportSection = "AzureDiagnostics Columns", Details = strcat(
        "Available columns: ",
        bag_keys(bag_pack_columns(*))
    )
)
| union (
    print "=== Step 3: Sample Data ==="
)
| union (
    AzureDiagnostics
    | where TimeGenerated > ago(24h)
    | where _ResourceId contains "databricks"
    | take 3
    | project
        ReportSection = "Sample Row",
        Details = strcat(
            "Category: ", Category, " | ",
            "OperationName: ", OperationName, " | ",
            "ResultType: ", ResultType, " | ",
            "Has properties_s: ", isnotempty(column_ifexists("properties_s", "")), " | ",
            "Has Properties: ", isnotempty(column_ifexists("Properties", ""))
        )
)
```

**This will tell you:**
1. What tables you have
2. What columns exist
3. Whether `properties_s` or `Properties` exists
4. Sample data structure

---

## 🔧 If Diagnostic Logs Are Not Enabled

If all queries return **0 results**, you need to enable diagnostic settings:

### Azure Portal Method:

1. Go to **Databricks Workspace** → **Monitoring** → **Diagnostic settings**
2. Click **Add diagnostic setting**
3. Name: `databricks-logs`
4. Select categories:
   - ✅ jobs
   - ✅ clusters
   - ✅ notebook
   - ✅ accounts
5. Destination: **Send to Log Analytics workspace**
6. Select your workspace
7. **Save**

### Azure CLI Method:

```bash
# Find your Databricks workspace resource ID
az databricks workspace list --query "[].{name:name, id:id}" -o table

# Enable diagnostic logs
az monitor diagnostic-settings create \
  --resource /subscriptions/{SUB_ID}/resourceGroups/{RG}/providers/Microsoft.Databricks/workspaces/{WORKSPACE_NAME} \
  --name databricks-diagnostics \
  --workspace /subscriptions/{SUB_ID}/resourceGroups/{RG}/providers/Microsoft.OperationalInsights/workspaces/{LOG_ANALYTICS_WORKSPACE} \
  --logs '[
    {
      "category": "jobs",
      "enabled": true,
      "retentionPolicy": {"enabled": false, "days": 0}
    },
    {
      "category": "clusters",
      "enabled": true,
      "retentionPolicy": {"enabled": false, "days": 0}
    },
    {
      "category": "notebook",
      "enabled": true,
      "retentionPolicy": {"enabled": false, "days": 0}
    },
    {
      "category": "accounts",
      "enabled": true,
      "retentionPolicy": {"enabled": false, "days": 0}
    }
  ]'
```

**Wait 15-30 minutes** after enabling, then run the queries again.

---

## 📊 Alternative: Use Databricks System Tables

If Azure diagnostic logs don't work, you can query Databricks **system tables** directly:

```sql
-- In Databricks SQL or notebook
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

Then set up a **Databricks SQL Alert** to webhook to your RCA API.

---

## 🎯 Next Steps

1. **Run the Diagnostic Script above** (copy the entire kusto block)
2. **Copy the output** and share it with me
3. I'll give you the **exact correct query** for your schema
4. Or share a screenshot of the Log Analytics results

The diagnostic script will tell us exactly what columns you have! 🔍

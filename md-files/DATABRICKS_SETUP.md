# Databricks Error Extraction Setup Guide

## Problem: Generic RCA Messages

If you're seeing generic error messages like:
> "The provided event notification only indicates the failure, but does not include the specific underlying reason or error details"

This guide will help you fix it.

---

## Understanding the Data Flow

### Current Architecture

```
Databricks Job Fails
        ↓
Databricks sends webhook (generic event notification)
        ↓
/databricks-monitor endpoint receives webhook
        ↓
System extracts run_id from webhook
        ↓
🔑 CRITICAL: System calls Databricks Jobs API to fetch detailed error
        ↓
Detailed error extracted from task outputs/logs
        ↓
Detailed error sent to RCA AI (Gemini)
        ↓
AI generates specific root cause analysis
```

### Where Things Go Wrong

**Symptom:** You're getting 6+ duplicate alerts with the same generic message.

**Root Causes:**
1. **Missing Databricks API credentials** → API fetch fails → only webhook data used
2. **Incorrect webhook format** → run_id not extracted → API not called
3. **API extraction failing** → API returns data but error not found in expected fields

---

## Step-by-Step Fix

### Step 1: Configure Databricks API Credentials

The system **MUST** have access to Databricks Jobs API to fetch detailed errors.

#### 1.1 Find Your Databricks Workspace URL

```bash
# Option 1: Azure Portal
# Go to: Azure Portal → Databricks Workspace → Overview → URL
# Example: https://adb-1234567890123456.7.azuredatabricks.net

# Option 2: Azure CLI
az databricks workspace show \
  --resource-group rg_techdemo_2025_Q4 \
  --name techdemo_databricks \
  --query workspaceUrl -o tsv
```

#### 1.2 Generate Databricks Personal Access Token

1. Open Databricks workspace in browser
2. Click your profile icon (top right) → **User Settings**
3. Go to **Access Tokens** tab
4. Click **Generate New Token**
   - Name: `RCA System API Access`
   - Lifetime: `365 days` (or as per your security policy)
5. Click **Generate**
6. **COPY THE TOKEN NOW** (it won't be shown again)

#### 1.3 Set Environment Variables

Create a `.env` file in the `genai_rca_assistant/` directory:

```bash
# Copy the example file
cp .env.example .env

# Edit .env and add:
DATABRICKS_HOST=https://adb-1234567890123456.7.azuredatabricks.net
DATABRICKS_TOKEN=dapi1234567890abcdef...
```

#### 1.4 Verify Configuration

```bash
# Test the Databricks API connection
cd genai_rca_assistant
python databricks_api_utils.py 204354054874177
```

Expected output:
```
Testing with run_id: 204354054874177
=== Run Details ===
Job ID: 404831337617650
Run ID: 204354054874177
Run Name: test4
State: TERMINATED
Result: FAILED

=== Error Message ===
[Task: task1] org.apache.spark.sql.AnalysisException: Table or view not found: invalid_table
```

If you see "Failed to fetch run details", your credentials are incorrect.

---

### Step 2: Verify Webhook Configuration

The enhanced code now logs the **complete raw webhook payload** for debugging.

#### 2.1 Check Application Logs

After the next Databricks job failure, check your application logs:

```bash
# If running locally
tail -f app.log | grep "DATABRICKS WEBHOOK RECEIVED"

# If running in Docker
docker logs <container-name> | grep "DATABRICKS WEBHOOK"

# If running in Azure App Service
az webapp log tail --name <app-service-name> --resource-group <resource-group>
```

You should see:
```
================================================================================
DATABRICKS WEBHOOK RECEIVED - RAW PAYLOAD:
{
  "event": "on_failure",
  "job_id": "404831337617650",
  "run_id": "204354054874177",
  "job": {
    "job_id": "404831337617650",
    "settings": {
      "name": "test4",
      ...
    }
  },
  "run": {
    "run_id": "204354054874177",
    "state": {
      "life_cycle_state": "TERMINATED",
      "result_state": "FAILED",
      "state_message": "..."
    }
  }
}
================================================================================
```

#### 2.2 Verify API Fetch is Attempted

Look for these log messages:
```
📋 Extracted from webhook: job_name=test4, run_id=204354054874177, job_id=404831337617650
🔄 Attempting to fetch detailed error from Databricks Jobs API for run_id: 204354054874177
✅ Successfully fetched run details from Databricks API
✅ Extracted detailed error from API: [Task: task1] org.apache.spark.sql.AnalysisException...
```

#### 2.3 Common Error Messages and Fixes

| Log Message | Problem | Fix |
|------------|---------|-----|
| `❌ CRITICAL: Databricks API credentials NOT configured!` | Missing env vars | Set `DATABRICKS_HOST` and `DATABRICKS_TOKEN` |
| `⚠️ No valid run_id found in webhook` | Webhook format issue | Check webhook payload structure |
| `❌ API returned run details but no specific error message found` | Error extraction issue | Job might not be failed, or error in unexpected field |
| `❌ Exception while fetching Databricks run details: 401` | Invalid token | Regenerate Databricks PAT |
| `❌ Exception while fetching Databricks run details: 404` | Invalid run_id | Check if run_id in webhook is correct |

---

### Step 3: Test with Real Databricks Job

#### 3.1 Create a Test Job That Fails

In Databricks workspace:

1. **Create a new notebook** called `test_rca_failure`
2. **Add this code** (it will fail intentionally):

```python
# Cell 1: This will fail with a clear error message
raise Exception("TEST RCA: Database connection failed - invalid credentials for 'prod_db'")

# Or test a SQL error:
spark.sql("SELECT * FROM non_existent_table")
```

3. **Create a workflow job**:
   - Workflows → Create Job
   - Name: `test_rca_job`
   - Task: Notebook task pointing to `test_rca_failure`
   - Cluster: Use existing all-purpose cluster

4. **Configure webhook** (if not already done):
   - Job → Job Settings → Add Notifications
   - Webhook URL: `https://your-app-url.com/databricks-monitor`
   - Events: Select "On Failure"

5. **Run the job** → It will fail

6. **Check your RCA system logs** for the detailed error extraction

---

### Step 4: Troubleshooting Checklist

#### ✅ Pre-Flight Checks

- [ ] `DATABRICKS_HOST` environment variable is set
- [ ] `DATABRICKS_TOKEN` environment variable is set
- [ ] Token is valid (test with `databricks_api_utils.py`)
- [ ] Webhook is configured in Databricks job settings
- [ ] Webhook URL is accessible from internet (use ngrok for local testing)
- [ ] Application logs show webhook payloads being received

#### ✅ Webhook Reception Checks

- [ ] Logs show `DATABRICKS WEBHOOK RECEIVED - RAW PAYLOAD:`
- [ ] Payload contains `run_id` field
- [ ] `run_id` is not "N/A" or empty

#### ✅ API Fetch Checks

- [ ] Logs show `🔄 Attempting to fetch detailed error from Databricks Jobs API`
- [ ] Logs show `✅ Successfully fetched run details from Databricks API`
- [ ] Logs show `✅ Extracted detailed error from API`
- [ ] Error message length > 50 characters (not generic)

#### ✅ RCA Quality Checks

- [ ] RCA mentions specific error type (not "DatabricksJobExecutionError" only)
- [ ] Root cause mentions actual error details (e.g., "Table not found: users_table")
- [ ] Recommendations are actionable (not "check logs manually")

---

## Understanding Databricks Webhook Formats

The system now supports **multiple webhook formats**:

### Format 1: Databricks Event Delivery (recommended)

```json
{
  "event": "on_failure",
  "job_id": "404831337617650",
  "run_id": "204354054874177",
  "job": {
    "job_id": "404831337617650",
    "settings": {
      "name": "test4"
    }
  },
  "run": {
    "run_id": "204354054874177",
    "run_name": "test4",
    "state": {
      "life_cycle_state": "TERMINATED",
      "result_state": "FAILED",
      "state_message": "Run failed"
    }
  }
}
```

### Format 2: Azure Monitor / Log Analytics

```json
{
  "job_name": "test4",
  "run_id": "204354054874177",
  "job_id": "404831337617650",
  "error_message": "Generic error from monitor",
  "workspace_url": "https://adb-123.azuredatabricks.net"
}
```

### Format 3: Custom Webhook

```json
{
  "JobName": "test4",
  "RunId": "204354054874177",
  "ErrorMessage": "Job failed",
  "ClusterId": "cluster-123"
}
```

The enhanced code now handles all three formats and extracts the `run_id` correctly.

---

## Deduplication Issue

You mentioned seeing **6 duplicate alerts** for the same job run. This is now prevented by:

1. **Unique index on run_id** in database (lines 244-284 in main.py)
2. **Duplicate check** before creating ticket (lines 1214-1232 in main.py)

If a webhook is received for a run_id that already has a ticket:
- **No new ticket is created**
- **Returns** `{"status": "duplicate_ignored", "ticket_id": "<existing>"}`
- **Audit log** records the duplicate attempt

---

## Expected Log Output (Success)

When everything is configured correctly, you should see:

```
================================================================================
DATABRICKS WEBHOOK RECEIVED - RAW PAYLOAD:
{
  "event": "on_failure",
  "job_id": "404831337617650",
  "run_id": "204354054874177",
  ...
}
================================================================================
📋 Extracted from webhook: job_name=test4, run_id=204354054874177, job_id=404831337617650
📝 Initial error_message from webhook: Databricks job event: on_failure...
🔄 Attempting to fetch detailed error from Databricks Jobs API for run_id: 204354054874177
✅ Successfully fetched run details from Databricks API
🔍 Extracting error message from Databricks API response...
   Found 1 task(s) in run data
   Task 'notebook_task': result_state=FAILED
   ✓ Task 'notebook_task' has FAILED state, extracting error...
   ✓ Found error in run_output for task 'notebook_task'
   ✓ Added error for task 'notebook_task': org.apache.spark.sql.AnalysisException: Table...
✅ Successfully extracted 1 error message(s)
✅ Extracted detailed error from API: [Task: notebook_task] org.apache.spark.sql.AnalysisException: Table or view not found: invalid_table...
================================================================================
📤 FINAL error_message being sent to RCA AI:
   API fetch attempted: True
   API fetch success: True
   Error message length: 245 chars
   Error message preview:
[Task: notebook_task] org.apache.spark.sql.AnalysisException: Table or view not found: invalid_table at SimpleCatalogManager...
================================================================================
Databricks RCA stored in DB for DBX-20251123T150045-a1b2c3
```

---

## Next Steps

1. **Immediate Action**: Set `DATABRICKS_HOST` and `DATABRICKS_TOKEN` environment variables
2. **Test**: Run a failing Databricks job and check logs
3. **Verify**: Ensure RCA messages are now specific (not generic)
4. **Monitor**: Check for duplicate prevention working

---

## Support

If you still see generic errors after following this guide:

1. **Capture the logs** showing the webhook payload and API fetch attempt
2. **Run the test command**: `python databricks_api_utils.py <your-run-id>`
3. **Check Databricks job run logs** to confirm actual error exists
4. **Share the log output** for further debugging

The enhanced logging will show exactly where the error extraction is failing.

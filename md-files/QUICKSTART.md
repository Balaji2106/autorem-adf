# 🚀 Quick Start: Fix Databricks Generic Errors

**Problem**: Getting generic RCA alerts like *"does not include the specific underlying reason or error details"*

**Solution**: Configure Databricks API credentials (5 minutes)

---

## ⚡ Quick Fix (3 Steps)

### Step 1: Run Setup Script

```bash
cd /home/user/latest_databricks
./setup_databricks.sh
```

This will prompt you for:
1. **Databricks Workspace URL** (get from Azure Portal)
2. **Personal Access Token** (generate in Databricks UI)

### Step 2: Test Connection

```bash
./test_databricks_connection.sh 204354054874177
```

Expected output:
```
✅ TEST PASSED: Successfully connected to Databricks API
✅ Run details fetched successfully
✅ Error extraction working
```

### Step 3: Restart Your RCA Application

```bash
# If running locally
cd genai_rca_assistant
source .env
python main.py

# If running in Docker
docker restart <container-name>

# If running in Azure App Service
az webapp restart --name <app-name> --resource-group rg_techdemo_2025_Q4
```

**Done!** Next Databricks job failure will show detailed errors.

---

## 📋 What You Need

### 1. Databricks Workspace URL

**Get it from Azure Portal:**
1. Go to: https://portal.azure.com
2. Navigate to: Resource Groups → `rg_techdemo_2025_Q4`
3. Click: `techdemo_databricks`
4. Copy the **URL** field

Format: `https://adb-1234567890123456.7.azuredatabricks.net`

### 2. Personal Access Token (PAT)

**Generate in Databricks:**
1. Open your Databricks workspace in browser
2. Click profile icon (top right) → **User Settings**
3. Go to **Access Tokens** tab
4. Click **Generate New Token**
   - Name: `RCA System`
   - Lifetime: `365 days`
5. Click **Generate** and **COPY THE TOKEN**

Format: `dapi` + 32+ hexadecimal characters

---

## 🧪 Testing the Fix

### Test 1: API Connection

```bash
# Test with your actual run_id from the alerts
./test_databricks_connection.sh 204354054874177
```

Should show:
- ✅ Job details
- ✅ Error message extracted
- ✅ Not just "Run failed"

### Test 2: Full Webhook Flow

```bash
# Create test webhook payload
cat > /tmp/test_webhook.json <<'EOF'
{
  "event": "on_failure",
  "job_id": "404831337617650",
  "run_id": "204354054874177",
  "job": {
    "job_id": "404831337617650",
    "settings": {"name": "test4"}
  },
  "run": {
    "run_id": "204354054874177",
    "state": {
      "result_state": "FAILED",
      "state_message": "Run failed"
    }
  }
}
EOF

# Send to your RCA endpoint
curl -X POST http://localhost:8000/databricks-monitor \
  -H "Content-Type: application/json" \
  -d @/tmp/test_webhook.json
```

Check logs for:
```
================================================================================
DATABRICKS WEBHOOK RECEIVED - RAW PAYLOAD:
...
🔄 Attempting to fetch detailed error from Databricks Jobs API for run_id: 204354054874177
✅ Successfully fetched run details from Databricks API
✅ Extracted detailed error from API: [Task: task1] ...
================================================================================
```

---

## 📊 Before vs After

### ❌ BEFORE (Generic - Not Helpful)

```
ALERT: Databricks Job/Cluster - Medium (P3)
Ticket: DBX-20251123T143107-440729
Run ID: N/A
Error Type: DatabricksJobExecutionError

Root Cause: The Databricks job named 'test4' with job_id 404831337617650
failed to complete its execution. This event message indicates a general
job failure but does not provide the specific underlying cause.

Resolution Steps:
* Navigate to the Databricks UI and open the job run details
* Review the individual task and notebook outputs
* Investigate common causes of job failures
```

### ✅ AFTER (Specific - Actionable)

```
ALERT: Databricks Job/Cluster - High (P2)
Ticket: DBX-20251123T153045-a1b2c3
Run ID: 204354054874177
Error Type: DatabricksTableNotFound

Root Cause: Databricks job 'test4' failed because a Spark SQL query
attempted to access table 'production.users_table' which does not
exist in the specified catalog. Error occurred in task 'notebook_task'
at line 42 of the ETL notebook.

Resolution Steps:
* Verify that table 'production.users_table' exists in Unity Catalog
* Check if the table was recently renamed or dropped
* Ensure the job service principal has SELECT permissions on the table
* Review the notebook code at line 42 for correct table name
```

---

## 🔍 Verifying It Works

### Check Application Logs

Look for these indicators:

✅ **Credentials loaded:**
```
DATABRICKS_HOST=https://adb-123...azuredatabricks.net
DATABRICKS_TOKEN=dapi***
```

✅ **API fetch attempted:**
```
🔄 Attempting to fetch detailed error from Databricks Jobs API for run_id: 204354054874177
```

✅ **API fetch successful:**
```
✅ Successfully fetched run details from Databricks API
✅ Extracted detailed error from API: [Task: notebook_task] ...
```

✅ **Error details found:**
```
📤 FINAL error_message being sent to RCA AI:
   API fetch attempted: True
   API fetch success: True
   Error message length: 245 chars
```

❌ **If you see this, credentials are missing:**
```
❌ CRITICAL: Databricks API credentials NOT configured!
❌ Cannot fetch detailed error messages from Databricks Jobs API
```

---

## 🐛 Troubleshooting

### Issue: "DATABRICKS_HOST not set"

**Fix:**
```bash
# Check .env file
cat genai_rca_assistant/.env | grep DATABRICKS

# Re-run setup if missing
./setup_databricks.sh
```

### Issue: "401 Unauthorized"

**Cause:** Token expired or invalid

**Fix:**
1. Generate new token in Databricks UI
2. Update `.env` file:
   ```bash
   nano genai_rca_assistant/.env
   # Update DATABRICKS_TOKEN=<new_token>
   ```
3. Restart application

### Issue: "404 Not Found for run_id"

**Cause:** Run ID doesn't exist or not accessible

**Fix:**
1. Verify run_id in Databricks UI
2. Check permissions (need at least CAN VIEW on job)
3. Try with a different, recent run_id

### Issue: "Still getting generic errors"

**Check:**
```bash
# 1. Verify credentials are loaded
./test_databricks_connection.sh 204354054874177

# 2. Check application logs
tail -f app.log | grep "DATABRICKS WEBHOOK"

# 3. Ensure .env is in correct location
ls -la genai_rca_assistant/.env

# 4. Restart application after configuration
```

---

## 📁 Files Created

```
latest_databricks/
├── .env.example              # Template with all env vars
├── DATABRICKS_SETUP.md       # Comprehensive guide
├── QUICKSTART.md            # This file
├── setup_databricks.sh      # Interactive setup script
├── test_databricks_connection.sh  # Test script
└── genai_rca_assistant/
    ├── .env                 # Your actual credentials (created by setup)
    ├── main.py              # Enhanced with logging
    └── databricks_api_utils.py  # Enhanced error extraction
```

---

## ✅ Success Checklist

- [ ] Setup script completed successfully
- [ ] Test script shows ✅ TEST PASSED
- [ ] `.env` file contains `DATABRICKS_HOST` and `DATABRICKS_TOKEN`
- [ ] Application restarted with new credentials
- [ ] Test webhook returns detailed error (not generic)
- [ ] Next real alert shows specific error message

---

## 📚 More Help

- **Full setup guide**: `DATABRICKS_SETUP.md`
- **Environment variables**: `.env.example`
- **Test connection**: `./test_databricks_connection.sh <run_id>`
- **View logs**: Check for "DATABRICKS WEBHOOK RECEIVED"

---

## 💡 Why This Fixes It

**The Problem:**
- Databricks webhooks send **minimal data** (just "job failed" notification)
- Without API credentials, system can't fetch **detailed error logs**
- AI correctly reports: "notification does not include specific error details"

**The Solution:**
- Configure **Databricks API credentials** (DATABRICKS_HOST + TOKEN)
- System now **calls Databricks Jobs API** to fetch full run details
- Extracts **actual error messages** from task outputs/logs
- AI generates **specific, actionable RCA** based on real errors

**The Flow:**
```
Webhook (generic) → Extract run_id → Call Databricks API →
Get task logs → Extract real error → Send to AI → Specific RCA
```

---

**Need Help?** Check the troubleshooting section in `DATABRICKS_SETUP.md`

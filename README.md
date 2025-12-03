# AIOps RCA Assistant - Databricks Integration

**Enterprise-grade Root Cause Analysis system for Azure Data Factory and Databricks**

---

## 🎯 Quick Start

### Problem: Generic Databricks Error Messages?

If you're seeing alerts like this:
> "The event notification does not include the specific underlying reason or error details"

**You need to configure Databricks API credentials.** Follow the Quick Start below.

### ⚡ 3-Step Fix (5 minutes)

```bash
# 1. Run setup
./setup_databricks.sh

# 2. Test connection
./test_databricks_connection.sh 204354054874177

# 3. Restart application
cd genai_rca_assistant && python main.py
```

**See**: [QUICKSTART.md](QUICKSTART.md) for detailed instructions.

---

## 📋 Documentation

| Document | Purpose | Use When |
|----------|---------|----------|
| [QUICKSTART.md](QUICKSTART.md) | 5-minute fix guide | You want to fix generic errors NOW |
| [DATABRICKS_SETUP.md](DATABRICKS_SETUP.md) | Complete setup guide | You need detailed troubleshooting |
| [.env.example](.env.example) | Configuration template | Setting up environment variables |
| This README | Project overview | Understanding the system |

---

## 🛠️ Setup Tools

### Automated Setup

```bash
# Interactive setup wizard - answers all questions
./setup_databricks.sh
```

Prompts for:
- Databricks workspace URL
- Personal Access Token
- Saves to `.env` file
- Tests connection automatically

### Connection Testing

```bash
# Test with a specific run_id
./test_databricks_connection.sh <run_id>

# Example
./test_databricks_connection.sh 204354054874177
```

Verifies:
- ✅ Credentials are loaded
- ✅ API connection works
- ✅ Error extraction succeeds
- ✅ Creates test webhook payload

---

## 🏗️ System Architecture

### Data Flow

```
┌─────────────────┐
│ Databricks Job  │
│ Fails           │
└────────┬────────┘
         │
         │ Webhook (minimal data: job_id, run_id, "failed")
         ↓
┌─────────────────────────────────────────────────┐
│ RCA System (/databricks-monitor endpoint)      │
│                                                 │
│  1. Receive webhook                            │
│  2. Log raw payload                            │
│  3. Extract run_id                             │
│  4. 🔑 Call Databricks Jobs API                │  ← Needs credentials
│  5. Fetch full run details                     │
│  6. Extract real error from task outputs       │
│  7. Send detailed error to AI                  │
│  8. Generate specific RCA                      │
└─────────────────────────────────────────────────┘
         │
         │ Detailed RCA with specific error
         ↓
┌─────────────────┐
│ Slack Alert     │
│ ITSM Ticket     │
│ Dashboard       │
└─────────────────┘
```

### Why API Credentials Are Critical

| Without Credentials | With Credentials |
|---------------------|------------------|
| ❌ Only webhook data (generic) | ✅ Full run details from API |
| ❌ "Job failed" message | ✅ Actual exception/stack trace |
| ❌ No task-level details | ✅ Which task failed, line numbers |
| ❌ Generic RCA | ✅ Specific, actionable RCA |

**Example:**

```
WITHOUT CREDENTIALS:
"A Databricks job failed. The event notification does not include specific error details."

WITH CREDENTIALS:
"Databricks job 'etl_pipeline' failed with org.apache.spark.sql.AnalysisException:
Table or view not found: production.users_table at line 42 in notebook ETL_Transform.
The table may have been dropped or renamed."
```

---

## 🔧 Configuration

### Required Environment Variables

```bash
# Databricks API (REQUIRED for detailed errors)
DATABRICKS_HOST=https://adb-1234567890123456.7.azuredatabricks.net
DATABRICKS_TOKEN=dapi1234567890abcdef...

# RCA System
GEMINI_API_KEY=your-gemini-key
RCA_API_KEY=your-rca-secret

# Optional: ITSM Integration
ITSM_TOOL=jira
JIRA_DOMAIN=https://your-company.atlassian.net
JIRA_API_TOKEN=your-token

# Optional: Slack Notifications
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_ALERT_CHANNEL=aiops-rca-alerts
```

See [.env.example](.env.example) for complete list.

### Getting Databricks Credentials

**Workspace URL:**
- Azure Portal → Databricks → Overview → URL
- Format: `https://adb-XXXXXXXXXX.X.azuredatabricks.net`

**Personal Access Token:**
1. Open Databricks workspace
2. User Settings → Access Tokens
3. Generate New Token (365 days)
4. Name: "RCA System"
5. Copy token (starts with `dapi`)

---

## 🎨 Features

### ✅ Enhanced in This Version

- **Complete webhook payload logging** - Debug exactly what Databricks sends
- **Databricks Event Delivery support** - Handle official webhook format
- **Automatic API enrichment** - Fetch detailed errors automatically
- **Comprehensive error extraction** - Check all fields for error messages
- **Detailed logging** - Track every step of error extraction
- **Duplicate prevention** - No multiple alerts for same run
- **Fallback handling** - Graceful degradation if API unavailable

### 🚀 Core Features

- **Multi-source support**: Azure Data Factory + Databricks
- **AI-powered RCA**: Google Gemini for intelligent analysis
- **ITSM integration**: Auto-create Jira tickets
- **Slack notifications**: Real-time alerts
- **Deduplication**: Prevent duplicate tickets
- **Audit trail**: Complete action history
- **FinOps tagging**: Cost center tracking
- **Auto-remediation**: Trigger healing playbooks
- **WebSocket updates**: Real-time dashboard

---

## 📂 Project Structure

```
latest_databricks/
├── README.md                          # This file
├── QUICKSTART.md                      # 5-minute setup guide
├── DATABRICKS_SETUP.md               # Detailed troubleshooting
├── .env.example                       # Configuration template
├── setup_databricks.sh               # Interactive setup wizard ⭐
├── test_databricks_connection.sh     # Connection testing ⭐
├── databricks_debug_commands.sh      # Azure diagnostics
│
├── genai_rca_assistant/
│   ├── main.py                       # FastAPI application (enhanced)
│   ├── databricks_api_utils.py      # Databricks API client (enhanced)
│   ├── dashboard.html                # Web UI
│   ├── login.html                    # Authentication
│   ├── requirements.txt              # Python dependencies
│   └── .env                          # Your credentials (created by setup)
│
└── prompts/
    └── rca_prompt.txt                # AI prompt templates
```

**⭐ New Tools** - Make setup and testing easy!

---

## 🧪 Testing

### Test 1: Databricks API Connection

```bash
# Test with actual run_id from your alerts
./test_databricks_connection.sh 204354054874177
```

Expected output:
```
✅ TEST PASSED: Successfully connected to Databricks API
✅ Run details fetched successfully
✅ Error extraction working

=== Run Details ===
Job ID: 404831337617650
Run ID: 204354054874177
Run Name: test4
State: TERMINATED
Result: FAILED

=== Error Message ===
[Task: notebook_task] org.apache.spark.sql.AnalysisException: ...
```

### Test 2: Full Webhook Flow

```bash
# Send test webhook to your running application
curl -X POST http://localhost:8000/databricks-monitor \
  -H "Content-Type: application/json" \
  -d '{
    "event": "on_failure",
    "run_id": "204354054874177",
    "job_id": "404831337617650"
  }'
```

Check logs for:
- ✅ Webhook received
- ✅ API fetch attempted
- ✅ Detailed error extracted
- ✅ Specific RCA generated

### Test 3: Create Failing Job in Databricks

```python
# In Databricks notebook
raise Exception("TEST: RCA system verification - table not found")

# Or
spark.sql("SELECT * FROM non_existent_table")
```

Run job → Check RCA alert → Should show specific error, not generic.

---

## 🐛 Troubleshooting

### Issue: Generic Error Messages

**Symptom:**
```
Root Cause: The event notification does not include the specific
underlying reason or error details for why the Databricks job failed.
```

**Diagnosis:**
```bash
# Check if credentials configured
cat genai_rca_assistant/.env | grep DATABRICKS

# Test API connection
./test_databricks_connection.sh 204354054874177
```

**Fix:**
```bash
./setup_databricks.sh
```

### Issue: "DATABRICKS_HOST not set"

**Cause:** Environment variables not loaded

**Fix:**
```bash
# Check .env exists
ls -la genai_rca_assistant/.env

# Restart application to load .env
cd genai_rca_assistant
source .env
python main.py
```

### Issue: "401 Unauthorized"

**Cause:** Token expired or invalid

**Fix:**
1. Generate new token in Databricks UI
2. Run: `./setup_databricks.sh` (will update token)
3. Restart application

### Issue: Duplicate Alerts

**Cause:** Multiple webhooks for same run (now prevented)

**Verification:**
```bash
# Check logs for deduplication
tail -f app.log | grep "DUPLICATE DETECTED"
```

Should see:
```
DUPLICATE DETECTED: run_id 204354054874177 already has ticket DBX-...
```

---

## 📊 Monitoring

### Application Logs

**Key log patterns to monitor:**

✅ **Successful flow:**
```
================================================================================
DATABRICKS WEBHOOK RECEIVED - RAW PAYLOAD:
...
📋 Extracted from webhook: job_name=test4, run_id=204354054874177
🔄 Attempting to fetch detailed error from Databricks Jobs API
✅ Successfully fetched run details from Databricks API
✅ Extracted detailed error from API: [Task: ...] ...
📤 FINAL error_message being sent to RCA AI:
   API fetch attempted: True
   API fetch success: True
   Error message length: 245 chars
================================================================================
```

❌ **Missing credentials:**
```
❌ CRITICAL: Databricks API credentials NOT configured!
❌ Cannot fetch detailed error messages from Databricks Jobs API
```

⚠️ **API fetch failed:**
```
❌ Databricks API fetch returned None
❌ Falling back to webhook error_message (may be generic)
```

### Metrics to Track

- **API fetch success rate**: Should be > 95%
- **Error message length**: Should be > 100 chars (not generic)
- **Duplicate prevention**: Count of "DUPLICATE DETECTED" logs
- **RCA specificity**: Check for specific error types vs "UnknownError"

---

## 🚀 Deployment

### Local Development

```bash
cd genai_rca_assistant
pip install -r requirements.txt
source .env
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY genai_rca_assistant/ .
COPY .env.example .env

RUN pip install -r requirements.txt

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t rca-system .
docker run -p 8000:8000 --env-file genai_rca_assistant/.env rca-system
```

### Azure App Service

```bash
# Deploy code
az webapp up \
  --name your-rca-app \
  --resource-group rg_techdemo_2025_Q4 \
  --runtime "PYTHON:3.11"

# Configure environment variables
az webapp config appsettings set \
  --name your-rca-app \
  --resource-group rg_techdemo_2025_Q4 \
  --settings \
    DATABRICKS_HOST="https://adb-123...azuredatabricks.net" \
    DATABRICKS_TOKEN="dapi..." \
    GEMINI_API_KEY="..." \
    RCA_API_KEY="..."
```

---

## 🤝 Contributing

### Code Enhancements Made

1. **main.py** (lines 1090-1212):
   - Complete raw webhook payload logging
   - Support for Databricks Event Delivery format
   - Enhanced error extraction from nested objects
   - Detailed API fetch status tracking

2. **databricks_api_utils.py** (lines 53-67, 155-246):
   - Prominent credential error messages
   - Step-by-step error extraction logging
   - Priority-based error field checking

3. **Documentation**:
   - QUICKSTART.md - Fast setup guide
   - DATABRICKS_SETUP.md - Complete reference
   - .env.example - All configuration options

4. **Tooling**:
   - setup_databricks.sh - Interactive setup
   - test_databricks_connection.sh - Verification

---

## 📄 License

Enterprise Internal Use

---

## 📞 Support

### Getting Help

1. **Quick issues**: Check [QUICKSTART.md](QUICKSTART.md)
2. **Setup problems**: See [DATABRICKS_SETUP.md](DATABRICKS_SETUP.md)
3. **Configuration**: Review [.env.example](.env.example)
4. **Testing**: Run `./test_databricks_connection.sh`

### Common Commands

```bash
# Setup from scratch
./setup_databricks.sh

# Test connection
./test_databricks_connection.sh <run_id>

# Check configuration
cat genai_rca_assistant/.env | grep DATABRICKS

# View logs
tail -f app.log | grep -A 10 "DATABRICKS WEBHOOK"

# Test API manually
cd genai_rca_assistant
python databricks_api_utils.py 204354054874177
```

---

## ✅ Success Criteria

Your system is working correctly when:

- [ ] `./test_databricks_connection.sh` shows ✅ TEST PASSED
- [ ] Application logs show "✅ Successfully fetched run details from Databricks API"
- [ ] Error message length > 100 characters (not "Job failed")
- [ ] RCA alerts contain specific error details (table names, line numbers, etc.)
- [ ] No duplicate tickets for same run_id
- [ ] Resolution steps are actionable (not just "check logs")

---

**Version**: 2.0 (Enhanced Databricks Integration)
**Last Updated**: 2025-11-23
**Status**: Production Ready ✅
# autorem-adf

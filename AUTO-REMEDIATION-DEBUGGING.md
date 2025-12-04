# Auto-Remediation Debugging Guide

## Step 1: Check Environment Variable

Run this command where your app is running:

```bash
# Check if AUTO_REMEDIATION_ENABLED is set
echo $AUTO_REMEDIATION_ENABLED

# Or check in Python
python3 -c "import os; from dotenv import load_dotenv; load_dotenv(); print('AUTO_REMEDIATION_ENABLED:', os.getenv('AUTO_REMEDIATION_ENABLED'))"
```

**Expected output:** `true` or `1`

If it shows `false` or `None`, update your `.env`:

```bash
# In .env file
AUTO_REMEDIATION_ENABLED=true
```

Then **restart your FastAPI app**:
```bash
# Kill existing process
pkill -f "uvicorn main:app"

# Restart
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Step 2: Add Debugging Logs

Add these debug logs to your `main.py` at line 2126 (in the auto-remediation section):

```python
# Auto-Remediation (if enabled)
logger.info("=" * 80)
logger.info("[AUTO-REM-DEBUG] Checking auto-remediation eligibility")
logger.info(f"[AUTO-REM-DEBUG] AUTO_REMEDIATION_ENABLED = {AUTO_REMEDIATION_ENABLED}")
logger.info(f"[AUTO-REM-DEBUG] auto_heal_possible = {rca.get('auto_heal_possible')}")
logger.info(f"[AUTO-REM-DEBUG] error_type = {rca.get('error_type')}")
logger.info(f"[AUTO-REM-DEBUG] error_type in REMEDIABLE_ERRORS = {rca.get('error_type') in REMEDIABLE_ERRORS}")
logger.info(f"[AUTO-REM-DEBUG] REMEDIABLE_ERRORS keys = {list(REMEDIABLE_ERRORS.keys())}")
logger.info("=" * 80)

if AUTO_REMEDIATION_ENABLED and rca.get("auto_heal_possible"):
    error_type = rca.get("error_type")
    if error_type in REMEDIABLE_ERRORS:
        logger.info(f"[AUTO-REM] ✅ Eligible for auto-remediation: {error_type} for ticket {tid}")
        # ... rest of the code
    else:
        logger.warning(f"[AUTO-REM] ❌ Error type '{error_type}' NOT in REMEDIABLE_ERRORS")
else:
    if not AUTO_REMEDIATION_ENABLED:
        logger.warning(f"[AUTO-REM] ❌ AUTO_REMEDIATION_ENABLED is False")
    if not rca.get("auto_heal_possible"):
        logger.warning(f"[AUTO-REM] ❌ AI determined auto_heal_possible=false for error: {rca.get('error_type')}")
```

---

## Step 3: Check Your RCA Prompts

The issue might be in your RCA prompt (lines 622-664 for Gemini, 734-778 for Ollama).

**Current prompt has this logic:**

```
FOR ADF ERRORS:
✅ auto_heal_possible=true:
  - GatewayTimeout (network timeout, retry helps)
  - HttpConnectionFailed (transient connection issues)
  - ThrottlingError (rate limiting, retry with backoff)
  - InternalServerError (Azure transient errors)

❌ auto_heal_possible=false:
  - UserErrorSourceBlobNotExists (missing data, needs manual check)
  - UserErrorInvalidDataType (data quality issue, needs investigation)
```

**Problem:** Your test is calling an **invalid endpoint**, which the AI might classify as a **configuration error**, not a transient network error!

**Solution:** Update the prompt to be more explicit about what's auto-remediable:

Replace lines 622-664 with:

```python
prompt = f"""
You are an expert AIOps Root Cause Analysis assistant for {service_name}.

AUTO-HEAL DECISION LOGIC - Set auto_heal_possible=true ONLY if error matches these criteria:

FOR ADF ERRORS:
✅ auto_heal_possible=true (ALWAYS set true for these):
  - GatewayTimeout (network timeout → retry helps)
  - HttpConnectionFailed (transient connection issues → retry helps)
  - ThrottlingError (rate limiting → retry with backoff)
  - InternalServerError (Azure transient errors → retry helps)
  - ServiceUnavailable (temporary service issues → retry helps)
  - Timeout errors (any timeout → retry helps)
  - HTTP 502, 503, 504 errors (transient → retry helps)

❌ auto_heal_possible=false (NEVER auto-remediate these):
  - UserErrorSourceBlobNotExists (missing data file → needs manual fix)
  - UserErrorInvalidDataType (data schema issue → needs code fix)
  - UserErrorSqlOperationFailed (query error → needs code fix)
  - AuthenticationError (credentials issue → needs manual fix)
  - PermissionDenied (access issue → needs manual fix)
  - InvalidConfiguration (config error → needs manual fix)

CRITICAL RULE:
- If error message contains "timeout", "connection failed", "502", "503", "504", "throttl" → ALWAYS set auto_heal_possible=true
- If error involves missing files, wrong data types, permissions, authentication → ALWAYS set auto_heal_possible=false

Your `error_type` MUST be a machine-readable code. Choose from this list:
[UserErrorSourceBlobNotExists, UserErrorColumnNameInvalid, GatewayTimeout,
HttpConnectionFailed, InternalServerError, UserErrorInvalidDataType, UserErrorSqlOperationFailed,
AuthenticationError, ThrottlingError, UnknownError]

IMPORTANT: For timeout and connection errors, you MUST return:
{{
  "error_type": "GatewayTimeout",  // or "HttpConnectionFailed"
  "auto_heal_possible": true       // MUST be true for network errors
}}

Error Message:
\"\"\"{service_prefixed_desc}\"\"\"

Return ONLY valid JSON (no markdown, no thinking):
{{
  "root_cause": "...",
  "error_type": "GatewayTimeout",
  "affected_entity": "...",
  "severity": "High",
  "priority": "P2",
  "confidence": "High",
  "recommendations": ["Retry pipeline", "Check network connectivity"],
  "auto_heal_possible": true
}}
"""
```

---

## Step 4: Test With a Real Timeout Error

Your current test "CallInvalidEndpoint" might be classified as a **configuration error** (not auto-remediable).

**Option A: Trigger a Real GatewayTimeout**

Create a new ADF pipeline that calls an endpoint with a **very short timeout**:

1. **Web Activity Settings:**
   - URL: `https://httpstat.us/200?sleep=30000` (delays 30 seconds)
   - Method: GET
   - Timeout: `00:00:05` (5 seconds) ← Force timeout

2. **Run the pipeline** → Should fail with `GatewayTimeout`

**Option B: Manually Set Error Type**

If you want to test with your current "CallInvalidEndpoint" test, temporarily modify the RCA prompt to force `auto_heal_possible=true`:

```python
# TEMPORARY DEBUG OVERRIDE (around line 660)
ai = call_ai_for_rca(desc, source_type)
if ai:
    # FORCE auto-remediation for testing
    ai["auto_heal_possible"] = True
    ai["error_type"] = "GatewayTimeout"
    logger.warning("🔧 DEBUG MODE: Forcing auto_heal_possible=true for testing")

    ai.setdefault("priority", derive_priority(ai.get("severity")))
    return ai
```

---

## Step 5: Check Playbook URL Configuration

Even if auto-remediation is triggered, it will fail if the Logic App webhook URL is not configured.

Check your `.env`:

```bash
# Must have valid Logic App webhook URL
PLAYBOOK_RETRY_PIPELINE=https://prod-XX.eastus.logic.azure.com/workflows/.../triggers/manual/paths/invoke?...&sig=...
```

**Verify it's set:**
```bash
echo $PLAYBOOK_RETRY_PIPELINE
```

If empty, auto-remediation will fail at line 1460:
```python
playbook_url = remediation_config["playbook_url"]
if not playbook_url:
    logger.error(f"[AUTO-REM] No playbook URL configured for {error_type}")
    return {"success": False, "message": "Playbook URL not configured"}
```

---

## Step 6: Check Database for Existing Remediation

Your code prevents duplicate remediation attempts. Check if there's already an active remediation:

```sql
-- Run this in your SQLite database
SELECT id, pipeline, error_type, status, remediation_status, remediation_attempts
FROM tickets
WHERE pipeline = 'Test_Timeout_Error'
ORDER BY timestamp DESC
LIMIT 5;
```

If `remediation_status = 'in_progress'` or `'max_retries_exceeded'`, it won't trigger a new one.

**Solution:** Delete test tickets:
```sql
DELETE FROM tickets WHERE pipeline LIKE '%Test%';
DELETE FROM remediation_attempts WHERE ticket_id LIKE 'ADF-%Test%';
```

---

## 🎯 Most Likely Issues (In Order)

1. **AUTO_REMEDIATION_ENABLED=false** (90% chance)
   - Fix: Set to `true` in `.env` and restart app

2. **AI returning auto_heal_possible=false** (5% chance)
   - Fix: Update RCA prompt to be more explicit about timeout errors
   - Or add debug override to force it to true

3. **Missing PLAYBOOK_RETRY_PIPELINE URL** (3% chance)
   - Fix: Configure Logic App webhook URL in `.env`

4. **Duplicate remediation blocked** (2% chance)
   - Fix: Delete test tickets from database

---

## 📊 Quick Test Command

Run your pipeline and immediately check logs:

```bash
# In one terminal - watch logs
tail -f /path/to/your/app/logs/uvicorn.log | grep -E "AUTO-REM|auto_heal"

# Or if running in Docker
docker logs -f your-container-name | grep -E "AUTO-REM|auto_heal"
```

**Expected output when working:**
```
[AUTO-REM-DEBUG] AUTO_REMEDIATION_ENABLED = True
[AUTO-REM-DEBUG] auto_heal_possible = True
[AUTO-REM-DEBUG] error_type = GatewayTimeout
[AUTO-REM-DEBUG] error_type in REMEDIABLE_ERRORS = True
[AUTO-REM] ✅ Eligible for auto-remediation: GatewayTimeout for ticket ADF-20251204T...
[AUTO-REM] Triggering auto-remediation for ADF-20251204T..., error: GatewayTimeout, attempt: 1
```

**If you see:**
```
[AUTO-REM] ❌ AUTO_REMEDIATION_ENABLED is False
```
→ Fix: Set `AUTO_REMEDIATION_ENABLED=true` in `.env`

**If you see:**
```
[AUTO-REM] ❌ AI determined auto_heal_possible=false
```
→ Fix: Update RCA prompt or use debug override

---

## 🚀 Final Checklist

- [ ] `AUTO_REMEDIATION_ENABLED=true` in `.env`
- [ ] App restarted after changing `.env`
- [ ] Logic App webhook URL configured (`PLAYBOOK_RETRY_PIPELINE=https://...`)
- [ ] No existing `in_progress` remediation for same pipeline
- [ ] RCA prompt explicitly sets `auto_heal_possible=true` for timeout errors
- [ ] Database has no duplicate run_id entries
- [ ] Logs show `[AUTO-REM] ✅ Eligible for auto-remediation`

---

## 💡 Immediate Fix (Test Mode)

**Add this at line 2126 to FORCE auto-remediation for ALL tickets (TESTING ONLY):**

```python
# 🔧 TESTING OVERRIDE - FORCE AUTO-REMEDIATION
logger.warning("🚨 TESTING MODE: Forcing auto-remediation for ALL tickets")
rca["auto_heal_possible"] = True
if rca.get("error_type") not in REMEDIABLE_ERRORS:
    rca["error_type"] = "GatewayTimeout"  # Force to a remediable error
# END TESTING OVERRIDE

# Auto-Remediation (if enabled)
if AUTO_REMEDIATION_ENABLED and rca.get("auto_heal_possible"):
    ...
```

**Don't forget to remove this after testing!**

---

Let me know what you find in the logs and I'll help you debug further! 🔍

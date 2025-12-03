# Complete Auto-Remediation Flow Implementation Plan

## Overview
This document provides a step-by-step approach to implement a complete auto-remediation system that:
1. Detects errors and determines if auto-remediation is possible
2. Triggers Azure Logic App to re-run pipelines
3. Monitors re-run status
4. Auto-closes tickets on successful remediation
5. Updates dashboard and sends Slack notifications

---

## Architecture Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     ADF PIPELINE FAILURE DETECTED                        │
└──────────────────────────────┬──────────────────────────────────────────┘
                                │
                                ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 1: AI-Powered RCA & Auto-Remediation Eligibility Check           │
│  ├─ Generate RCA via Gemini AI                                          │
│  ├─ Check: AUTO_REMEDIATION_ENABLED=true                                │
│  ├─ Check: auto_heal_possible=true                                      │
│  └─ Check: Error type is in REMEDIABLE_ERRORS list                      │
└──────────────────────────────┬──────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
              Yes (Auto-Remediate)    No (Manual Intervention)
                    │                       │
                    ↓                       ↓
┌─────────────────────────────────┐  ┌──────────────────────────┐
│ STEP 2: Trigger Logic App       │  │ Create Ticket            │
│ POST to Azure Logic App          │  │ Send Slack Alert         │
│ Payload:                         │  │ Wait for Manual Ack      │
│   - pipeline_name                │  └──────────────────────────┘
│   - ticket_id                    │
│   - error_type                   │
│   - retry_attempt                │
└──────────┬──────────────────────┘
           │
           ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 3: Logic App Creates Pipeline Re-Run                               │
│ Returns: run_id, status                                                  │
└──────────────────────────────┬──────────────────────────────────────────┘
           │
           ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 4: Store Remediation Attempt in Database                           │
│ New table: remediation_attempts                                          │
│   - ticket_id                                                            │
│   - original_run_id                                                      │
│   - remediation_run_id (new run)                                         │
│   - attempt_number (1, 2, 3...)                                          │
│   - status (in_progress, succeeded, failed)                              │
│   - started_at, completed_at                                             │
└──────────────────────────────┬──────────────────────────────────────────┘
           │
           ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 5: Update Ticket Status                                            │
│ ticket.status = "auto_remediation_in_progress"                           │
│ ticket.remediation_run_id = new_run_id                                   │
└──────────────────────────────┬──────────────────────────────────────────┘
           │
           ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 6: Send Slack Notification - Remediation Started                   │
│ "🤖 Auto-remediation triggered for pipeline XYZ"                        │
│ "Attempt 1/3 - Re-running pipeline..."                                  │
└──────────────────────────────┬──────────────────────────────────────────┘
           │
           ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 7: Start Monitoring Service (Background Task)                      │
│ Poll ADF API every 30 seconds:                                           │
│   GET /pipelines/{pipeline}/pipelineruns/{run_id}                        │
│ Check status: InProgress, Succeeded, Failed                              │
└──────────────────────────────┬──────────────────────────────────────────┘
           │
    ┌──────┴──────┐
    │             │
Succeeded      Failed
    │             │
    ↓             ↓
┌─────────────────────────┐  ┌──────────────────────────────────────────┐
│ STEP 8A: SUCCESS PATH   │  │ STEP 8B: FAILURE PATH                    │
│                         │  │                                          │
│ 1. Update Database:     │  │ 1. Increment retry attempt               │
│    - ticket.status =    │  │ 2. Check if retry_attempt < max_retries  │
│      "auto_remediated"  │  │                                          │
│    - ticket.ack_ts =    │  │    If Yes:                               │
│      now()              │  │      → Go back to STEP 2 (retry)         │
│    - ticket.ack_user =  │  │                                          │
│      "AI_AUTO_HEAL"     │  │    If No (max retries exceeded):         │
│                         │  │      → ticket.status =                   │
│ 2. Close Jira Ticket:   │  │        "auto_remediation_failed"         │
│    - Add comment with   │  │      → Slack: "❌ Auto-remediation       │
│      remediation details│  │        failed after 3 attempts"          │
│    - Transition to      │  │      → Update Jira: Add failure comment  │
│      "Done" status      │  │      → Escalate to manual intervention   │
│                         │  │                                          │
│ 3. Update Slack:        │  └──────────────────────────────────────────┘
│    - Edit original msg  │
│    - Add: "✅ Auto-     │
│      remediated         │
│      successfully!"     │
│    - Show new run_id    │
│                         │
│ 4. Update Dashboard:    │
│    - Broadcast WebSocket│
│    - Move ticket to     │
│      "Closed" tab       │
│    - Show auto-heal     │
│      badge              │
│                         │
│ 5. Log Audit Trail:     │
│    - Action: auto_      │
│      remediation_success│
│    - Time taken (MTTR)  │
│    - New run details    │
└─────────────────────────┘
```

---

## Step-by-Step Implementation

### **STEP 1: Enhance Database Schema**

Add new fields to track auto-remediation:

```sql
-- Add to tickets table
ALTER TABLE tickets ADD COLUMN remediation_status TEXT DEFAULT NULL;
  -- Values: null, in_progress, succeeded, failed, max_retries_exceeded

ALTER TABLE tickets ADD COLUMN remediation_run_id TEXT DEFAULT NULL;
  -- Stores the new pipeline run_id after remediation trigger

ALTER TABLE tickets ADD COLUMN remediation_attempts INTEGER DEFAULT 0;
  -- Counter for retry attempts

ALTER TABLE tickets ADD COLUMN remediation_last_attempt_at TEXT DEFAULT NULL;
  -- Timestamp of last remediation attempt

-- Create new table: remediation_attempts
CREATE TABLE IF NOT EXISTS remediation_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    original_run_id TEXT NOT NULL,
    remediation_run_id TEXT,
    attempt_number INTEGER NOT NULL,
    status TEXT NOT NULL,  -- in_progress, succeeded, failed
    error_type TEXT,
    remediation_action TEXT,  -- retry_pipeline, restart_cluster, etc.
    logic_app_response TEXT,  -- JSON response from Logic App
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_seconds INTEGER,
    failure_reason TEXT,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
);
```

**File to modify:** `genai_rca_assistant/main.py` (lines 110-286)

---

### **STEP 2: Create Remediation Configuration**

Define remediable error types and their strategies:

```python
# Add to main.py

REMEDIABLE_ERRORS = {
    # Transient/Network Errors - Retry Strategy
    "GatewayTimeout": {
        "action": "retry_pipeline",
        "max_retries": 3,
        "backoff_seconds": [30, 60, 120],
        "playbook_url": os.getenv("PLAYBOOK_RETRY_PIPELINE")
    },
    "HttpConnectionFailed": {
        "action": "retry_pipeline",
        "max_retries": 3,
        "backoff_seconds": [30, 60, 120],
        "playbook_url": os.getenv("PLAYBOOK_RETRY_PIPELINE")
    },
    "ThrottlingError": {
        "action": "retry_pipeline",
        "max_retries": 5,
        "backoff_seconds": [30, 60, 120, 300, 600],
        "playbook_url": os.getenv("PLAYBOOK_RETRY_PIPELINE")
    },

    # Databricks Cluster Errors
    "DatabricksClusterStartFailure": {
        "action": "restart_cluster",
        "max_retries": 2,
        "backoff_seconds": [60, 180],
        "playbook_url": os.getenv("PLAYBOOK_RESTART_CLUSTER")
    },
    "ClusterMemoryExhausted": {
        "action": "scale_up_cluster",
        "max_retries": 1,
        "backoff_seconds": [120],
        "playbook_url": os.getenv("PLAYBOOK_SCALE_CLUSTER")
    },

    # Databricks Library Errors
    "LibraryInstallationFailed": {
        "action": "reinstall_libraries",
        "max_retries": 2,
        "backoff_seconds": [60, 180],
        "playbook_url": os.getenv("PLAYBOOK_REINSTALL_LIBRARIES")
    },

    # Databricks Job Errors
    "DatabricksJobExecutionError": {
        "action": "retry_job",
        "max_retries": 3,
        "backoff_seconds": [30, 60, 120],
        "playbook_url": os.getenv("PLAYBOOK_RETRY_JOB")
    },

    # Conditional Remediation
    "UserErrorSourceBlobNotExists": {
        "action": "check_upstream",
        "max_retries": 2,
        "backoff_seconds": [300, 600],  # Wait 5 min, then 10 min
        "playbook_url": os.getenv("PLAYBOOK_RERUN_UPSTREAM")
    },
}

# Add to .env
AUTO_REMEDIATION_ENABLED=true
AUTO_REMEDIATION_MAX_RETRIES=3
PLAYBOOK_RETRY_PIPELINE=https://prod-12.northcentralus.logic.azure.com:443/workflows/.../triggers/manual/paths/invoke?...
PLAYBOOK_RESTART_CLUSTER=https://prod-12.northcentralus.logic.azure.com:443/workflows/.../triggers/manual/paths/invoke?...
PLAYBOOK_RETRY_JOB=https://prod-12.northcentralus.logic.azure.com:443/workflows/.../triggers/manual/paths/invoke?...
PLAYBOOK_RERUN_UPSTREAM=https://prod-12.northcentralus.logic.azure.com:443/workflows/.../triggers/manual/paths/invoke?...
```

---

### **STEP 3: Implement Auto-Remediation Logic**

Replace placeholder code in `main.py` (lines 1054-1058) with:

```python
async def trigger_auto_remediation(ticket_id: str, pipeline_name: str, error_type: str,
                                     original_run_id: str, attempt_number: int = 1):
    """
    Triggers auto-remediation via Azure Logic App

    Returns:
        dict: {"success": bool, "remediation_run_id": str, "message": str}
    """

    # Check if error is remediable
    if error_type not in REMEDIABLE_ERRORS:
        logger.info(f"Error type {error_type} is not auto-remediable")
        return {"success": False, "message": "Error type not remediable"}

    remediation_config = REMEDIABLE_ERRORS[error_type]

    # Check retry limits
    if attempt_number > remediation_config["max_retries"]:
        logger.warning(f"Max retries ({remediation_config['max_retries']}) exceeded for {ticket_id}")
        return {"success": False, "message": "Max retries exceeded"}

    # Get playbook URL
    playbook_url = remediation_config["playbook_url"]
    if not playbook_url:
        logger.error(f"No playbook URL configured for {error_type}")
        return {"success": False, "message": "Playbook URL not configured"}

    # Calculate backoff delay
    if attempt_number > 1:
        backoff_index = attempt_number - 2  # 0-indexed
        if backoff_index < len(remediation_config["backoff_seconds"]):
            delay = remediation_config["backoff_seconds"][backoff_index]
            logger.info(f"Waiting {delay}s before retry attempt {attempt_number}")
            await asyncio.sleep(delay)

    # Prepare payload for Logic App
    payload = {
        "pipeline_name": pipeline_name,
        "ticket_id": ticket_id,
        "error_type": error_type,
        "original_run_id": original_run_id,
        "retry_attempt": attempt_number,
        "max_retries": remediation_config["max_retries"],
        "remediation_action": remediation_config["action"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    try:
        # Call Logic App with retry logic
        response = await _http_post_with_retries(
            playbook_url,
            payload,
            max_retries=3,
            timeout=30
        )

        if response and response.get("status") == "success":
            remediation_run_id = response.get("run_id")

            # Store remediation attempt
            c.execute('''INSERT INTO remediation_attempts
                        (ticket_id, original_run_id, remediation_run_id, attempt_number,
                         status, error_type, remediation_action, logic_app_response, started_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (ticket_id, original_run_id, remediation_run_id, attempt_number,
                      "in_progress", error_type, remediation_config["action"],
                      json.dumps(response), datetime.now(timezone.utc).isoformat()))

            # Update ticket
            c.execute('''UPDATE tickets
                        SET remediation_status = ?,
                            remediation_run_id = ?,
                            remediation_attempts = ?,
                            remediation_last_attempt_at = ?
                        WHERE id = ?''',
                     ("in_progress", remediation_run_id, attempt_number,
                      datetime.now(timezone.utc).isoformat(), ticket_id))
            conn.commit()

            # Log audit trail
            c.execute('''INSERT INTO audit_trail
                        (timestamp, ticket_id, pipeline, run_id, action, user_name, details)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (datetime.now(timezone.utc).isoformat(), ticket_id, pipeline_name,
                      remediation_run_id, "auto_remediation_triggered", "AI_AUTO_HEAL",
                      json.dumps({"attempt": attempt_number, "action": remediation_config["action"]})))
            conn.commit()

            logger.info(f"Auto-remediation triggered successfully for {ticket_id}, run_id: {remediation_run_id}")

            # Send Slack notification
            await send_slack_remediation_started(ticket_id, pipeline_name, attempt_number,
                                                   remediation_config["max_retries"])

            # Broadcast to dashboard
            await manager.broadcast({
                "event": "remediation_started",
                "ticket_id": ticket_id,
                "attempt": attempt_number,
                "remediation_run_id": remediation_run_id
            })

            # Start monitoring in background
            asyncio.create_task(monitor_remediation_run(
                ticket_id, pipeline_name, remediation_run_id,
                original_run_id, error_type, attempt_number
            ))

            return {"success": True, "remediation_run_id": remediation_run_id}

        else:
            logger.error(f"Logic App returned error: {response}")
            return {"success": False, "message": f"Logic App error: {response}"}

    except Exception as e:
        logger.exception(f"Error triggering auto-remediation: {e}")
        return {"success": False, "message": str(e)}


async def _http_post_with_retries(url: str, payload: dict, max_retries: int = 3, timeout: int = 30):
    """HTTP POST with exponential backoff"""
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt == max_retries:
                logger.error(f"HTTP POST failed after {max_retries} attempts: {e}")
                return None
            wait_time = 2 ** attempt  # 2, 4, 8 seconds
            logger.warning(f"HTTP POST attempt {attempt} failed, retrying in {wait_time}s: {e}")
            await asyncio.sleep(wait_time)
    return None
```

---

### **STEP 4: Create Pipeline Monitoring Service**

Add background task to monitor re-run status:

```python
async def monitor_remediation_run(ticket_id: str, pipeline_name: str,
                                    remediation_run_id: str, original_run_id: str,
                                    error_type: str, attempt_number: int):
    """
    Background task to monitor ADF pipeline re-run status
    Polls every 30 seconds until completion
    """

    logger.info(f"Starting monitoring for remediation run {remediation_run_id}")

    max_poll_duration = 3600  # 1 hour max
    poll_interval = 30  # 30 seconds
    elapsed = 0

    adf_subscription = os.getenv("AZURE_SUBSCRIPTION_ID")
    adf_resource_group = os.getenv("AZURE_RESOURCE_GROUP")
    adf_factory_name = os.getenv("AZURE_DATA_FACTORY_NAME")

    # ADF REST API endpoint
    api_url = (f"https://management.azure.com/subscriptions/{adf_subscription}"
               f"/resourceGroups/{adf_resource_group}/providers/Microsoft.DataFactory"
               f"/factories/{adf_factory_name}/pipelineruns/{remediation_run_id}"
               f"?api-version=2018-06-01")

    # Get Azure access token (requires managed identity or service principal)
    headers = {
        "Authorization": f"Bearer {await get_azure_access_token()}",
        "Content-Type": "application/json"
    }

    while elapsed < max_poll_duration:
        try:
            response = requests.get(api_url, headers=headers, timeout=10)

            if response.status_code == 200:
                run_data = response.json()
                status = run_data.get("status")  # InProgress, Succeeded, Failed, Cancelled

                logger.info(f"Remediation run {remediation_run_id} status: {status}")

                if status == "Succeeded":
                    await handle_remediation_success(
                        ticket_id, pipeline_name, remediation_run_id,
                        original_run_id, attempt_number
                    )
                    return

                elif status in ["Failed", "Cancelled"]:
                    await handle_remediation_failure(
                        ticket_id, pipeline_name, remediation_run_id,
                        original_run_id, error_type, attempt_number,
                        run_data
                    )
                    return

                elif status == "InProgress":
                    # Still running, continue polling
                    pass

            else:
                logger.error(f"Failed to get pipeline status: {response.status_code}")

        except Exception as e:
            logger.exception(f"Error monitoring remediation run: {e}")

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    # Timeout reached
    logger.warning(f"Monitoring timeout reached for {remediation_run_id}")
    await handle_remediation_timeout(ticket_id, remediation_run_id)


async def get_azure_access_token():
    """
    Get Azure AD access token for ADF API calls
    Uses Managed Identity or Service Principal
    """
    # For Managed Identity (recommended for Azure App Service)
    try:
        msi_endpoint = os.getenv("MSI_ENDPOINT")
        msi_secret = os.getenv("MSI_SECRET")

        if msi_endpoint and msi_secret:
            # Managed Identity
            response = requests.get(
                msi_endpoint,
                params={"resource": "https://management.azure.com/", "api-version": "2019-08-01"},
                headers={"X-IDENTITY-HEADER": msi_secret},
                timeout=5
            )
            return response.json()["access_token"]
        else:
            # Service Principal (fallback)
            tenant_id = os.getenv("AZURE_TENANT_ID")
            client_id = os.getenv("AZURE_CLIENT_ID")
            client_secret = os.getenv("AZURE_CLIENT_SECRET")

            token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/token"
            data = {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "resource": "https://management.azure.com/"
            }
            response = requests.post(token_url, data=data, timeout=5)
            return response.json()["access_token"]

    except Exception as e:
        logger.error(f"Failed to get Azure access token: {e}")
        return None
```

---

### **STEP 5: Handle Remediation Success**

```python
async def handle_remediation_success(ticket_id: str, pipeline_name: str,
                                      remediation_run_id: str, original_run_id: str,
                                      attempt_number: int):
    """
    Called when remediation pipeline run succeeds
    - Closes ticket
    - Updates Jira
    - Sends Slack success notification
    - Updates dashboard
    """

    logger.info(f"✅ Auto-remediation succeeded for {ticket_id}")

    now = datetime.now(timezone.utc).isoformat()

    # Update remediation attempt record
    c.execute('''UPDATE remediation_attempts
                SET status = ?, completed_at = ?,
                    duration_seconds = (julianday(?) - julianday(started_at)) * 86400
                WHERE ticket_id = ? AND remediation_run_id = ?''',
             ("succeeded", now, now, ticket_id, remediation_run_id))

    # Update ticket status to auto-remediated
    c.execute('''UPDATE tickets
                SET status = ?,
                    remediation_status = ?,
                    ack_user = ?,
                    ack_empid = ?,
                    ack_ts = ?,
                    ack_seconds = (julianday(?) - julianday(timestamp)) * 86400,
                    sla_status = CASE
                        WHEN (julianday(?) - julianday(timestamp)) * 86400 <= sla_seconds
                        THEN 'Met'
                        ELSE 'Breached'
                    END
                WHERE id = ?''',
             ("acknowledged", "succeeded", "AI_AUTO_HEAL", "AUTO_REM_001",
              now, now, now, ticket_id))
    conn.commit()

    # Get ticket details for notifications
    c.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    ticket = dict(c.fetchone())

    # Calculate MTTR
    mttr_seconds = ticket['ack_seconds']
    mttr_minutes = mttr_seconds / 60 if mttr_seconds else 0

    # Log audit trail
    c.execute('''INSERT INTO audit_trail
                (timestamp, ticket_id, pipeline, run_id, action, user_name,
                 user_empid, time_taken_seconds, mttr_minutes, sla_status,
                 rca_summary, finops_team, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
             (now, ticket_id, pipeline_name, remediation_run_id,
              "auto_remediation_success", "AI_AUTO_HEAL", "AUTO_REM_001",
              int(mttr_seconds), mttr_minutes, ticket['sla_status'],
              ticket['rca_result'][:500], ticket['finops_team'],
              json.dumps({
                  "attempt_number": attempt_number,
                  "original_run_id": original_run_id,
                  "remediation_run_id": remediation_run_id
              })))
    conn.commit()

    # Close Jira ticket (if enabled)
    if ticket.get('itsm_ticket_id'):
        await close_jira_ticket_auto(
            ticket['itsm_ticket_id'],
            ticket_id,
            remediation_run_id,
            attempt_number
        )

    # Update Slack message
    await update_slack_message_on_remediation_success(
        ticket['slack_channel'],
        ticket['slack_ts'],
        ticket_id,
        pipeline_name,
        remediation_run_id,
        attempt_number,
        mttr_minutes
    )

    # Broadcast to dashboard
    await manager.broadcast({
        "event": "status_update",
        "ticket_id": ticket_id,
        "new_status": "acknowledged",
        "user": "AI_AUTO_HEAL",
        "remediation_success": True
    })

    logger.info(f"Auto-remediation success handling completed for {ticket_id}")


async def close_jira_ticket_auto(jira_ticket_id: str, ticket_id: str,
                                   remediation_run_id: str, attempt_number: int):
    """Automatically closes Jira ticket with remediation details"""

    jira_domain = os.getenv("JIRA_DOMAIN")
    jira_email = os.getenv("JIRA_USER_EMAIL")
    jira_token = os.getenv("JIRA_API_TOKEN")

    if not all([jira_domain, jira_email, jira_token]):
        logger.warning("Jira not configured, skipping auto-close")
        return

    # Add comment with remediation details
    comment_url = f"{jira_domain}/rest/api/3/issue/{jira_ticket_id}/comment"
    comment_payload = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [{
                "type": "panel",
                "attrs": {"panelType": "success"},
                "content": [{
                    "type": "paragraph",
                    "content": [{
                        "type": "text",
                        "text": f"✅ Auto-Remediation Successful",
                        "marks": [{"type": "strong"}]
                    }]
                }, {
                    "type": "paragraph",
                    "content": [{
                        "type": "text",
                        "text": f"Ticket ID: {ticket_id}\n"
                                f"Remediation Run ID: {remediation_run_id}\n"
                                f"Attempt Number: {attempt_number}\n"
                                f"Action: Pipeline re-run completed successfully\n"
                                f"Closed By: AI Auto-Heal System"
                    }]
                }]
            }]
        }
    }

    try:
        requests.post(
            comment_url,
            auth=(jira_email, jira_token),
            headers={"Content-Type": "application/json"},
            json=comment_payload,
            timeout=10
        )

        # Transition to Done (status ID typically 31 or 41)
        transition_url = f"{jira_domain}/rest/api/3/issue/{jira_ticket_id}/transitions"
        transition_payload = {
            "transition": {"id": "31"}  # May need to adjust based on your Jira workflow
        }
        requests.post(
            transition_url,
            auth=(jira_email, jira_token),
            headers={"Content-Type": "application/json"},
            json=transition_payload,
            timeout=10
        )

        logger.info(f"Jira ticket {jira_ticket_id} auto-closed")

    except Exception as e:
        logger.error(f"Failed to auto-close Jira ticket: {e}")


async def update_slack_message_on_remediation_success(channel: str, ts: str,
                                                        ticket_id: str, pipeline_name: str,
                                                        remediation_run_id: str, attempt_number: int,
                                                        mttr_minutes: float):
    """Updates original Slack alert message with success status"""

    slack_token = os.getenv("SLACK_BOT_TOKEN")
    if not slack_token:
        return

    client = WebClient(token=slack_token)

    # Get original message to preserve RCA
    try:
        result = client.conversations_history(channel=channel, latest=ts, limit=1, inclusive=True)
        original_blocks = result['messages'][0]['blocks'] if result['messages'] else []

        # Add success header
        success_blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "✅ Auto-Remediation Successful"
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Ticket ID:*\n{ticket_id}"},
                    {"type": "mrkdwn", "text": f"*Pipeline:*\n{pipeline_name}"},
                    {"type": "mrkdwn", "text": f"*New Run ID:*\n`{remediation_run_id}`"},
                    {"type": "mrkdwn", "text": f"*Attempt:*\n{attempt_number}"},
                    {"type": "mrkdwn", "text": f"*MTTR:*\n{mttr_minutes:.1f} minutes"},
                    {"type": "mrkdwn", "text": f"*Closed By:*\nAI Auto-Heal"}
                ]
            },
            {"type": "divider"}
        ]

        # Append original RCA blocks
        updated_blocks = success_blocks + original_blocks

        client.chat_update(
            channel=channel,
            ts=ts,
            blocks=updated_blocks,
            text=f"✅ Auto-remediation successful for {pipeline_name}"
        )

    except Exception as e:
        logger.error(f"Failed to update Slack message: {e}")
```

---

### **STEP 6: Handle Remediation Failure**

```python
async def handle_remediation_failure(ticket_id: str, pipeline_name: str,
                                      remediation_run_id: str, original_run_id: str,
                                      error_type: str, attempt_number: int,
                                      run_data: dict):
    """
    Called when remediation pipeline run fails
    - Checks if retries available
    - Triggers retry or escalates to manual
    """

    logger.warning(f"❌ Auto-remediation attempt {attempt_number} failed for {ticket_id}")

    now = datetime.now(timezone.utc).isoformat()

    # Extract failure reason
    failure_reason = run_data.get("message", "Unknown failure")

    # Update remediation attempt
    c.execute('''UPDATE remediation_attempts
                SET status = ?, completed_at = ?, failure_reason = ?,
                    duration_seconds = (julianday(?) - julianday(started_at)) * 86400
                WHERE ticket_id = ? AND remediation_run_id = ?''',
             ("failed", now, failure_reason, now, ticket_id, remediation_run_id))
    conn.commit()

    # Check if we can retry
    if error_type in REMEDIABLE_ERRORS:
        max_retries = REMEDIABLE_ERRORS[error_type]["max_retries"]

        if attempt_number < max_retries:
            # Retry available
            logger.info(f"Retrying auto-remediation (attempt {attempt_number + 1}/{max_retries})")

            # Send Slack notification about retry
            await send_slack_remediation_retry(ticket_id, pipeline_name,
                                                 attempt_number + 1, max_retries)

            # Trigger next attempt
            await trigger_auto_remediation(
                ticket_id, pipeline_name, error_type,
                original_run_id, attempt_number + 1
            )
        else:
            # Max retries exceeded
            await handle_max_retries_exceeded(ticket_id, pipeline_name,
                                                error_type, failure_reason)
    else:
        await handle_max_retries_exceeded(ticket_id, pipeline_name,
                                            error_type, failure_reason)


async def handle_max_retries_exceeded(ticket_id: str, pipeline_name: str,
                                        error_type: str, failure_reason: str):
    """
    Called when all retry attempts exhausted
    Escalates to manual intervention
    """

    logger.error(f"Max retries exceeded for {ticket_id}, escalating to manual intervention")

    now = datetime.now(timezone.utc).isoformat()

    # Update ticket
    c.execute('''UPDATE tickets
                SET remediation_status = ?,
                    status = ?
                WHERE id = ?''',
             ("max_retries_exceeded", "open", ticket_id))
    conn.commit()

    # Get ticket details
    c.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    ticket = dict(c.fetchone())

    # Log audit trail
    c.execute('''INSERT INTO audit_trail
                (timestamp, ticket_id, pipeline, action, user_name, details)
                VALUES (?, ?, ?, ?, ?, ?)''',
             (now, ticket_id, pipeline_name, "auto_remediation_max_retries_exceeded",
              "AI_AUTO_HEAL", json.dumps({
                  "error_type": error_type,
                  "failure_reason": failure_reason,
                  "attempts": ticket['remediation_attempts']
              })))
    conn.commit()

    # Update Jira with escalation
    if ticket.get('itsm_ticket_id'):
        await add_jira_escalation_comment(
            ticket['itsm_ticket_id'],
            ticket_id,
            error_type,
            ticket['remediation_attempts'],
            failure_reason
        )

    # Send Slack escalation alert
    await send_slack_escalation_alert(
        ticket['slack_channel'],
        ticket['slack_ts'],
        ticket_id,
        pipeline_name,
        error_type,
        ticket['remediation_attempts'],
        failure_reason
    )

    # Broadcast to dashboard
    await manager.broadcast({
        "event": "status_update",
        "ticket_id": ticket_id,
        "new_status": "open",
        "remediation_failed": True,
        "escalated": True
    })


async def send_slack_escalation_alert(channel: str, ts: str, ticket_id: str,
                                        pipeline_name: str, error_type: str,
                                        attempts: int, failure_reason: str):
    """Sends Slack alert when auto-remediation fails after max retries"""

    slack_token = os.getenv("SLACK_BOT_TOKEN")
    if not slack_token:
        return

    client = WebClient(token=slack_token)

    escalation_blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "⚠️ Auto-Remediation Failed - Manual Intervention Required"
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Ticket ID:*\n{ticket_id}"},
                {"type": "mrkdwn", "text": f"*Pipeline:*\n{pipeline_name}"},
                {"type": "mrkdwn", "text": f"*Error Type:*\n{error_type}"},
                {"type": "mrkdwn", "text": f"*Attempts:*\n{attempts}"},
                {"type": "mrkdwn", "text": f"*Last Failure:*\n{failure_reason[:200]}"}
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "🔴 *Action Required:* All automated remediation attempts have been exhausted. "
                        "Please investigate and resolve manually."
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View in Dashboard"},
                    "url": f"{os.getenv('DASHBOARD_URL')}?ticket={ticket_id}",
                    "style": "danger"
                }
            ]
        }
    ]

    try:
        # Post as thread reply to original alert
        client.chat_postMessage(
            channel=channel,
            thread_ts=ts,
            blocks=escalation_blocks,
            text=f"⚠️ Auto-remediation failed for {pipeline_name} after {attempts} attempts"
        )
    except Exception as e:
        logger.error(f"Failed to send Slack escalation alert: {e}")
```

---

### **STEP 7: Add Slack Remediation Notifications**

```python
async def send_slack_remediation_started(ticket_id: str, pipeline_name: str,
                                          attempt_number: int, max_retries: int):
    """Sends Slack notification when auto-remediation starts"""

    slack_token = os.getenv("SLACK_BOT_TOKEN")
    slack_channel = os.getenv("SLACK_ALERT_CHANNEL")

    if not all([slack_token, slack_channel]):
        return

    client = WebClient(token=slack_token)

    # Get ticket to thread on original message
    c.execute("SELECT slack_ts FROM tickets WHERE id = ?", (ticket_id,))
    row = c.fetchone()
    thread_ts = row['slack_ts'] if row else None

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🤖 *Auto-remediation initiated for `{pipeline_name}`*\n"
                        f"Ticket: {ticket_id}\n"
                        f"Attempt: {attempt_number}/{max_retries}\n"
                        f"Action: Re-running pipeline..."
            }
        }
    ]

    try:
        client.chat_postMessage(
            channel=slack_channel,
            thread_ts=thread_ts,  # Thread on original alert
            blocks=blocks,
            text=f"🤖 Auto-remediation attempt {attempt_number} for {pipeline_name}"
        )
    except Exception as e:
        logger.error(f"Failed to send Slack remediation start notification: {e}")


async def send_slack_remediation_retry(ticket_id: str, pipeline_name: str,
                                         attempt_number: int, max_retries: int):
    """Sends Slack notification for retry attempts"""

    slack_token = os.getenv("SLACK_BOT_TOKEN")
    slack_channel = os.getenv("SLACK_ALERT_CHANNEL")

    if not all([slack_token, slack_channel]):
        return

    client = WebClient(token=slack_token)

    c.execute("SELECT slack_ts FROM tickets WHERE id = ?", (ticket_id,))
    row = c.fetchone()
    thread_ts = row['slack_ts'] if row else None

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"🔄 *Retry attempt {attempt_number}/{max_retries}*\n"
                        f"Previous attempt failed, retrying auto-remediation for `{pipeline_name}`..."
            }
        }
    ]

    try:
        client.chat_postMessage(
            channel=slack_channel,
            thread_ts=thread_ts,
            blocks=blocks,
            text=f"🔄 Retry attempt {attempt_number} for {pipeline_name}"
        )
    except Exception as e:
        logger.error(f"Failed to send Slack retry notification: {e}")
```

---

### **STEP 8: Update Dashboard for Real-Time Remediation Status**

Add to `dashboard.html`:

```javascript
// Add remediation status badge
function getRemediationBadge(ticket) {
    if (ticket.remediation_status === 'in_progress') {
        return `<span class="badge bg-info">🤖 Auto-Healing</span>`;
    } else if (ticket.remediation_status === 'succeeded') {
        return `<span class="badge bg-success">✅ Auto-Remediated</span>`;
    } else if (ticket.remediation_status === 'max_retries_exceeded') {
        return `<span class="badge bg-danger">⚠️ Escalated</span>`;
    }
    return '';
}

// Listen for remediation events
socket.onmessage = function(event) {
    const data = JSON.parse(event.data);

    if (data.event === 'remediation_started') {
        showNotification(`🤖 Auto-remediation started for ${data.ticket_id}`, 'info');
        updateTicketBadge(data.ticket_id, 'auto-healing');
    }
    else if (data.event === 'status_update' && data.remediation_success) {
        showNotification(`✅ Auto-remediation succeeded for ${data.ticket_id}`, 'success');
        loadTickets();  // Refresh ticket list
    }
    else if (data.event === 'status_update' && data.remediation_failed) {
        showNotification(`⚠️ Auto-remediation failed for ${data.ticket_id} - Manual intervention required`, 'danger');
        loadTickets();
    }
};
```

---

### **STEP 9: Integrate into Main Webhook Handler**

Update `/azure-monitor` endpoint (around line 1054):

```python
@app.post("/azure-monitor")
async def azure_monitor_webhook(request: Request, background_tasks: BackgroundTasks):
    # ... existing code ...

    # After ticket creation and RCA generation
    if os.getenv("AUTO_REMEDIATION_ENABLED", "false").lower() == "true":
        # Check if AI determined auto-remediation is possible
        if rca_result.get("auto_heal_possible") and error_type in REMEDIABLE_ERRORS:
            logger.info(f"Auto-remediation eligible for {ticket_id}, error: {error_type}")

            # Trigger auto-remediation in background
            background_tasks.add_task(
                trigger_auto_remediation,
                ticket_id=ticket_id,
                pipeline_name=pipeline_name,
                error_type=error_type,
                original_run_id=run_id,
                attempt_number=1
            )
        else:
            logger.info(f"Auto-remediation not eligible for {ticket_id}")

    # ... rest of existing code ...
```

---

### **STEP 10: Environment Configuration**

Add to `.env`:

```bash
# Auto-Remediation Settings
AUTO_REMEDIATION_ENABLED=true
AUTO_REMEDIATION_MAX_RETRIES=3

# Azure Data Factory API (for monitoring re-runs)
AZURE_SUBSCRIPTION_ID=d28a053b-ed09-40dd-92d6-43401a2c9799
AZURE_RESOURCE_GROUP=rg_techdemo_2025_Q4
AZURE_DATA_FACTORY_NAME=adf-techdemo-rca
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id  # Service Principal
AZURE_CLIENT_SECRET=your-secret  # Service Principal

# Logic App Playbook URLs
PLAYBOOK_RETRY_PIPELINE=https://prod-12.northcentralus.logic.azure.com:443/workflows/abc123/triggers/manual/paths/invoke?api-version=2016-10-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=xyz789
PLAYBOOK_RESTART_CLUSTER=https://prod-12.northcentralus.logic.azure.com:443/workflows/def456/...
PLAYBOOK_RETRY_JOB=https://prod-12.northcentralus.logic.azure.com:443/workflows/ghi789/...
PLAYBOOK_RERUN_UPSTREAM=https://prod-12.northcentralus.logic.azure.com:443/workflows/jkl012/...
```

---

## ADF-Specific Errors Auto-Resolution

### Common Resolvable ADF Errors:

| Error Type | Resolution Strategy | Implementation |
|------------|---------------------|----------------|
| **GatewayTimeout** | Retry with backoff | Logic App triggers pipeline re-run after 30s, 60s, 120s delays |
| **HttpConnectionFailed** | Retry transient network issues | Same as above |
| **ThrottlingError** | Retry with exponential backoff | Longer delays: 30s, 60s, 120s, 300s, 600s |
| **UserErrorSourceBlobNotExists** | Check if upstream pipeline succeeded, re-run if yes | Logic App checks upstream pipeline status, triggers if complete |
| **LinkedServiceError** | Validate credentials, refresh connection | Logic App can call refresh endpoint or recreate linked service |
| **DataFactoryTimeout** | Increase timeout in pipeline settings | Not auto-resolvable, requires manual config change |

---

## Testing the Flow

### Test Scenario 1: Successful Auto-Remediation

1. Trigger a pipeline failure (e.g., GatewayTimeout)
2. Verify:
   - ✅ Ticket created with `status='open'`
   - ✅ AI sets `auto_heal_possible=true`
   - ✅ Logic App called via webhook
   - ✅ `remediation_status='in_progress'`
   - ✅ Slack notification: "Auto-remediation initiated"
   - ✅ Dashboard shows "🤖 Auto-Healing" badge
   - ✅ Pipeline re-run succeeds
   - ✅ Ticket auto-closed with `ack_user='AI_AUTO_HEAL'`
   - ✅ Jira ticket transitioned to "Done"
   - ✅ Slack updated: "✅ Auto-remediation successful"
   - ✅ Dashboard shows "✅ Auto-Remediated" badge

### Test Scenario 2: Failed Retry with Escalation

1. Trigger a remediable error that will fail again
2. Verify:
   - ✅ Attempt 1 fails, Slack: "🔄 Retry attempt 2/3"
   - ✅ Attempt 2 fails, Slack: "🔄 Retry attempt 3/3"
   - ✅ Attempt 3 fails
   - ✅ `remediation_status='max_retries_exceeded'`
   - ✅ Slack: "⚠️ Manual intervention required"
   - ✅ Jira comment added with escalation details
   - ✅ Dashboard shows "⚠️ Escalated" badge
   - ✅ Ticket remains `status='open'`

---

## API Endpoints Summary

| Endpoint | Purpose |
|----------|---------|
| `POST /azure-monitor` | Receives ADF failure alerts, triggers RCA + auto-remediation |
| `POST /databricks-monitor` | Receives Databricks failure alerts |
| `POST /webhook/jira` | Syncs Jira status changes back to dashboard |
| `GET /api/tickets/{id}/remediation-history` | View all remediation attempts for a ticket |
| `GET /api/metrics/auto-remediation` | Auto-remediation success rate, MTTR stats |

---

## Database Queries for Monitoring

```sql
-- Auto-remediation success rate
SELECT
    COUNT(CASE WHEN remediation_status = 'succeeded' THEN 1 END) * 100.0 / COUNT(*) as success_rate
FROM tickets
WHERE remediation_status IS NOT NULL;

-- Average MTTR for auto-remediated tickets
SELECT AVG(ack_seconds) / 60.0 as avg_mttr_minutes
FROM tickets
WHERE ack_user = 'AI_AUTO_HEAL';

-- Top remediable errors
SELECT error_type, COUNT(*) as count,
       COUNT(CASE WHEN remediation_status = 'succeeded' THEN 1 END) as auto_remediated
FROM tickets
GROUP BY error_type
ORDER BY count DESC;

-- Recent remediation attempts
SELECT * FROM remediation_attempts
ORDER BY started_at DESC
LIMIT 20;
```

---

## Next Steps

1. **Deploy Logic App** from provided JSON
2. **Update environment variables** with Logic App webhook URL
3. **Deploy updated code** to Azure App Service
4. **Configure Azure Monitor alerts** to POST to `/azure-monitor` endpoint
5. **Test with sample pipeline failures**
6. **Monitor dashboard and Slack for auto-remediation progress**

---

## Notes

- Auto-remediation only works for **predefined error types** in `REMEDIABLE_ERRORS`
- Each error type has its own **retry strategy and backoff delays**
- System automatically **escalates to manual intervention** after max retries
- All remediation attempts are **fully audited** and visible in dashboard
- Jira tickets are **automatically closed** on successful auto-remediation
- Slack messages are **updated in real-time** with remediation progress

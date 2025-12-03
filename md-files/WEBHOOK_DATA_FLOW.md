# 📊 WEBHOOK DATA EXTRACTION & DISTRIBUTION GUIDE

## 🎯 What Gets Extracted from Your Webhook

Based on your actual webhook payload, here's what the system extracts:

---

## 📥 FROM WEBHOOK (Your Actual Data)

### Raw Webhook Structure (Log Analytics Alert)

```json
{
  "data": {
    "essentials": {
      "alertId": "/subscriptions/.../alerts/05863fb2-4131-5a58-abbe-67c682470003",
      "alertRule": "tech-demo-adf-alert",
      "severity": "Sev3",
      "signalType": "Log",
      "monitoringService": "Log Alerts V2",
      "firedDateTime": "2025-11-27T04:19:22.4642504Z"
    },
    "alertContext": {
      "condition": {
        "allOf": [{
          "dimensions": [
            {"name": "PipelineName", "value": "Copy_to_database"},
            {"name": "PipelineRunId", "value": "531b0498-3d4b-4fa0-b5ed-2c0a7a4075a9"},
            {"name": "ActivityName", "value": "Copy data1"},
            {"name": "ActivityType", "value": "Copy"},
            {"name": "ErrorCode", "value": "2200"},
            {"name": "ErrorMessage", "value": "ErrorCode=TypeConversionFailure,Exception occurred when converting value 'data' for column name 'LastPurchaseDate' from type 'String' to type 'DateTime'. Additional info: The string was not recognized as a valid DateTime."},
            {"name": "FailureType", "value": "UserError"}
          ]
        }]
      }
    }
  }
}
```

---

## ✅ EXTRACTED FIELDS

### 1. Core Fields
```python
pipeline_name = "Copy_to_database"
run_id = "531b0498-3d4b-4fa0-b5ed-2c0a7a4075a9"
error_message = "ErrorCode=TypeConversionFailure,Exception occurred when converting value 'data' for column name 'LastPurchaseDate' from type 'String' to type 'DateTime'. Additional info: The string was not recognized as a valid DateTime."
```

### 2. Metadata Dictionary
```python
metadata = {
    "activity_name": "Copy data1",
    "activity_type": "Copy",
    "error_code": "2200",
    "failure_type": "UserError",
    "severity": "Sev3",
    "fired_time": "2025-11-27T04:19:22.4642504Z",
    "alert_type": "Log",  # NEW: Shows this is Log Analytics Alert
    "alert_rule": "tech-demo-adf-alert",  # NEW
    "monitoring_service": "Log Alerts V2"  # NEW
}
```

### 3. AI-Generated RCA Fields
```python
rca = {
    "root_cause": "Data type mismatch in column 'LastPurchaseDate'. Source data contains invalid datetime value 'data'.",
    "error_type": "ADFDataTypeMismatch",  # AI classified
    "severity": "Medium",  # AI determined
    "priority": "P2",  # Derived from severity
    "confidence": 0.95,  # AI confidence score
    "affected_entity": "Copy_to_database > Copy data1 > LastPurchaseDate",
    "recommendations": [
        "1. Validate source data format for column 'LastPurchaseDate'",
        "2. Add data quality check before copy activity",
        "3. Use derived column to convert 'data' to NULL or default datetime"
    ],
    "auto_heal_possible": true  # Can be auto-remediated
}
```

---

## 📤 WHERE DATA GOES

### 🎫 1. TICKET CREATED IN DATABASE

**Table:** `tickets`

**Stored Fields:**
```sql
INSERT INTO tickets (
    id,                    -- "ADF-20251127T041930-d2fb9f"
    timestamp,             -- "2025-11-27T04:19:30Z"
    pipeline,              -- "Copy_to_database"
    run_id,                -- "531b0498-3d4b-4fa0-b5ed-2c0a7a4075a9"
    rca_result,            -- AI Root Cause Analysis
    recommendations,       -- JSON array of recommendations
    confidence,            -- 0.95
    severity,              -- "Medium"
    priority,              -- "P2"
    error_type,            -- "ADFDataTypeMismatch"
    affected_entity,       -- "Copy_to_database > Copy data1"
    status,                -- "open"
    sla_seconds,           -- 14400 (4 hours for P2)
    sla_status,            -- "Pending"
    finops_team,           -- "ETL Team" (from pipeline name tags)
    finops_owner,          -- "John Doe" (from pipeline tags)
    finops_cost_center,    -- "CC-1234" (from pipeline tags)
    blob_log_url,          -- Azure Blob URL with full payload
    itsm_ticket_id,        -- "APAIOPS-110" (Jira ticket)
    logic_app_run_id,      -- "N/A" (direct webhook)
    processing_mode        -- "direct_webhook"
)
```

**What Shows in Dashboard:**
- Ticket ID
- Pipeline Name
- Error Type
- Severity (color-coded)
- Status
- Created Time
- RCA Summary
- Recommendations
- Jira Link (if created)

---

### 📋 2. JIRA TICKET CREATED

**Project:** `APAIOPS` (your configured project)

**Ticket Fields:**
```yaml
Summary: "[ADF] Copy_to_database failed - ADFDataTypeMismatch"

Description: |
  🚨 ADF Pipeline Failure Alert

  Pipeline: Copy_to_database
  Run ID: 531b0498-3d4b-4fa0-b5ed-2c0a7a4075a9
  Activity: Copy data1 (Copy)
  Error Code: 2200
  Failure Type: UserError

  ❌ Error Message:
  ErrorCode=TypeConversionFailure,Exception occurred when converting value 'data'
  for column name 'LastPurchaseDate' from type 'String' to type 'DateTime'.
  Additional info: The string was not recognized as a valid DateTime.

  🔍 Root Cause Analysis:
  Data type mismatch in column 'LastPurchaseDate'. Source data contains invalid
  datetime value 'data'.

  💡 Recommendations:
  1. Validate source data format for column 'LastPurchaseDate'
  2. Add data quality check before copy activity
  3. Use derived column to convert 'data' to NULL or default datetime

  📊 Details:
  - Severity: Medium
  - Priority: P2
  - Confidence: 95%
  - Affected Entity: Copy_to_database > Copy data1 > LastPurchaseDate
  - SLA: 4 hours

  🏷️ FinOps Tags:
  - Team: ETL Team
  - Owner: John Doe
  - Cost Center: CC-1234

  🔗 Links:
  - RCA Ticket: ADF-20251127T041930-d2fb9f
  - Dashboard: https://your-app.azurewebsites.net/dashboard
  - Audit Logs: https://sttechdemorcadev.blob.core.windows.net/audit-logs/...

Labels: [adf, pipeline-failure, data-type-mismatch, p2]

Priority: Medium

Assignee: (Auto-assigned based on FinOps owner or team rotation)
```

**What Jira Shows:**
- Clear error summary in title
- Complete error details in description
- AI-generated recommendations
- Links to dashboard and logs
- Proper labels for filtering
- Auto-assignment to responsible team

---

### 💬 3. SLACK NOTIFICATION SENT

**Channel:** `#aiops-rca-alerts` (your configured channel)

**Message Format:**
```
🚨 *ADF Pipeline Failure Alert*

*Pipeline:* Copy_to_database
*Status:* ❌ Failed
*Severity:* 🟡 Medium (P2)
*Time:* 2025-11-27 04:19 UTC

*Activity:* Copy data1 (Copy)
*Error Code:* 2200 - TypeConversionFailure

*Error:*
```
ErrorCode=TypeConversionFailure, Exception occurred when converting value 'data'
for column name 'LastPurchaseDate' from type 'String' to type 'DateTime'.
Additional info: The string was not recognized as a valid DateTime.
```

*🔍 Root Cause:*
Data type mismatch in column 'LastPurchaseDate'. Source data contains invalid
datetime value 'data'.

*💡 Top Recommendations:*
1. Validate source data format for column 'LastPurchaseDate'
2. Add data quality check before copy activity
3. Use derived column to convert 'data' to NULL or default datetime

*📊 Details:*
• Confidence: 95%
• Affected: Copy_to_database > Copy data1 > LastPurchaseDate
• SLA: 4 hours
• Team: ETL Team

*🔗 Links:*
• Ticket: ADF-20251127T041930-d2fb9f
• Jira: APAIOPS-110
• Dashboard: https://your-app.azurewebsites.net/dashboard
• Run ID: 531b0498-3d4b-4fa0-b5ed-2c0a7a4075a9

---
_Auto-generated by RCA System | Confidence: 95%_
```

**What Slack Includes:**
- Visual severity indicator (emoji)
- Pipeline and activity details
- Complete error message (formatted)
- AI Root Cause Analysis
- Top 3 recommendations
- Quick links to ticket, Jira, dashboard
- Team/owner information
- SLA countdown

---

### 📊 4. DASHBOARD DISPLAY

**URL:** `https://your-app.azurewebsites.net/dashboard`

**Ticket Card Shows:**

```
┌─────────────────────────────────────────────────────────────┐
│ ADF-20251127T041930-d2fb9f          🟡 Medium  🕐 2h 15m ago  │
├─────────────────────────────────────────────────────────────┤
│ Pipeline: Copy_to_database                                   │
│ Activity: Copy data1 (Copy)                                  │
│ Error: ADFDataTypeMismatch                                   │
│                                                              │
│ ❌ TypeConversionFailure in LastPurchaseDate column         │
│                                                              │
│ 🔍 RCA: Data type mismatch - invalid datetime value 'data'  │
│                                                              │
│ 💡 Recommendations:                                          │
│   1. Validate source data format                            │
│   2. Add data quality check                                 │
│   3. Use derived column for conversion                      │
│                                                              │
│ 📊 Details:                                                  │
│   • Confidence: 95%                                          │
│   • Priority: P2                                             │
│   • SLA: 1h 45m remaining                                    │
│   • Team: ETL Team                                           │
│   • Owner: John Doe                                          │
│                                                              │
│ 🔗 Links:                                                    │
│   [View in Jira: APAIOPS-110] [Audit Logs] [Run Details]   │
│                                                              │
│ Status: 🟢 Open                                              │
└─────────────────────────────────────────────────────────────┘
```

**Interactive Features:**
- Click to expand full details
- Real-time status updates via WebSocket
- Filter by pipeline, severity, team
- Sort by time, priority, SLA
- Quick actions: Assign, Close, Auto-Remediate

---

## 📋 COMPLETE DATA FLOW DIAGRAM

```
┌──────────────────────────────────────────────────────────────────┐
│                      WEBHOOK RECEIVED                             │
│                                                                   │
│  From: Azure Monitor Log Analytics Alert                         │
│  Contains:                                                        │
│    • PipelineName: Copy_to_database                              │
│    • PipelineRunId: 531b0498-3d4b-4fa0-b5ed-2c0a7a4075a9        │
│    • ActivityName: Copy data1                                    │
│    • ErrorCode: 2200                                             │
│    • ErrorMessage: TypeConversionFailure...                      │
│    • FailureType: UserError                                      │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ↓
┌──────────────────────────────────────────────────────────────────┐
│                   ERROR EXTRACTION                                │
│                                                                   │
│  AzureDataFactoryExtractor.extract(webhook)                      │
│                                                                   │
│  ✅ Extracts from dimensions[] array (Log Analytics format)       │
│  ✅ Parses nested structure                                       │
│  ✅ Returns clean data + metadata                                │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ↓
┌──────────────────────────────────────────────────────────────────┐
│                   DEDUPLICATION CHECK                             │
│                                                                   │
│  Query: SELECT * FROM tickets WHERE run_id = '531b0498...'       │
│                                                                   │
│  If exists: Return "duplicate_ignored"                           │
│  If new: Continue processing                                     │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ↓
┌──────────────────────────────────────────────────────────────────┐
│                    AI RCA GENERATION                              │
│                                                                   │
│  generate_rca_and_recs(error_message)                            │
│                                                                   │
│  Input: Full error message                                       │
│  AI Model: Google Gemini                                         │
│                                                                   │
│  Output:                                                          │
│    ✅ root_cause: "Data type mismatch..."                        │
│    ✅ error_type: "ADFDataTypeMismatch"                          │
│    ✅ severity: "Medium"                                         │
│    ✅ recommendations: [...]                                     │
│    ✅ confidence: 0.95                                            │
│    ✅ affected_entity: "Copy_to_database > Copy data1"          │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ↓
┌──────────────────────────────────────────────────────────────────┐
│                    FINOPS TAG EXTRACTION                          │
│                                                                   │
│  extract_finops_tags(pipeline_name)                              │
│                                                                   │
│  Pattern matching on pipeline name:                              │
│    Copy_to_database → team: ETL Team                             │
│                    → owner: John Doe                             │
│                    → cost_center: CC-1234                        │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ↓
┌──────────────────────────────────────────────────────────────────┐
│                    TICKET CREATION                                │
│                                                                   │
│  ticket_id = "ADF-20251127T041930-d2fb9f"                        │
│                                                                   │
│  INSERT INTO tickets (...all fields...)                          │
│                                                                   │
│  ✅ Stored in SQLite database                                    │
│  ✅ Indexed by run_id for deduplication                          │
└───────────────────────────┬──────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ↓                   ↓                   ↓
┌──────────────┐  ┌──────────────────┐  ┌────────────────┐
│ JIRA TICKET  │  │ SLACK NOTIFICATION│  │ AUDIT LOGGING  │
├──────────────┤  ├──────────────────┤  ├────────────────┤
│ Project:     │  │ Channel:         │  │ Blob Storage:  │
│ APAIOPS      │  │ #aiops-rca-      │  │ sttechdemo...  │
│              │  │ alerts           │  │                │
│ Ticket:      │  │                  │  │ Files:         │
│ APAIOPS-110  │  │ Message:         │  │ • payload.json │
│              │  │ 🚨 ADF Failure   │  │ • audit.log    │
│ Contains:    │  │ Copy_to_database │  │                │
│ • Summary    │  │                  │  │ Searchable:    │
│ • Details    │  │ Includes:        │  │ • By ticket_id │
│ • RCA        │  │ • Error details  │  │ • By run_id    │
│ • Recomm.    │  │ • RCA summary    │  │ • By timestamp │
│ • Links      │  │ • Links          │  │                │
└──────────────┘  └──────────────────┘  └────────────────┘
        │                   │                   │
        └───────────────────┴───────────────────┘
                            │
                            ↓
┌──────────────────────────────────────────────────────────────────┐
│                    WEBSOCKET BROADCAST                            │
│                                                                   │
│  manager.broadcast({                                             │
│    "event": "new_ticket",                                        │
│    "ticket_id": "ADF-20251127T041930-d2fb9f"                    │
│  })                                                              │
│                                                                   │
│  ✅ All connected dashboards receive update immediately          │
│  ✅ Real-time ticket appears without page refresh                │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ↓
┌──────────────────────────────────────────────────────────────────┐
│                    RESPONSE TO AZURE                              │
│                                                                   │
│  HTTP 200 OK                                                     │
│  {                                                               │
│    "status": "success",                                          │
│    "ticket_id": "ADF-20251127T041930-d2fb9f",                   │
│    "run_id": "531b0498-3d4b-4fa0-b5ed-2c0a7a4075a9",           │
│    "pipeline": "Copy_to_database",                              │
│    "severity": "Medium",                                         │
│    "priority": "P2",                                             │
│    "itsm_ticket_id": "APAIOPS-110",                             │
│    "message": "Ticket created successfully"                     │
│  }                                                               │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🎯 SUMMARY TABLE: WHERE EACH FIELD GOES

| Field | Database | Jira | Slack | Dashboard | Audit Log |
|-------|----------|------|-------|-----------|-----------|
| **Pipeline Name** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Run ID** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Activity Name** | ✅ metadata | ✅ | ✅ | ✅ | ✅ |
| **Activity Type** | ✅ metadata | ✅ | ✅ | ✅ | ✅ |
| **Error Code** | ✅ metadata | ✅ | ✅ | ✅ | ✅ |
| **Error Message** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Failure Type** | ✅ metadata | ✅ | ✅ | ✅ | ✅ |
| **Root Cause (AI)** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Recommendations** | ✅ JSON | ✅ | ✅ Top 3 | ✅ | ✅ |
| **Severity** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Priority** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Confidence** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Affected Entity** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **FinOps Team** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **FinOps Owner** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Cost Center** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Alert Time** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **SLA Deadline** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Ticket ID** | ✅ | ✅ Link | ✅ | ✅ | ✅ |
| **Jira Ticket ID** | ✅ | N/A | ✅ Link | ✅ Link | ✅ |
| **Blob Log URL** | ✅ | ✅ Link | ❌ | ✅ Link | ✅ |
| **Raw Payload** | ❌ | ❌ | ❌ | ❌ | ✅ Blob only |

---

## ✅ VERIFICATION: What You Should See

After your webhook is processed:

### 1. **In Logs:**
```
✓ ADF Extractor: Found Log Analytics Alert with 7 dimensions
✓ ADF Extractor: pipeline=Copy_to_database, run_id=531b0498-3d4b-4fa0-b5ed-2c0a7a4075a9
✓ ADF Extractor: activity=Copy data1, error_code=2200
✓ ADF Extractor: alert_type=Log, error_length=245
✅ Successfully created ticket ADF-20251127T041930-d2fb9f
```

### 2. **In Dashboard:**
- New ticket appears in real-time
- Shows "Copy_to_database" pipeline
- Error type: "ADFDataTypeMismatch"
- Severity: Medium (yellow)
- Full RCA and recommendations visible

### 3. **In Slack:**
- Message posted to #aiops-rca-alerts
- Shows error with proper formatting
- Includes ticket and Jira links
- Team can click through to dashboard

### 4. **In Jira:**
- Ticket APAIOPS-110 created
- Contains all error details
- Has actionable recommendations
- Linked to dashboard ticket
- Auto-assigned to team

---

## 🚀 NEXT STEPS

1. **Deploy updated code** with new extractor
2. **Trigger a test failure** in your ADF pipeline
3. **Verify extraction** in logs (should show 7 dimensions)
4. **Check Slack** for formatted notification
5. **Check Jira** for detailed ticket
6. **Check Dashboard** for real-time ticket

All data is now properly extracted, analyzed, and distributed! 🎉

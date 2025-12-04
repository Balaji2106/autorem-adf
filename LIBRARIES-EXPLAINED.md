# Libraries Used in Auto-Remediation System

This document explains all the libraries used in the ADF/Databricks auto-remediation system and the technical rationale behind each choice.

---

## Core Web Framework Libraries

### 1. **FastAPI** (v0.104.1)
```python
from fastapi import FastAPI, Request, HTTPException, WebSocket
```

**Purpose**: Modern Python web framework for building APIs

**Why chosen:**
- ✅ **High Performance**: ASGI-based, handles async/await natively → critical for webhook processing
- ✅ **Auto API Documentation**: Generates OpenAPI/Swagger UI automatically → easy testing and integration
- ✅ **Type Validation**: Uses Pydantic for automatic request/response validation → prevents malformed data
- ✅ **WebSocket Support**: Built-in real-time dashboard updates via WebSockets
- ✅ **Production-Ready**: Used by Netflix, Uber, Microsoft for production APIs

**Use cases in our system:**
- `/webhook/adf` - Receives Azure Monitor alerts for ADF failures
- `/webhook/databricks` - Receives Databricks job failure webhooks
- `/dashboard` - Real-time ticket monitoring dashboard
- `/api/trigger-auto-remediation` - Manual remediation trigger endpoint

**Alternatives considered:**
- Flask: Lacks native async support, no auto-validation
- Django: Too heavyweight for API-only service
- Express.js (Node): Python ecosystem better for AI/ML integration

---

### 2. **Uvicorn** (v0.24.0)
```python
# Used to run the FastAPI app
uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Purpose**: ASGI web server for running FastAPI applications

**Why chosen:**
- ✅ **ASGI Standard**: Supports async Python (FastAPI requirement)
- ✅ **High Throughput**: Handles concurrent webhook requests efficiently
- ✅ **Production-Grade**: Used with Gunicorn in production for worker management
- ✅ **WebSocket Support**: Required for real-time dashboard updates

**Deployment pattern:**
```bash
# Production deployment
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app
```

---

### 3. **Pydantic** (v2.5.0)
```python
from pydantic import BaseModel, EmailStr, validator

class RemediationRequest(BaseModel):
    pipeline_name: str
    ticket_id: str
    error_type: str
    retry_attempt: int
```

**Purpose**: Data validation using Python type annotations

**Why chosen:**
- ✅ **Type Safety**: Validates webhook payloads from Azure Monitor/Databricks automatically
- ✅ **Error Messages**: Clear validation errors → easier debugging
- ✅ **Performance**: Written in Rust (v2) → 2-3x faster than v1
- ✅ **FastAPI Integration**: Native integration with FastAPI

**Real example from codebase:**
```python
class User(BaseModel):
    email: EmailStr  # Validates email format automatically
    username: str
    role: str  # admin, developer, viewer
```

**Why critical for auto-remediation:**
- Webhook payloads from Azure can be malformed → Pydantic rejects bad data before processing
- Prevents auto-remediation from triggering on invalid error types

---

### 4. **Python-Multipart** (v0.0.6)
```python
# Required for file uploads in FastAPI
```

**Purpose**: Handle file uploads in web forms

**Why needed:**
- FastAPI needs it for processing `multipart/form-data` requests
- Future use: Upload error logs, custom playbook definitions

---

## Configuration & Environment

### 5. **Python-Dotenv** (v1.0.0)
```python
from dotenv import load_dotenv
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
```

**Purpose**: Load environment variables from `.env` file

**Why chosen:**
- ✅ **Security**: Secrets stay out of code (no hardcoded API keys)
- ✅ **12-Factor App**: Standard practice for production apps
- ✅ **Dev/Prod Parity**: Same codebase, different .env files

**Our .env structure:**
```bash
# AI Configuration
GEMINI_API_KEY=xxx
AI_PROVIDER=gemini

# Auto-Remediation
AUTO_REMEDIATION_ENABLED=true
PLAYBOOK_RETRY_PIPELINE=https://prod-XX.logic.azure.com/...

# Database
DB_TYPE=azure_sql
AZURE_SQL_SERVER=xxx.database.windows.net
```

---

## Database Libraries

### 6. **SQLAlchemy** (v2.0.23)
```python
from sqlalchemy import create_engine, text

engine = create_engine(f"sqlite:///{DB_PATH}")
conn = engine.connect()
result = conn.execute(text("SELECT * FROM tickets WHERE status = :status"), {"status": "open"})
```

**Purpose**: Database ORM and SQL toolkit

**Why chosen:**
- ✅ **Database Agnostic**: Same code works with SQLite (dev) and Azure SQL (prod)
- ✅ **Connection Pooling**: Handles concurrent webhook requests efficiently
- ✅ **SQL Injection Protection**: Parameterized queries prevent SQL injection
- ✅ **Schema Management**: Easy to add columns for new features

**Our database strategy:**
- **Development**: SQLite (`sqlite:///data/tickets.db`)
- **Production**: Azure SQL Server (`mssql+pyodbc://...`)

**Key tables:**
- `tickets` - RCA audit trail
- `audit_log` - All actions (Slack, Jira, remediation attempts)
- `users` - Dashboard authentication

---

### 7. **PyODBC** (v5.0.1)
```python
# Driver for Azure SQL Server connections
connection_string = f"mssql+pyodbc://{user}:{pwd}@{server}/{db}?driver=ODBC+Driver+17+for+SQL+Server"
```

**Purpose**: ODBC database driver for SQL Server

**Why needed:**
- ✅ **Azure SQL Support**: Official Microsoft ODBC driver for SQL Server
- ✅ **Production Requirement**: Azure SQL is the production database
- ✅ **Windows Authentication**: Supports Azure AD authentication

**Installation requirement:**
```bash
# Requires ODBC Driver 17 or 18 for SQL Server
# Linux: sudo apt-get install unixodbc-dev msodbcsql17
# Windows: Included in SQL Server installations
```

---

## AI/LLM Libraries

### 8. **Google Generative AI** (v0.3.1)
```python
import google.generativeai as genai

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-2.5-flash')
response = model.generate_content(prompt)
```

**Purpose**: Google's Gemini AI for RCA generation

**Why chosen:**
- ✅ **Cost-Effective**: $0.075 per 1M tokens (Gemini 1.5 Flash) vs OpenAI $0.50
- ✅ **Large Context**: 1M token context window → can send full error logs
- ✅ **Speed**: Gemini 2.5 Flash returns RCA in <2 seconds
- ✅ **Auto-Heal Logic**: Strong reasoning for determining `auto_heal_possible=true/false`
- ✅ **JSON Mode**: Reliable structured output for RCA format

**Our RCA prompt structure:**
```python
prompt = f"""
You are an expert in ADF/Databricks troubleshooting.

Error Type: {error_type}
Error Message: {error_message}
Pipeline: {pipeline_name}

AUTO-HEAL DECISION LOGIC:
✅ auto_heal_possible=true if:
  - GatewayTimeout (transient network error)
  - ThrottlingError (retry with backoff)

❌ auto_heal_possible=false if:
  - UserErrorSourceBlobNotExists (missing data file)
  - Code execution errors

Generate RCA in JSON format:
{{
  "error_type": "GatewayTimeout",
  "root_cause": "...",
  "auto_heal_possible": true,
  "recommended_action": "retry_pipeline",
  ...
}}
"""
```

**Fallback option:**
- If Gemini API fails → Use Ollama (local LLM) with `deepseek-r1:latest`

---

## HTTP Client Library

### 9. **Requests** (v2.31.0)
```python
import requests

# Call Logic App for auto-remediation
response = requests.post(
    PLAYBOOK_RETRY_PIPELINE,
    json={
        "pipeline_name": "ETL_Pipeline",
        "ticket_id": "ADF-123",
        "error_type": "GatewayTimeout",
        "retry_attempt": 1
    },
    headers={"Content-Type": "application/json"}
)
```

**Purpose**: HTTP library for making REST API calls

**Why chosen:**
- ✅ **Simple API**: Easy to use for webhook calls, Jira API, Slack API
- ✅ **Reliable**: Industry standard (50M+ downloads/month)
- ✅ **Rich Features**: Automatic retry, timeout handling, session management
- ✅ **Authentication Support**: Basic Auth, Bearer tokens, OAuth

**Use cases in our system:**

1. **Trigger Logic Apps (Auto-Remediation)**
```python
response = requests.post(PLAYBOOK_RETRY_PIPELINE, json=payload)
run_id = response.json()["run_id"]
```

2. **Monitor ADF Pipeline Status**
```python
# Check if remediation succeeded
response = requests.get(
    f"https://management.azure.com/subscriptions/{sub}/.../{run_id}",
    headers={"Authorization": f"Bearer {token}"}
)
status = response.json()["properties"]["status"]  # Succeeded/Failed
```

3. **Fetch Databricks Job Details**
```python
response = requests.get(
    f"{DATABRICKS_HOST}/api/2.1/jobs/runs/get?run_id={run_id}",
    headers={"Authorization": f"Bearer {DATABRICKS_TOKEN}"}
)
```

4. **Send Slack Notifications**
```python
requests.post(
    "https://slack.com/api/chat.postMessage",
    headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
    json={"channel": "#alerts", "text": "Auto-remediation succeeded!"}
)
```

5. **Create Jira Tickets**
```python
requests.post(
    f"{JIRA_DOMAIN}/rest/api/3/issue",
    auth=HTTPBasicAuth(JIRA_USER_EMAIL, JIRA_API_TOKEN),
    json={
        "fields": {
            "project": {"key": "OPS"},
            "summary": f"ADF Pipeline Failed: {pipeline_name}",
            "description": rca_text,
            "issuetype": {"name": "Bug"}
        }
    }
)
```

**Why not use Azure SDK?**
- Azure Management SDK (`azure-mgmt-datafactory`) is heavy (100+ dependencies)
- Direct REST API calls are simpler and faster for our use case
- We only need 2-3 ADF API calls (get run status, trigger pipeline)

---

## Real-Time Communication

### 10. **WebSockets** (v12.0)
```python
from fastapi import WebSocket

@app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        # Send live ticket updates to dashboard
        await websocket.send_json({
            "type": "ticket_update",
            "ticket_id": "ADF-123",
            "status": "remediation_in_progress"
        })
```

**Purpose**: Real-time bidirectional communication for dashboard

**Why needed:**
- ✅ **Live Updates**: Dashboard shows remediation progress in real-time
- ✅ **No Polling**: Eliminates need to refresh page every 5 seconds
- ✅ **Better UX**: Users see "Remediation In Progress" → "Auto-Remediated" instantly

**User experience:**
```
User opens dashboard → Sees ticket in "Open" status
(30 seconds later)
Azure Monitor sends alert → Auto-remediation triggered
Dashboard updates IMMEDIATELY to "Remediation In Progress" ✅
(2 minutes later)
Logic App completes → Dashboard shows "Auto-Remediated" ✅
```

---

## Security Libraries

### 11. **Passlib** (v1.7.4) + **Bcrypt** (v4.1.1)
```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash password
hashed = pwd_context.hash("MySecurePassword123")

# Verify password
is_valid = pwd_context.verify("MySecurePassword123", hashed)
```

**Purpose**: Password hashing for dashboard authentication

**Why chosen:**
- ✅ **Industry Standard**: Bcrypt is the gold standard for password hashing
- ✅ **Slow by Design**: Prevents brute-force attacks (adjustable cost factor)
- ✅ **Rainbow Table Protection**: Each hash has unique salt

**Security features:**
- Cost factor = 12 (2^12 rounds) → takes ~300ms to verify (prevents brute force)
- Salted hashes → same password = different hash each time

---

### 12. **PyJWT** (v2.8.0)
```python
import jwt

# Generate JWT token for dashboard login
token = jwt.encode(
    {
        "username": "admin",
        "role": "admin",
        "exp": datetime.utcnow() + timedelta(hours=24)
    },
    JWT_SECRET_KEY,
    algorithm="HS256"
)

# Verify token
payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
```

**Purpose**: JWT (JSON Web Tokens) for API authentication

**Why chosen:**
- ✅ **Stateless Auth**: No need to store sessions in database
- ✅ **Token Expiry**: Tokens expire after 24 hours (configurable)
- ✅ **Role-Based Access**: Embed user role in token → check permissions

**Authentication flow:**
```
1. User logs in → POST /login with username/password
2. Server verifies password with bcrypt
3. Server generates JWT with user role
4. Client stores JWT in localStorage
5. Client sends JWT in Authorization header for all requests
6. Server validates JWT signature and expiry
```

---

### 13. **Email-Validator** (v2.1.0)
```python
from pydantic import EmailStr

class User(BaseModel):
    email: EmailStr  # Validates email format
```

**Purpose**: Validate email addresses

**Why needed:**
- ✅ **User Registration**: Ensure valid email format for dashboard users
- ✅ **Jira Integration**: Validate Jira user email in configuration
- ✅ **RFC Compliance**: Checks DNS records, special characters, etc.

---

## Azure Integration

### 14. **Azure Storage Blob** (v12.19.0)
```python
from azure.storage.blob import BlobServiceClient

blob_service = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONN)
container = blob_service.get_container_client(AZURE_BLOB_CONTAINER_NAME)

# Upload audit log to Azure Blob
blob_client = container.get_blob_client(f"audit-logs/{ticket_id}.json")
blob_client.upload_blob(json.dumps(audit_data))
```

**Purpose**: Store audit logs in Azure Blob Storage

**Why chosen:**
- ✅ **Long-Term Storage**: Keep audit trail for compliance (90 days, 1 year, etc.)
- ✅ **Cost-Effective**: $0.018 per GB/month (Cool tier) vs $5/GB for SQL
- ✅ **Immutable Storage**: Enable WORM (Write Once Read Many) for compliance

**Our audit strategy:**
- **SQLite/Azure SQL**: Last 30 days of tickets (fast queries for dashboard)
- **Azure Blob**: All historical audit logs (compliance, forensics)

**Blob structure:**
```
audit-logs/
├── 2025-12/
│   ├── ADF-20251203T123456-abc123.json
│   ├── DBR-20251203T130000-xyz789.json
├── 2025-11/
│   └── ...
```

---

## Additional Python Libraries (Built-in)

### 15. **logging** (Standard Library)
```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auto_remediation")

logger.info(f"Auto-remediation triggered for {ticket_id}")
logger.error(f"Logic App failed: {error}")
```

**Purpose**: Application logging for debugging and monitoring

**Log locations:**
- Console output (Docker logs)
- `/var/log/auto-remediation.log` (systemd service)
- Azure Application Insights (future)

---

### 16. **json** (Standard Library)
```python
import json

# Parse webhook payloads
payload = json.loads(request.body)

# Generate RCA response
rca_json = json.dumps(rca_dict, indent=2)
```

**Purpose**: JSON parsing and serialization

---

### 17. **datetime** (Standard Library)
```python
from datetime import datetime, timezone, timedelta

# Calculate MTTR
failure_time = datetime.fromisoformat(ticket["timestamp"])
resolution_time = datetime.utcnow()
mttr_seconds = (resolution_time - failure_time).total_seconds()

# Deduplication time window
threshold = datetime.utcnow() - timedelta(minutes=5)
```

**Purpose**: Time calculations for MTTR, deduplication, retry backoff

---

### 18. **hmac** + **hashlib** (Standard Library)
```python
import hmac
import hashlib

# Verify Jira webhook signature
expected_signature = hmac.new(
    JIRA_WEBHOOK_SECRET.encode(),
    request.body,
    hashlib.sha256
).hexdigest()

if request.headers["X-Hub-Signature-256"] != expected_signature:
    raise HTTPException(403, "Invalid signature")
```

**Purpose**: Webhook signature verification (Jira, GitHub webhooks)

**Why critical:**
- Prevents attackers from sending fake webhook payloads
- Ensures webhook is genuinely from Jira/Azure Monitor

---

## Libraries NOT Used (But Could Be)

### ❌ Azure Management SDK
```python
# NOT USED
from azure.mgmt.datafactory import DataFactoryManagementClient
```

**Why not:**
- ✅ Direct REST API calls are simpler
- ✅ Avoids 100+ dependency packages
- ✅ Logic Apps handle ADF API calls (separation of concerns)

**When to use:**
- If building complex ADF automation (create pipelines, datasets, etc.)
- Our use case: Only trigger pipeline runs → REST API sufficient

---

### ❌ Slack SDK
```python
# NOT USED
from slack_sdk import WebClient
```

**Why not:**
- ✅ `requests` library is sufficient for Slack API calls
- ✅ Only need `chat.postMessage` → simple POST request

**When to use:**
- If using Slack interactive buttons, modals, etc.

---

### ❌ Databricks SDK
```python
# NOT USED
from databricks_sdk import WorkspaceClient
```

**Why not:**
- ✅ Direct REST API calls are simpler
- ✅ Only need 2-3 API endpoints (get job run, trigger job)
- ✅ Logic Apps handle Databricks API calls

---

## Summary: Library Selection Criteria

Our library choices follow these principles:

1. **Simplicity First**: Use `requests` for HTTP calls instead of SDKs when possible
2. **Performance**: FastAPI + Uvicorn for async webhook processing
3. **Security**: Bcrypt for passwords, JWT for stateless auth, signature verification
4. **Maintainability**: SQLAlchemy for database agnostic code
5. **Cost**: Gemini AI ($0.075/1M tokens) over OpenAI ($0.50/1M)
6. **Production-Ready**: All libraries are actively maintained with 1M+ downloads

---

## Total Dependency Count

**Production dependencies**: 14 libraries (listed in requirements.txt)
**Dev dependencies**: ~50 (including transitive dependencies)

**Lightweight footprint:**
- Docker image size: ~450 MB (Python + dependencies)
- Memory usage: ~200 MB (FastAPI app)
- Cold start time: <2 seconds

---

## Installation Commands

```bash
# Install all dependencies
pip install -r genai_rca_assistant/requirements.txt

# For Azure SQL support (requires ODBC driver)
# Ubuntu/Debian
sudo apt-get install unixodbc-dev msodbcsql17

# Windows
# ODBC Driver included in SQL Server installations
```

---

## Future Libraries (Roadmap)

### Planned Additions:

1. **Azure Application Insights SDK**
   - Purpose: Advanced telemetry and monitoring
   - Why: Better than basic logging for production

2. **Celery + Redis**
   - Purpose: Background job queue for long-running remediation monitoring
   - Why: Async task processing without blocking webhooks

3. **Prometheus Client**
   - Purpose: Metrics export for Grafana dashboards
   - Why: Track auto-remediation success rate, MTTR trends

4. **Sentry SDK**
   - Purpose: Error tracking and alerting
   - Why: Get notified when auto-remediation logic crashes

---

## Questions for Stakeholders

When presenting this to stakeholders, be ready to answer:

**Q1: Why not use Azure Functions instead of FastAPI?**
- ✅ FastAPI: Full control, easier debugging, free hosting on VM
- ❌ Azure Functions: Cold start delays, vendor lock-in, complex local testing

**Q2: Why Gemini instead of OpenAI?**
- ✅ 7x cheaper ($0.075 vs $0.50 per 1M tokens)
- ✅ Larger context window (1M tokens vs 128K)
- ✅ Similar accuracy for RCA generation

**Q3: Why SQLite for dev and Azure SQL for prod?**
- ✅ SQLAlchemy makes database migration seamless
- ✅ SQLite: Zero setup for developers
- ✅ Azure SQL: Enterprise features (backups, HA, geo-replication)

**Q4: Why not use Azure SDK libraries?**
- ✅ Logic Apps abstract Azure API complexity
- ✅ Direct REST API calls are faster to implement
- ✅ Fewer dependencies = smaller attack surface

---

## Cost Breakdown (Monthly Estimates)

| Library/Service | Cost | Notes |
|----------------|------|-------|
| FastAPI + Uvicorn | Free | Open source |
| Gemini AI API | $10-30 | ~1000 RCA generations/month |
| Azure SQL Database | $5-50 | Basic tier sufficient |
| Azure Blob Storage | $2-10 | Audit logs |
| Logic Apps | $5-20 | Consumption plan |
| **Total** | **$22-110/month** | Scales with usage |

---

## Conclusion

This stack was chosen for:
- ✅ **Speed**: Auto-remediation completes in <5 minutes (vs 2-4 hours manual)
- ✅ **Cost**: <$100/month for full automation
- ✅ **Reliability**: Production-grade libraries with millions of users
- ✅ **Maintainability**: Simple architecture, easy to debug

**Next Steps:**
1. Review this library stack with security team
2. Deploy to production environment
3. Monitor library vulnerabilities (Dependabot alerts)
4. Plan migration to Celery for background tasks (if >1000 tickets/day)

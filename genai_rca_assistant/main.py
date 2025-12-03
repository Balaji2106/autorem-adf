# main.py - COMPLETE VERSION WITH PARALLEL PIPELINE SUPPORT & DEDUPLICATION
import os
import json
import uuid
import logging
import re
import requests
import time
import asyncio
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
from io import BytesIO, StringIO
import csv
from requests.auth import HTTPBasicAuth

from fastapi import FastAPI, Request, Header, HTTPException, WebSocket, WebSocketDisconnect, Query, Depends, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, validator
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
import jwt
from passlib.context import CryptContext

from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

# Databricks API utilities
from databricks_api_utils import fetch_databricks_run_details, extract_error_message

# Azure Blob Storage imports
try:
    from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
    AZURE_BLOB_AVAILABLE = True
except ImportError:
    AZURE_BLOB_AVAILABLE = False
    logging.warning("azure-storage-blob not installed. Azure Blob logging disabled.")

# --- Initialization & Configuration ---
load_dotenv()
RCA_API_KEY = os.getenv("RCA_API_KEY", "balaji-rca-secret-2025")

# AI Provider Configuration
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()  # Options: gemini, ollama, auto

# Gemini Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_ID = os.getenv("MODEL_ID", "models/gemini-2.5-flash")

# Ollama Configuration
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:latest")

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_ALERT_CHANNEL = os.getenv("SLACK_ALERT_CHANNEL", "aiops-rca-alerts")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()
DB_PATH = os.getenv("DB_PATH", "data/tickets.db")
AZURE_SQL_SERVER = os.getenv("AZURE_SQL_SERVER", "")
AZURE_SQL_DATABASE = os.getenv("AZURE_SQL_DATABASE", "")
AZURE_SQL_USERNAME = os.getenv("AZURE_SQL_USERNAME", "")
AZURE_SQL_PASSWORD = os.getenv("AZURE_SQL_PASSWORD", "")

# --- JWT Configuration ---
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production-please-use-a-long-random-string")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# --- Password Hashing ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Auto-Remediation Config ---
AUTO_REMEDIATION_ENABLED = os.getenv("AUTO_REMEDIATION_ENABLED", "false").lower() in ("1", "true", "yes")

# --- Azure Blob Storage Config ---
AZURE_STORAGE_CONN = os.getenv("AZURE_STORAGE_CONN")
AZURE_BLOB_CONTAINER_NAME = os.getenv("AZURE_BLOB_CONTAINER_NAME", "audit-logs")
AZURE_BLOB_ENABLED = os.getenv("AZURE_BLOB_ENABLED", "false").lower() in ("1", "true", "yes")

if AZURE_BLOB_ENABLED and not AZURE_BLOB_AVAILABLE:
    logging.warning("AZURE_BLOB_ENABLED=true but azure-storage-blob not installed. Disabling.")
    AZURE_BLOB_ENABLED = False

# --- ITSM Integration Config ---
ITSM_TOOL = os.getenv("ITSM_TOOL", "none").lower()
JIRA_DOMAIN = os.getenv("JIRA_DOMAIN", "").rstrip('/')
JIRA_USER_EMAIL = os.getenv("JIRA_USER_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "")
JIRA_WEBHOOK_SECRET = os.getenv("JIRA_WEBHOOK_SECRET", "")

# --- PLAYBOOK REGISTRY ---
PLAYBOOK_REGISTRY: Dict[str, Optional[str]] = {
    # ADF Error Types
    "UserErrorSourceBlobNotExists": os.getenv("PLAYBOOK_RERUN_UPSTREAM"),
    "GatewayTimeout": os.getenv("PLAYBOOK_RETRY_PIPELINE"),
    "HttpConnectionFailed": os.getenv("PLAYBOOK_RETRY_PIPELINE"),
    # Databricks Error Types
    "DatabricksClusterStartFailure": os.getenv("PLAYBOOK_RESTART_CLUSTER"),
    "DatabricksJobExecutionError": os.getenv("PLAYBOOK_RETRY_JOB"),
    "DatabricksLibraryInstallationError": os.getenv("PLAYBOOK_REINSTALL_LIBRARIES"),
    "DatabricksPermissionDenied": os.getenv("PLAYBOOK_CHECK_PERMISSIONS"),
}

# --- REMEDIABLE ERRORS CONFIGURATION ---
REMEDIABLE_ERRORS: Dict[str, Dict] = {
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
        "action": "restart_cluster",
        "max_retries": 2,
        "backoff_seconds": [60, 180],
        "playbook_url": os.getenv("PLAYBOOK_RESTART_CLUSTER")
    },

    # Databricks Library Errors
    "DatabricksLibraryInstallationError": {
        "action": "reinstall_libraries",
        "max_retries": 2,
        "backoff_seconds": [60, 180],
        "playbook_url": os.getenv("PLAYBOOK_REINSTALL_LIBRARIES")
    },
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

# Azure ADF API Configuration for monitoring
AZURE_SUBSCRIPTION_ID = os.getenv("AZURE_SUBSCRIPTION_ID", "")
AZURE_RESOURCE_GROUP = os.getenv("AZURE_RESOURCE_GROUP", "")
AZURE_DATA_FACTORY_NAME = os.getenv("AZURE_DATA_FACTORY_NAME", "")
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aiops_rca")

# --- Initialize Blob Service Client ---
blob_service_client: Optional[BlobServiceClient] = None
if AZURE_BLOB_ENABLED and AZURE_STORAGE_CONN:
    try:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONN)
        logger.info(AZURE_BLOB_CONTAINER_NAME)
    except Exception as e:
        logger.error("Failed to initialize Azure Blob client: %s", e)
        AZURE_BLOB_ENABLED = False

# --- DB Setup ---
def build_azure_sqlalchemy_url():
    if not (AZURE_SQL_SERVER and AZURE_SQL_DATABASE and AZURE_SQL_USERNAME and AZURE_SQL_PASSWORD):
        return None
    pwd = quote_plus(AZURE_SQL_PASSWORD)
    user = quote_plus(AZURE_SQL_USERNAME)
    server = AZURE_SQL_SERVER
    database = AZURE_SQL_DATABASE
    return f"mssql+pyodbc://{user}:{pwd}@{server}/{database}?driver=ODBC+Driver+18+for+SQL+Server;TrustServerCertificate=yes"

AZURE_DB_URL = build_azure_sqlalchemy_url() if DB_TYPE == "azuresql" else None

if DB_TYPE == "sqlite":
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
        except Exception as e:
            logger.warning("Could not create DB directory %s: %s", db_dir, e)

def get_engine_with_retry(retries: int = 3, backoff: int = 3):
    if AZURE_DB_URL:
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                eng = create_engine(AZURE_DB_URL, pool_pre_ping=True, pool_recycle=3600)
                with eng.connect() as conn:
                    conn.execute(text("SELECT 1"))
                logger.info("Connected to Azure SQL (attempt %d)", attempt)
                return eng
            except Exception as e:
                last_exc = e
                time.sleep(backoff * attempt)
        logger.warning("Azure SQL unavailable after %s attempts, falling back to SQLite. Last: %s", retries, last_exc)

    eng = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
    return eng

engine = get_engine_with_retry()

def init_db():
    with engine.begin() as conn:
        # Tickets table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tickets (
                id TEXT PRIMARY KEY, 
                timestamp TEXT, 
                pipeline TEXT, 
                run_id TEXT, 
                rca_result TEXT,
                recommendations TEXT, 
                confidence TEXT, 
                severity TEXT, 
                priority TEXT, 
                error_type TEXT,
                affected_entity TEXT, 
                status TEXT, 
                ack_user TEXT, 
                ack_empid TEXT, 
                ack_ts TEXT,
                ack_seconds INTEGER, 
                sla_seconds INTEGER, 
                sla_status TEXT, 
                slack_ts TEXT,
                slack_channel TEXT, 
                finops_team TEXT, 
                finops_owner TEXT, 
                finops_cost_center TEXT,
                blob_log_url TEXT, 
                itsm_ticket_id TEXT,
                logic_app_run_id TEXT,
                processing_mode TEXT
            )
        """))
        
        # Audit trail table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_trail (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                timestamp TEXT NOT NULL, 
                ticket_id TEXT NOT NULL,
                pipeline TEXT, 
                run_id TEXT, 
                action TEXT NOT NULL, 
                user_name TEXT, 
                user_empid TEXT,
                time_taken_seconds INTEGER, 
                mttr_minutes REAL, 
                sla_status TEXT, 
                rca_summary TEXT,
                finops_team TEXT, 
                finops_owner TEXT, 
                details TEXT, 
                itsm_ticket_id TEXT
            )
        """))
        
        # Users table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                created_at TEXT NOT NULL,
                last_login TEXT
            )
        """))

        # Remediation attempts table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS remediation_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL,
                original_run_id TEXT NOT NULL,
                remediation_run_id TEXT,
                attempt_number INTEGER NOT NULL,
                status TEXT NOT NULL,
                error_type TEXT,
                remediation_action TEXT,
                logic_app_response TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                duration_seconds INTEGER,
                failure_reason TEXT
            )
        """))
        
        # Migration: Add columns if they don't exist
        migration_columns = {
            "finops_team": "TEXT",
            "finops_owner": "TEXT",
            "finops_cost_center": "TEXT",
            "blob_log_url": "TEXT",
            "itsm_ticket_id": "TEXT",
            "logic_app_run_id": "TEXT",
            "processing_mode": "TEXT",
            "remediation_status": "TEXT",
            "remediation_run_id": "TEXT",
            "remediation_attempts": "INTEGER DEFAULT 0",
            "remediation_last_attempt_at": "TEXT"
        }
        
        for col, col_type in migration_columns.items():
            try:
                conn.execute(text(f"ALTER TABLE tickets ADD COLUMN {col} {col_type}"))
                logger.info(f"Added '{col}' column to tickets table.")
            except Exception as e:
                logger.debug(f"Column {col} may already exist: {str(e).strip()}")
        
        # Add itsm_ticket_id to audit_trail
        try:
            conn.execute(text("ALTER TABLE audit_trail ADD COLUMN itsm_ticket_id TEXT"))
            logger.info("Added 'itsm_ticket_id' column to audit_trail table.")
        except Exception as e:
            logger.debug(f"Column itsm_ticket_id may already exist: {str(e).strip()}")
        
        # **CRITICAL: Add unique index on run_id for deduplication**
        try:
            # First, update any existing 'N/A' values to NULL for consistency
            conn.execute(text("""
                UPDATE tickets SET run_id = NULL WHERE run_id = 'N/A' OR run_id = ''
            """))
            # logger.info("Updated existing 'N/A' run_id values to NULL.")

            # Drop old index if it exists (to ensure we create it correctly)
            if DB_TYPE == "sqlite":
                try:
                    conn.execute(text("DROP INDEX IF EXISTS idx_tickets_run_id"))
                    # logger.info("Dropped old unique index on run_id.")
                except Exception:
                    pass

                # Create unique index that excludes NULL values
                conn.execute(text("""
                    CREATE UNIQUE INDEX idx_tickets_run_id
                    ON tickets(run_id)
                    WHERE run_id IS NOT NULL
                """))
                # logger.info("Created unique index on run_id for deduplication (excludes NULL).")
            # For Azure SQL
            else:
                # Drop old index if exists
                conn.execute(text("""
                    IF EXISTS (SELECT * FROM sys.indexes WHERE name = 'idx_tickets_run_id' AND object_id = OBJECT_ID('tickets'))
                    BEGIN
                        DROP INDEX idx_tickets_run_id ON tickets
                    END
                """))

                # Create unique index that excludes NULL values
                conn.execute(text("""
                    CREATE UNIQUE INDEX idx_tickets_run_id ON tickets(run_id)
                    WHERE run_id IS NOT NULL
                """))
                logger.info("Created unique index on run_id for deduplication (Azure SQL, excludes NULL).")
        except Exception as e:
            logger.warning(f"Could not create/update unique index: {e}")

init_db()

def db_execute(q: str, params: Optional[dict] = None):
    params = params or {}
    with engine.begin() as conn:
        conn.execute(text(q), params)

def db_query(q: str, params: Optional[dict] = None, one: bool = False):
    params = params or {}
    with engine.connect() as conn:
        result = conn.execute(text(q), params)
        rows = [dict(r._mapping) for r in result.fetchall()]
    return rows[0] if one and rows else rows

# --- Authentication Helper Functions ---
def hash_password(password: str) -> str:
    password_bytes = password.encode('utf-8')[:72]
    password_truncated = password_bytes.decode('utf-8', errors='ignore')
    return pwd_context.hash(password_truncated)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode('utf-8')[:72]
    password_truncated = password_bytes.decode('utf-8', errors='ignore')
    return pwd_context.verify(password_truncated, hashed_password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.JWTError:
        return None

# --- Pydantic Models ---
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    
    @validator('email')
    def email_must_be_sigmoid(cls, v):
        if not v.endswith('@sigmoidanalytics.com'):
            raise ValueError('Email must be from @sigmoidanalytics.com domain')
        return v
    
    @validator('password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

# --- Authentication Dependency ---
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    email = payload.get("sub")
    if email is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    
    user = db_query("SELECT * FROM users WHERE email = :email", {"email": email}, one=True)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user

# --- Audit Trail Helper Functions ---
def log_audit(ticket_id: str, action: str, pipeline: str = None, run_id: str = None, 
              user_name: str = None, user_empid: str = None, time_taken_seconds: int = None,
              mttr_minutes: float = None, sla_status: str = None, rca_summary: str = None,
              finops_team: str = None, finops_owner: str = None, details: str = None,
              itsm_ticket_id: str = None):
    """Log audit trail entry to database with ITSM ticket ID"""
    try:
        timestamp = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        db_execute("""
            INSERT INTO audit_trail 
            (timestamp, ticket_id, pipeline, run_id, action, user_name, user_empid, 
             time_taken_seconds, mttr_minutes, sla_status, rca_summary, finops_team, 
             finops_owner, details, itsm_ticket_id)
            VALUES 
            (:timestamp, :ticket_id, :pipeline, :run_id, :action, :user_name, :user_empid,
             :time_taken, :mttr, :sla_status, :rca_summary, :finops_team, :finops_owner, :details, :itsm_ticket_id)
        """, {
            "timestamp": timestamp, "ticket_id": ticket_id, "pipeline": pipeline, "run_id": run_id,
            "action": action, "user_name": user_name, "user_empid": user_empid,
            "time_taken": time_taken_seconds, "mttr": mttr_minutes, "sla_status": sla_status,
            "rca_summary": rca_summary, "finops_team": finops_team, "finops_owner": finops_owner,
            "details": details, "itsm_ticket_id": itsm_ticket_id
        })
        logger.info(f"Audit logged: {action} for {ticket_id}")
    except Exception as e:
        logger.error(f"Failed to log audit: {e}")

# --- Blob Upload Helper Function ---
def upload_payload_to_blob(ticket_id: str, payload: dict) -> Optional[str]:
    """Uploads the raw payload to Azure Blob Storage and logs to audit trail."""
    if not (blob_service_client and AZURE_BLOB_ENABLED):
        return None
    try:
        blob_name = f"{datetime.utcnow().strftime('%Y-%m-%d')}/{ticket_id}-payload.json"
        blob_client = blob_service_client.get_blob_client(container=AZURE_BLOB_CONTAINER_NAME, blob=blob_name)
        payload_bytes = json.dumps(payload, indent=2).encode('utf-8')
        with BytesIO(payload_bytes) as data_stream:
            blob_client.upload_blob(data_stream, overwrite=True)
        url = blob_client.url
        logger.info("Uploaded payload for %s to blob: %s", ticket_id, url)
        log_audit(ticket_id=ticket_id, action="Blob Payload Saved", details=f"Raw payload saved to: {url}")
        return url
    except Exception as e:
        logger.error(f"Failed to upload blob for %s: %s", ticket_id, e)
        log_audit(ticket_id=ticket_id, action="Blob Upload Failed", details=str(e))
        return None

def extract_finops_tags(resource_name: str, resource_type: str = "adf"):
    """Extract FinOps tags from ADF pipeline or Databricks job/cluster name"""
    tags = {"team": "Unknown", "owner": "Unknown", "cost_center": "Unknown"}
    if not resource_name: return tags
    resource_lower = resource_name.lower()

    # Enhanced tag extraction with resource type consideration
    if "finance" in resource_lower or "fin" in resource_lower:
        tags.update(team="Finance", cost_center="CC-FIN-001")
    elif "data" in resource_lower or "analytics" in resource_lower or "etl" in resource_lower:
        tags.update(team="DataEngineering", cost_center="CC-DATA-001")
    elif "sales" in resource_lower:
        tags.update(team="Sales", cost_center="CC-SALES-001")
    elif "hr" in resource_lower:
        tags.update(team="HumanResources", cost_center="CC-HR-001")
    elif "marketing" in resource_lower or "mkt" in resource_lower:
        tags.update(team="Marketing", cost_center="CC-MKT-001")
    elif "ml" in resource_lower or "machine" in resource_lower or "model" in resource_lower:
        tags.update(team="MachineLearning", cost_center="CC-ML-001")
    else:
        tags.update(team="Operations", cost_center="CC-OPS-001")

    tags["owner"] = f"{tags['team'].lower()}@company.com"
    tags["resource_type"] = resource_type
    return tags

# --- RCA Logic (AI fully controls) ---
try:
    import google.generativeai as genai
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    genai = None
    logger.warning("Gemini not initialized: %s", e)

def call_ai_for_rca(description: str, source_type: str = "adf"):
    """
    Generate RCA using AI for both ADF and Databricks errors
    source_type: "adf" or "databricks"
    """
    if not (genai and GEMINI_API_KEY):
        return None

    # Define error types based on source
    if source_type == "databricks":
        error_types = """[DatabricksClusterStartFailure, DatabricksJobExecutionError, DatabricksNotebookExecutionError,
DatabricksLibraryInstallationError, DatabricksPermissionDenied, DatabricksResourceExhausted,
DatabricksDriverNotResponding, DatabricksSparkException, DatabricksTableNotFound,
DatabricksAuthenticationError, DatabricksTimeoutError, UnknownError]"""
        service_name = "Databricks"
    else:
        error_types = """[UserErrorSourceBlobNotExists, UserErrorColumnNameInvalid, GatewayTimeout,
HttpConnectionFailed, InternalServerError, UserErrorInvalidDataType, UserErrorSqlOperationFailed,
AuthenticationError, ThrottlingError, UnknownError]"""
        service_name = "Azure Data Factory"

    service_prefixed_desc = f"[{service_name.upper()}] {description}"

    prompt = f"""
You are an expert AIOps Root Cause Analysis assistant for {service_name}.

CRITICAL: This error is from {service_name.upper()}, NOT from any other Azure service.
DO NOT mention Azure Data Factory if this is a Databricks error.
DO NOT mention Databricks if this is an Azure Data Factory error.

Analyze the following {service_name} failure message and provide a precise, data-driven Root Cause Analysis.

Your `error_type` MUST be a machine-readable code. Choose from this list:
{error_types}

Return a STRICT JSON in this format (NO markdown, NO extra text):
{{
  "root_cause": "Clear, concise explanation of what went wrong in {service_name}",
  "error_type": "...",
  "affected_entity": "Name of the specific resource/component that failed",
  "severity": "Critical|High|Medium|Low",
  "priority": "P1|P2|P3|P4",
  "confidence": "Very High|High|Medium|Low",
  "recommendations": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
  "auto_heal_possible": true|false
}}

Severity Guidelines:
- Critical: Production data loss, complete service outage, security breach
- High: Major functionality broken, significant business impact
- Medium: Partial functionality affected, workarounds available
- Low: Minor issues, minimal business impact

Priority Guidelines:
- P1: Fix immediately (< 15 min) - Production down, Critical severity
- P2: Fix within 30 min - High severity, major impact
- P3: Fix within 2 hours - Medium severity
- P4: Fix within 24 hours - Low severity

IMPORTANT: In your root_cause, explicitly mention "{service_name}" (not any other service).
Analyze logically - don't invent details. Use only what's in the message.
Be specific about the affected entity (cluster name, job name, table name, etc.)

Error Message:
\"\"\"{service_prefixed_desc}\"\"\"
"""
    try:
        model = genai.GenerativeModel(MODEL_ID)
        resp = model.generate_content(prompt)
        text = resp.text.strip().strip("`").replace("json", "").strip()
        return json.loads(text)
    except Exception as e:
        logger.warning("Gemini RCA failed: %s", e)
        return None

def call_ollama_for_rca(description: str, source_type: str = "adf"):
    """
    Generate RCA using Ollama (local LLM like DeepSeek-R1) for both ADF and Databricks errors
    source_type: "adf" or "databricks"
    """
    if not OLLAMA_HOST:
        logger.warning("Ollama host not configured")
        return None

    # Define error types based on source
    if source_type == "databricks":
        error_types = """[DatabricksClusterStartFailure, DatabricksJobExecutionError, DatabricksNotebookExecutionError,
DatabricksLibraryInstallationError, DatabricksPermissionDenied, DatabricksResourceExhausted,
DatabricksDriverNotResponding, DatabricksSparkException, DatabricksTableNotFound,
DatabricksAuthenticationError, DatabricksTimeoutError, UnknownError]"""
        service_name = "Databricks"
    else:
        error_types = """[UserErrorSourceBlobNotExists, UserErrorColumnNameInvalid, GatewayTimeout,
HttpConnectionFailed, InternalServerError, UserErrorInvalidDataType, UserErrorSqlOperationFailed,
AuthenticationError, ThrottlingError, UnknownError]"""
        service_name = "Azure Data Factory"

    service_prefixed_desc = f"[{service_name.upper()}] {description}"

    prompt = f"""
You are an expert AIOps Root Cause Analysis assistant for {service_name}.

CRITICAL: This error is from {service_name.upper()}, NOT from any other Azure service.
DO NOT mention Azure Data Factory if this is a Databricks error.
DO NOT mention Databricks if this is an Azure Data Factory error.

Analyze the following {service_name} failure message and provide a precise, data-driven Root Cause Analysis.

Your `error_type` MUST be a machine-readable code. Choose from this list:
{error_types}

Return a STRICT JSON in this format (NO markdown, NO extra text, NO thinking tags):
{{
  "root_cause": "Clear, concise explanation of what went wrong in {service_name}",
  "error_type": "...",
  "affected_entity": "Name of the specific resource/component that failed",
  "severity": "Critical|High|Medium|Low",
  "priority": "P1|P2|P3|P4",
  "confidence": "Very High|High|Medium|Low",
  "recommendations": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
  "auto_heal_possible": true|false
}}

Severity Guidelines:
- Critical: Production data loss, complete service outage, security breach
- High: Major functionality broken, significant business impact
- Medium: Partial functionality affected, workarounds available
- Low: Minor issues, minimal business impact

Priority Guidelines:
- P1: Fix immediately (< 15 min) - Production down, Critical severity
- P2: Fix within 30 min - High severity, major impact
- P3: Fix within 2 hours - Medium severity
- P4: Fix within 24 hours - Low severity

IMPORTANT: In your root_cause, explicitly mention "{service_name}" (not any other service).
Analyze logically - don't invent details. Use only what's in the message.
Be specific about the affected entity (cluster name, job name, table name, etc.)

Error Message:
\"\"\"{service_prefixed_desc}\"\"\"

Respond with ONLY the JSON object, no thinking tags, no markdown.
"""

    try:
        # Call Ollama API
        url = f"{OLLAMA_HOST.rstrip('/')}/api/generate"
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }

        logger.info(f"[OLLAMA] Calling Ollama at {url} with model {OLLAMA_MODEL}")
        response = requests.post(url, json=payload, timeout=120)

        if response.status_code == 200:
            result = response.json()
            response_text = result.get("response", "")

            # Clean up response - remove thinking tags if present (DeepSeek-R1 specific)
            # DeepSeek-R1 sometimes wraps responses in <think>...</think> tags
            if "<think>" in response_text:
                # Extract only the JSON part after thinking
                parts = response_text.split("</think>")
                if len(parts) > 1:
                    response_text = parts[-1].strip()

            # Clean up markdown if present
            response_text = response_text.strip().strip("`").replace("json", "").strip()

            # Parse JSON
            rca_data = json.loads(response_text)
            logger.info(f"[OLLAMA] Successfully generated RCA using Ollama")
            return rca_data
        else:
            logger.error(f"[OLLAMA] Ollama API returned status {response.status_code}: {response.text}")
            return None

    except requests.exceptions.Timeout:
        logger.error("[OLLAMA] Ollama request timed out (120s)")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"[OLLAMA] Cannot connect to Ollama at {OLLAMA_HOST}: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"[OLLAMA] Failed to parse Ollama response as JSON: {e}")
        logger.error(f"[OLLAMA] Raw response: {response_text[:500]}")
        return None
    except Exception as e:
        logger.warning(f"[OLLAMA] Ollama RCA failed: {e}")
        return None

def derive_priority(sev):
    sev = (sev or "").lower()
    return {"critical":"P1","high":"P2","medium":"P3","low":"P4"}.get(sev,"P3")

def sla_for_priority(p):
    return {"P1":900,"P2":1800,"P3":7200,"P4":86400}.get(p,1800)

def fallback_rca(desc: str, source_type: str = "adf"):
    """Fallback RCA when AI fails"""
    service_name = "Databricks job/cluster" if source_type == "databricks" else "ADF pipeline"
    return {
        "root_cause": f"{service_name} failed. Unable to determine root cause from logs.",
        "error_type": "UnknownError",
        "affected_entity": None,
        "severity": "Medium",
        "priority": "P3",
        "confidence": "Low",
        "recommendations": [f"Inspect {source_type.upper()} logs for more context.", "Check resource health and configurations."],
        "auto_heal_possible": False
    }

def generate_rca_and_recs(desc, source_type="adf"):
    """
    Generate RCA using configured AI provider(s)
    AI_PROVIDER options: 'gemini', 'ollama', 'auto'
    - gemini: Use Google Gemini only
    - ollama: Use local Ollama only
    - auto: Try Ollama first, fallback to Gemini, then to static fallback
    """
    ai = None

    if AI_PROVIDER == "ollama":
        # Use Ollama only
        logger.info(f"[AI-PROVIDER] Using Ollama for RCA generation")
        ai = call_ollama_for_rca(desc, source_type)
        if ai:
            ai.setdefault("priority", derive_priority(ai.get("severity")))
            logger.info("Ollama RCA successful for %s", source_type.upper())
            return ai
        logger.warning("Ollama RCA failed for %s. Using fallback.", source_type.upper())

    elif AI_PROVIDER == "gemini":
        # Use Gemini only
        logger.info(f"[AI-PROVIDER] Using Gemini for RCA generation")
        ai = call_ai_for_rca(desc, source_type)
        if ai:
            ai.setdefault("priority", derive_priority(ai.get("severity")))
            logger.info("Gemini RCA successful for %s", source_type.upper())
            return ai
        logger.warning("Gemini RCA failed for %s. Using fallback.", source_type.upper())

    elif AI_PROVIDER == "auto":
        # Auto mode: Try Ollama first, then Gemini, then fallback
        logger.info(f"[AI-PROVIDER] Auto mode: Trying Ollama first, then Gemini")

        # Try Ollama first
        ai = call_ollama_for_rca(desc, source_type)
        if ai:
            ai.setdefault("priority", derive_priority(ai.get("severity")))
            logger.info("Ollama RCA successful for %s", source_type.upper())
            return ai

        logger.info("[AI-PROVIDER] Ollama failed, trying Gemini...")

        # Try Gemini as fallback
        ai = call_ai_for_rca(desc, source_type)
        if ai:
            ai.setdefault("priority", derive_priority(ai.get("severity")))
            logger.info("Gemini RCA successful for %s", source_type.upper())
            return ai

        logger.warning("Both Ollama and Gemini RCA failed for %s. Using fallback.", source_type.upper())

    else:
        # Unknown provider, default to Gemini
        logger.warning(f"[AI-PROVIDER] Unknown AI_PROVIDER '{AI_PROVIDER}', defaulting to Gemini")
        ai = call_ai_for_rca(desc, source_type)
        if ai:
            ai.setdefault("priority", derive_priority(ai.get("severity")))
            logger.info("Gemini RCA successful for %s", source_type.upper())
            return ai

    # All AI attempts failed, use static fallback
    return fallback_rca(desc, source_type)

# --- ITSM Integration Functions ---
def _get_jira_auth() -> Optional[HTTPBasicAuth]:
    """Returns Jira auth object if configured."""
    if JIRA_USER_EMAIL and JIRA_API_TOKEN:
        return HTTPBasicAuth(JIRA_USER_EMAIL, JIRA_API_TOKEN)
    return None

def create_jira_ticket(ticket_id: str, pipeline: str, rca_data: dict, finops: dict, run_id: str) -> Optional[str]:
    auth = _get_jira_auth()
    if not (JIRA_DOMAIN and auth and JIRA_PROJECT_KEY):
        logger.warning("Jira settings are incomplete. Skipping ticket creation.")
        return None
    url = f"{JIRA_DOMAIN}/rest/api/3/issue"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    description_adf = {
        "type": "doc", "version": 1, "content": [
            {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "AIOps RCA Details"}]},
            {"type": "panel", "attrs": {"panelType": "info"}, "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": f"This ticket was auto-generated by the AIOps RCA system for ticket {ticket_id}."}]}
            ]},
            {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Root Cause Analysis"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": rca_data.get('root_cause', 'N/A')}]},
            {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Recommendations"}]},
            {"type": "bulletList", "content": [
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": rec}]}]}
                for rec in rca_data.get('recommendations', [])
            ]},
            {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Ticket Details"}]},
            {"type": "codeBlock", "attrs": {"language": "json"}, "content": [{
                "type": "text",
                "text": json.dumps({
                    "AIOps_Ticket_ID": ticket_id, "Pipeline_Name": pipeline, "ADF_Run_ID": run_id,
                    "Severity": rca_data.get('severity', 'N/A'), "Priority": rca_data.get('priority', 'N/A'),
                    "Error_Type": rca_data.get('error_type', 'N/A'), "Affected_Entity": rca_data.get('affected_entity', 'N/A'),
                    "FinOps_Team": finops.get('team', 'N/A'), "FinOps_Owner": finops.get('owner', 'N/A'),
                    "FinOps_Cost_Center": finops.get('cost_center', 'N/A')
                }, indent=2)
            }]}
        ]
    }
    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": f"AIOps Alert: {pipeline} failed - {rca_data.get('error_type', 'Unknown Error')}",
            "description": description_adf,
            "issuetype": {"name": "Task"}
        }
    }
    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), auth=auth, timeout=20)
        if r.status_code == 201:
            jira_key = r.json().get('key')
            logger.info(f"Successfully created Jira ticket: {jira_key}")
            return jira_key
        else:
            logger.error(f"ailed to create Jira ticket. Status: {r.status_code}, Response: {r.text}")
            return None
    except Exception as e:
        logger.error(f"Exception while creating Jira ticket: {e}")
        return None

# --- FastAPI App ---
app = FastAPI(title="AIOps RCA Assistant")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- WebSocket manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    async def broadcast(self, message: dict):
        dead = []
        for conn in list(self.active_connections):
            try: await conn.send_json(message)
            except WebSocketDisconnect: dead.append(conn)
        for d in dead: self.disconnect(d)
manager = ConnectionManager()

# --- Slack helpers ---
def post_slack_notification(ticket_id: str, essentials: dict, rca: dict, itsm_ticket_id: str = None):
    if not SLACK_BOT_TOKEN: return None
    title = essentials.get("alertRule") or essentials.get("pipelineName") or "ADF Alert"
    run_id = essentials.get("alertId") or essentials.get("runId") or "N/A"
    root = rca.get("root_cause")
    severity = rca.get("severity", "Medium")
    priority = rca.get("priority", derive_priority(severity))
    recs = rca.get("recommendations", [])
    confidence = rca.get("confidence", "Low")
    error_type = rca.get("error_type", "N/A")
    itsm_info = f"\n*ITSM Ticket:* `{itsm_ticket_id}`" if itsm_ticket_id else ""
    blocks = [
        {"type":"header","text":{"type":"plain_text","text":f"ALERT: {title} - {severity} ({priority})"}},
        {"type":"section", "text": {"type":"mrkdwn", "text": f"*Ticket:* `{ticket_id}`{itsm_info}\n*Run ID:* `{run_id}`\n*Error Type:* `{error_type}`"}},
        {"type":"section", "text": {"type":"mrkdwn", "text": f"*Root Cause:* {root}\n*Confidence:* {confidence}"}},
    ]
    if recs:
        rec_text = "\n".join([f"* {r}" for r in recs])
        blocks.append({"type":"section", "text": {"type":"mrkdwn", "text": f"*Resolution Steps:*\n{rec_text}"}})
    dash_url = f"{PUBLIC_BASE_URL.rstrip('/')}/dashboard"
    blocks.append({
        "type":"actions",
        "elements":[
            {"type":"button","text":{"type":"plain_text","text":"Open in Dashboard"},"url":dash_url, "style": "primary"}
        ]
    })
    payload = {"channel": SLACK_ALERT_CHANNEL, "blocks": blocks, "text": f"Ticket {ticket_id}: {title}"}
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-type": "application/json; charset=utf-8"}
    try:
        r = requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=payload, timeout=10)
        if r.status_code != 200:
            logger.warning("Slack post failed: %s %s", r.status_code, r.text)
            return None
        j = r.json()
        ts = j.get("ts")
        ch = j.get("channel")
        if ts and ch:
            db_execute("UPDATE tickets SET slack_ts=:ts, slack_channel=:ch WHERE id=:id", {"ts": ts, "ch": ch, "id": ticket_id})
        return j
    except Exception as e:
        logger.warning("Slack post exception: %s", e)
    return None

def update_slack_message_on_ack(ticket_id: str, user_name: str):
    if not SLACK_BOT_TOKEN: return
    row = db_query("SELECT * FROM tickets WHERE id=:id", {"id": ticket_id}, one=True)
    if not (row and row.get("slack_ts") and row.get("slack_channel")):
        logger.warning("Cannot update Slack message: Missing slack_ts or channel for %s", ticket_id)
        return
    title = row.get("pipeline", "ADF Alert"); run_id = row.get("run_id", "N/A"); root = row.get("rca_result", "N/A")
    confidence = row.get("confidence", "Low"); error_type = row.get("error_type", "N/A"); itsm_ticket_id = row.get("itsm_ticket_id")
    try: recs = json.loads(row.get("recommendations", "[]"))
    except Exception: recs = []
    itsm_info = f"\n*ITSM Ticket:* `{itsm_ticket_id}`" if itsm_ticket_id else ""
    ack_time = row.get("ack_ts") or datetime.utcnow().isoformat()
    ack_by = user_name or row.get("ack_user", "System")
    blocks = [
        {"type":"header","text":{"type":"plain_text","text":f"{title} - CLOSED"}},
        {"type":"section", "text": {"type":"mrkdwn", "text": f"*Ticket:* `{ticket_id}`{itsm_info}\n*Run ID:* `{run_id}`\n*Status:* `CLOSED`"}},
        {"type":"context", "elements": [{"type": "mrkdwn", "text": f"Closed by *{ack_by}* on {datetime.fromisoformat(ack_time).strftime('%Y-%m-%d %H:%M:%S UTC')}"}]},
        {"type":"divider"},
        {"type":"section", "text": {"type":"mrkdwn", "text": f"*Root Cause:* {root}\n*Confidence:* {confidence}\n*Error Type:* `{error_type}`"}},
    ]
    if recs:
        rec_text = "\n".join([f"* {r}" for r in recs])
        blocks.append({"type":"section", "text": {"type":"mrkdwn", "text": f"*Resolution Steps:*\n{rec_text}"}})
    dash_url = f"{PUBLIC_BASE_URL.rstrip('/')}/dashboard"
    blocks.append({
        "type":"actions",
        "elements":[{"type":"button","text":{"type":"plain_text","text":"Open in Dashboard"},"url":dash_url, "style": "primary"}]
    })
    payload = {
        "channel": row["slack_channel"], "ts": row["slack_ts"],
        "blocks": blocks, "text": f"Ticket {ticket_id}: {title} - CLOSED"
    }
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-type": "application/json; charset=utf-8"}
    try:
        r = requests.post("https://slack.com/api/chat.update", headers=headers, json=payload, timeout=10)
        if r.status_code != 200:
            logger.warning("Slack update failed: %s %s", r.status_code, r.text)
        else:
            logger.info(f"Slack message updated for ticket {ticket_id}")
    except Exception as e:
        logger.warning("Slack update post exception: %s", e)

# --- Helper: resilient POST (for Logic App 502s) ---
def _http_post_with_retries(url: str, payload: dict, timeout: int = 60, retries: int = 3, backoff: float = 1.5):
    last = None
    for attempt in range(1, retries+1):
        try:
            r = requests.post(url, json=payload, timeout=timeout)
            if r.status_code < 500:
                return r
            last = r
        except Exception as e:
            last = e
        time.sleep(backoff * attempt)
    if isinstance(last, requests.Response):
        return last
    raise last if last else RuntimeError("HTTP post failed with unknown error")

# --- Auto-Remediation Functions ---

async def get_azure_access_token():
    """
    Get Azure AD access token for ADF API calls
    Uses Managed Identity or Service Principal
    """
    try:
        # Try Managed Identity first (for Azure App Service)
        msi_endpoint = os.getenv("MSI_ENDPOINT")
        msi_secret = os.getenv("MSI_SECRET")

        if msi_endpoint and msi_secret:
            response = requests.get(
                msi_endpoint,
                params={"resource": "https://management.azure.com/", "api-version": "2019-08-01"},
                headers={"X-IDENTITY-HEADER": msi_secret},
                timeout=5
            )
            return response.json()["access_token"]
        elif AZURE_TENANT_ID and AZURE_CLIENT_ID and AZURE_CLIENT_SECRET:
            # Service Principal fallback
            token_url = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/token"
            data = {
                "grant_type": "client_credentials",
                "client_id": AZURE_CLIENT_ID,
                "client_secret": AZURE_CLIENT_SECRET,
                "resource": "https://management.azure.com/"
            }
            response = requests.post(token_url, data=data, timeout=5)
            return response.json()["access_token"]
    except Exception as e:
        logger.error(f"Failed to get Azure access token: {e}")
    return None


async def trigger_auto_remediation(ticket_id: str, pipeline_name: str, error_type: str,
                                     original_run_id: str, attempt_number: int = 1):
    """
    Triggers auto-remediation via Azure Logic App
    Returns: dict with success status and remediation_run_id
    """
    logger.info(f"[AUTO-REM] Triggering auto-remediation for {ticket_id}, error: {error_type}, attempt: {attempt_number}")

    # Check if error is remediable
    if error_type not in REMEDIABLE_ERRORS:
        logger.info(f"[AUTO-REM] Error type {error_type} is not auto-remediable")
        return {"success": False, "message": "Error type not remediable"}

    remediation_config = REMEDIABLE_ERRORS[error_type]

    # Check retry limits
    if attempt_number > remediation_config["max_retries"]:
        logger.warning(f"[AUTO-REM] Max retries ({remediation_config['max_retries']}) exceeded for {ticket_id}")
        return {"success": False, "message": "Max retries exceeded"}

    # Get playbook URL
    playbook_url = remediation_config["playbook_url"]
    if not playbook_url:
        logger.error(f"[AUTO-REM] No playbook URL configured for {error_type}")
        return {"success": False, "message": "Playbook URL not configured"}

    # Calculate backoff delay
    if attempt_number > 1:
        backoff_index = attempt_number - 2
        if backoff_index < len(remediation_config["backoff_seconds"]):
            delay = remediation_config["backoff_seconds"][backoff_index]
            logger.info(f"[AUTO-REM] Waiting {delay}s before retry attempt {attempt_number}")
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
        # Call Logic App
        response = _http_post_with_retries(playbook_url, payload, timeout=30, retries=3)

        if response and response.status_code == 200:
            response_data = response.json()
            remediation_run_id = response_data.get("run_id", "N/A")

            # Store remediation attempt
            db_execute('''INSERT INTO remediation_attempts
                        (ticket_id, original_run_id, remediation_run_id, attempt_number,
                         status, error_type, remediation_action, logic_app_response, started_at)
                        VALUES (:ticket_id, :original_run_id, :remediation_run_id, :attempt_number,
                         :status, :error_type, :remediation_action, :logic_app_response, :started_at)''',
                     {"ticket_id": ticket_id, "original_run_id": original_run_id, "remediation_run_id": remediation_run_id,
                      "attempt_number": attempt_number, "status": "in_progress", "error_type": error_type,
                      "remediation_action": remediation_config["action"], "logic_app_response": json.dumps(response_data),
                      "started_at": datetime.now(timezone.utc).isoformat()})

            # Update ticket
            db_execute('''UPDATE tickets
                        SET remediation_status = :status,
                            remediation_run_id = :run_id,
                            remediation_attempts = :attempts,
                            remediation_last_attempt_at = :last_attempt
                        WHERE id = :id''',
                     {"status": "in_progress", "run_id": remediation_run_id, "attempts": attempt_number,
                      "last_attempt": datetime.now(timezone.utc).isoformat(), "id": ticket_id})

            # Log audit trail
            log_audit(
                ticket_id=ticket_id, action="auto_remediation_triggered", pipeline=pipeline_name,
                run_id=remediation_run_id, user_name="AI_AUTO_HEAL", user_empid="AUTO_REM_001",
                details=json.dumps({"attempt": attempt_number, "action": remediation_config["action"], "error_type": error_type})
            )

            logger.info(f"[AUTO-REM] Successfully triggered for {ticket_id}, remediation_run_id: {remediation_run_id}")

            # Send Slack notification
            await send_slack_remediation_started(ticket_id, pipeline_name, attempt_number, remediation_config["max_retries"])

            # Broadcast to dashboard
            try:
                await manager.broadcast({
                    "event": "remediation_started",
                    "ticket_id": ticket_id,
                    "attempt": attempt_number,
                    "remediation_run_id": remediation_run_id
                })
            except Exception:
                pass

            # Start monitoring in background
            asyncio.create_task(monitor_remediation_run(
                ticket_id, pipeline_name, remediation_run_id,
                original_run_id, error_type, attempt_number
            ))

            return {"success": True, "remediation_run_id": remediation_run_id}
        else:
            logger.error(f"[AUTO-REM] Logic App returned error: {response.status_code if response else 'No response'}")
            return {"success": False, "message": f"Logic App error: {response.status_code if response else 'No response'}"}

    except Exception as e:
        logger.exception(f"[AUTO-REM] Error triggering auto-remediation: {e}")
        return {"success": False, "message": str(e)}


async def monitor_remediation_run(ticket_id: str, pipeline_name: str,
                                    remediation_run_id: str, original_run_id: str,
                                    error_type: str, attempt_number: int):
    """
    Background task to monitor ADF pipeline re-run status
    Polls every 30 seconds until completion
    """
    logger.info(f"[AUTO-REM] Starting monitoring for remediation run {remediation_run_id}")

    if not all([AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP, AZURE_DATA_FACTORY_NAME]):
        logger.warning("[AUTO-REM] Azure ADF monitoring not configured, skipping monitoring")
        return

    max_poll_duration = 3600  # 1 hour max
    poll_interval = 30  # 30 seconds
    elapsed = 0

    # ADF REST API endpoint
    api_url = (f"https://management.azure.com/subscriptions/{AZURE_SUBSCRIPTION_ID}"
               f"/resourceGroups/{AZURE_RESOURCE_GROUP}/providers/Microsoft.DataFactory"
               f"/factories/{AZURE_DATA_FACTORY_NAME}/pipelineruns/{remediation_run_id}"
               f"?api-version=2018-06-01")

    # Get Azure access token
    access_token = await get_azure_access_token()
    if not access_token:
        logger.error("[AUTO-REM] Failed to get Azure access token, cannot monitor remediation")
        return

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    while elapsed < max_poll_duration:
        try:
            response = requests.get(api_url, headers=headers, timeout=10)

            if response.status_code == 200:
                run_data = response.json()
                status = run_data.get("status")  # InProgress, Succeeded, Failed, Cancelled

                logger.info(f"[AUTO-REM] Remediation run {remediation_run_id} status: {status}")

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

            elif response.status_code == 401:
                # Token expired, refresh it
                logger.info("[AUTO-REM] Access token expired, refreshing...")
                access_token = await get_azure_access_token()
                if access_token:
                    headers["Authorization"] = f"Bearer {access_token}"
            else:
                logger.error(f"[AUTO-REM] Failed to get pipeline status: {response.status_code}")

        except Exception as e:
            logger.exception(f"[AUTO-REM] Error monitoring remediation run: {e}")

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    # Timeout reached
    logger.warning(f"[AUTO-REM] Monitoring timeout reached for {remediation_run_id}")
    await handle_remediation_timeout(ticket_id, remediation_run_id)


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
    logger.info(f"[AUTO-REM] ✅ Auto-remediation succeeded for {ticket_id}")

    now = datetime.now(timezone.utc).isoformat()

    # Update remediation attempt record
    db_execute('''UPDATE remediation_attempts
                SET status = :status, completed_at = :completed_at,
                    duration_seconds = CAST((julianday(:completed_at) - julianday(started_at)) * 86400 AS INTEGER)
                WHERE ticket_id = :ticket_id AND remediation_run_id = :remediation_run_id''',
             {"status": "succeeded", "completed_at": now, "ticket_id": ticket_id, "remediation_run_id": remediation_run_id})

    # Get ticket details
    row = db_query("SELECT * FROM tickets WHERE id = :id", {"id": ticket_id}, one=True)
    if not row:
        logger.error(f"[AUTO-REM] Ticket {ticket_id} not found")
        return

    start_ts = datetime.fromisoformat(row["timestamp"]) if row.get("timestamp") else datetime.now(timezone.utc)
    diff = int((datetime.now(timezone.utc) - start_ts).total_seconds())
    mttr_minutes = round(diff / 60, 2)
    sla_seconds = int(row.get("sla_seconds", 1800))
    sla_status = "Met" if diff <= sla_seconds else "Breached"

    # Update ticket status to auto-remediated
    db_execute('''UPDATE tickets
                SET status = :status,
                    remediation_status = :rem_status,
                    ack_user = :ack_user,
                    ack_empid = :ack_empid,
                    ack_ts = :ack_ts,
                    ack_seconds = :ack_seconds,
                    sla_status = :sla_status
                WHERE id = :id''',
             {"status": "acknowledged", "rem_status": "succeeded", "ack_user": "AI_AUTO_HEAL",
              "ack_empid": "AUTO_REM_001", "ack_ts": now, "ack_seconds": diff, "sla_status": sla_status, "id": ticket_id})

    # Log audit trail
    log_audit(
        ticket_id=ticket_id, action="auto_remediation_success", pipeline=pipeline_name,
        run_id=remediation_run_id, user_name="AI_AUTO_HEAL", user_empid="AUTO_REM_001",
        time_taken_seconds=diff, mttr_minutes=mttr_minutes, sla_status=sla_status,
        rca_summary=(row.get("rca_result", "")[:500] if row.get("rca_result") else ""),
        finops_team=row.get("finops_team"), finops_owner=row.get("finops_owner"),
        details=json.dumps({
            "attempt_number": attempt_number,
            "original_run_id": original_run_id,
            "remediation_run_id": remediation_run_id
        }),
        itsm_ticket_id=row.get("itsm_ticket_id")
    )

    # Close Jira ticket (if enabled)
    if row.get('itsm_ticket_id') and ITSM_TOOL == "jira":
        try:
            await close_jira_ticket_auto(row['itsm_ticket_id'], ticket_id, remediation_run_id, attempt_number)
        except Exception as e:
            logger.error(f"[AUTO-REM] Failed to close Jira ticket: {e}")

    # Update Slack message
    if row.get("slack_channel") and row.get("slack_ts"):
        await update_slack_message_on_remediation_success(
            row['slack_channel'], row['slack_ts'], ticket_id, pipeline_name,
            remediation_run_id, attempt_number, mttr_minutes
        )

    # Broadcast to dashboard
    try:
        await manager.broadcast({
            "event": "status_update",
            "ticket_id": ticket_id,
            "new_status": "acknowledged",
            "user": "AI_AUTO_HEAL",
            "remediation_success": True
        })
    except Exception:
        pass

    logger.info(f"[AUTO-REM] Auto-remediation success handling completed for {ticket_id}")


async def handle_remediation_failure(ticket_id: str, pipeline_name: str,
                                      remediation_run_id: str, original_run_id: str,
                                      error_type: str, attempt_number: int,
                                      run_data: dict):
    """
    Called when remediation pipeline run fails
    - Checks if retries available
    - Triggers retry or escalates to manual
    """
    logger.warning(f"[AUTO-REM] ❌ Auto-remediation attempt {attempt_number} failed for {ticket_id}")

    now = datetime.now(timezone.utc).isoformat()
    failure_reason = run_data.get("message", "Unknown failure")

    # Update remediation attempt
    db_execute('''UPDATE remediation_attempts
                SET status = :status, completed_at = :completed_at, failure_reason = :failure_reason,
                    duration_seconds = CAST((julianday(:completed_at) - julianday(started_at)) * 86400 AS INTEGER)
                WHERE ticket_id = :ticket_id AND remediation_run_id = :remediation_run_id''',
             {"status": "failed", "completed_at": now, "failure_reason": failure_reason,
              "ticket_id": ticket_id, "remediation_run_id": remediation_run_id})

    # Log audit trail for failed attempt
    log_audit(
        ticket_id=ticket_id, action="auto_remediation_attempt_failed", pipeline=pipeline_name,
        run_id=remediation_run_id, user_name="AI_AUTO_HEAL", user_empid="AUTO_REM_001",
        details=json.dumps({"attempt": attempt_number, "error_type": error_type, "failure_reason": failure_reason})
    )

    # Check if we can retry
    if error_type in REMEDIABLE_ERRORS:
        max_retries = REMEDIABLE_ERRORS[error_type]["max_retries"]

        if attempt_number < max_retries:
            # Retry available
            logger.info(f"[AUTO-REM] Retrying auto-remediation (attempt {attempt_number + 1}/{max_retries})")

            # Send Slack notification about retry
            await send_slack_remediation_retry(ticket_id, pipeline_name, attempt_number + 1, max_retries)

            # Trigger next attempt
            await trigger_auto_remediation(
                ticket_id, pipeline_name, error_type,
                original_run_id, attempt_number + 1
            )
        else:
            # Max retries exceeded
            await handle_max_retries_exceeded(ticket_id, pipeline_name, error_type, failure_reason)
    else:
        await handle_max_retries_exceeded(ticket_id, pipeline_name, error_type, failure_reason)


async def handle_max_retries_exceeded(ticket_id: str, pipeline_name: str,
                                        error_type: str, failure_reason: str):
    """
    Called when all retry attempts exhausted
    Escalates to manual intervention
    """
    logger.error(f"[AUTO-REM] Max retries exceeded for {ticket_id}, escalating to manual intervention")

    now = datetime.now(timezone.utc).isoformat()

    # Update ticket
    db_execute('''UPDATE tickets
                SET remediation_status = :status,
                    status = :ticket_status
                WHERE id = :id''',
             {"status": "max_retries_exceeded", "ticket_status": "open", "id": ticket_id})

    # Get ticket details
    row = db_query("SELECT * FROM tickets WHERE id = :id", {"id": ticket_id}, one=True)
    if not row:
        return

    # Log audit trail
    log_audit(
        ticket_id=ticket_id, action="auto_remediation_max_retries_exceeded", pipeline=pipeline_name,
        user_name="AI_AUTO_HEAL", user_empid="AUTO_REM_001",
        details=json.dumps({
            "error_type": error_type,
            "failure_reason": failure_reason,
            "attempts": row.get('remediation_attempts', 0)
        }),
        itsm_ticket_id=row.get("itsm_ticket_id")
    )

    # Send Slack escalation alert
    if row.get("slack_channel") and row.get("slack_ts"):
        await send_slack_escalation_alert(
            row['slack_channel'], row['slack_ts'], ticket_id, pipeline_name,
            error_type, row.get('remediation_attempts', 0), failure_reason
        )

    # Broadcast to dashboard
    try:
        await manager.broadcast({
            "event": "status_update",
            "ticket_id": ticket_id,
            "new_status": "open",
            "remediation_failed": True,
            "escalated": True
        })
    except Exception:
        pass


async def handle_remediation_timeout(ticket_id: str, remediation_run_id: str):
    """
    Called when monitoring timeout is reached
    """
    logger.warning(f"[AUTO-REM] Monitoring timeout for {ticket_id}, remediation_run_id: {remediation_run_id}")

    db_execute('''UPDATE remediation_attempts
                SET status = :status, failure_reason = :failure_reason
                WHERE ticket_id = :ticket_id AND remediation_run_id = :remediation_run_id''',
             {"status": "timeout", "failure_reason": "Monitoring timeout reached (1 hour)",
              "ticket_id": ticket_id, "remediation_run_id": remediation_run_id})

    log_audit(
        ticket_id=ticket_id, action="auto_remediation_monitoring_timeout",
        run_id=remediation_run_id, user_name="AI_AUTO_HEAL", user_empid="AUTO_REM_001",
        details=json.dumps({"remediation_run_id": remediation_run_id, "reason": "Monitoring timeout"})
    )


# Slack notification functions for auto-remediation

async def send_slack_remediation_started(ticket_id: str, pipeline_name: str,
                                          attempt_number: int, max_retries: int):
    """Sends Slack notification when auto-remediation starts"""
    if not SLACK_BOT_TOKEN:
        return

    row = db_query("SELECT slack_ts, slack_channel FROM tickets WHERE id = :id", {"id": ticket_id}, one=True)
    if not row:
        return

    thread_ts = row.get('slack_ts')
    channel = row.get('slack_channel') or SLACK_ALERT_CHANNEL

    blocks = [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"🤖 *Auto-remediation initiated for `{pipeline_name}`*\n"
                    f"Ticket: {ticket_id}\n"
                    f"Attempt: {attempt_number}/{max_retries}\n"
                    f"Action: Re-running pipeline..."
        }
    }]

    payload = {
        "channel": channel,
        "thread_ts": thread_ts,
        "blocks": blocks,
        "text": f"🤖 Auto-remediation attempt {attempt_number} for {pipeline_name}"
    }
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-type": "application/json; charset=utf-8"}

    try:
        requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"[AUTO-REM] Failed to send Slack remediation start notification: {e}")


async def send_slack_remediation_retry(ticket_id: str, pipeline_name: str,
                                         attempt_number: int, max_retries: int):
    """Sends Slack notification for retry attempts"""
    if not SLACK_BOT_TOKEN:
        return

    row = db_query("SELECT slack_ts, slack_channel FROM tickets WHERE id = :id", {"id": ticket_id}, one=True)
    if not row:
        return

    thread_ts = row.get('slack_ts')
    channel = row.get('slack_channel') or SLACK_ALERT_CHANNEL

    blocks = [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"🔄 *Retry attempt {attempt_number}/{max_retries}*\n"
                    f"Previous attempt failed, retrying auto-remediation for `{pipeline_name}`..."
        }
    }]

    payload = {
        "channel": channel,
        "thread_ts": thread_ts,
        "blocks": blocks,
        "text": f"🔄 Retry attempt {attempt_number} for {pipeline_name}"
    }
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-type": "application/json; charset=utf-8"}

    try:
        requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"[AUTO-REM] Failed to send Slack retry notification: {e}")


async def update_slack_message_on_remediation_success(channel: str, ts: str,
                                                        ticket_id: str, pipeline_name: str,
                                                        remediation_run_id: str, attempt_number: int,
                                                        mttr_minutes: float):
    """Updates original Slack alert message with success status"""
    if not SLACK_BOT_TOKEN:
        return

    try:
        # Get original message
        headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
        result = requests.get(
            "https://slack.com/api/conversations.history",
            headers=headers,
            params={"channel": channel, "latest": ts, "limit": 1, "inclusive": "true"},
            timeout=10
        )

        if result.status_code == 200 and result.json().get("ok"):
            messages = result.json().get("messages", [])
            original_blocks = messages[0].get("blocks", []) if messages else []

            # Add success header
            success_blocks = [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "✅ Auto-Remediation Successful"}
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

            payload = {
                "channel": channel,
                "ts": ts,
                "blocks": updated_blocks,
                "text": f"✅ Auto-remediation successful for {pipeline_name}"
            }

            requests.post(
                "https://slack.com/api/chat.update",
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-type": "application/json"},
                json=payload,
                timeout=10
            )
    except Exception as e:
        logger.error(f"[AUTO-REM] Failed to update Slack message: {e}")


async def send_slack_escalation_alert(channel: str, ts: str, ticket_id: str,
                                        pipeline_name: str, error_type: str,
                                        attempts: int, failure_reason: str):
    """Sends Slack alert when auto-remediation fails after max retries"""
    if not SLACK_BOT_TOKEN:
        return

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "⚠️ Auto-Remediation Failed - Manual Intervention Required"}
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
        }
    ]

    dash_url = f"{PUBLIC_BASE_URL.rstrip('/')}/dashboard?ticket={ticket_id}"
    blocks.append({
        "type": "actions",
        "elements": [{
            "type": "button",
            "text": {"type": "plain_text", "text": "View in Dashboard"},
            "url": dash_url,
            "style": "danger"
        }]
    })

    payload = {
        "channel": channel,
        "thread_ts": ts,
        "blocks": blocks,
        "text": f"⚠️ Auto-remediation failed for {pipeline_name} after {attempts} attempts"
    }
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-type": "application/json; charset=utf-8"}

    try:
        requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"[AUTO-REM] Failed to send Slack escalation alert: {e}")


async def close_jira_ticket_auto(jira_ticket_id: str, ticket_id: str,
                                   remediation_run_id: str, attempt_number: int):
    """Automatically closes Jira ticket with remediation details"""
    if not all([JIRA_DOMAIN, JIRA_USER_EMAIL, JIRA_API_TOKEN]):
        logger.warning("[AUTO-REM] Jira not configured, skipping auto-close")
        return

    # Add comment with remediation details
    comment_url = f"{JIRA_DOMAIN}/rest/api/3/issue/{jira_ticket_id}/comment"
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
                        "text": "✅ Auto-Remediation Successful",
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
            auth=(JIRA_USER_EMAIL, JIRA_API_TOKEN),
            headers={"Content-Type": "application/json"},
            json=comment_payload,
            timeout=10
        )

        # Transition to Done
        transition_url = f"{JIRA_DOMAIN}/rest/api/3/issue/{jira_ticket_id}/transitions"
        transition_payload = {"transition": {"id": "31"}}  # May need adjustment
        requests.post(
            transition_url,
            auth=(JIRA_USER_EMAIL, JIRA_API_TOKEN),
            headers={"Content-Type": "application/json"},
            json=transition_payload,
            timeout=10
        )

        logger.info(f"[AUTO-REM] Jira ticket {jira_ticket_id} auto-closed")

    except Exception as e:
        logger.error(f"[AUTO-REM] Failed to auto-close Jira ticket: {e}")

# --- SIMPLIFIED: Ticket State Function ---
async def perform_close_from_jira(ticket_id: str, row: dict, user_name: str, user_empid: str, details: str):
    """Internal function to move a ticket to 'acknowledged' (Closed) from a Jira Webhook."""
    if row.get("status") == "acknowledged":
        logger.info(f"Jira Webhook: Ticket {ticket_id} is already closed. Ignoring.")
        return

    logger.info(f"PERFORM_CLOSE (from Jira): Closing {ticket_id} for user {user_name}...")
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    start_ts = datetime.fromisoformat(row["timestamp"]) if row.get("timestamp") else now
    diff = int((now - start_ts).total_seconds())
    mttr_minutes = round(diff / 60, 2)
    sla_seconds = int(row.get("sla_seconds", 1800))
    sla_status = "Met" if diff <= sla_seconds else "Breached"
    
    db_execute("""
      UPDATE tickets SET status='acknowledged', ack_user=:u, ack_empid=:e, ack_ts=:t, ack_seconds=:d, sla_status=:s WHERE id=:id
    """, dict(u=user_name, e=user_empid, t=now.isoformat(), d=diff, s=sla_status, id=ticket_id))
    
    log_audit(
        ticket_id=ticket_id, action="Ticket Closed", pipeline=row.get("pipeline"), run_id=row.get("run_id"),
        user_name=user_name, user_empid=user_empid, time_taken_seconds=diff, mttr_minutes=mttr_minutes,
        sla_status=sla_status, rca_summary=row.get("rca_result")[:200] if row.get("rca_result") else "", 
        finops_team=row.get("finops_team"),
        finops_owner=row.get("finops_owner"), details=details, itsm_ticket_id=row.get("itsm_ticket_id")
    )
    try: await manager.broadcast({"event":"status_update","ticket_id":ticket_id,"new_status":"acknowledged", "user": user_name})
    except Exception: pass
    try: update_slack_message_on_ack(ticket_id, user_name)
    except Exception as e: logger.debug(f"Ack Slack update failed for {ticket_id}: {e}")

# --- Authentication Endpoints ---
@app.post("/api/register", response_model=TokenResponse)
async def register(user: UserRegister):
    existing_user = db_query("SELECT * FROM users WHERE email = :email", {"email": user.email}, one=True)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    password_hash = hash_password(user.password)
    created_at = datetime.utcnow().isoformat()
    
    try:
        db_execute("""
            INSERT INTO users (email, password_hash, full_name, created_at)
            VALUES (:email, :password_hash, :full_name, :created_at)
        """, {
            "email": user.email,
            "password_hash": password_hash,
            "full_name": user.full_name,
            "created_at": created_at
        })
        
        access_token = create_access_token(data={"sub": user.email})
        
        logger.info(f"New user registered: {user.email}")
        return TokenResponse(access_token=access_token)
    except Exception as e:
        logger.error(f"Failed to register user: {e}")
        raise HTTPException(status_code=500, detail="Failed to create user")

@app.post("/api/login", response_model=TokenResponse)
async def login(user: UserLogin):
    db_user = db_query("SELECT * FROM users WHERE email = :email", {"email": user.email}, one=True)
    
    if not db_user or not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    db_execute("UPDATE users SET last_login = :last_login WHERE email = :email", {
        "last_login": datetime.utcnow().isoformat(),
        "email": user.email
    })
    
    access_token = create_access_token(data={"sub": user.email})
    
    logger.info(f"User logged in: {user.email}")
    return TokenResponse(access_token=access_token)

@app.get("/api/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    return {
        "email": current_user["email"],
        "full_name": current_user.get("full_name"),
        "created_at": current_user.get("created_at"),
        "last_login": current_user.get("last_login")
    }

# --- Public Endpoints (No Auth Required) ---
@app.get("/")
def root():
    return {"message": "AIOps RCA Assistant running", "db_type": DB_TYPE, 
            "auto_remediation_enabled": AUTO_REMEDIATION_ENABLED, 
            "blob_logging_enabled": AZURE_BLOB_ENABLED, "itsm_integration": ITSM_TOOL}

@app.get("/login", response_class=HTMLResponse)
def login_page():
    try:
        with open("login.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="login.html missing")

# --- DEDUPLICATION ENDPOINT ---
@app.get("/api/check-ticket-exists/{run_id}")
async def check_ticket_exists(run_id: str, x_api_key: Optional[str] = Header(None)):
    """Check if a ticket already exists for this ADF run ID"""
    if x_api_key != RCA_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Clean run_id
    run_id = run_id.strip()
    if not run_id or run_id == "N/A":
        return {"exists": False, "ticket_id": None}
    
    existing = db_query("SELECT id, timestamp, status FROM tickets WHERE run_id = :run_id", 
                        {"run_id": run_id}, one=True)
    
    if existing:
        logger.info(f"Ticket exists for run_id {run_id}: {existing['id']}")
        return {
            "exists": True,
            "ticket_id": existing.get("id"),
            "status": existing.get("status"),
            "timestamp": existing.get("timestamp")
        }
    else:
        logger.info(f"INFO: No existing ticket for run_id {run_id}")
        return {"exists": False, "ticket_id": None}

# --- Azure Monitor Endpoint (NO AUTH - Azure Action Groups don't support headers) ---
@app.post("/azure-monitor")
async def azure_monitor(request: Request):
    """
    Receive alerts directly from Azure Monitor Action Groups

    NOTE: No API key authentication because Azure Monitor Action Groups
    do not support custom headers. Security is provided by:
    1. Non-public endpoint URL (keep it secret)
    2. Azure network security groups (if configured)
    3. Payload validation
    4. Azure subscription access controls
    """

    logger.info("=" * 80)
    logger.info("AZURE MONITOR WEBHOOK RECEIVED (Direct - No Auth)")
    logger.info("=" * 80)

    try:
        body = await request.json()
    except Exception as e:
        logger.error("Invalid JSON body: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Log raw payload preview for debugging
    logger.info("Raw payload preview (first 500 chars):")
    logger.info(json.dumps(body, indent=2)[:500])

    # Use error extractor to parse webhook
    from error_extractors import AzureDataFactoryExtractor

    try:
        pipeline, runid, desc, metadata = AzureDataFactoryExtractor.extract(body)
        logger.info(f"✓ Extracted via AzureDataFactoryExtractor: pipeline={pipeline}, run_id={runid}")
        logger.info(f"✓ Error message length: {len(desc)} chars")
        logic_app_run_id = metadata.get("logic_app_run_id", "N/A")
        processing_mode = "direct_webhook"
    except Exception as e:
        logger.error(f"Error extraction failed: {e}")
        # Fallback to manual extraction
        essentials = body.get("essentials") or body.get("data", {}).get("essentials") or body
        properties = body.get("data", {}).get("context", {}).get("properties", {})
        err = properties.get("error") or properties.get("Error") or {}
        specific_error = None
        if isinstance(err, dict):
            specific_error = (err.get("message") or err.get("Message") or err.get("value") or err.get("Value"))

        desc = (specific_error or properties.get("detailedMessage") or properties.get("ErrorMessage") or
                properties.get("message") or essentials.get("description") or str(body))

        pipeline = (properties.get("PipelineName") or
                    essentials.get("pipelineName") or
                    essentials.get("alertRule") or
                    "ADF Pipeline Failure")
        runid = (properties.get("PipelineRunId") or
                 essentials.get("runId") or
                 essentials.get("alertId"))
        logic_app_run_id = "N/A"
        processing_mode = "direct_webhook_fallback"

    logger.info("ADF Error being sent to Gemini:\n%s", desc[:500])

    # ** DEDUPLICATION CHECK**
    if runid:
        existing = db_query("SELECT id, status FROM tickets WHERE run_id = :run_id",
                           {"run_id": runid}, one=True)
        if existing:
            logger.warning(f"WARNING: DUPLICATE DETECTED: run_id {runid} already has ticket {existing['id']}")
            log_audit(
                ticket_id=existing["id"],
                action="Duplicate Run Detected",
                pipeline=pipeline,
                run_id=runid,
                details=f"Azure Monitor webhook attempted to create duplicate ticket for run_id {runid}. Original ticket: {existing['id']}"
            )
            return JSONResponse({
                "status": "duplicate_ignored",
                "ticket_id": existing["id"],
                "message": f"Ticket already exists for run_id {runid}",
                "existing_status": existing.get("status")
            })

    finops_tags = extract_finops_tags(pipeline)
    rca = generate_rca_and_recs(desc)
    severity = rca.get("severity", "Medium")
    priority = rca.get("priority", derive_priority(severity))
    sla_seconds = sla_for_priority(priority)
    tid = f"ADF-{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    ts = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()

    blob_url = None
    if AZURE_BLOB_ENABLED:
        try:
            blob_url = await asyncio.to_thread(upload_payload_to_blob, tid, body)
        except Exception as e:
            logger.error("Blob upload thread task failed: %s", e)

    affected_entity_value = rca.get("affected_entity")
    if isinstance(affected_entity_value, dict):
        affected_entity_value = json.dumps(affected_entity_value)
    
    ticket_data = dict(
        id=tid, timestamp=ts, pipeline=pipeline, run_id=runid,
        rca_result=rca.get("root_cause"), recommendations=json.dumps(rca.get("recommendations") or []),
        confidence=rca.get("confidence"), severity=severity, priority=priority,
        error_type=rca.get("error_type"), affected_entity=affected_entity_value,
        status="open", sla_seconds=sla_seconds, sla_status="Pending",
        finops_team=finops_tags["team"], finops_owner=finops_tags["owner"], 
        finops_cost_center=finops_tags["cost_center"],
        blob_log_url=blob_url, itsm_ticket_id=None,
        logic_app_run_id=logic_app_run_id, processing_mode=processing_mode
    )
    
    try:
        db_execute("""
        INSERT INTO tickets (id, timestamp, pipeline, run_id, rca_result, recommendations, confidence, severity, priority,
                             error_type, affected_entity, status, sla_seconds, sla_status, 
                             finops_team, finops_owner, finops_cost_center, blob_log_url, itsm_ticket_id,
                             logic_app_run_id, processing_mode)
        VALUES (:id, :timestamp, :pipeline, :run_id, :rca_result, :recommendations, :confidence, :severity, :priority,
                :error_type, :affected_entity, :status, :sla_seconds, :sla_status, 
                :finops_team, :finops_owner, :finops_cost_center, :blob_log_url, :itsm_ticket_id,
                :logic_app_run_id, :processing_mode)
        """, ticket_data)
        logger.info("RCA stored in DB for %s (run_id: %s)", tid, runid)
    except Exception as e:
        logger.error(f"Failed to insert ticket: {e}")
        # If unique constraint violation, it's a race condition duplicate
        if "UNIQUE constraint failed" in str(e) or "duplicate key" in str(e).lower():
            existing = db_query("SELECT id FROM tickets WHERE run_id = :run_id", {"run_id": runid}, one=True)
            return JSONResponse({
                "status": "duplicate_race_condition",
                "ticket_id": existing["id"] if existing else "unknown",
                "message": f"Race condition: Ticket for run_id {runid} was created by another request"
            })
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    log_audit(ticket_id=tid, action="Ticket Created", pipeline=pipeline, run_id=runid,
              rca_summary=rca.get("root_cause")[:200] if rca.get("root_cause") else "", sla_status="Pending",
              finops_team=finops_tags["team"], finops_owner=finops_tags["owner"],
              details=f"Severity: {severity}, Priority: {priority}, Source: Azure Monitor Direct Webhook")

    log_audit(ticket_id=tid, action="Azure Monitor Webhook Received", pipeline=pipeline, run_id=runid,
              details=f"Alert received directly from Azure Monitor Action Group (no Logic App)")
    
    itsm_ticket_id = None
    logger.info(f"ITSM_TOOL setting is: '{ITSM_TOOL}'")
    if ITSM_TOOL == "jira":
        try:
            itsm_ticket_id = await asyncio.to_thread(create_jira_ticket, tid, pipeline, rca, finops_tags, runid)
            if itsm_ticket_id:
                db_execute("UPDATE tickets SET itsm_ticket_id = :itsm_id WHERE id = :tid",
                           {"itsm_id": itsm_ticket_id, "tid": tid})
                log_audit(ticket_id=tid, action="Jira Ticket Created", details=f"Jira ID: {itsm_ticket_id}",
                         itsm_ticket_id=itsm_ticket_id)
                ticket_data["itsm_ticket_id"] = itsm_ticket_id
            else:
                log_audit(ticket_id=tid, action="Jira Ticket Failed",
                          details="Jira settings incomplete or API returned null.")
        except Exception as e:
            logger.error(f"Jira ticket creation thread task failed: {e}")
            log_audit(ticket_id=tid, action="Jira Ticket Failed", details=str(e))

    try:
        await manager.broadcast({"event": "new_ticket", "ticket_id": tid})
    except Exception as e:
        logger.debug("Broadcast failed: %s", e)
    
    try:
        # Create essentials dict for Slack notification
        essentials_for_slack = {"alertRule": pipeline, "runId": runid, "pipelineName": pipeline}
        slack_result = post_slack_notification(tid, essentials_for_slack, rca, itsm_ticket_id)
        if slack_result:
            log_audit(ticket_id=tid, action="Slack Notification Sent", pipeline=pipeline, run_id=runid,
                      details=f"Notification sent to channel: {SLACK_ALERT_CHANNEL}",
                      itsm_ticket_id=itsm_ticket_id)
    except Exception as e:
        logger.debug("Slack notify failure: %s", e)
        log_audit(ticket_id=tid, action="Slack Notification Failed", pipeline=pipeline, run_id=runid,
                  details=f"Error: {str(e)}")

    # Auto-Remediation (if enabled)
    if AUTO_REMEDIATION_ENABLED and rca.get("auto_heal_possible"):
        error_type = rca.get("error_type")
        if error_type in REMEDIABLE_ERRORS:
            logger.info(f"[AUTO-REM] Eligible for auto-remediation: {error_type} for ticket {tid}")
            try:
                # Trigger auto-remediation in background
                asyncio.create_task(trigger_auto_remediation(
                    ticket_id=tid,
                    pipeline_name=pipeline,
                    error_type=error_type,
                    original_run_id=runid or "N/A",
                    attempt_number=1
                ))
                log_audit(ticket_id=tid, action="auto_remediation_eligible", pipeline=pipeline, run_id=runid,
                         details=f"Auto-remediation triggered for error_type: {error_type}")
            except Exception as e:
                logger.error(f"[AUTO-REM] Failed to trigger auto-remediation: {e}")
                log_audit(ticket_id=tid, action="auto_remediation_trigger_failed", pipeline=pipeline, run_id=runid,
                         details=f"Error: {str(e)}")
        else:
            logger.info(f"[AUTO-REM] Error type {error_type} not in REMEDIABLE_ERRORS list")

    logger.info(f"Successfully created ticket {tid} for ADF alert")

    return JSONResponse({
        "status": "success",
        "ticket_id": tid,
        "run_id": runid,
        "pipeline": pipeline,
        "severity": severity,
        "priority": priority,
        "itsm_ticket_id": itsm_ticket_id,
        "message": "Ticket created successfully from Azure Monitor webhook"
    })


###########################################################################################################################
@app.post("/databricks-monitor")
async def databricks_monitor(request: Request):

    # ------------------------------------------
    # STEP 1: Parse raw payload
    # ------------------------------------------
    try:
        body = await request.json()
    except Exception as e:
        logger.error("Invalid JSON body: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    logger.info("=" * 120)
    logger.info("DATABRICKS MONITORING PAYLOAD RECEIVED 🔥")
    logger.info(json.dumps(body, indent=2))
    logger.info("=" * 120)

    # ===================================================================================
    # STEP 2: Azure Monitor → Cluster Failure Path (DatabricksClusters KQL alerts)
    # ===================================================================================
    if "data" in body and "searchResults" in body["data"]:
        try:
            tables = body["data"]["searchResults"]["tables"]
            if tables:
                cols = tables[0]["columns"]
                rows = tables[0]["rows"]

                if rows:
                    colnames = [c["name"] for c in cols]
                    rowdict = dict(zip(colnames, rows[0]))

                    cluster_id = rowdict.get("ClusterId")
                    cluster_name = rowdict.get("ClusterName")
                    state = rowdict.get("State")
                    termination = rowdict.get("TerminationCode")
                    failure_text = rowdict.get("FailureText")

                    error_message = (
                        "Databricks Cluster Failure Detected\n"
                        f"Cluster: {cluster_name}\n"
                        f"ClusterId: {cluster_id}\n"
                        f"State: {state}\n"
                        f"TerminationCode: {termination}\n"
                        f"RawError: {failure_text}"
                    )

                    logger.info(f"🔥 Cluster failure parsed for cluster_id={cluster_id}")

                    return await process_databricks_failure(
                        job_name=f"Cluster Failure: {cluster_name}",
                        run_id=None,
                        job_id=None,
                        cluster_id=cluster_id,
                        error_message=error_message,
                        is_cluster_failure=True
                    )

        except Exception as e:
            logger.error(f"❌ Error parsing Azure Monitor cluster failure payload: {e}")

    # ===================================================================================
    # STEP 3: Databricks Job Failure Handling (Webhook or other job alerts)
    # ===================================================================================

    event_type = body.get("event") or body.get("event_type")
    job_obj = body.get("job", {})
    run_obj = body.get("run", {})

    # Extract job name
    job_name = (
        run_obj.get("run_name")
        or job_obj.get("settings", {}).get("name")
        or body.get("job_name") or body.get("JobName")
        or "Databricks Job"
    )

    # Extract run_id
    run_id = (
        run_obj.get("run_id")
        or body.get("run_id") or body.get("RunId")
        or body.get("job_run_id") or body.get("JobRunId")
        or None
    )

    # Extract job_id
    job_id = (
        run_obj.get("job_id")
        or job_obj.get("job_id")
        or body.get("job_id")
        or None
    )

    # Extract cluster_id
    cluster_id = (
        run_obj.get("cluster_instance", {}).get("cluster_id")
        or body.get("cluster_id")
        or None
    )

    # Initial error message
    error_message = (
        run_obj.get("state", {}).get("state_message")
        or run_obj.get("state_message")
        or body.get("error_message")
        or f"Databricks job event: {event_type}"
    )

    logger.info(f"📌 Job Info: job={job_name}, run_id={run_id}, job_id={job_id}, cluster={cluster_id}")

    # ===================================================================================
    # STEP 4: Fetch detailed error from Databricks API using run_id
    # ===================================================================================
    api_fetch_attempted = False
    api_fetch_success = False

    if run_id:
        api_fetch_attempted = True
        try:
            logger.info(f"🔄 Fetching Databricks API details for run_id={run_id}")
            run_details = fetch_databricks_run_details(run_id)

            if run_details:
                api_fetch_success = True

                extracted_error = extract_error_message(run_details)
                if extracted_error:
                    error_message = extracted_error

                # Update metadata if present
                job_name = run_details.get("run_name") or job_name
                job_id = run_details.get("job_id") or job_id
                cluster_id = run_details.get("cluster_instance", {}).get("cluster_id") or cluster_id

        except Exception as e:
            logger.error(f"❌ Failed API fetch for run_id={run_id}: {e}")

    logger.info("=" * 120)
    logger.info(f"📤 FINAL ERROR SENT TO RCA ENGINE:\n{error_message[:500]}")
    logger.info("=" * 120)

    # ===================================================================================
    # STEP 5: Send to unified failure processor
    # ===================================================================================
    return await process_databricks_failure(
        job_name=job_name,
        run_id=run_id,
        job_id=job_id,
        cluster_id=cluster_id,
        error_message=error_message,
        is_cluster_failure=False
    )

# ====================================================================================================
#  UNIFIED PROCESSOR — Handles both job and cluster failures (100% of your original code preserved)
# ====================================================================================================
async def process_databricks_failure(job_name, run_id, job_id, cluster_id, error_message, is_cluster_failure):

    logger.info(f"Processing {'Cluster' if is_cluster_failure else 'Job'} Failure")

    # -----------------------
    # DUPLICATE CHECK FOR JOB FAILURES
    # -----------------------
    if run_id:
        existing = db_query(
            "SELECT id, status FROM tickets WHERE run_id = :run_id",
            {"run_id": run_id},
            one=True
        )
        if existing:
            logger.warning(f"❗ Duplicate Databricks run detected: run_id={run_id}")
            return {
                "status": "duplicate_ignored",
                "ticket_id": existing["id"],
                "message": f"Ticket already exists for run_id {run_id}"
            }

    # -----------------------
    # FINOPS TAG EXTRACTION
    # -----------------------
    finops_tags = extract_finops_tags(job_name, "databricks")

    # -----------------------
    # RCA GENERATION
    # -----------------------
    rca = generate_rca_and_recs(error_message, source_type="databricks")
    severity = rca.get("severity", "Medium")
    priority = derive_priority(severity)
    sla_seconds = sla_for_priority(priority)

    # -----------------------
    # TICKET CREATION
    # -----------------------
    tid = f"DBX-{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    timestamp = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()

    affected_entity = rca.get("affected_entity")
    if isinstance(affected_entity, dict):
        affected_entity = json.dumps(affected_entity)

    ticket_data = dict(
        id=tid,
        timestamp=timestamp,
        pipeline=job_name,
        run_id=run_id or "N/A",
        rca_result=rca.get("root_cause"),
        recommendations=json.dumps(rca.get("recommendations") or []),
        confidence=rca.get("confidence"),
        severity=severity,
        priority=priority,
        error_type=rca.get("error_type"),
        affected_entity=affected_entity,
        status="open",
        sla_seconds=sla_seconds,
        sla_status="Pending",
        finops_team=finops_tags["team"],
        finops_owner=finops_tags["owner"],
        finops_cost_center=finops_tags["cost_center"],
        blob_log_url=None,
        itsm_ticket_id=None,
        logic_app_run_id="N/A",
        processing_mode="databricks"
    )

    db_execute("""
        INSERT INTO tickets (
            id, timestamp, pipeline, run_id, rca_result, recommendations, confidence,
            severity, priority, error_type, affected_entity, status, sla_seconds, sla_status,
            finops_team, finops_owner, finops_cost_center, blob_log_url, itsm_ticket_id,
            logic_app_run_id, processing_mode
        ) VALUES (
            :id, :timestamp, :pipeline, :run_id, :rca_result, :recommendations, :confidence,
            :severity, :priority, :error_type, :affected_entity, :status, :sla_seconds, :sla_status,
            :finops_team, :finops_owner, :finops_cost_center, :blob_log_url, :itsm_ticket_id,
            :logic_app_run_id, :processing_mode
        )
    """, ticket_data)

    logger.info(f"🎫 Ticket created: {tid}")

    # -----------------------
    # AUDIT LOG
    # -----------------------
    log_audit(
        ticket_id=tid,
        action="Ticket Created",
        pipeline=job_name,
        run_id=run_id or "N/A",
        rca_summary=rca.get("root_cause", "")[:150],
        details=f"Source={'Cluster' if is_cluster_failure else 'Job'} Failure",
        finops_team=finops_tags["team"],
        finops_owner=finops_tags["owner"]
    )

    # -----------------------
    # JIRA TICKET CREATION
    # -----------------------
    if ITSM_TOOL == "jira":
        try:
            itsm_id = await asyncio.to_thread(create_jira_ticket, tid, job_name, rca, finops_tags, run_id)
            if itsm_id:
                db_execute("UPDATE tickets SET itsm_ticket_id = :id WHERE id = :tid",
                           {"id": itsm_id, "tid": tid})
        except Exception as e:
            logger.error(f"Jira error: {e}")

    # -----------------------
    # BROADCAST WEBSOCKET
    # -----------------------
    try:
        await manager.broadcast({"event": "new_ticket", "ticket_id": tid})
    except:
        pass

    # -----------------------
    # SLACK NOTIFICATION
    # -----------------------
    try:
        essentials = {"alertRule": job_name, "runId": run_id, "pipelineName": job_name}
        post_slack_notification(tid, essentials, rca, None)
    except:
        pass

    return {"status": "ticket_created", "ticket_id": tid}

###########################################################################################################################

# --- Protected Endpoints (Require Auth) ---
def _get_ticket_columns():
    return ("id, timestamp, pipeline, run_id, rca_result, recommendations, confidence, severity, priority, "
            "error_type, affected_entity, status, ack_user, ack_empid, ack_ts, ack_seconds, sla_seconds, "
            "sla_status, slack_ts, slack_channel, finops_team, finops_owner, finops_cost_center, itsm_ticket_id, "
            "logic_app_run_id, processing_mode")

@app.get("/api/tickets/{ticket_id}")
async def get_ticket_details(ticket_id: str, current_user: dict = Depends(get_current_user)):
    columns = _get_ticket_columns()
    row = db_query(f"SELECT {columns} FROM tickets WHERE id=:id", {"id": ticket_id}, one=True)
    if not row:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if isinstance(row.get("recommendations"), str):
        try:
            row["recommendations"] = json.loads(row["recommendations"]) if row.get("recommendations") else []
        except Exception:
            row["recommendations"] = [row["recommendations"]]
    return {"ticket": row}

@app.get("/api/open-tickets")
async def api_open_tickets(current_user: dict = Depends(get_current_user)):
    columns = _get_ticket_columns()
    rows = db_query(f"SELECT {columns} FROM tickets WHERE status = 'open' ORDER BY timestamp DESC")
    for r in rows:
        if isinstance(r.get("recommendations"), str):
            try:
                r["recommendations"] = json.loads(r["recommendations"]) if r.get("recommendations") else []
            except Exception:
                r["recommendations"] = [r["recommendations"]]
    return {"tickets": rows}

@app.get("/api/in-progress-tickets")
async def api_in_progress_tickets(current_user: dict = Depends(get_current_user)):
    columns = _get_ticket_columns()
    rows = db_query(f"SELECT {columns} FROM tickets WHERE status = 'in_progress' ORDER BY timestamp DESC")
    for r in rows:
        if isinstance(r.get("recommendations"), str):
            try:
                r["recommendations"] = json.loads(r["recommendations"]) if r.get("recommendations") else []
            except Exception:
                r["recommendations"] = [r["recommendations"]]
    return {"tickets": rows}

@app.get("/api/closed-tickets")
async def api_closed_tickets(current_user: dict = Depends(get_current_user)):
    columns = _get_ticket_columns()
    rows = db_query(f"SELECT {columns} FROM tickets WHERE status = 'acknowledged' ORDER BY ack_ts DESC")
    for r in rows:
        if isinstance(r.get("recommendations"), str):
            try:
                r["recommendations"] = json.loads(r["recommendations"]) if r.get("recommendations") else []
            except Exception:
                r["recommendations"] = [r["recommendations"]]
    return {"tickets": rows}

@app.get("/api/summary")
async def api_summary(current_user: dict = Depends(get_current_user)):
    tickets = db_query("SELECT * FROM tickets")
    total = len(tickets)
    open_tickets_list = [t for t in tickets if t.get("status") != "acknowledged"]
    ack_tickets = [t for t in tickets if t.get("status") == "acknowledged"]
    breached = [t for t in tickets if str(t.get("sla_status", "")).lower() == "breached"]
    ack_times = []
    for t in ack_tickets:
        if t.get("ack_seconds"):
            ack_times.append(t.get("ack_seconds"))
        elif t.get("timestamp") and t.get("ack_ts"):
            try:
                start = datetime.fromisoformat(t["timestamp"])
                end = datetime.fromisoformat(t["ack_ts"])
                ack_times.append((end - start).total_seconds())
            except Exception:
                pass
    avg_ack = round(sum(ack_times) / len(ack_times), 2) if ack_times else 0
    
    total_audits_result = db_query("SELECT COUNT(*) as count FROM audit_trail", one=True)
    total_audits = total_audits_result.get("count", 0) if total_audits_result else 0
    
    return {
        "total_tickets": total, "open_tickets": len(open_tickets_list), 
        "acknowledged_tickets": len(ack_tickets),
        "sla_breached": len(breached), "avg_ack_time_sec": avg_ack,
        "mttr_min": round(avg_ack / 60, 1) if avg_ack else 0,
        "total_audits": total_audits,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    try:
        with open("dashboard.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="dashboard.html missing")

@app.get("/api/audit-trail")
async def api_audit_trail(action: Optional[str] = Query(None), current_user: dict = Depends(get_current_user)):
    try:
        if action and action != "all":
            if action == "Jira:":
                rows = db_query("SELECT * FROM audit_trail WHERE action LIKE :action ORDER BY timestamp DESC LIMIT 500",
                                {"action": "Jira:%"})
            else:
                rows = db_query("SELECT * FROM audit_trail WHERE action=:action ORDER BY timestamp DESC LIMIT 500",
                                {"action": action})
        else:
            rows = db_query("SELECT * FROM audit_trail ORDER BY timestamp DESC LIMIT 500")
        return {"audits": rows, "count": len(rows)}
    except Exception as e:
        logger.error(f"Failed to fetch audit trail: {e}")
        return {"audits": [], "count": 0, "error": str(e)}

@app.get("/api/audit-summary")
async def api_audit_summary(current_user: dict = Depends(get_current_user)):
    try:
        total_audits = db_query("SELECT COUNT(*) as count FROM audit_trail", one=True)
        action_counts = db_query("""
            SELECT action, COUNT(*) as count 
            FROM audit_trail GROUP BY action ORDER BY count DESC
        """)
        recent_audits = db_query("SELECT * FROM audit_trail ORDER BY timestamp DESC LIMIT 10")
        summary_data = await api_summary(current_user)
        return {
            "total_audits": total_audits.get("count", 0) if total_audits else 0,
            "action_breakdown": action_counts, 
            "recent_audits": recent_audits,
            "open_tickets": summary_data.get("open_tickets", 0),
            "acknowledged_tickets": summary_data.get("acknowledged_tickets", 0),
            "mttr_min": summary_data.get("mttr_min", 0),
            "sla_breached": summary_data.get("sla_breached", 0)
        }
    except Exception as e:
        logger.error(f"Failed to fetch audit summary: {e}")
        return {"total_audits": 0, "action_breakdown": [], "recent_audits": []}

@app.get("/api/config")
async def api_config():
    return { "itsm_tool": ITSM_TOOL, "jira_domain": JIRA_DOMAIN }

# --- Export/Download Endpoints ---
@app.get("/api/export/open-tickets")
async def export_open_tickets(current_user: dict = Depends(get_current_user)):
    columns = _get_ticket_columns()
    rows = db_query(f"SELECT {columns} FROM tickets WHERE status = 'open' ORDER BY timestamp DESC")

    output = StringIO()
    if rows:
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=open_tickets_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"}
    )

@app.get("/api/export/in-progress-tickets")
async def export_in_progress_tickets(current_user: dict = Depends(get_current_user)):
    columns = _get_ticket_columns()
    rows = db_query(f"SELECT {columns} FROM tickets WHERE status = 'in_progress' ORDER BY timestamp DESC")

    output = StringIO()
    if rows:
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=in_progress_tickets_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"}
    )

@app.get("/api/export/closed-tickets")
async def export_closed_tickets(current_user: dict = Depends(get_current_user)):
    columns = _get_ticket_columns()
    rows = db_query(f"SELECT {columns} FROM tickets WHERE status = 'acknowledged' ORDER BY ack_ts DESC")
    
    output = StringIO()
    if rows:
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=closed_tickets_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"}
    )

@app.get("/api/export/audit-trail")
async def export_audit_trail(current_user: dict = Depends(get_current_user)):
    rows = db_query("SELECT * FROM audit_trail ORDER BY timestamp DESC")
    
    output = StringIO()
    if rows:
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=audit_trail_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"}
    )

# --- JIRA WEBHOOK LISTENER ---
@app.post("/webhook/jira")
async def webhook_jira(request: Request):
    logger.info("Jira Webhook: Received a request.")
    if JIRA_WEBHOOK_SECRET:
        secret = request.query_params.get("secret")
        if secret != JIRA_WEBHOOK_SECRET:
            logger.warning(f"Jira Webhook: Invalid secret: {secret}")
            raise HTTPException(status_code=401, detail="Invalid secret")
    else:
        logger.warning("JIRA_WEBHOOK_SECRET is not set. Webhook is insecure.")

    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Jira Webhook: Invalid JSON: {e}")
        return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)

    event = body.get("webhookEvent")
    if event == "jira:issue_updated":
        try:
            issue = body.get("issue", {})
            jira_key = issue.get("key")
            changelog = body.get("changelog", {})
            changed_item = next((item for item in changelog.get("items", []) if item.get("field") == "status"), None)
            if not changed_item:
                logger.info(f"Jira Webhook: Ignoring update for {jira_key} (no status change).")
                return JSONResponse({"status": "ignored", "message": "No status change"})
            new_status_name = changed_item.get("toString", "Unknown")
            new_status_name_lower = new_status_name.lower()
            logger.info(f"Jira Webhook: Received status update for {jira_key}. New status: {new_status_name}")

            ticket = db_query("SELECT * FROM tickets WHERE itsm_ticket_id = :key", {"key": jira_key}, one=True)
            if not ticket:
                logger.warning(f"Jira Webhook: Received update for {jira_key}, but no matching ticket found in local DB.")
                return JSONResponse({"status": "not_found"})

            dynamic_action = f"Jira: {new_status_name.title()}"
            log_audit(ticket_id=ticket["id"], action=dynamic_action, 
                      details=f"Status for {jira_key} changed to '{new_status_name}' in Jira.",
                      itsm_ticket_id=jira_key)
            
            new_local_status = None
            if new_status_name_lower in ["done", "resolved", "closed"]:
                new_local_status = "acknowledged"
            elif new_status_name_lower in ["in progress", "selected for development", "in review"]:
                new_local_status = "in_progress"
            else:
                new_local_status = "open"
            
            # Update ticket status based on Jira status
            if new_local_status == "acknowledged" and ticket.get("status") != "acknowledged":
                user_name = body.get('user', {}).get('displayName', 'Jira User')
                await perform_close_from_jira(
                    ticket_id=ticket["id"], row=ticket, user_name=user_name, user_empid="JIRA",
                    details=f"Ticket closed via Jira Webhook by user {user_name}"
                )
            elif new_local_status == "in_progress" and ticket.get("status") != "in_progress":
                db_execute("UPDATE tickets SET status = 'in_progress' WHERE id = :id", {"id": ticket["id"]})
                logger.info(f"Jira Webhook: Moved ticket {ticket['id']} to IN PROGRESS (Jira: {jira_key}).")
                log_audit(ticket_id=ticket["id"], action="Ticket In Progress",
                         details=f"Status changed to In Progress via Jira",
                         itsm_ticket_id=jira_key)
            elif new_local_status == "open" and ticket.get("status") != "open":
                db_execute("UPDATE tickets SET status = 'open' WHERE id = :id", {"id": ticket["id"]})
                logger.info(f"Jira Webhook: Re-opened ticket {ticket['id']} (Jira: {jira_key}).")

            await manager.broadcast({"event": "status_update", "ticket_id": ticket["id"], "new_status": new_local_status})
            return JSONResponse({"status": "ok"})
        except Exception as e:
            logger.error(f"Jira Webhook: Error processing issue_updated event: {e}")
            return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
            
    return JSONResponse({"status": "ignored", "event": event})

# --- WebSocket ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
#  uvicorn main:app --host 0.0.0.0 --port 8000
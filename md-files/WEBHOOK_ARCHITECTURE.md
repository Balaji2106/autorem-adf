# 🚀 WEBHOOK-BASED ERROR MONITORING ARCHITECTURE

## 📋 TABLE OF CONTENTS
1. [Architecture Overview](#architecture-overview)
2. [Current vs Proposed Flow](#current-vs-proposed-flow)
3. [Service-Specific Endpoints](#service-specific-endpoints)
4. [Azure Data Factory Webhook Setup](#azure-data-factory-webhook-setup)
5. [Databricks Complete Setup](#databricks-complete-setup)
6. [Complete Code Implementation](#complete-code-implementation)
7. [Auto-Remediation Opportunities](#auto-remediation-opportunities)
8. [Testing & Validation](#testing--validation)

---

## 🏗️ ARCHITECTURE OVERVIEW

### Design Principles

```
┌─────────────────────────────────────────────────────────────────┐
│                    UNIFIED ERROR MONITORING                      │
│                                                                  │
│  Each Service → Specific Endpoint → Extract Error → Common RCA  │
└─────────────────────────────────────────────────────────────────┘
```

### Service-Specific Endpoints Strategy

| Service | Endpoint | Webhook Source | Error Extraction |
|---------|----------|----------------|------------------|
| **Azure Data Factory** | `/azure-monitor` | Azure Monitor Action Groups | From alert properties |
| **Databricks Jobs** | `/databricks-monitor` | Databricks Job Notifications | From API + Webhook |
| **Databricks Clusters** | `/databricks-monitor` | Databricks Event Notifications | From event payload |
| **Azure Functions** | `/azure-functions-monitor` | Application Insights | From exceptions |
| **Azure Synapse** | `/synapse-monitor` | Synapse Alerts | From pipeline errors |

**✅ Advantages:**
- **Decoupled**: Each service has its own entry point
- **Extensible**: Easy to add new services
- **Maintainable**: Service-specific error parsing logic
- **Stable**: Changes to one service don't affect others

---

## 🔄 CURRENT VS PROPOSED FLOW

### ❌ CURRENT FLOW (Using Logic Apps)

```
┌─────────────────────┐
│ ADF Pipeline Fails  │
└──────────┬──────────┘
           │
           ↓
┌─────────────────────────────────────┐
│ Azure Monitor Alert Rule            │
│ - Detects failure                   │
│ - Extracts basic info               │
└──────────┬──────────────────────────┘
           │
           ↓
┌─────────────────────────────────────┐
│ Action Group                        │
│ - Triggers Logic App                │
└──────────┬──────────────────────────┘
           │
           ↓
┌─────────────────────────────────────┐
│ Logic App (Intermediary) ⚠️         │  ← UNNECESSARY LAYER
│ - Receives alert                    │
│ - Parses JSON                       │
│ - Formats payload                   │
│ - Adds metadata                     │
│ - HTTP POST to FastAPI              │
└──────────┬──────────────────────────┘
           │ Latency: +2-5 seconds
           │ Reliability: 99.5%
           │ Cost: $$$
           ↓
┌─────────────────────────────────────┐
│ FastAPI /azure-monitor              │
│ - Receives alert from Logic App     │
│ - Extracts error message            │
│ - Generates RCA                     │
└─────────────────────────────────────┘
```

**Problems:**
- ❌ Extra latency (Logic App processing)
- ❌ Additional cost (Logic App execution)
- ❌ More failure points
- ❌ Complex troubleshooting
- ❌ Logic App 502 errors during retries

---

### ✅ PROPOSED FLOW (Direct Webhook)

```
┌─────────────────────┐
│ ADF Pipeline Fails  │
└──────────┬──────────┘
           │
           ↓
┌─────────────────────────────────────┐
│ Azure Monitor Alert Rule            │
│ - Detects failure                   │
│ - Extracts error details            │
└──────────┬──────────────────────────┘
           │
           ↓
┌─────────────────────────────────────┐
│ Action Group                        │
│ - Webhook: https://your-api.com/azure-monitor
│ - Headers: x-api-key: secret       │
└──────────┬──────────────────────────┘
           │ Direct HTTP POST
           │ Latency: <500ms
           │ Reliability: 99.9%
           ↓
┌─────────────────────────────────────┐
│ FastAPI /azure-monitor              │
│ - Receives alert DIRECTLY           │
│ - Extracts error message            │
│ - Generates RCA                     │
│ - Creates ticket                    │
│ - Sends notifications               │
└─────────────────────────────────────┘
```

**Benefits:**
- ✅ Faster response (no Logic App delay)
- ✅ Lower cost (no Logic App charges)
- ✅ Fewer failure points
- ✅ Simpler architecture
- ✅ Easier troubleshooting

---

## 🎯 SERVICE-SPECIFIC ENDPOINTS

### 1. Azure Data Factory - `/azure-monitor`

**Purpose:** Handle ADF pipeline failures from Azure Monitor Action Groups

**Webhook Source:**
```
Azure Monitor Alert Rule → Action Group (Webhook) → /azure-monitor
```

**Error Extraction Strategy:**
```python
# Priority order for error extraction:
1. properties.error.message              # Specific ADF error
2. properties.detailedMessage           # Detailed error info
3. properties.ErrorMessage              # Alternate field
4. essentials.description               # Generic description
5. Full body as fallback                # Last resort
```

**API Key Required:** ✅ Yes (`x-api-key` header)

---

### 2. Databricks Jobs & Clusters - `/databricks-monitor`

**Purpose:** Handle Databricks job/cluster failures from Event Notifications

**Webhook Source:**
```
Databricks Job/Cluster Event → Event Notification → /databricks-monitor
```

**Error Extraction Strategy:**
```python
# For job failures:
1. Fetch from Databricks API using run_id
2. Extract from task.run_output.error    # Real error with stack trace
3. Extract from task.exception.message   # Exception message
4. Fallback to state.state_message       # Generic message

# For cluster failures:
1. Extract from event.cluster.state_message
2. Extract from event.cause              # Cluster termination cause
3. Parse cluster logs URL
```

**API Key Required:** ❌ No (Databricks validates webhook internally)

---

## 📊 AZURE DATA FACTORY WEBHOOK SETUP

### STEP 1: Create Azure Monitor Alert Rule

#### Option A: Azure Portal (Manual)

1. **Navigate to Azure Monitor**
   ```
   Azure Portal → Monitor → Alerts → Alert Rules → + Create
   ```

2. **Configure Scope**
   ```
   Resource Type: Data Factory
   Resource: <your-adf-name>
   ```

3. **Configure Condition**
   ```
   Signal Name: Activity Run Failed
   Operator: Greater than
   Threshold: 0
   Aggregation: Total
   Period: 5 minutes
   Frequency: 1 minute
   ```

4. **Configure Action Group** (See Step 2)

---

#### Option B: Azure CLI (Automated) ⭐ RECOMMENDED

```bash
#!/bin/bash
# create_adf_alert_webhook.sh

# Configuration
RESOURCE_GROUP="rg_techdemo_2025_Q4"
ADF_NAME="your-adf-name"
LOCATION="eastus"
FASTAPI_ENDPOINT="https://your-app.azurewebsites.net/azure-monitor"
API_KEY="your-rca-api-key-here"

# Create Action Group with Webhook
az monitor action-group create \
  --name "ag-adf-rca-webhook" \
  --resource-group "$RESOURCE_GROUP" \
  --short-name "adf-rca" \
  --action webhook "adf-rca-webhook" \
    --uri "$FASTAPI_ENDPOINT" \
    --use-common-alert-schema false

# Get ADF Resource ID
ADF_ID=$(az datafactory show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ADF_NAME" \
  --query id -o tsv)

# Create Alert Rule for Pipeline Failures
az monitor metrics alert create \
  --name "alert-adf-pipeline-failure" \
  --resource-group "$RESOURCE_GROUP" \
  --scopes "$ADF_ID" \
  --condition "total PipelineFailedRuns > 0" \
  --window-size 5m \
  --evaluation-frequency 1m \
  --action "ag-adf-rca-webhook" \
  --description "Alert on ADF pipeline failures - sends to RCA system"

# Create Alert Rule for Activity Failures
az monitor metrics alert create \
  --name "alert-adf-activity-failure" \
  --resource-group "$RESOURCE_GROUP" \
  --scopes "$ADF_ID" \
  --condition "total ActivityFailedRuns > 0" \
  --window-size 5m \
  --evaluation-frequency 1m \
  --action "ag-adf-rca-webhook" \
  --description "Alert on ADF activity failures - sends to RCA system"

echo "✅ Alert rules created successfully!"
echo "Webhook endpoint: $FASTAPI_ENDPOINT"
```

**Run the script:**
```bash
chmod +x create_adf_alert_webhook.sh
./create_adf_alert_webhook.sh
```

---

### STEP 2: Configure Action Group with Custom Headers

Azure Monitor Action Groups **DO NOT support custom headers** (like `x-api-key`) directly in the portal.

**Solution: Use one of these approaches**

#### Approach A: Query Parameter (Simple)

```bash
# In Action Group webhook URL
https://your-app.azurewebsites.net/azure-monitor?api_key=your-secret-key
```

```python
# In FastAPI endpoint
@app.post("/azure-monitor")
async def azure_monitor(request: Request, api_key: Optional[str] = Query(None)):
    if api_key != RCA_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # ... rest of code
```

---

#### Approach B: Logic App as Header Injector (Hybrid)

If you MUST use header-based auth, use a minimal Logic App:

```json
{
  "definition": {
    "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
    "triggers": {
      "manual": {
        "type": "Request",
        "kind": "Http"
      }
    },
    "actions": {
      "Forward_to_FastAPI": {
        "type": "Http",
        "inputs": {
          "method": "POST",
          "uri": "https://your-app.azurewebsites.net/azure-monitor",
          "headers": {
            "x-api-key": "@{parameters('RCA_API_KEY')}",
            "Content-Type": "application/json"
          },
          "body": "@triggerBody()"
        }
      }
    }
  }
}
```

**But this defeats the purpose of removing Logic Apps!** ⚠️

---

#### Approach C: Azure API Management (Enterprise) ⭐ BEST

Use Azure APIM to add headers:

```bash
# 1. Create APIM instance
az apim create \
  --name "apim-rca-proxy" \
  --resource-group "$RESOURCE_GROUP" \
  --publisher-email "admin@company.com" \
  --publisher-name "RCA Team" \
  --sku-name "Consumption"

# 2. Create API
az apim api create \
  --resource-group "$RESOURCE_GROUP" \
  --service-name "apim-rca-proxy" \
  --api-id "rca-webhook" \
  --path "/webhook" \
  --display-name "RCA Webhook Proxy" \
  --protocols "https" \
  --service-url "https://your-app.azurewebsites.net"

# 3. Add policy to inject header
az apim api policy create \
  --resource-group "$RESOURCE_GROUP" \
  --service-name "apim-rca-proxy" \
  --api-id "rca-webhook" \
  --xml-file policy.xml
```

**policy.xml:**
```xml
<policies>
  <inbound>
    <set-header name="x-api-key" exists-action="override">
      <value>{{RCA_API_KEY}}</value>
    </set-header>
    <base />
  </inbound>
  <backend>
    <base />
  </backend>
</policies>
```

**Use APIM endpoint in Action Group:**
```
https://apim-rca-proxy.azure-api.net/webhook/azure-monitor
```

---

### STEP 3: Understand Azure Monitor Webhook Payload

#### Sample Payload from Action Group

```json
{
  "schemaId": "azureMonitorCommonAlertSchema",
  "data": {
    "essentials": {
      "alertId": "/subscriptions/.../alerts/...",
      "alertRule": "ADF-PipelineFailure-Alert",
      "severity": "Sev3",
      "signalType": "Metric",
      "monitorCondition": "Fired",
      "alertTargetIDs": ["/subscriptions/.../providers/Microsoft.DataFactory/factories/your-adf"],
      "originAlertId": "...",
      "firedDateTime": "2025-11-26T10:30:00Z",
      "description": "Pipeline failed: Copy_Data_Pipeline"
    },
    "alertContext": {
      "properties": {
        "PipelineName": "Copy_Data_Pipeline",
        "PipelineRunId": "abc123-def456-789",
        "ActivityName": "CopyActivity1",
        "ActivityType": "Copy",
        "ErrorCode": "UserErrorSourceBlobNotExists",
        "ErrorMessage": "The specified blob does not exist. RequestId:xxx-xxx-xxx",
        "Error": {
          "errorCode": "UserErrorSourceBlobNotExists",
          "message": "The specified blob does not exist.",
          "failureType": "UserError",
          "target": "CopyActivity1"
        }
      }
    }
  }
}
```

**Key Fields:**
- `data.essentials.alertRule` → Pipeline name
- `data.alertContext.properties.PipelineRunId` → Run ID (for deduplication)
- `data.alertContext.properties.Error.message` → Actual error message
- `data.alertContext.properties.ErrorMessage` → Detailed error

---

### STEP 4: Test ADF Webhook

#### Test Script

```bash
#!/bin/bash
# test_adf_webhook.sh

FASTAPI_URL="https://your-app.azurewebsites.net/azure-monitor"
API_KEY="your-rca-api-key"

# Test payload simulating ADF failure
curl -X POST "$FASTAPI_URL?api_key=$API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "schemaId": "azureMonitorCommonAlertSchema",
    "data": {
      "essentials": {
        "alertRule": "TEST_Pipeline_Failure",
        "severity": "Sev2",
        "firedDateTime": "2025-11-26T10:30:00Z",
        "description": "Test alert for RCA system"
      },
      "alertContext": {
        "properties": {
          "PipelineName": "Test_ETL_Pipeline",
          "PipelineRunId": "test-run-12345",
          "ActivityName": "CopyData",
          "ErrorCode": "UserErrorSourceBlobNotExists",
          "ErrorMessage": "The specified blob container '\''input-data'\'' does not exist. Container: input-data, Storage Account: storageacct123",
          "Error": {
            "errorCode": "UserErrorSourceBlobNotExists",
            "message": "The specified blob container '\''input-data'\'' does not exist.",
            "failureType": "UserError",
            "target": "CopyData"
          }
        }
      }
    }
  }'

echo ""
echo "Check FastAPI logs and dashboard for new ticket!"
```

---

## 🔧 DATABRICKS COMPLETE SETUP

### Current Limitation: Only Job-Level Notifications

**What's covered now:**
- ✅ Job failures
- ✅ Task failures within jobs
- ❌ Cluster startup failures
- ❌ Cluster termination events
- ❌ Library installation errors

---

### STEP 1: Enable ALL Databricks Event Notifications

#### 1.1 Job Notifications (Already Configured)

```python
# In Databricks Job Configuration
{
  "job_id": 123,
  "settings": {
    "name": "ETL Pipeline",
    "email_notifications": {},
    "webhook_notifications": {
      "on_failure": [{
        "id": "rca-webhook-job-failure",
        "url": "https://your-app.azurewebsites.net/databricks-monitor"
      }]
    }
  }
}
```

---

#### 1.2 Cluster Event Notifications (NEW) ⭐

**Option A: Databricks Workspace Level (Recommended)**

```bash
# Using Databricks CLI
databricks workspace-conf set-status \
  --json '{
    "enableWebhookNotifications": "true",
    "webhookNotifications": {
      "endpoints": [
        {
          "id": "rca-cluster-events",
          "url": "https://your-app.azurewebsites.net/databricks-monitor",
          "events": [
            "CLUSTER_CREATED",
            "CLUSTER_RUNNING",
            "CLUSTER_TERMINATED",
            "CLUSTER_FAILED"
          ]
        }
      ]
    }
  }'
```

**Option B: Per-Cluster Configuration**

```python
# In cluster configuration JSON
{
  "cluster_name": "Production ETL Cluster",
  "spark_version": "13.3.x-scala2.12",
  "node_type_id": "Standard_DS3_v2",
  "custom_tags": {
    "Project": "ETL",
    "Environment": "Production"
  },
  "cluster_log_conf": {
    "dbfs": {
      "destination": "dbfs:/cluster-logs"
    }
  },
  "init_scripts": [],
  "webhook_notifications": {
    "on_start": [{
      "id": "cluster-start-webhook",
      "url": "https://your-app.azurewebsites.net/databricks-monitor"
    }],
    "on_unexpected_termination": [{
      "id": "cluster-terminated-webhook",
      "url": "https://your-app.azurewebsites.net/databricks-monitor"
    }],
    "on_failed_start": [{
      "id": "cluster-failed-start-webhook",
      "url": "https://your-app.azurewebsites.net/databricks-monitor"
    }]
  }
}
```

---

#### 1.3 Library Installation Failures (NEW)

```python
# Webhook for library installation events
# Configure at workspace level
{
  "webhook_notifications": {
    "endpoints": [
      {
        "id": "rca-library-events",
        "url": "https://your-app.azurewebsites.net/databricks-monitor",
        "events": [
          "LIBRARY_INSTALL_STARTED",
          "LIBRARY_INSTALL_FAILED"
        ]
      }
    ]
  }
}
```

---

### STEP 2: Databricks Webhook Payload Examples

#### Job Failure Event

```json
{
  "event": "job.failure",
  "event_type": "job.failure",
  "timestamp": 1732627800000,
  "job": {
    "job_id": 404831337617650,
    "settings": {
      "name": "ETL_Production_Pipeline"
    }
  },
  "run": {
    "run_id": 204354054874177,
    "run_name": "Manual run",
    "state": {
      "life_cycle_state": "TERMINATED",
      "result_state": "FAILED",
      "state_message": "Task failed. Check task logs for details."
    }
  }
}
```

---

#### Cluster Termination Event (NEW)

```json
{
  "event": "cluster.terminated",
  "event_type": "cluster.terminated",
  "timestamp": 1732627900000,
  "cluster": {
    "cluster_id": "1234-567890-abc123",
    "cluster_name": "Production ETL Cluster",
    "state": "TERMINATED",
    "state_message": "Cluster terminated due to inactivity",
    "termination_reason": {
      "code": "INACTIVITY",
      "type": "SUCCESS",
      "parameters": {
        "inactivity_duration_min": "120"
      }
    }
  }
}
```

---

#### Cluster Failed to Start (NEW)

```json
{
  "event": "cluster.failed_to_start",
  "event_type": "cluster.failed_to_start",
  "timestamp": 1732628000000,
  "cluster": {
    "cluster_id": "1234-567890-abc123",
    "cluster_name": "ML Training Cluster",
    "state": "ERROR",
    "state_message": "Cluster failed to start: Instance type Standard_DS3_v2 is not available in region eastus",
    "termination_reason": {
      "code": "INSTANCE_UNREACHABLE",
      "type": "CLOUD_FAILURE",
      "parameters": {
        "aws_error_message": "Instance type not available"
      }
    }
  }
}
```

---

### STEP 3: Enhanced Databricks Endpoint

See **Complete Code Implementation** section below for full code.

---

## 💻 COMPLETE CODE IMPLEMENTATION

### Enhanced Error Extraction Module

Create new file: `/genai_rca_assistant/error_extractors.py`

```python
"""
Error extraction utilities for different services
Each service has its own extraction logic
"""
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger("error_extractors")


class AzureDataFactoryExtractor:
    """Extract error details from ADF webhook payloads"""

    @staticmethod
    def extract(payload: Dict) -> Tuple[str, str, str, Dict]:
        """
        Extract error details from ADF webhook

        Returns:
            (pipeline_name, run_id, error_message, metadata)
        """
        # Handle both common alert schema and custom payloads
        essentials = payload.get("data", {}).get("essentials") or payload.get("essentials") or {}
        alert_context = payload.get("data", {}).get("alertContext") or {}
        properties = alert_context.get("properties", {}) or payload.get("properties", {})

        # Extract pipeline name
        pipeline_name = (
            properties.get("PipelineName") or
            properties.get("pipelineName") or
            essentials.get("alertRule") or
            essentials.get("pipelineName") or
            "ADF Pipeline"
        )

        # Extract run ID
        run_id = (
            properties.get("PipelineRunId") or
            properties.get("pipelineRunId") or
            properties.get("RunId") or
            properties.get("runId") or
            essentials.get("alertId")
        )

        # Extract error message (Priority order)
        error_obj = properties.get("Error") or properties.get("error") or {}

        error_message = (
            # 1. Detailed error object message
            error_obj.get("message") or
            error_obj.get("Message") or
            # 2. Error message fields
            properties.get("ErrorMessage") or
            properties.get("errorMessage") or
            properties.get("detailedMessage") or
            # 3. Generic message
            properties.get("message") or
            essentials.get("description") or
            # 4. Fallback
            "ADF pipeline failed. No detailed error message available."
        )

        # Extract metadata
        metadata = {
            "activity_name": properties.get("ActivityName") or properties.get("activityName"),
            "activity_type": properties.get("ActivityType") or properties.get("activityType"),
            "error_code": (
                error_obj.get("errorCode") or
                properties.get("ErrorCode") or
                properties.get("errorCode")
            ),
            "failure_type": error_obj.get("failureType") or error_obj.get("FailureType"),
            "severity": essentials.get("severity"),
            "fired_time": essentials.get("firedDateTime"),
        }

        logger.info(f"ADF Extractor: pipeline={pipeline_name}, run_id={run_id}")
        logger.info(f"ADF Extractor: error_code={metadata['error_code']}")

        return pipeline_name, run_id, error_message, metadata


class DatabricksExtractor:
    """Extract error details from Databricks webhook payloads"""

    @staticmethod
    def extract(payload: Dict) -> Tuple[str, str, str, str, Dict]:
        """
        Extract error details from Databricks webhook

        Returns:
            (resource_name, run_id, event_type, error_message, metadata)
        """
        event_type = payload.get("event") or payload.get("event_type") or "unknown"

        # Determine if this is a job event or cluster event
        if "job" in event_type.lower() or "run" in payload:
            return DatabricksExtractor._extract_job_event(payload, event_type)
        elif "cluster" in event_type.lower() or "cluster" in payload:
            return DatabricksExtractor._extract_cluster_event(payload, event_type)
        else:
            return DatabricksExtractor._extract_generic_event(payload, event_type)

    @staticmethod
    def _extract_job_event(payload: Dict, event_type: str) -> Tuple[str, str, str, str, Dict]:
        """Extract job failure event details"""
        job_obj = payload.get("job", {})
        run_obj = payload.get("run", {})

        job_name = (
            job_obj.get("settings", {}).get("name") or
            run_obj.get("run_name") or
            payload.get("job_name") or
            "Databricks Job"
        )

        run_id = (
            run_obj.get("run_id") or
            payload.get("run_id") or
            payload.get("job_run_id")
        )

        # Initial error from webhook
        error_message = (
            run_obj.get("state", {}).get("state_message") or
            run_obj.get("state_message") or
            payload.get("error_message") or
            f"Databricks job event: {event_type}"
        )

        metadata = {
            "job_id": job_obj.get("job_id") or payload.get("job_id"),
            "cluster_id": run_obj.get("cluster_instance", {}).get("cluster_id"),
            "event_type": event_type,
            "resource_type": "job",
            "life_cycle_state": run_obj.get("state", {}).get("life_cycle_state"),
            "result_state": run_obj.get("state", {}).get("result_state"),
        }

        logger.info(f"Databricks Job Extractor: job={job_name}, run_id={run_id}, event={event_type}")

        return job_name, run_id, event_type, error_message, metadata

    @staticmethod
    def _extract_cluster_event(payload: Dict, event_type: str) -> Tuple[str, str, str, str, Dict]:
        """Extract cluster event details (NEW)"""
        cluster_obj = payload.get("cluster", {})

        cluster_name = (
            cluster_obj.get("cluster_name") or
            payload.get("cluster_name") or
            "Databricks Cluster"
        )

        cluster_id = (
            cluster_obj.get("cluster_id") or
            payload.get("cluster_id")
        )

        # Extract termination reason
        termination_reason = cluster_obj.get("termination_reason", {})
        state_message = cluster_obj.get("state_message", "")

        if termination_reason:
            code = termination_reason.get("code")
            term_type = termination_reason.get("type")
            params = termination_reason.get("parameters", {})

            error_message = f"Cluster {event_type}: {state_message}. Reason: {code} ({term_type})"
            if params:
                param_str = ", ".join([f"{k}={v}" for k, v in params.items()])
                error_message += f". Details: {param_str}"
        else:
            error_message = state_message or f"Cluster {event_type}"

        metadata = {
            "cluster_id": cluster_id,
            "event_type": event_type,
            "resource_type": "cluster",
            "cluster_state": cluster_obj.get("state"),
            "termination_code": termination_reason.get("code"),
            "termination_type": termination_reason.get("type"),
            "driver_node_type": cluster_obj.get("driver_node_type_id"),
            "num_workers": cluster_obj.get("num_workers"),
        }

        logger.info(f"Databricks Cluster Extractor: cluster={cluster_name}, id={cluster_id}, event={event_type}")

        return cluster_name, cluster_id, event_type, error_message, metadata

    @staticmethod
    def _extract_generic_event(payload: Dict, event_type: str) -> Tuple[str, str, str, str, Dict]:
        """Fallback for unknown event types"""
        resource_name = (
            payload.get("name") or
            payload.get("resource_name") or
            "Databricks Resource"
        )

        resource_id = (
            payload.get("id") or
            payload.get("resource_id") or
            "unknown"
        )

        error_message = payload.get("message") or payload.get("error_message") or str(payload)

        metadata = {
            "event_type": event_type,
            "resource_type": "unknown",
            "raw_payload_keys": list(payload.keys())
        }

        logger.warning(f"Databricks Generic Extractor: Unrecognized event type: {event_type}")

        return resource_name, resource_id, event_type, error_message, metadata


# Factory function
def get_extractor(source_type: str):
    """Get appropriate extractor for source type"""
    extractors = {
        "adf": AzureDataFactoryExtractor,
        "azure_data_factory": AzureDataFactoryExtractor,
        "databricks": DatabricksExtractor,
    }
    return extractors.get(source_type.lower())
```

Save this to: `genai_rca_assistant/error_extractors.py`

---

### Updated Main Endpoints

Now update `main.py` to use the extractors:

```python
# At the top of main.py, add:
from error_extractors import AzureDataFactoryExtractor, DatabricksExtractor

# Replace /azure-monitor endpoint with this enhanced version:
```

I'll create a new file with the enhanced endpoints:

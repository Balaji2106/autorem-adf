#!/bin/bash

# Test Payload for Auto-Remediation
# This simulates an Azure Monitor alert for the Test_Timeout_Error pipeline

echo "=========================================="
echo "🧪 Sending Auto-Solvable Test Payload"
echo "=========================================="
echo ""
echo "Pipeline: Test_Timeout_Error"
echo "Error Type: GatewayTimeout (Auto-solvable)"
echo "Expected: Auto-remediation should trigger"
echo ""

# Replace with your actual RCA endpoint
RCA_ENDPOINT="https://unepitaphed-brazenly-lola.ngrok-free.dev/azure-monitor"

# If your RCA is on a different server, update this:
# RCA_ENDPOINT="http://your-server-ip:8000/azure-monitor"

echo "Sending to: $RCA_ENDPOINT"
echo ""

curl -X POST "$RCA_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{
    "schemaId": "azureMonitorCommonAlertSchema",
    "data": {
      "essentials": {
        "alertId": "test-alert-'$(date +%s)'",
        "alertRule": "Test_Timeout_Error_Alert",
        "severity": "Sev2",
        "signalType": "Log",
        "monitoringService": "Data Factory",
        "alertTargetIDs": [
          "/subscriptions/d28a053b-ed09-40dd-92d6-43401a2c9799/resourceGroups/rg_techdemo_2025_Q4/providers/Microsoft.DataFactory/factories/adf-techdemo-rca"
        ],
        "originAlertId": "test-'$(date +%s)'",
        "firedDateTime": "'$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)'",
        "description": "Pipeline Test_Timeout_Error failed due to gateway timeout",
        "essentialsVersion": "1.0",
        "alertContextVersion": "1.0"
      },
      "alertContext": {
        "properties": {
          "PipelineName": "Test_Timeout_Error",
          "PipelineRunId": "test-run-'$(date +%s)'-auto-remediation",
          "RunId": "test-run-'$(date +%s)'-auto-remediation",
          "ActivityName": "CallInvalidEndpoint",
          "ActivityType": "WebActivity",
          "ErrorMessage": "Gateway timeout error occurred during pipeline execution. The HTTP request to https://httpstat.us/504?sleep=35000 timed out after 30 seconds. This is a transient network error that can be resolved by retrying the pipeline.",
          "ErrorCode": "GatewayTimeout",
          "FailureType": "UserError",
          "Error": {
            "errorCode": "GatewayTimeout",
            "message": "Gateway timeout error occurred during pipeline execution. The HTTP request to https://httpstat.us/504?sleep=35000 timed out after 30 seconds.",
            "failureType": "UserError"
          }
        },
        "context": {
          "resourceGroupName": "rg_techdemo_2025_Q4",
          "subscriptionId": "d28a053b-ed09-40dd-92d6-43401a2c9799",
          "factoryName": "adf-techdemo-rca"
        }
      }
    }
  }' \
  -w "\n\n📊 HTTP Status: %{http_code}\n" \
  -s | jq '.'

echo ""
echo "=========================================="
echo "✅ Payload sent!"
echo "=========================================="
echo ""
echo "🔍 What to check now:"
echo ""
echo "1. Dashboard: http://localhost:8000/dashboard"
echo "   → Check 'Open Tickets' tab"
echo "   → Should see ticket status change to 'In Progress'"
echo ""
echo "2. Application Logs:"
echo "   tail -f logs/aiops.log | grep --color=always -E 'Auto-Remediation|Test_Timeout_Error'"
echo ""
echo "3. Database Audit Trail:"
echo "   sqlite3 data/tickets.db \"SELECT timestamp, action, details FROM audit_trail WHERE pipeline='Test_Timeout_Error' ORDER BY timestamp DESC LIMIT 5\""
echo ""
echo "4. Logic App Run History:"
echo "   → Azure Portal → Your Logic App → Run history"
echo ""
echo "5. ADF Pipeline Runs:"
echo "   → ADF Studio → Monitor → Pipeline runs"
echo "   → Filter: Test_Timeout_Error"
echo ""
echo "=========================================="
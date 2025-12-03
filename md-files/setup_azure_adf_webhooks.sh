#!/bin/bash

################################################################################
# Azure Data Factory Webhook Setup Script
#
# This script creates Azure Monitor Alert Rules that send webhooks directly
# to FastAPI endpoints, bypassing Logic Apps for faster response times.
################################################################################

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Azure Data Factory Webhook Setup                     ║${NC}"
echo -e "${BLUE}║   Direct Integration with FastAPI (No Logic Apps)      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

################################################################################
# Step 1: Collect Configuration
################################################################################

echo -e "${GREEN}Step 1: Configuration${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Resource Group
read -p "Enter Azure Resource Group name [rg_techdemo_2025_Q4]: " RESOURCE_GROUP
RESOURCE_GROUP=${RESOURCE_GROUP:-rg_techdemo_2025_Q4}

# ADF Name
read -p "Enter Azure Data Factory name: " ADF_NAME
if [ -z "$ADF_NAME" ]; then
    echo -e "${RED}Error: ADF name is required${NC}"
    exit 1
fi

# FastAPI Endpoint
read -p "Enter FastAPI endpoint URL (e.g., https://your-app.azurewebsites.net): " FASTAPI_BASE_URL
if [ -z "$FASTAPI_BASE_URL" ]; then
    echo -e "${RED}Error: FastAPI URL is required${NC}"
    exit 1
fi

# Remove trailing slash from URL
FASTAPI_BASE_URL=${FASTAPI_BASE_URL%/}

# Construct full endpoint URL (NO API KEY NEEDED)
# Azure Monitor Action Groups don't support custom headers
# Security is provided by non-public endpoint URL
WEBHOOK_URL="${FASTAPI_BASE_URL}/azure-monitor"

echo ""
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  SECURITY NOTE: API Key Authentication Disabled       ${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Azure Monitor Action Groups do NOT support custom headers.${NC}"
echo -e "${YELLOW}Your FastAPI endpoint will accept webhooks without API key.${NC}"
echo ""
echo -e "${BLUE}Security is provided by:${NC}"
echo "  1. 🔒 Non-public endpoint URL (keep it secret!)"
echo "  2. 🛡️  Azure network security groups (if configured)"
echo "  3. ✅ Payload validation in FastAPI"
echo "  4. 🔐 Azure subscription access controls"
echo ""
echo -e "${YELLOW}IMPORTANT: Do NOT share the webhook URL publicly!${NC}"
echo ""

echo -e "${BLUE}Configuration Summary:${NC}"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  ADF Name: $ADF_NAME"
echo "  Webhook URL: ${FASTAPI_BASE_URL}/azure-monitor"
echo ""

read -p "Is this correct? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Setup cancelled${NC}"
    exit 0
fi

################################################################################
# Step 2: Get ADF Resource ID
################################################################################

echo ""
echo -e "${GREEN}Step 2: Getting ADF Resource ID${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

ADF_ID=$(az datafactory show \
    --resource-group "$RESOURCE_GROUP" \
    --name "$ADF_NAME" \
    --query id \
    --output tsv 2>&1)

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to get ADF Resource ID${NC}"
    echo "$ADF_ID"
    exit 1
fi

echo -e "${GREEN}✓ ADF Resource ID: $ADF_ID${NC}"

################################################################################
# Step 3: Create Action Group with Webhook
################################################################################

echo ""
echo -e "${GREEN}Step 3: Creating Action Group${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

ACTION_GROUP_NAME="ag-adf-rca-webhook-${ADF_NAME}"
SHORT_NAME="adf-rca"

echo "Creating action group: $ACTION_GROUP_NAME"

# Create action group with webhook
az monitor action-group create \
    --name "$ACTION_GROUP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --short-name "$SHORT_NAME" \
    --action webhook "rca-webhook" "$WEBHOOK_URL" \
    --output table

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Action Group created successfully${NC}"
else
    echo -e "${RED}✗ Failed to create Action Group${NC}"
    exit 1
fi

################################################################################
# Step 4: Create Alert Rules
################################################################################

echo ""
echo -e "${GREEN}Step 4: Creating Alert Rules${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Alert Rule 1: Pipeline Failures
echo ""
echo "Creating alert rule: Pipeline Failures"

ALERT_PIPELINE_NAME="alert-${ADF_NAME}-pipeline-failure"

az monitor metrics alert create \
    --name "$ALERT_PIPELINE_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --scopes "$ADF_ID" \
    --condition "total PipelineFailedRuns > 0" \
    --window-size 5m \
    --evaluation-frequency 1m \
    --action "$ACTION_GROUP_NAME" \
    --description "Alert on ADF pipeline failures - sends to RCA system via webhook" \
    --severity 2 \
    --output table

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Pipeline failure alert created${NC}"
else
    echo -e "${YELLOW}⚠ Pipeline failure alert may already exist${NC}"
fi

# Alert Rule 2: Activity Failures
echo ""
echo "Creating alert rule: Activity Failures"

ALERT_ACTIVITY_NAME="alert-${ADF_NAME}-activity-failure"

az monitor metrics alert create \
    --name "$ALERT_ACTIVITY_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --scopes "$ADF_ID" \
    --condition "total ActivityFailedRuns > 0" \
    --window-size 5m \
    --evaluation-frequency 1m \
    --action "$ACTION_GROUP_NAME" \
    --description "Alert on ADF activity failures - sends to RCA system via webhook" \
    --severity 3 \
    --output table

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Activity failure alert created${NC}"
else
    echo -e "${YELLOW}⚠ Activity failure alert may already exist${NC}"
fi

################################################################################
# Step 5: Test Webhook
################################################################################

echo ""
echo -e "${GREEN}Step 5: Testing Webhook (Optional)${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
read -p "Would you like to send a test webhook now? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Sending test webhook..."

    TEST_PAYLOAD='{
        "schemaId": "azureMonitorCommonAlertSchema",
        "data": {
            "essentials": {
                "alertRule": "TEST-Pipeline-Alert",
                "severity": "Sev2",
                "signalType": "Metric",
                "monitorCondition": "Fired",
                "firedDateTime": "'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'",
                "description": "Test alert from setup script"
            },
            "alertContext": {
                "properties": {
                    "PipelineName": "TEST_Pipeline_'$(date +%s)'",
                    "PipelineRunId": "test-run-'$(uuidgen)'",
                    "ActivityName": "TestActivity",
                    "ErrorCode": "UserErrorSourceBlobNotExists",
                    "ErrorMessage": "TEST ERROR: This is a test webhook from the setup script to verify RCA system integration.",
                    "Error": {
                        "errorCode": "UserErrorSourceBlobNotExists",
                        "message": "TEST: The specified blob container does not exist.",
                        "failureType": "UserError",
                        "target": "TestActivity"
                    }
                }
            }
        }
    }'

    RESPONSE=$(curl -s -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "$TEST_PAYLOAD" \
        -w "\nHTTP_STATUS:%{http_code}")

    HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
    BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS/d')

    if [ "$HTTP_STATUS" == "200" ]; then
        echo -e "${GREEN}✓ Test webhook sent successfully!${NC}"
        echo ""
        echo "Response:"
        echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
        echo ""
        echo -e "${BLUE}Check your FastAPI logs and dashboard for the test ticket${NC}"
    else
        echo -e "${RED}✗ Test webhook failed${NC}"
        echo "HTTP Status: $HTTP_STATUS"
        echo "Response: $BODY"
    fi
fi

################################################################################
# Summary
################################################################################

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    Setup Complete!                      ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Summary:${NC}"
echo "  ✓ Action Group created: $ACTION_GROUP_NAME"
echo "  ✓ Pipeline failure alert created: $ALERT_PIPELINE_NAME"
echo "  ✓ Activity failure alert created: $ALERT_ACTIVITY_NAME"
echo "  ✓ Webhook URL configured: ${FASTAPI_BASE_URL}/azure-monitor"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. Trigger a test pipeline failure in ADF to verify end-to-end flow"
echo "  2. Check FastAPI logs for incoming webhooks"
echo "  3. Verify ticket creation in dashboard"
echo "  4. Monitor alert rule firing in Azure Monitor"
echo ""
echo -e "${BLUE}Useful Commands:${NC}"
echo ""
echo "  # View alert rules"
echo "  az monitor metrics alert list --resource-group $RESOURCE_GROUP --output table"
echo ""
echo "  # View action groups"
echo "  az monitor action-group list --resource-group $RESOURCE_GROUP --output table"
echo ""
echo "  # Test webhook manually"
echo "  curl -X POST '$WEBHOOK_URL' -H 'Content-Type: application/json' -d @test_payload.json"
echo ""
echo "  # Delete alert rules (if needed)"
echo "  az monitor metrics alert delete --name $ALERT_PIPELINE_NAME --resource-group $RESOURCE_GROUP"
echo "  az monitor metrics alert delete --name $ALERT_ACTIVITY_NAME --resource-group $RESOURCE_GROUP"
echo ""
echo "  # Delete action group (if needed)"
echo "  az monitor action-group delete --name $ACTION_GROUP_NAME --resource-group $RESOURCE_GROUP"
echo ""

echo -e "${GREEN}Setup completed successfully!${NC}"

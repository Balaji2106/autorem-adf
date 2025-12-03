#!/bin/bash

################################################################################
# Databricks Webhook Setup Script
#
# This script helps configure Databricks webhooks for:
# - Job failures
# - Cluster termination events
# - Library installation failures
#
# All events are sent to the FastAPI /databricks-monitor endpoint
################################################################################

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Databricks Webhook Configuration Guide               ║${NC}"
echo -e "${BLUE}║   Job, Cluster & Library Event Notifications           ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

################################################################################
# Step 1: Collect Configuration
################################################################################

echo -e "${GREEN}Step 1: Configuration${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# FastAPI Endpoint
read -p "Enter FastAPI endpoint URL (e.g., https://your-app.azurewebsites.net): " FASTAPI_BASE_URL
if [ -z "$FASTAPI_BASE_URL" ]; then
    echo -e "${RED}Error: FastAPI URL is required${NC}"
    exit 1
fi

# Remove trailing slash
FASTAPI_BASE_URL=${FASTAPI_BASE_URL%/}
WEBHOOK_URL="${FASTAPI_BASE_URL}/databricks-monitor"

echo ""
echo -e "${BLUE}Webhook URL: $WEBHOOK_URL${NC}"
echo ""
echo -e "${YELLOW}Note: Databricks webhooks do NOT require API key authentication.${NC}"
echo -e "${YELLOW}Databricks validates webhooks internally.${NC}"
echo ""

################################################################################
# Step 2: Check Databricks CLI
################################################################################

echo ""
echo -e "${GREEN}Step 2: Checking Databricks CLI${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if ! command -v databricks &> /dev/null; then
    echo -e "${YELLOW}⚠ Databricks CLI not found${NC}"
    echo ""
    echo "Install Databricks CLI:"
    echo "  pip install databricks-cli"
    echo ""
    echo "Configure authentication:"
    echo "  databricks configure --token"
    echo ""
    echo -e "${RED}Please install and configure Databricks CLI, then run this script again${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Databricks CLI found${NC}"

# Check if configured
if ! databricks workspace ls / &> /dev/null; then
    echo -e "${YELLOW}⚠ Databricks CLI not configured${NC}"
    echo ""
    echo "Configure authentication:"
    echo "  databricks configure --token"
    echo ""
    read -p "Would you like to configure now? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        databricks configure --token
    else
        echo -e "${RED}Please configure Databricks CLI and run this script again${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}✓ Databricks CLI is configured${NC}"

################################################################################
# Step 3: Job Webhook Configuration
################################################################################

echo ""
echo -e "${GREEN}Step 3: Job Webhook Configuration${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "Job webhooks must be configured per job in the Databricks UI."
echo ""
echo -e "${BLUE}Instructions:${NC}"
echo "  1. Open Databricks Workspace"
echo "  2. Navigate to Workflows → Your Job"
echo "  3. Click 'Edit Job'"
echo "  4. Scroll to 'Notifications' section"
echo "  5. Click 'Add notification'"
echo "  6. Select 'On Failure' or 'On Success'"
echo "  7. Choose 'Webhook'"
echo "  8. Enter URL: ${WEBHOOK_URL}"
echo "  9. Click 'Save'"
echo ""

# Generate job configuration JSON for CLI users
cat > databricks_job_webhook_config.json <<EOF
{
  "webhook_notifications": {
    "on_failure": [
      {
        "id": "rca-webhook-job-failure-$(date +%s)",
        "url": "${WEBHOOK_URL}"
      }
    ],
    "on_success": [
      {
        "id": "rca-webhook-job-success-$(date +%s)",
        "url": "${WEBHOOK_URL}"
      }
    ]
  }
}
EOF

echo -e "${GREEN}✓ Job webhook configuration saved to: databricks_job_webhook_config.json${NC}"
echo ""
echo "To apply this configuration to a job via CLI:"
echo ""
echo -e "${BLUE}# Get your job ID${NC}"
echo "databricks jobs list"
echo ""
echo -e "${BLUE}# Get current job configuration${NC}"
echo "databricks jobs get --job-id <YOUR_JOB_ID> > current_job_config.json"
echo ""
echo -e "${BLUE}# Merge webhook configuration into job settings and update${NC}"
echo "# (Manual merge required - add 'webhook_notifications' block to job settings)"
echo "databricks jobs reset --job-id <YOUR_JOB_ID> --json-file updated_job_config.json"
echo ""

################################################################################
# Step 4: Cluster Webhook Configuration
################################################################################

echo ""
echo -e "${GREEN}Step 4: Cluster Webhook Configuration${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "Cluster webhooks can be configured:"
echo "  A) Per cluster (specific clusters)"
echo "  B) Workspace-wide (all clusters)"
echo ""

read -p "Configure cluster webhooks? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Skipping cluster webhook configuration"
else
    # Generate cluster webhook configuration
    cat > databricks_cluster_webhook_config.json <<EOF
{
  "webhook_notifications": {
    "on_start": [
      {
        "id": "rca-webhook-cluster-start-$(date +%s)",
        "url": "${WEBHOOK_URL}"
      }
    ],
    "on_unexpected_termination": [
      {
        "id": "rca-webhook-cluster-terminated-$(date +%s)",
        "url": "${WEBHOOK_URL}"
      }
    ],
    "on_failed_start": [
      {
        "id": "rca-webhook-cluster-failed-$(date +%s)",
        "url": "${WEBHOOK_URL}"
      }
    ]
  }
}
EOF

    echo -e "${GREEN}✓ Cluster webhook configuration saved to: databricks_cluster_webhook_config.json${NC}"
    echo ""
    echo -e "${BLUE}To apply to a specific cluster:${NC}"
    echo ""
    echo "1. List clusters:"
    echo "   databricks clusters list"
    echo ""
    echo "2. Get cluster configuration:"
    echo "   databricks clusters get --cluster-id <CLUSTER_ID> > current_cluster_config.json"
    echo ""
    echo "3. Add 'webhook_notifications' block from databricks_cluster_webhook_config.json"
    echo ""
    echo "4. Update cluster:"
    echo "   databricks clusters edit --json-file updated_cluster_config.json"
    echo ""
    echo -e "${BLUE}For workspace-wide cluster webhooks:${NC}"
    echo ""
    echo "This requires Workspace Admin permissions and API calls."
    echo "See: https://docs.databricks.com/api/workspace/workspaceconf/setstatus"
    echo ""
fi

################################################################################
# Step 5: Test Webhook
################################################################################

echo ""
echo -e "${GREEN}Step 5: Test Webhook${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

read -p "Would you like to send test webhooks now? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Skipping test webhooks"
else
    # Test 1: Job Failure
    echo ""
    echo "Test 1: Simulating job failure webhook..."

    TEST_JOB_PAYLOAD='{
        "event": "job.failure",
        "event_type": "job.failure",
        "timestamp": '$(date +%s000)',
        "job": {
            "job_id": 999999999,
            "settings": {
                "name": "TEST_Job_'$(date +%s)'"
            }
        },
        "run": {
            "run_id": '$(date +%s)'123,
            "run_name": "Manual test run from setup script",
            "state": {
                "life_cycle_state": "TERMINATED",
                "result_state": "FAILED",
                "state_message": "TEST: This is a simulated job failure for RCA system verification."
            }
        }
    }'

    RESPONSE=$(curl -s -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "$TEST_JOB_PAYLOAD" \
        -w "\nHTTP_STATUS:%{http_code}")

    HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
    BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS/d')

    if [ "$HTTP_STATUS" == "200" ]; then
        echo -e "${GREEN}✓ Job failure test webhook sent successfully!${NC}"
    else
        echo -e "${RED}✗ Job failure test webhook failed${NC}"
        echo "HTTP Status: $HTTP_STATUS"
    fi

    # Test 2: Cluster Termination
    echo ""
    echo "Test 2: Simulating cluster termination webhook..."

    TEST_CLUSTER_PAYLOAD='{
        "event": "cluster.terminated",
        "event_type": "cluster.terminated",
        "timestamp": '$(date +%s000)',
        "cluster": {
            "cluster_id": "test-cluster-'$(date +%s)'",
            "cluster_name": "TEST_Cluster_'$(date +%s)'",
            "state": "TERMINATED",
            "state_message": "TEST: Cluster terminated due to simulated driver failure",
            "termination_reason": {
                "code": "DRIVER_NOT_RESPONDING",
                "type": "ERROR",
                "parameters": {
                    "test": "true"
                }
            }
        }
    }'

    RESPONSE=$(curl -s -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "$TEST_CLUSTER_PAYLOAD" \
        -w "\nHTTP_STATUS:%{http_code}")

    HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)

    if [ "$HTTP_STATUS" == "200" ]; then
        echo -e "${GREEN}✓ Cluster termination test webhook sent successfully!${NC}"
    else
        echo -e "${RED}✗ Cluster termination test webhook failed${NC}"
        echo "HTTP Status: $HTTP_STATUS"
    fi

    echo ""
    echo -e "${BLUE}Check your FastAPI logs and dashboard for test tickets${NC}"
fi

################################################################################
# Step 6: Create Test Job (Optional)
################################################################################

echo ""
echo -e "${GREEN}Step 6: Create Test Job (Optional)${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

read -p "Would you like to create a test job that will fail? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Generate test job configuration
    cat > databricks_test_job.json <<EOF
{
  "name": "RCA_Test_Job_$(date +%s)",
  "tasks": [
    {
      "task_key": "test_failure_task",
      "notebook_task": {
        "notebook_path": "/Shared/RCA_Test_Failure",
        "source": "WORKSPACE"
      },
      "new_cluster": {
        "spark_version": "13.3.x-scala2.12",
        "node_type_id": "Standard_DS3_v2",
        "num_workers": 1
      }
    }
  ],
  "webhook_notifications": {
    "on_failure": [
      {
        "id": "rca-test-webhook",
        "url": "${WEBHOOK_URL}"
      }
    ]
  }
}
EOF

    echo -e "${GREEN}✓ Test job configuration saved to: databricks_test_job.json${NC}"
    echo ""
    echo "To create the test job:"
    echo ""
    echo "1. Create a test notebook at /Shared/RCA_Test_Failure with this code:"
    echo ""
    echo -e "${BLUE}"
    cat <<'NOTEBOOK'
# Databricks notebook
# Test notebook that intentionally fails for RCA system testing

print("RCA Test: Starting intentional failure test...")

# Simulate a realistic error
raise Exception("TEST ERROR: Table not found - 'production.users_table'. This is an intentional error for testing the RCA system.")
NOTEBOOK
    echo -e "${NC}"
    echo ""
    echo "2. Create the job:"
    echo "   databricks jobs create --json-file databricks_test_job.json"
    echo ""
    echo "3. Run the job:"
    echo "   databricks jobs run-now --job-id <JOB_ID>"
    echo ""
    echo "4. Check FastAPI for the RCA ticket"
    echo ""
fi

################################################################################
# Summary
################################################################################

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           Databricks Webhook Setup Complete!           ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BLUE}Generated Configuration Files:${NC}"
echo "  • databricks_job_webhook_config.json"
if [ -f "databricks_cluster_webhook_config.json" ]; then
    echo "  • databricks_cluster_webhook_config.json"
fi
if [ -f "databricks_test_job.json" ]; then
    echo "  • databricks_test_job.json"
fi
echo ""

echo -e "${BLUE}Webhook URL:${NC}"
echo "  $WEBHOOK_URL"
echo ""

echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. Configure job webhooks in Databricks UI or via CLI"
echo "  2. Configure cluster webhooks (optional)"
echo "  3. Run test jobs to verify webhook delivery"
echo "  4. Monitor FastAPI logs and dashboard"
echo ""

echo -e "${BLUE}Useful Commands:${NC}"
echo ""
echo "  # List all jobs"
echo "  databricks jobs list"
echo ""
echo "  # Get job details"
echo "  databricks jobs get --job-id <JOB_ID>"
echo ""
echo "  # List clusters"
echo "  databricks clusters list"
echo ""
echo "  # Test webhook manually"
echo "  curl -X POST '$WEBHOOK_URL' -H 'Content-Type: application/json' -d @test_payload.json"
echo ""

echo -e "${BLUE}Documentation:${NC}"
echo "  • Job webhooks: https://docs.databricks.com/workflows/jobs/job-notifications.html"
echo "  • Cluster events: https://docs.databricks.com/api/workspace/clusters/events"
echo "  • Event types: https://docs.databricks.com/dev-tools/api/latest/events.html"
echo ""

echo -e "${GREEN}Setup completed successfully!${NC}"

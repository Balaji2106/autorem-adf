#!/bin/bash
# =============================================================================
# Test Databricks API Connection and Error Extraction
# =============================================================================
# This script tests if your Databricks API credentials are working correctly
#
# Usage: ./test_databricks_connection.sh [run_id]
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/genai_rca_assistant/.env"

echo "================================================================================"
echo "  DATABRICKS API CONNECTION TEST"
echo "================================================================================"
echo ""

# Check if .env exists
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ ERROR: .env file not found at: $ENV_FILE"
    echo ""
    echo "Please run setup first:"
    echo "  ./setup_databricks.sh"
    echo ""
    exit 1
fi

# Load environment variables
echo "📂 Loading environment variables from .env..."
source "$ENV_FILE"

# Check if credentials are set
if [ -z "$DATABRICKS_HOST" ] || [ -z "$DATABRICKS_TOKEN" ]; then
    echo "❌ ERROR: Databricks credentials not configured in .env"
    echo ""
    echo "Missing:"
    [ -z "$DATABRICKS_HOST" ] && echo "  - DATABRICKS_HOST"
    [ -z "$DATABRICKS_TOKEN" ] && echo "  - DATABRICKS_TOKEN"
    echo ""
    echo "Please run setup:"
    echo "  ./setup_databricks.sh"
    echo ""
    exit 1
fi

echo "✅ Credentials loaded"
echo "   Workspace: $DATABRICKS_HOST"
echo "   Token: ****${DATABRICKS_TOKEN: -8}"
echo ""

# Get run_id from argument or prompt
RUN_ID="$1"

if [ -z "$RUN_ID" ]; then
    echo "================================================================================"
    echo "EXAMPLE RUN IDs (from your recent alerts):"
    echo "================================================================================"
    echo "  204354054874177  - test4 job (the one from your alerts)"
    echo ""
    read -p "Enter a Databricks run_id to test: " RUN_ID
    echo ""
fi

if [ -z "$RUN_ID" ]; then
    echo "❌ ERROR: No run_id provided"
    echo ""
    echo "Usage:"
    echo "  ./test_databricks_connection.sh <run_id>"
    echo "  ./test_databricks_connection.sh 204354054874177"
    echo ""
    exit 1
fi

# Run the test
echo "================================================================================"
echo "TEST 1: Databricks Jobs API Connection"
echo "================================================================================"
echo ""
echo "🔄 Testing connection to Databricks Jobs API..."
echo "   URL: $DATABRICKS_HOST/api/2.1/jobs/runs/get"
echo "   Run ID: $RUN_ID"
echo ""

cd "$SCRIPT_DIR/genai_rca_assistant"

# Test using Python
echo "Running: python3 databricks_api_utils.py $RUN_ID"
echo ""
echo "--------------------------------------------------------------------------------"

if python3 databricks_api_utils.py "$RUN_ID" 2>&1; then
    TEST_RESULT=$?
    echo "--------------------------------------------------------------------------------"
    echo ""

    if [ $TEST_RESULT -eq 0 ]; then
        echo "✅ TEST PASSED: Successfully connected to Databricks API"
        echo "✅ Run details fetched successfully"
        echo "✅ Error extraction working"
        echo ""

        echo "================================================================================"
        echo "TEST 2: Webhook Simulation"
        echo "================================================================================"
        echo ""
        echo "Would you like to test the full webhook → API → RCA flow?"
        read -p "Simulate a webhook with this run_id? (y/N): " SIMULATE

        if [[ $SIMULATE =~ ^[Yy]$ ]]; then
            echo ""
            echo "📤 Creating test webhook payload..."

            cat > /tmp/test_webhook.json <<EOF
{
  "event": "on_failure",
  "job_id": "404831337617650",
  "run_id": "$RUN_ID",
  "job": {
    "job_id": "404831337617650",
    "settings": {
      "name": "test4"
    }
  },
  "run": {
    "run_id": "$RUN_ID",
    "run_name": "test4",
    "state": {
      "life_cycle_state": "TERMINATED",
      "result_state": "FAILED",
      "state_message": "Run failed with error"
    }
  }
}
EOF

            echo "✅ Webhook payload created at /tmp/test_webhook.json"
            echo ""
            echo "To test the full RCA flow, send this webhook to your endpoint:"
            echo ""
            echo "curl -X POST http://localhost:8000/databricks-monitor \\"
            echo "  -H \"Content-Type: application/json\" \\"
            echo "  -d @/tmp/test_webhook.json"
            echo ""
            echo "Expected behavior:"
            echo "  1. ✅ Webhook received and logged"
            echo "  2. ✅ Run ID extracted: $RUN_ID"
            echo "  3. ✅ API fetch attempted"
            echo "  4. ✅ Detailed error extracted"
            echo "  5. ✅ Specific RCA generated (not generic)"
            echo ""
        fi

        echo "================================================================================"
        echo "SUMMARY"
        echo "================================================================================"
        echo ""
        echo "✅ Databricks API is configured correctly"
        echo "✅ Your RCA system will now extract detailed error messages"
        echo ""
        echo "What changed:"
        echo "  BEFORE: 'The event notification does not include specific error details'"
        echo "  AFTER:  '[Task: task1] org.apache.spark.sql.AnalysisException: ...'"
        echo ""
        echo "Next steps:"
        echo "  1. Restart your RCA application"
        echo "  2. Trigger a new Databricks job failure"
        echo "  3. Check the RCA alert - it should now have specific error details"
        echo ""

    else
        echo "❌ TEST FAILED: Error occurred during API call"
        echo ""
        echo "Troubleshooting:"
        echo "  - Check if the workspace URL is correct"
        echo "  - Verify the token is valid and not expired"
        echo "  - Ensure the run_id exists: $RUN_ID"
        echo ""
    fi
else
    echo "--------------------------------------------------------------------------------"
    echo ""
    echo "❌ TEST FAILED: Could not fetch run details"
    echo ""
    echo "Common issues:"
    echo ""
    echo "1. Invalid credentials"
    echo "   → Re-run setup: ./setup_databricks.sh"
    echo ""
    echo "2. Token expired"
    echo "   → Generate new token in Databricks UI"
    echo "   → Update .env file"
    echo ""
    echo "3. Wrong workspace URL"
    echo "   → Check Azure Portal for correct URL"
    echo "   → Update .env file"
    echo ""
    echo "4. Run ID doesn't exist or not accessible"
    echo "   → Try a different run_id"
    echo "   → Check permissions in Databricks"
    echo ""
    echo "For detailed troubleshooting, see: DATABRICKS_SETUP.md"
    echo ""
fi

exit $TEST_RESULT

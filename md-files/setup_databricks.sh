#!/bin/bash
# =============================================================================
# Databricks API Configuration Setup Script
# =============================================================================
# This script helps you configure Databricks API credentials for the RCA system
#
# Usage: ./setup_databricks.sh
# =============================================================================

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/genai_rca_assistant/.env"

echo "================================================================================"
echo "  DATABRICKS API CONFIGURATION SETUP"
echo "================================================================================"
echo ""

# Check if .env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo "📝 Creating .env file from template..."
    cp "$SCRIPT_DIR/.env.example" "$ENV_FILE"
    echo "✅ .env file created at: $ENV_FILE"
    echo ""
fi

# Step 1: Get Databricks Workspace URL
echo "================================================================================"
echo "STEP 1: Get Databricks Workspace URL"
echo "================================================================================"
echo ""
echo "You need your Databricks workspace URL from Azure Portal:"
echo ""
echo "Option A: Using Azure Portal"
echo "  1. Go to: https://portal.azure.com"
echo "  2. Navigate to: Resource Groups → rg_techdemo_2025_Q4"
echo "  3. Click on: techdemo_databricks"
echo "  4. In Overview tab, copy the 'URL' field"
echo "     Example: https://adb-1234567890123456.7.azuredatabricks.net"
echo ""
echo "Option B: Using Azure CLI (if available)"
echo "  Run this command:"
echo "  az databricks workspace show \\"
echo "    --resource-group rg_techdemo_2025_Q4 \\"
echo "    --name techdemo_databricks \\"
echo "    --query workspaceUrl -o tsv"
echo ""
read -p "Enter your Databricks workspace URL: " DATABRICKS_HOST

# Validate URL format
if [[ ! $DATABRICKS_HOST =~ ^https://adb-[0-9]+\.[0-9]+\.azuredatabricks\.net$ ]]; then
    echo "⚠️  Warning: URL format doesn't match expected pattern."
    echo "   Expected: https://adb-XXXXXXXXXX.XX.azuredatabricks.net"
    echo "   You entered: $DATABRICKS_HOST"
    read -p "Continue anyway? (y/N): " CONTINUE
    if [[ ! $CONTINUE =~ ^[Yy]$ ]]; then
        echo "❌ Setup cancelled."
        exit 1
    fi
fi

echo "✅ Workspace URL: $DATABRICKS_HOST"
echo ""

# Step 2: Generate Personal Access Token
echo "================================================================================"
echo "STEP 2: Generate Databricks Personal Access Token (PAT)"
echo "================================================================================"
echo ""
echo "You need to generate a Personal Access Token from Databricks:"
echo ""
echo "1. Open Databricks workspace in browser:"
echo "   → Go to: $DATABRICKS_HOST"
echo ""
echo "2. Click your profile icon (top right) → User Settings"
echo ""
echo "3. Go to 'Access Tokens' tab"
echo ""
echo "4. Click 'Generate New Token'"
echo "   - Token name: 'RCA System API Access'"
echo "   - Lifetime: 365 days (or as per your policy)"
echo ""
echo "5. Click 'Generate' and COPY THE TOKEN"
echo "   ⚠️  Important: The token won't be shown again!"
echo ""
echo "6. Paste the token below"
echo ""
read -sp "Enter your Databricks Personal Access Token: " DATABRICKS_TOKEN
echo ""

# Validate token format
if [[ ! $DATABRICKS_TOKEN =~ ^dapi[a-f0-9]{32,}$ ]]; then
    echo ""
    echo "⚠️  Warning: Token format doesn't match expected pattern."
    echo "   Expected: dapi + 32+ hexadecimal characters"
    echo "   Token length: ${#DATABRICKS_TOKEN} characters"
    read -p "Continue anyway? (y/N): " CONTINUE
    if [[ ! $CONTINUE =~ ^[Yy]$ ]]; then
        echo "❌ Setup cancelled."
        exit 1
    fi
fi

echo "✅ Token received (length: ${#DATABRICKS_TOKEN} chars)"
echo ""

# Step 3: Update .env file
echo "================================================================================"
echo "STEP 3: Updating .env file"
echo "================================================================================"
echo ""

# Backup existing .env if it has content
if [ -s "$ENV_FILE" ]; then
    BACKUP_FILE="${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$ENV_FILE" "$BACKUP_FILE"
    echo "📦 Backed up existing .env to: $BACKUP_FILE"
fi

# Update or add DATABRICKS_HOST
if grep -q "^DATABRICKS_HOST=" "$ENV_FILE"; then
    sed -i "s|^DATABRICKS_HOST=.*|DATABRICKS_HOST=$DATABRICKS_HOST|" "$ENV_FILE"
    echo "✅ Updated DATABRICKS_HOST in .env"
else
    echo "" >> "$ENV_FILE"
    echo "DATABRICKS_HOST=$DATABRICKS_HOST" >> "$ENV_FILE"
    echo "✅ Added DATABRICKS_HOST to .env"
fi

# Update or add DATABRICKS_TOKEN
if grep -q "^DATABRICKS_TOKEN=" "$ENV_FILE"; then
    sed -i "s|^DATABRICKS_TOKEN=.*|DATABRICKS_TOKEN=$DATABRICKS_TOKEN|" "$ENV_FILE"
    echo "✅ Updated DATABRICKS_TOKEN in .env"
else
    echo "DATABRICKS_TOKEN=$DATABRICKS_TOKEN" >> "$ENV_FILE"
    echo "✅ Added DATABRICKS_TOKEN to .env"
fi

echo ""
echo "✅ Configuration saved to: $ENV_FILE"
echo ""

# Step 4: Test the connection
echo "================================================================================"
echo "STEP 4: Testing Databricks API Connection"
echo "================================================================================"
echo ""
echo "Would you like to test the connection now?"
echo ""
read -p "Enter a Databricks run_id to test (or press Enter to skip): " TEST_RUN_ID

if [ ! -z "$TEST_RUN_ID" ]; then
    echo ""
    echo "🔄 Testing connection with run_id: $TEST_RUN_ID"
    echo ""

    # Export variables for the test
    export DATABRICKS_HOST="$DATABRICKS_HOST"
    export DATABRICKS_TOKEN="$DATABRICKS_TOKEN"

    cd "$SCRIPT_DIR/genai_rca_assistant"

    if python3 databricks_api_utils.py "$TEST_RUN_ID"; then
        echo ""
        echo "✅ Connection test PASSED!"
        echo "✅ Error extraction is working correctly"
    else
        echo ""
        echo "❌ Connection test FAILED"
        echo "   Please check:"
        echo "   1. Workspace URL is correct"
        echo "   2. Token is valid and not expired"
        echo "   3. Run ID exists and is accessible"
    fi
else
    echo "⏭️  Skipping connection test"
    echo ""
    echo "To test later, run:"
    echo "  cd genai_rca_assistant"
    echo "  source ../.env"
    echo "  python3 databricks_api_utils.py <run_id>"
fi

echo ""
echo "================================================================================"
echo "SETUP COMPLETE"
echo "================================================================================"
echo ""
echo "✅ Databricks API credentials configured successfully!"
echo ""
echo "Configuration:"
echo "  - Workspace URL: $DATABRICKS_HOST"
echo "  - Token: ****${DATABRICKS_TOKEN: -8}"
echo "  - Config file: $ENV_FILE"
echo ""
echo "Next steps:"
echo "  1. Restart your RCA application to load new credentials"
echo "  2. Trigger a test Databricks job failure"
echo "  3. Check logs for detailed error extraction"
echo ""
echo "For troubleshooting, see: DATABRICKS_SETUP.md"
echo ""

#!/bin/bash

# Databricks Debug Commands
# Run these to diagnose why logs aren't flowing

RESOURCE_GROUP="rg_techdemo_2025_Q4"
DATABRICKS_WORKSPACE="techdemo_databricks"
LA_WORKSPACE="log-techdemo-rca"  # Correct workspace name from diagnostic settings

echo "============================================"
echo "DATABRICKS LOG FLOW DIAGNOSTICS"
echo "============================================"
echo ""

# Get resource IDs
DATABRICKS_ID=$(az resource show \
  --resource-group $RESOURCE_GROUP \
  --resource-type Microsoft.Databricks/workspaces \
  --name $DATABRICKS_WORKSPACE \
  --query id -o tsv)

LA_WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group $RESOURCE_GROUP \
  --workspace-name $LA_WORKSPACE \
  --query id -o tsv)

echo "Resource IDs:"
echo "  Databricks: $DATABRICKS_ID"
echo "  Log Analytics: $LA_WORKSPACE_ID"
echo ""

# Check 1: Databricks SKU (Premium required for audit logs)
echo "============================================"
echo "CHECK 1: Databricks SKU"
echo "============================================"
SKU=$(az databricks workspace show \
  --resource-group $RESOURCE_GROUP \
  --name $DATABRICKS_WORKSPACE \
  --query "sku.name" -o tsv)

echo "SKU: $SKU"
if [ "$SKU" == "premium" ]; then
  echo "✅ PASS: Premium SKU (audit logs available)"
else
  echo "❌ FAIL: SKU is '$SKU' - audit logs require Premium tier"
  echo "   Fix: Upgrade to Premium tier in Azure Portal"
fi
echo ""

# Check 2: IAM Permissions on Databricks
echo "============================================"
echo "CHECK 2: Databricks IAM Permissions"
echo "============================================"
echo "Checking roles assigned to Databricks workspace..."
az role assignment list \
  --scope $DATABRICKS_ID \
  --query "[].{Principal:principalName, Role:roleDefinitionName, Type:principalType}" \
  -o table

echo ""
echo "Looking for 'Monitoring Contributor' role..."
MONITORING_CONTRIBUTOR=$(az role assignment list \
  --scope $DATABRICKS_ID \
  --query "[?roleDefinitionName=='Monitoring Contributor'].principalName" -o tsv)

if [ -z "$MONITORING_CONTRIBUTOR" ]; then
  echo "❌ FAIL: No 'Monitoring Contributor' role found"
  echo "   This role is required for diagnostic log collection"
  echo ""
  echo "   Fix command:"
  echo "   SP_OBJECT_ID=\$(az ad sp list --display-name 'techdemo-2025_Q4' --query '[0].id' -o tsv)"
  echo "   az role assignment create \\"
  echo "     --role 'Monitoring Contributor' \\"
  echo "     --assignee-object-id \$SP_OBJECT_ID \\"
  echo "     --assignee-principal-type ServicePrincipal \\"
  echo "     --scope $DATABRICKS_ID"
else
  echo "✅ PASS: Monitoring Contributor assigned to: $MONITORING_CONTRIBUTOR"
fi
echo ""

# Check 3: IAM Permissions on Log Analytics
echo "============================================"
echo "CHECK 3: Log Analytics IAM Permissions"
echo "============================================"
echo "Checking roles assigned to Log Analytics workspace..."
az role assignment list \
  --scope $LA_WORKSPACE_ID \
  --query "[].{Principal:principalName, Role:roleDefinitionName, Type:principalType}" \
  -o table

echo ""
echo "Looking for 'Log Analytics Contributor' role..."
LA_CONTRIBUTOR=$(az role assignment list \
  --scope $LA_WORKSPACE_ID \
  --query "[?roleDefinitionName=='Log Analytics Contributor'].principalName" -o tsv)

if [ -z "$LA_CONTRIBUTOR" ]; then
  echo "❌ FAIL: No 'Log Analytics Contributor' role found"
  echo "   This role is required for writing logs"
  echo ""
  echo "   Fix command:"
  echo "   SP_OBJECT_ID=\$(az ad sp list --display-name 'techdemo-2025_Q4' --query '[0].id' -o tsv)"
  echo "   az role assignment create \\"
  echo "     --role 'Log Analytics Contributor' \\"
  echo "     --assignee-object-id \$SP_OBJECT_ID \\"
  echo "     --assignee-principal-type ServicePrincipal \\"
  echo "     --scope $LA_WORKSPACE_ID"
else
  echo "✅ PASS: Log Analytics Contributor assigned to: $LA_CONTRIBUTOR"
fi
echo ""

# Check 4: Verify workspace destination matches
echo "============================================"
echo "CHECK 4: Workspace Destination"
echo "============================================"
DIAG_WORKSPACE=$(az monitor diagnostic-settings show \
  --name send-to-log-analytics \
  --resource $DATABRICKS_ID \
  --query "workspaceId" -o tsv)

echo "Diagnostic settings destination: $DIAG_WORKSPACE"
echo "Expected Log Analytics workspace: $LA_WORKSPACE_ID"

if [ "$DIAG_WORKSPACE" == "$LA_WORKSPACE_ID" ]; then
  echo "✅ PASS: Workspace destinations match"
else
  echo "⚠️  WARNING: Workspace destinations don't match"
  echo "   Logs may be going to a different workspace"
fi
echo ""

# Check 5: Recent Databricks activity
echo "============================================"
echo "CHECK 5: Query Log Analytics for Data"
echo "============================================"
echo "NOTE: Run these KQL queries in Azure Portal → Log Analytics → Logs"
echo ""
echo "Query 1: Check if ANY Databricks logs exist (last 7 days)"
echo "----------------------------------------"
cat <<'EOF'
union
  DatabricksJobs,
  DatabricksClusters,
  DatabricksDBFS,
  DatabricksAccounts,
  DatabricksNotebook,
  DatabricksWorkspace
| where TimeGenerated > ago(7d)
| summarize Count=count() by Type, bin(TimeGenerated, 1d)
| order by TimeGenerated desc
EOF
echo ""
echo "Query 2: Check DatabricksJobs specifically (last 7 days)"
echo "----------------------------------------"
cat <<'EOF'
DatabricksJobs
| where TimeGenerated > ago(7d)
| take 100
| project TimeGenerated, JobName, RunId, ResultType, ErrorMessage
| order by TimeGenerated desc
EOF
echo ""
echo "Query 3: Check recent activity (last 24 hours)"
echo "----------------------------------------"
cat <<'EOF'
DatabricksJobs
| where TimeGenerated > ago(24h)
| summarize Count=count() by bin(TimeGenerated, 1h)
| render timechart
EOF
echo ""

# Summary
echo "============================================"
echo "SUMMARY & NEXT STEPS"
echo "============================================"
echo ""
echo "1. If SKU is not Premium: Upgrade Databricks workspace"
echo "2. If IAM roles missing: Run the fix commands shown above"
echo "3. If no logs in KQL queries:"
echo "   a) Run a test Databricks job (see instructions below)"
echo "   b) Wait 15 minutes"
echo "   c) Re-run the KQL queries"
echo ""
echo "============================================"
echo "TEST JOB INSTRUCTIONS"
echo "============================================"
echo "1. Go to Databricks Workspace → Launch Workspace"
echo "2. Workflows → Jobs → Create Job"
echo "3. Create notebook with this code:"
echo "   raise Exception('TEST: Log flow verification')"
echo "4. Run the job (it will fail intentionally)"
echo "5. Wait 15 minutes for logs to appear"
echo "6. Run KQL queries in Log Analytics"
echo ""
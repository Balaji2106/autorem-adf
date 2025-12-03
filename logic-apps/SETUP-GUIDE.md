# Logic Apps Setup Guide for Auto-Remediation

This guide explains how to deploy and configure Azure Logic Apps for ADF and Databricks auto-remediation.

## Overview

The auto-remediation system uses two Logic Apps:

1. **ADF Auto-Remediation Logic App** - Retries failed ADF pipelines
2. **Databricks Auto-Remediation Logic App** - Handles Databricks job retries, cluster restarts, and library reinstalls

## Architecture Flow

```
ADF/Databricks Failure
    ↓
Azure Monitor Alert
    ↓
Python API (FastAPI)
    ↓
AI generates RCA (auto_heal_possible=true)
    ↓
Python API calls Logic App
    ↓
Logic App performs remediation
    ↓
Returns new run_id
    ↓
Python API monitors remediation
    ↓
Success/Failure handling
```

---

## Part 1: Deploy ADF Auto-Remediation Logic App

### Step 1: Prepare Parameters

Create a file `adf-logicapp-parameters.json`:

```json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "logicAppName": {
      "value": "adf-auto-remediation"
    },
    "location": {
      "value": "eastus"
    },
    "subscriptionId": {
      "value": "YOUR_SUBSCRIPTION_ID"
    },
    "resourceGroupName": {
      "value": "YOUR_ADF_RESOURCE_GROUP"
    },
    "dataFactoryName": {
      "value": "YOUR_DATA_FACTORY_NAME"
    }
  }
}
```

### Step 2: Deploy Logic App

```bash
# Login to Azure
az login

# Set your subscription
az account set --subscription "YOUR_SUBSCRIPTION_ID"

# Create resource group (if doesn't exist)
az group create --name rg-auto-remediation --location eastus

# Deploy Logic App
az deployment group create \
  --resource-group rg-auto-remediation \
  --template-file adf-auto-remediation-logicapp.json \
  --parameters adf-logicapp-parameters.json
```

### Step 3: Authorize ADF API Connection

The Logic App uses an **ADF API Connection** (not Managed Identity). You need to authorize it:

**Option A: Via Azure Portal (Recommended)**

1. Go to Azure Portal → Resource Groups → `rg-auto-remediation`
2. Find the API Connection: `azuredatafactory`
3. Click on it → Left menu → **Edit API connection**
4. Click **Authorize** button
5. Sign in with your Azure account
6. Click **Save**

**Option B: Via Azure CLI**

```bash
# The API Connection was created during deployment
# You can authorize it programmatically (if needed)
# Or just use the Azure Portal method above
```

**IMPORTANT:** Without authorization, the Logic App will fail with "AuthorizationFailed" error.

### Step 4: Get Webhook URL

```bash
# Get Logic App webhook URL
az deployment group show \
  --resource-group rg-auto-remediation \
  --name <deployment-name> \
  --query properties.outputs.logicAppUrl.value -o tsv
```

**Save this URL** - you'll need it for the Python API configuration.

---

## Part 2: Deploy Databricks Auto-Remediation Logic App

### Step 1: Create Databricks Access Token

1. Go to Databricks workspace → User Settings → Access Tokens
2. Click "Generate New Token"
3. Set lifetime (e.g., 90 days)
4. Copy the token - **you'll only see it once!**

**IMPORTANT:** For production, store this token in Azure Key Vault (see section below).

### Step 2: Prepare Parameters

Create `databricks-logicapp-parameters.json`:

```json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "logicAppName": {
      "value": "databricks-auto-remediation"
    },
    "location": {
      "value": "eastus"
    },
    "databricksWorkspaceUrl": {
      "value": "https://adb-1234567890.azuredatabricks.net"
    },
    "databricksToken": {
      "value": "dapi..."
    }
  }
}
```

### Step 3: Deploy Logic App

```bash
# Deploy Databricks Logic App
az deployment group create \
  --resource-group rg-auto-remediation \
  --template-file databricks-auto-remediation-logicapp.json \
  --parameters databricks-logicapp-parameters.json
```

### Step 4: Get Webhook URL

```bash
# Get Logic App webhook URL
az deployment group show \
  --resource-group rg-auto-remediation \
  --name <deployment-name> \
  --query properties.outputs.logicAppUrl.value -o tsv
```

**Save this URL** for Python API configuration.

---

## Part 3: Configure Python API

Update your `.env` file with Logic App URLs:

```bash
# Enable auto-remediation
AUTO_REMEDIATION_ENABLED=true

# ADF configuration
AZURE_SUBSCRIPTION_ID=your-subscription-id
AZURE_RESOURCE_GROUP=your-adf-resource-group
AZURE_DATA_FACTORY_NAME=your-data-factory-name

# Logic App URLs
PLAYBOOK_RETRY_PIPELINE=https://prod-XX.eastus.logic.azure.com/workflows/.../triggers/manual/paths/invoke?api-version=...
PLAYBOOK_RESTART_CLUSTER=https://prod-YY.eastus.logic.azure.com/workflows/.../triggers/manual/paths/invoke?api-version=...
PLAYBOOK_RETRY_JOB=https://prod-YY.eastus.logic.azure.com/workflows/.../triggers/manual/paths/invoke?api-version=...
PLAYBOOK_REINSTALL_LIBRARIES=https://prod-YY.eastus.logic.azure.com/workflows/.../triggers/manual/paths/invoke?api-version=...

# Azure authentication (for monitoring ADF runs)
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret

# Databricks (for monitoring job runs)
DATABRICKS_HOST=https://adb-1234567890.azuredatabricks.net
DATABRICKS_TOKEN=dapi...
```

---

## Part 4: Test the Integration

### Test ADF Remediation

```bash
# Send test request to Logic App
curl -X POST "YOUR_ADF_LOGIC_APP_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_name": "TestPipeline",
    "ticket_id": "TEST-001",
    "error_type": "GatewayTimeout",
    "original_run_id": "abc123",
    "retry_attempt": 1,
    "max_retries": 3,
    "remediation_action": "retry_pipeline",
    "timestamp": "2025-12-03T12:00:00Z"
  }'
```

**Expected Response:**
```json
{
  "status": "success",
  "run_id": "new-run-id-456",
  "message": "ADF pipeline re-run triggered successfully",
  "pipeline_name": "TestPipeline",
  "ticket_id": "TEST-001",
  "retry_attempt": 1
}
```

### Test Databricks Job Retry

```bash
curl -X POST "YOUR_DATABRICKS_LOGIC_APP_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "job_name": "TestJob",
    "job_id": "123456",
    "ticket_id": "TEST-002",
    "error_type": "DatabricksTimeoutError",
    "original_run_id": "789",
    "retry_attempt": 1,
    "max_retries": 3,
    "remediation_action": "retry_job",
    "timestamp": "2025-12-03T12:00:00Z"
  }'
```

### Test Databricks Cluster Restart

```bash
curl -X POST "YOUR_DATABRICKS_LOGIC_APP_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_id": "0123-456789-abc123",
    "ticket_id": "TEST-003",
    "error_type": "DatabricksClusterStartFailure",
    "retry_attempt": 1,
    "remediation_action": "restart_cluster",
    "timestamp": "2025-12-03T12:00:00Z"
  }'
```

---

## Part 5: Production Best Practices

### 1. Store Secrets in Azure Key Vault

```bash
# Create Key Vault
az keyvault create \
  --name kv-auto-remediation \
  --resource-group rg-auto-remediation \
  --location eastus

# Store Databricks token
az keyvault secret set \
  --vault-name kv-auto-remediation \
  --name databricks-token \
  --value "dapi..."

# Grant Logic App access to Key Vault
az keyvault set-policy \
  --name kv-auto-remediation \
  --object-id $PRINCIPAL_ID \
  --secret-permissions get
```

### 2. Enable Logic App Diagnostic Logs

```bash
# Create Log Analytics workspace
az monitor log-analytics workspace create \
  --resource-group rg-auto-remediation \
  --workspace-name law-auto-remediation

# Enable diagnostics
az monitor diagnostic-settings create \
  --name logic-app-diagnostics \
  --resource /subscriptions/.../resourceGroups/rg-auto-remediation/providers/Microsoft.Logic/workflows/adf-auto-remediation \
  --workspace /subscriptions/.../resourceGroups/rg-auto-remediation/providers/Microsoft.OperationalInsights/workspaces/law-auto-remediation \
  --logs '[{"category":"WorkflowRuntime","enabled":true}]' \
  --metrics '[{"category":"AllMetrics","enabled":true}]'
```

### 3. Set Up Alerts for Logic App Failures

```bash
# Create action group
az monitor action-group create \
  --name ag-logic-app-failures \
  --resource-group rg-auto-remediation \
  --short-name LAFailures \
  --email-receiver name=DevOps email=devops@company.com

# Create alert rule
az monitor metrics alert create \
  --name "Logic App Failures" \
  --resource-group rg-auto-remediation \
  --scopes /subscriptions/.../resourceGroups/rg-auto-remediation/providers/Microsoft.Logic/workflows/adf-auto-remediation \
  --condition "count RunsFailed > 5" \
  --window-size 5m \
  --evaluation-frequency 1m \
  --action ag-logic-app-failures
```

---

## Part 6: Monitoring and Troubleshooting

### View Logic App Run History

```bash
# Azure Portal
# Navigate to: Logic App → Overview → Runs history

# Or via CLI
az logic workflow run list \
  --resource-group rg-auto-remediation \
  --workflow-name adf-auto-remediation \
  --top 10
```

### Debug Failed Runs

1. Go to Logic App → Run history → Click failed run
2. Expand each action to see inputs/outputs
3. Check "Retry_ADF_Pipeline" action for ADF API errors
4. Check "Parse_Run_ID" for JSON parsing issues

### Common Issues

**Issue 1: "Forbidden" error when calling ADF API**
- **Solution:** Verify Logic App Managed Identity has Contributor role on ADF

**Issue 2: Databricks token expired**
- **Solution:** Regenerate token and update Logic App parameters

**Issue 3: Logic App times out**
- **Solution:** Check ADF/Databricks API responsiveness. Add retry logic if needed.

**Issue 4: Run ID not returned**
- **Solution:** Check ADF API response format. Update "Parse_Run_ID" schema if needed.

---

## Part 7: Cost Optimization

### Logic App Pricing

- **Consumption Plan:** Pay per execution
  - ~$0.000025 per action execution
  - ~100 actions per remediation = $0.0025 per remediation
  - Expected cost: $5-20/month for typical usage

### Reduce Costs

1. **Minimize polling:** Use exponential backoff for monitoring
2. **Batch operations:** Consolidate multiple retries
3. **Use Standard Plan** if >10,000 executions/month

---

## Part 8: Scaling Considerations

### High Volume Scenarios

If processing >1000 remediations/day:

1. **Use Azure Functions** instead of Logic Apps for complex logic
2. **Implement queue-based processing** (Azure Service Bus)
3. **Add rate limiting** to avoid throttling ADF/Databricks APIs
4. **Cache job/cluster metadata** to reduce API calls

---

## Summary

You now have:
- ✅ ADF Logic App deployed and configured
- ✅ Databricks Logic App deployed and configured
- ✅ Python API integrated with Logic Apps
- ✅ Auto-heal logic in RCA prompts
- ✅ Monitoring and alerting set up

## Next Steps

1. Test end-to-end flow with a real ADF pipeline failure
2. Monitor remediation success rate in dashboard
3. Tune retry limits and backoff intervals based on data
4. Extend to other error types as needed

## Support

For issues or questions:
- Check Logic App run history for errors
- Review Python API logs (`/var/log/auto-remediation.log`)
- Refer to Azure Logic Apps documentation

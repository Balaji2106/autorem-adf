# Quick Start Guide - Logic Apps Auto-Remediation

This is a simplified guide to get your auto-remediation Logic Apps up and running quickly.

## Prerequisites

- Azure subscription with ADF and/or Databricks
- Python API already deployed (from this repo)
- Azure CLI installed

---

## Step 1: Deploy ADF Logic App (5 minutes)

### 1.1 Create parameters file

Create `adf-params.json`:

```json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "logicAppName": {"value": "adf-auto-remediation"},
    "location": {"value": "northcentralus"},
    "subscriptionId": {"value": "d28a053b-ed09-40dd-92d6-43401a2c9799"},
    "resourceGroupName": {"value": "rg_techdemo_2025_Q4"},
    "dataFactoryName": {"value": "adf-techdemo-rca"}
  }
}
```

### 1.2 Deploy

```bash
az deployment group create \
  --resource-group rg_techdemo_2025_Q4 \
  --template-file logic-apps/adf-auto-remediation-logicapp.json \
  --parameters adf-params.json
```

### 1.3 Authorize the API Connection

**CRITICAL STEP:** The Logic App won't work until you authorize the ADF connection.

1. Go to Azure Portal
2. Navigate to: Resource Groups → `rg_techdemo_2025_Q4` → API Connections → `azuredatafactory`
3. Click **Edit API connection** (left menu)
4. Click **Authorize** button
5. Sign in with your Azure account
6. Click **Save**

### 1.4 Get Webhook URL

```bash
az deployment group show \
  --resource-group rg_techdemo_2025_Q4 \
  --name adf-auto-remediation \
  --query properties.outputs.logicAppUrl.value -o tsv
```

Copy this URL - you'll add it to `.env` as `PLAYBOOK_RETRY_PIPELINE`

---

## Step 2: Deploy Databricks Logic App (5 minutes)

### 2.1 Get Databricks Token

1. Go to your Databricks workspace
2. Click User Settings (top right)
3. Go to **Access Tokens** tab
4. Click **Generate New Token**
5. Set name: "Auto-Remediation"
6. Set lifetime: 90 days
7. Click **Generate**
8. **Copy the token** (you won't see it again!)

### 2.2 Create parameters file

Create `databricks-params.json`:

```json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "logicAppName": {"value": "databricks-auto-remediation"},
    "location": {"value": "northcentralus"},
    "databricksWorkspaceUrl": {"value": "https://adb-XXXXXXX.azuredatabricks.net"},
    "databricksToken": {"value": "dapi...YOUR_TOKEN_HERE..."}
  }
}
```

### 2.3 Deploy

```bash
az deployment group create \
  --resource-group rg_techdemo_2025_Q4 \
  --template-file logic-apps/databricks-auto-remediation-logicapp.json \
  --parameters databricks-params.json
```

### 2.4 Get Webhook URL

```bash
az deployment group show \
  --resource-group rg_techdemo_2025_Q4 \
  --name databricks-auto-remediation \
  --query properties.outputs.logicAppUrl.value -o tsv
```

Copy this URL - you'll use it for all Databricks playbooks.

---

## Step 3: Configure Python API (2 minutes)

Update your `.env` file:

```bash
# Enable auto-remediation
AUTO_REMEDIATION_ENABLED=true

# ADF Logic App URL (from Step 1.4)
PLAYBOOK_RETRY_PIPELINE=https://prod-XX.northcentralus.logic.azure.com/workflows/.../invoke?api-version=...&sig=...

# Databricks Logic App URLs (all use the same URL from Step 2.4)
PLAYBOOK_RETRY_JOB=https://prod-YY.northcentralus.logic.azure.com/workflows/.../invoke?api-version=...&sig=...
PLAYBOOK_RESTART_CLUSTER=https://prod-YY.northcentralus.logic.azure.com/workflows/.../invoke?api-version=...&sig=...
PLAYBOOK_REINSTALL_LIBRARIES=https://prod-YY.northcentralus.logic.azure.com/workflows/.../invoke?api-version=...&sig=...

# Azure credentials (for monitoring remediation runs)
AZURE_SUBSCRIPTION_ID=d28a053b-ed09-40dd-92d6-43401a2c9799
AZURE_RESOURCE_GROUP=rg_techdemo_2025_Q4
AZURE_DATA_FACTORY_NAME=adf-techdemo-rca
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret

# Databricks (for monitoring job runs)
DATABRICKS_HOST=https://adb-XXXXXXX.azuredatabricks.net
DATABRICKS_TOKEN=dapi...
```

Restart your Python API:

```bash
# If using systemd
sudo systemctl restart autorem-api

# Or if running manually
# Stop the current process and restart
python genai_rca_assistant/main.py
```

---

## Step 4: Test It! (5 minutes)

### Test ADF Remediation

```bash
curl -X POST "YOUR_ADF_LOGIC_APP_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_name": "TestPipeline",
    "ticket_id": "TEST-001",
    "error_type": "GatewayTimeout",
    "remediation_action": "retry_pipeline",
    "retry_attempt": 1
  }'
```

**Expected response:**
```json
{
  "status": "success",
  "run_id": "new-run-id-here",
  "message": "ADF pipeline re-run triggered successfully",
  ...
}
```

**If you get "AuthorizationFailed" error:** Go back to Step 1.3 and authorize the API connection!

### Test Databricks Job Retry

```bash
curl -X POST "YOUR_DATABRICKS_LOGIC_APP_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "123456",
    "ticket_id": "TEST-002",
    "error_type": "DatabricksTimeoutError",
    "remediation_action": "retry_job",
    "retry_attempt": 1
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
    "remediation_action": "restart_cluster",
    "retry_attempt": 1
  }'
```

---

## Step 5: Monitor (Ongoing)

### Check Logic App Runs

```bash
# Via Azure Portal
# Navigate to: Logic App → Overview → Runs history

# Via CLI
az logic workflow run list \
  --resource-group rg_techdemo_2025_Q4 \
  --workflow-name adf-auto-remediation \
  --top 10
```

### View Auto-Remediation in Dashboard

1. Go to your dashboard: `http://your-api-url/dashboard`
2. Look for tickets with status: **Remediation In Progress** or **Auto-Remediated**
3. Check the MTTR (should be < 5 minutes for auto-remediated tickets!)

---

## Troubleshooting

### Issue: "AuthorizationFailed" when Logic App runs

**Solution:** You didn't authorize the ADF API Connection. Go to Azure Portal → API Connections → azuredatafactory → Edit API connection → Authorize → Save.

### Issue: Logic App not triggering

**Check:**
1. Is `AUTO_REMEDIATION_ENABLED=true` in `.env`?
2. Did the RCA show `auto_heal_possible: true`?
3. Is the Logic App URL correct in `.env`?
4. Check Python API logs for errors

### Issue: Databricks token expired

**Solution:** Generate a new token (Step 2.1) and update the Logic App parameters:

```bash
# Update just the token parameter
az logic workflow update \
  --resource-group rg_techdemo_2025_Q4 \
  --name databricks-auto-remediation \
  --set parameters.databricksToken.value='dapi-new-token-here'
```

### Issue: Pipeline/Job not found

**Check:**
- Pipeline name in the payload matches the actual pipeline name in ADF
- Job ID in the payload is correct (get from Databricks UI)
- Cluster ID is correct (get from Databricks UI)

---

## Summary

You should now have:

- ✅ ADF Logic App deployed and authorized
- ✅ Databricks Logic App deployed
- ✅ Python API configured with Logic App URLs
- ✅ Auto-remediation enabled
- ✅ Test requests working

**Next:** Wait for a real ADF/Databricks failure to see auto-remediation in action! 🎉

---

## What Gets Auto-Remediated

**ADF (4 error types):**
- GatewayTimeout
- HttpConnectionFailed
- ThrottlingError
- InternalServerError

**Databricks (5 error types):**
- DatabricksClusterStartFailure
- DatabricksResourceExhausted
- DatabricksLibraryInstallationError
- DatabricksDriverNotResponding
- DatabricksTimeoutError

All others require manual intervention.

---

## Cost Estimate

- **Logic App (Consumption):** ~$5-20/month
- **API Connection:** Free
- **Azure Monitor:** Included in existing alerts

Total: **$5-20/month** for auto-remediation!

---

## Need Help?

- Detailed guide: See `SETUP-GUIDE.md`
- Error matrix: See `AUTO-REMEDIATION-MATRIX.md`
- Architecture: See `README.md`

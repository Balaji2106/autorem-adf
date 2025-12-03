# Logic Apps for Auto-Remediation

This directory contains Azure Logic Apps for automatic remediation of ADF and Databricks failures.

## Files

- **`adf-auto-remediation-logicapp.json`** - ARM template for ADF pipeline retry Logic App
- **`databricks-auto-remediation-logicapp.json`** - ARM template for Databricks job/cluster remediation Logic App
- **`SETUP-GUIDE.md`** - Complete deployment and configuration guide
- **`AUTO-REMEDIATION-MATRIX.md`** - Reference for which errors can be auto-remediated

## Quick Start

1. **Deploy Logic Apps:**
   ```bash
   # See SETUP-GUIDE.md for detailed instructions
   az deployment group create \
     --resource-group rg-auto-remediation \
     --template-file adf-auto-remediation-logicapp.json

   az deployment group create \
     --resource-group rg-auto-remediation \
     --template-file databricks-auto-remediation-logicapp.json
   ```

2. **Configure Python API:**
   - Get Logic App webhook URLs from deployment outputs
   - Add URLs to `.env` file:
     - `PLAYBOOK_RETRY_PIPELINE=<adf-logic-app-url>`
     - `PLAYBOOK_RETRY_JOB=<databricks-logic-app-url>`
     - `PLAYBOOK_RESTART_CLUSTER=<databricks-logic-app-url>`

3. **Enable Auto-Remediation:**
   ```bash
   # In .env file
   AUTO_REMEDIATION_ENABLED=true
   ```

## What Gets Auto-Remediated

### ADF Errors (4 types)
- ✅ GatewayTimeout
- ✅ HttpConnectionFailed
- ✅ ThrottlingError
- ✅ InternalServerError

### Databricks Errors (5 types)
- ✅ DatabricksClusterStartFailure
- ✅ DatabricksResourceExhausted
- ✅ DatabricksLibraryInstallationError
- ✅ DatabricksDriverNotResponding
- ✅ DatabricksTimeoutError

See `AUTO-REMEDIATION-MATRIX.md` for complete list.

## How It Works

```
Pipeline Fails → Azure Monitor → Python API → AI RCA (auto_heal_possible=true)
    ↓
Python API calls Logic App with remediation payload
    ↓
Logic App retries pipeline/job via Azure API
    ↓
Returns new run_id
    ↓
Python API monitors run status (polls every 30s)
    ↓
Success: Close ticket, update Jira/Slack ✅
Failure: Retry with backoff OR escalate to manual 🔴
```

## Support

- **Deployment:** See `SETUP-GUIDE.md`
- **Error Matrix:** See `AUTO-REMEDIATION-MATRIX.md`
- **Configuration:** See `../md-files/.env.example`
- **Code:** See `../genai_rca_assistant/main.py` (lines 1064-1610)

## Architecture

```
┌─────────────────────────────────────────────┐
│         ADF Auto-Remediation                │
│         Logic App                           │
│  ┌───────────────────────────────────────┐  │
│  │ 1. Receive webhook from Python API    │  │
│  │ 2. Parse payload (pipeline_name, etc) │  │
│  │ 3. Call ADF REST API to retry pipeline│  │
│  │ 4. Return new run_id                  │  │
│  └───────────────────────────────────────┘  │
│  Uses: Managed Identity for ADF access     │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│      Databricks Auto-Remediation            │
│         Logic App                           │
│  ┌───────────────────────────────────────┐  │
│  │ 1. Receive webhook from Python API    │  │
│  │ 2. Parse payload (action type)        │  │
│  │ 3. Switch on remediation_action:      │  │
│  │    - retry_job: Call Jobs API         │  │
│  │    - restart_cluster: Call Cluster API│  │
│  │    - reinstall_libraries: Call Lib API│  │
│  │ 4. Return new run_id/status           │  │
│  └───────────────────────────────────────┘  │
│  Uses: Databricks PAT for API access       │
└─────────────────────────────────────────────┘
```

## Cost Estimate

- **Logic App Consumption Plan:** ~$0.000025 per action execution
- **Typical remediation:** ~100 actions = $0.0025 per remediation
- **Expected monthly cost:** $5-20 for typical usage (100-1000 remediations/month)

## Next Steps

1. Review `AUTO-REMEDIATION-MATRIX.md` to understand what can be auto-remediated
2. Follow `SETUP-GUIDE.md` to deploy Logic Apps
3. Test with sample payloads (examples in SETUP-GUIDE.md)
4. Enable `AUTO_REMEDIATION_ENABLED=true` in production
5. Monitor Logic App run history and dashboard metrics

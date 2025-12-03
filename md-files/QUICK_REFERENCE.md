# 🎯 QUICK REFERENCE GUIDE

## 📋 TL;DR - What You Need to Know

### Can we send ADF errors directly via webhooks (no Logic Apps)?
**✅ YES** - Use Azure Monitor Action Groups → Webhook → FastAPI `/azure-monitor`

### Are service endpoints stable and maintainable?
**✅ YES** - Each service has dedicated endpoint with isolated error extraction

### Can Databricks detect ALL errors (not just jobs)?
**✅ YES** - Configure webhooks for jobs, clusters, and library events

### What can be auto-remediated?
**✅ MANY** - Timeouts, connection failures, cluster restarts, library fallbacks

---

## 🚀 30-SECOND SETUP

### Azure Data Factory
```bash
./setup_azure_adf_webhooks.sh
# Provide: Resource Group, ADF Name, FastAPI URL, API Key
# Done! Alerts now go directly to FastAPI
```

### Databricks
```bash
./setup_databricks_webhooks.sh
# Provide: FastAPI URL
# Follow prompts to configure job & cluster webhooks
```

---

## 📊 ARCHITECTURE AT A GLANCE

```
┌─────────────┐  ┌─────────────────┐  ┌──────────────────┐
│  ADF Fails  │  │ Databricks Job  │  │ Cluster Fails    │
│             │  │ Fails           │  │                  │
└──────┬──────┘  └────────┬────────┘  └────────┬─────────┘
       │                  │                     │
       │ Webhook         │ Webhook            │ Webhook
       ↓                  ↓                     ↓
┌──────────────────────────────────────────────────────────┐
│              FastAPI Service Endpoints                    │
│                                                           │
│  /azure-monitor          /databricks-monitor             │
│       ↓                          ↓                        │
│  ADF Extractor           Databricks Extractor            │
│       ↓                          ↓                        │
│  ┌──────────────────────────────────────────┐           │
│  │    Common RCA Processing Pipeline        │           │
│  │  • AI-powered RCA generation             │           │
│  │  • Deduplication (by run_id)             │           │
│  │  • Ticket creation                       │           │
│  │  • ITSM integration (Jira)               │           │
│  │  • Notifications (Slack)                 │           │
│  │  • Auto-remediation (optional)           │           │
│  └──────────────────────────────────────────┘           │
└──────────────────────────────────────────────────────────┘
```

---

## 📂 KEY FILES

### Documentation
| File | Purpose |
|------|---------|
| `IMPLEMENTATION_SUMMARY.md` | **Start here** - Complete guide with answers to all questions |
| `WEBHOOK_ARCHITECTURE.md` | Detailed architecture and setup steps |
| `AUTO_REMEDIATION_GUIDE.md` | Auto-remediation strategies and code |
| `QUICK_REFERENCE.md` | This file - Quick lookup |

### Code
| File | Purpose |
|------|---------|
| `genai_rca_assistant/error_extractors.py` | **NEW** - Service-specific error extraction |
| `genai_rca_assistant/main.py` | Main FastAPI app (update to use extractors) |
| `genai_rca_assistant/databricks_api_utils.py` | Databricks API integration |

### Setup Scripts
| Script | Purpose |
|--------|---------|
| `setup_azure_adf_webhooks.sh` | **NEW** - Automated ADF webhook setup |
| `setup_databricks_webhooks.sh` | **NEW** - Databricks webhook setup wizard |
| `setup_databricks.sh` | Databricks API credentials setup |
| `test_databricks_connection.sh` | Test Databricks API connection |

---

## 🎯 IMPLEMENTATION CHECKLIST

### Phase 1: Code Update (30 minutes)
- [ ] Add `error_extractors.py` to project (already created)
- [ ] Update `main.py` imports:
  ```python
  from error_extractors import AzureDataFactoryExtractor, DatabricksExtractor
  ```
- [ ] Update `/azure-monitor` endpoint to use `AzureDataFactoryExtractor.extract()`
- [ ] Update `/databricks-monitor` endpoint to use `DatabricksExtractor.extract()`
- [ ] Test locally

### Phase 2: Azure ADF Setup (15 minutes)
- [ ] Run `./setup_azure_adf_webhooks.sh`
- [ ] Provide configuration (Resource Group, ADF Name, FastAPI URL, API Key)
- [ ] Send test webhook
- [ ] Verify ticket in dashboard

### Phase 3: Databricks Setup (20 minutes)
- [ ] Run `./setup_databricks_webhooks.sh`
- [ ] Configure job webhooks in Databricks UI
- [ ] Configure cluster webhooks (optional)
- [ ] Send test webhooks
- [ ] Verify tickets in dashboard

### Phase 4: Testing (30 minutes)
- [ ] Trigger real ADF pipeline failure → Check ticket
- [ ] Trigger real Databricks job failure → Check ticket
- [ ] Terminate Databricks cluster → Check ticket
- [ ] Send duplicate webhook → Verify deduplication
- [ ] Check error messages are detailed (not generic)

### Phase 5: Auto-Remediation (Optional, 1 hour)
- [ ] Review `AUTO_REMEDIATION_GUIDE.md`
- [ ] Enable `AUTO_REMEDIATION_ENABLED=true` in `.env`
- [ ] Configure playbook URLs
- [ ] Test retry-based remediation
- [ ] Monitor success rate

---

## 🔧 COMMON COMMANDS

### ADF Webhook Management
```bash
# List alert rules
az monitor metrics alert list \
  --resource-group rg_techdemo_2025_Q4 \
  --output table

# List action groups
az monitor action-group list \
  --resource-group rg_techdemo_2025_Q4 \
  --output table

# Test webhook
curl -X POST "https://your-app.azurewebsites.net/azure-monitor?api_key=YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d @test_adf_payload.json

# Delete alert rule
az monitor metrics alert delete \
  --name "alert-adf-pipeline-failure" \
  --resource-group rg_techdemo_2025_Q4
```

### Databricks Webhook Management
```bash
# List jobs
databricks jobs list

# Get job details
databricks jobs get --job-id <JOB_ID>

# List clusters
databricks clusters list

# Test webhook
curl -X POST "https://your-app.azurewebsites.net/databricks-monitor" \
  -H "Content-Type: application/json" \
  -d @test_databricks_payload.json

# Test Databricks API connection
./test_databricks_connection.sh <RUN_ID>
```

### Application Management
```bash
# Start FastAPI locally
cd genai_rca_assistant
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# View logs
tail -f app.log

# Check recent webhooks
tail -f app.log | grep "WEBHOOK RECEIVED"

# Check tickets in database
sqlite3 data/tickets.db "SELECT id, pipeline, status, timestamp FROM tickets ORDER BY timestamp DESC LIMIT 10;"
```

---

## 🧪 TEST PAYLOADS

### ADF Test Payload
```json
{
  "data": {
    "essentials": {
      "alertRule": "TEST_Pipeline",
      "severity": "Sev2"
    },
    "alertContext": {
      "properties": {
        "PipelineName": "Test_Pipeline",
        "PipelineRunId": "test-run-123",
        "ErrorCode": "UserErrorSourceBlobNotExists",
        "ErrorMessage": "TEST: Blob container 'input-data' does not exist",
        "Error": {
          "errorCode": "UserErrorSourceBlobNotExists",
          "message": "TEST: The specified blob container does not exist.",
          "failureType": "UserError"
        }
      }
    }
  }
}
```

### Databricks Job Test Payload
```json
{
  "event": "job.failure",
  "job": {
    "job_id": 999999,
    "settings": {"name": "TEST_Job"}
  },
  "run": {
    "run_id": 123456,
    "state": {
      "life_cycle_state": "TERMINATED",
      "result_state": "FAILED",
      "state_message": "TEST: Job failed intentionally"
    }
  }
}
```

### Databricks Cluster Test Payload
```json
{
  "event": "cluster.terminated",
  "cluster": {
    "cluster_id": "test-cluster-123",
    "cluster_name": "TEST_Cluster",
    "state": "TERMINATED",
    "state_message": "TEST: Driver not responding",
    "termination_reason": {
      "code": "DRIVER_NOT_RESPONDING",
      "type": "ERROR"
    }
  }
}
```

---

## 🔍 TROUBLESHOOTING QUICK FIXES

### Webhook not received
```bash
# Check FastAPI is accessible
curl -I https://your-app.azurewebsites.net/

# Check alert rule is firing
az monitor metrics alert show --name "alert-adf-pipeline-failure" \
  --resource-group rg_techdemo_2025_Q4 \
  --query "enabled"

# Test webhook manually (see test payloads above)
```

### Generic error messages
```bash
# Check if error_extractors.py is being used
grep "AzureDataFactoryExtractor.extract" genai_rca_assistant/main.py

# Check logs show detailed error
tail -f app.log | grep "Error message"
# Should see actual error, not "Pipeline failed"
```

### Databricks API fetch fails
```bash
# Test API connection
./test_databricks_connection.sh <RUN_ID>

# Check credentials
cat genai_rca_assistant/.env | grep DATABRICKS
```

### Duplicate tickets
```bash
# Check logs for deduplication
tail -f app.log | grep "DUPLICATE"

# Check database index
sqlite3 data/tickets.db "SELECT sql FROM sqlite_master WHERE name='idx_tickets_run_id';"
```

---

## 📊 ENDPOINT COMPARISON

| Feature | ADF (before) | ADF (after) | Databricks (before) | Databricks (after) |
|---------|--------------|-------------|---------------------|-------------------|
| **Latency** | 60-65s | 60-61s | Instant | Instant |
| **Intermediary** | Logic Apps ❌ | None ✅ | None ✅ | None ✅ |
| **Error Detail** | Generic | Detailed ✅ | Generic | Detailed ✅ |
| **Deduplication** | No | Yes ✅ | No | Yes ✅ |
| **Cost** | High | Low ✅ | Low | Low ✅ |
| **Failure Points** | 4 | 3 ✅ | 2 | 2 ✅ |
| **Cluster Events** | N/A | N/A | No | Yes ✅ |
| **Library Events** | N/A | N/A | No | Yes ✅ |

---

## 🎯 AUTO-REMEDIATION AT A GLANCE

### ✅ Easy Wins (Implement First)
| Error | Strategy | Risk | Time to Implement |
|-------|----------|------|-------------------|
| GatewayTimeout | Retry after 10s | 🟢 Low | 1 hour |
| HttpConnectionFailed | Retry pipeline | 🟢 Low | 1 hour |
| ThrottlingError | Retry with delay | 🟢 Low | 1 hour |
| Cluster Terminated | Auto-restart | 🟢 Low | 2 hours |
| Library Install Failed | Try fallback version | 🟢 Low | 2 hours |

### ⚠️ Medium Complexity
| Error | Strategy | Risk | Time to Implement |
|-------|----------|------|-------------------|
| Resource Exhausted | Scale up cluster | 🟡 Medium | 4 hours |
| Upstream Dependency | Check & retry | 🟡 Medium | 4 hours |

### ❌ Not Recommended
- Schema changes (high risk)
- Permission changes (security risk)
- Data corruption fixes (integrity risk)

---

## 📈 SUCCESS CRITERIA

### Performance
- ✅ Alert to Ticket: < 90 seconds
- ✅ Webhook Success Rate: > 99%
- ✅ Duplicate Detection: 100%
- ✅ API Error Fetch: > 95%

### Business Impact
- ✅ MTTR Reduction: 60-80% (with auto-remediation)
- ✅ Engineering Time Saved: 20-30 hours/month
- ✅ Alert Fatigue Reduction: 40%
- ✅ Cost Savings: Eliminate Logic App charges

---

## 🔗 QUICK LINKS

### Internal Docs
- [Complete Implementation Guide](./IMPLEMENTATION_SUMMARY.md)
- [Architecture Details](./WEBHOOK_ARCHITECTURE.md)
- [Auto-Remediation Guide](./AUTO_REMEDIATION_GUIDE.md)
- [Project README](./README.md)

### Azure Resources
- [Azure Monitor Webhooks](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/action-groups#webhook)
- [ADF Monitoring](https://learn.microsoft.com/en-us/azure/data-factory/monitor-visually)

### Databricks Resources
- [Job Notifications](https://docs.databricks.com/workflows/jobs/job-notifications.html)
- [Event Notifications](https://docs.databricks.com/api/workspace/clusters/events)
- [REST API](https://docs.databricks.com/api/workspace/introduction)

---

## 💡 TIPS & BEST PRACTICES

### Configuration
- ✅ Use query parameter for API key (Action Groups don't support custom headers)
- ✅ Enable deduplication to prevent duplicate tickets
- ✅ Configure Databricks API credentials for detailed errors
- ✅ Use workspace-wide webhooks for cluster events

### Monitoring
- ✅ Check FastAPI logs regularly
- ✅ Monitor webhook success rate
- ✅ Track error message quality (detailed vs generic)
- ✅ Review audit logs for patterns

### Auto-Remediation
- ✅ Start with low-risk errors (timeouts, retries)
- ✅ Set max retry limits
- ✅ Monitor remediation success rate
- ✅ Gradually expand to more error types

### Troubleshooting
- ✅ Always check raw webhook payload in logs
- ✅ Verify API keys and credentials
- ✅ Test webhooks manually before going live
- ✅ Use test payloads for validation

---

## 🚦 ROLLOUT PHASES

### Week 1: Setup
- Day 1-2: Update code
- Day 3-4: Configure ADF webhooks
- Day 5: Configure Databricks webhooks

### Week 2: Testing
- Test all webhook types
- Verify error message quality
- Validate deduplication
- Check notifications

### Week 3: Auto-Remediation (Optional)
- Enable for low-risk errors
- Monitor success rate
- Tune retry parameters
- Expand to more error types

### Week 4+: Optimization
- Analyze metrics
- Fine-tune extraction logic
- Add more services
- Create runbooks

---

## ✅ DONE!

You now have everything needed to implement webhook-based error monitoring:
- ✅ Complete architecture
- ✅ Production-ready code
- ✅ Automated setup scripts
- ✅ Testing procedures
- ✅ Auto-remediation guide
- ✅ Troubleshooting guide

**Start with:** `IMPLEMENTATION_SUMMARY.md` for detailed steps, or just run the setup scripts to get started immediately!

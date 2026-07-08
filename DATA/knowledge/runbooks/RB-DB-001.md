---
document_id: RB-DB-001
document_type: runbook
title: Database Connection Pool Exhaustion
service_scope:
  - checkout-service
  - payment-service
fault_category: database_connection_pool
version: "1.0"
approved: true
---

# Symptoms

Connection wait latency, pending requests, request latency, and timeout errors may rise when a connection pool is saturated.

# Diagnostic Signals

Check active, idle, and pending connection counts. Compare connection acquisition latency with the healthy baseline. Review recent deployment and configuration events.

# Investigation Steps

1. Check connection utilization around symptom onset.
2. Compare pool settings with the last validated deployment.
3. Search for connection acquisition timeout logs.
4. Inspect request traces for database acquisition delay.
5. Check whether application instances recover after configuration rollback.

# Possible Causes

Possible causes include invalid pool limits, connection leaks, database slowdown, or workload growth. Do not select a cause without incident evidence.

# Containment Options

Consider rollback to validated configuration after human review. Reduce traffic only when operational policy allows it.

# Remediation Options

Restore validated pool settings or fix connection lifecycle defects after confirmation.

# Verification Steps

Verify connection wait latency, request p95 latency, pending connections, and HTTP 5xx rate.

# Escalation Conditions

Escalate when database health is degraded independently of the application pool or when evidence remains contradictory.

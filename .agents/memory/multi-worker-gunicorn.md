---
name: Multi-worker Gunicorn pitfalls
description: Concurrency constraints for this app's Gunicorn multi-worker deployment (workers = cpu_count*2+1)
---

# Multi-worker Gunicorn pitfalls

This Flask app runs under Gunicorn with multiple sync workers (cpu_count*2+1).
Two concurrency consequences that have bitten us:

## 1. Auto-migrations race across workers
The startup auto-migration suite (ALTER TABLE ... ADD COLUMN) runs in EVERY worker
on boot. The first worker wins; the rest log a benign
`psycopg2.errors.DuplicateColumn ... already exists` which is caught and ignored.
**This log noise on first boot after adding a migration is expected, not a bug.**
Subsequent restarts are quiet because the column-existence check skips it.

## 2. Per-row counters must be updated atomically at the DB level
**Why:** A read-modify-write in Python (`obj.counter = (obj.counter or 0) + 1; commit()`)
suffers lost updates when multiple workers process concurrent requests — e.g. a
brute-force login counter would undercount and the lockout could be bypassed.
**How to apply:** Use a single atomic SQL statement instead:
`UPDATE users SET failed_login_attempts = failed_login_attempts + 1 WHERE id=:id RETURNING failed_login_attempts`
then branch on the returned value. Same pattern for any rate-limit/quota counter.

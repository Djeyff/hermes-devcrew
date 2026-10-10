# Regression fixture — env-replace-all (check_library id: env-replace-all)

**Incident.** RET-241 worker branch `srlanes-5fix` (Djeyff/retena-ops) set variables
via `executeDatabaseCommand` with the deprecated PUT-style 'replace all' verb while
simultaneously executing a destructive SQL `DELETE`. The API silently replaced the
service's entire variables map, wiping ~11 pre-existing env vars (UI endpoints,
Redis, Twilio, dashboard tokens) and the Zeabur 'updatedBy' fields needed to restore
them — the dashboard was left unable to manage the service at all.

**Rule the check enforces.** When a worker task branch both (a) sets service
variables through an orchestration API and (b) executes destructive SQL
(DELETE/DROP/TRUNCATE/ALTER ... DROP), the release-harness must BLOCK the merge
until the run log shows a pre-call snapshot of the affected service's full
variables map and the exact variable keys + values it intended to write.

**Reproducing input** (task-branch audit log with one env-replace-all event):

```json
{
  "branch": "srlanes-5fix",
  "events": [
    {"kind": "variables.write", "service": "retena-ops",
     "mode": "replace-all", "keys": ["SRLANES_URL"]},
    {"kind": "db.command", "service": "retena-ops",
     "sql": "DELETE FROM assignments WHERE lane = 'x'"}
  ]
}
```

With `pr_hygiene_gate.verify_env_replace_all`, this log must produce an
`env-replace-all` BLOCK finding (no pre-write snapshot event exists for
`retena-ops`), and the CLI must exit VIOLATIONS (1). Covered by
`test_pr_hygiene_gate.py::test_env_replace_all_without_snapshot_blocks`.

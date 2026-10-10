# Regression fixture — duplicate-release-lane (check_library id: duplicate-release-lane)

**Incident.** Two live cards targeted the same release-lane mutation (PR #357
integration on Djeyff/vozclara-api): t_a97c1916 claimed 1791658306, then t_3b42f921
was dispatched 53s later (claimed 1791658426). Both agents were alive and
heartbeating; without a guard the later run would have raced the merge / deploy-ref
advance / service pin. Same class as the earlier t_ad81e625 double-merge incident:
dispatch dedup missed a near-simultaneous create for the same PR lane.

**Rule the check enforces.** Before any release-lane mutation (PR merge, deploy-ref
advance, service image tag/pin), scan the board for a live sibling card whose
title/body targets the same PR number or release branch, and compare claim age +
worker pid liveness. The earlier live claim owns the lane; later dispatches must
stand down (no mutations) and complete with a stand-down note.

**Reproducing input** (board rows; `now - created_at` in seconds, both runs `running`,
both pids alive):

```json
[{"id": "t_first",  "title": "integrate PR #357 (squash + pin)", "status": "running",
  "claimed_at": 1791658306, "pid": 913361, "pid_alive": true},
 {"id": "t_second", "title": "integrate PR #357 (merge + pin + canary)", "status": "running",
  "claimed_at": 1791658426, "pid": 915441, "pid_alive": true}]
```

With `verify_duplicate_lanes(board, mutating_task="t_second")` the verifier must emit
a `duplicate-release-lane` finding (earlier live claim `t_first` owns the lane) and
exit VIOLATIONS. If the earlier claim's pid is dead AND its last heartbeat exceeds
the reclaim window, the finding downgrades to a warning (stale claim, lane may be
taken over).

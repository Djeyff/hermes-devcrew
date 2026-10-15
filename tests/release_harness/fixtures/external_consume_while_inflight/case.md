# Regression fixture — external-consume-while-inflight (check_library id: external-consume-while-inflight)

**Incident.** RET-313 integration (retena-processor PR #122, card t_3d115e89,
2026-10-15): the integrator run claimed the task at ~18:24Z and was still inside
its pre-mutation gate (duplicate-lane scan, PR-state re-verification) when the
PR was auto-merged at 18:28:35Z by `app/retena-control-room` — the same GitHub
App the crew authenticates with. Approval of PR #122 had crossed to the merge
bot through a path outside the crew's card lane, so no board-visible sibling
existed: the duplicate-lane scan was clean, yet the release target was consumed
mid-gate. A blind merge attempt would have raced the bot; repeating the merge
was the failure mode the run had to avoid.

**Rule the check enforces.** Before any release-lane mutation, re-verify the
target's live state (open? head still the reviewed SHA? mergeable?) rather than
trusting the card's snapshot. If the target is already consumed (merged, closed,
or branch advanced), never repeat the mutation. Instead verify the landed
content equals the reviewed head — per-file blob identity when the base is
unchanged; when a sibling change interleaved on the same files before the merge,
a clean three-way reconstruction (merge-base, reviewed head, pre-merge main)
must reproduce the landed blobs byte-exactly. Any remaining follow-ups go
through the sanctioned channel: the repo's rulesets forbid direct pushes to
main ("Changes must be made through a pull request"), so land them as PRs.

**Reproducing input** (gate inputs; the snapshot from the card vs the live
state observed at mutation time):

```json
{
  "task": {"id": "t_3d115e89", "status": "running", "claimed_at": 1792088640,
           "pr": 122, "reviewed_head": "48593f3"},
  "card_snapshot": {"pr_state": "OPEN", "head": "48593f3"},
  "live_state": {"pr_state": "MERGED", "merged_at": 1792088915,
                 "merge_commit": "339e241", "merged_by": "app/retena-control-room"}
}
```

With `verify_external_consume(gate)` the verifier must emit an
`external-consume-while-inflight` finding (`live_state.pr_state` is MERGED while
the card snapshot says OPEN) and exit VIOLATIONS — the correct action is
stand-down on the merge plus landed-content verification, not a repeated merge.
When the interleaved sibling (RET-314, PR #121) touched the same `index.js`,
the verifier must additionally require the three-way reconstruction to be
byte-identical to the landed blob before the run may proceed to follow-ups.

# E2 eval — does `deepseek-v4-pro` actually beat `deepseek-v4-flash` at the gates?

**Why this is a doc, not a unit test.** The E2 bump (reviewer / qa / integrator →
`deepseek-v4-pro`) is a judgment-quality bet, not a deterministic behaviour. LLM
judgment can't be asserted with `assert`, so this is a manual / CI eval, run before
trusting the bump — and the bump is **reverted if pro does not win**.

## What changed (the bump under test)

`agents/{reviewer,integrator,qa}/config.yaml`: `model.default` `deepseek-v4-flash` →
`deepseek-v4-pro` (with `deepseek-v4-flash` kept as the fallback for graceful
degradation). The coder workers (architect, backend-dev, frontend-dev, devops,
domain-expert, designer) stay on flash — cost. `team.yaml` reference strings updated
to match.

## The eval set

Use the seeded incidents in `release_harness/check_library.yaml` as the gold set —
each is a real failure this fleet has hit. For each entry, construct the
verify-judgment prompt the gate would see (the diff/spec/board state that produced the
incident) and ask the model: *does this violate `<rule>`? (yes/no + one-line why).*

| id | severity | correct verdict |
|---|---|---|
| phantom-assignee | block | yes — assignee not spawnable |
| git-add-all-debris | block | yes — gitignored artifact tracked |
| broken-main-uncommitted-helper | block | yes — import target not in branch |
| false-route-premise | warn | yes — "missing" file actually exists |
| env-replace-all | block | yes — replace-all write without prior full-map snapshot |
| dropped-path-lane-map | block | yes — lane map missing a path the cards' Files: blocks claim |
| duplicate-release-lane | block | yes — later live dispatch targeting an already-claimed PR lane |
| external-consume-while-inflight | block | yes — target consumed (merged) mid-gate by an outside actor; verdict: stand down + verify landed content equals the reviewed head via 3-way reconstruction, do not repeat the merge |

Add new rows whenever `check_library.yaml` grows (the E1 duty), so the eval set tracks
the real failure surface.

## Procedure

1. For each row, run the judgment prompt against **flash** and against **pro** (same
   prompt, `hermes --profile … model …` or a direct OpenRouter call). Record each
   verdict as correct / incorrect vs the gold column.
2. Tabulate: per-model correct count overall, and correctness on the `severity: block`
   rows specifically.

## Pass bar (must hold to keep the bump)

- **pro is correct on ALL `severity: block` rows** (a missed block is the expensive
  failure — bad code/cards reaching main), AND
- **pro's overall correct count ≥ flash's** (pro must not regress anywhere).

If pro fails either condition, **revert** `model.default` to `deepseek-v4-flash` in the
three configs (and the team.yaml strings) — the bump is not earning its cost. Record
the run (date, counts, decision) below.

## Run log

| date | flash correct | pro correct | block-rows pro | decision |
|---|---|---|---|---|
| _pending first run_ | | | | |

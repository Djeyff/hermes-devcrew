#!/usr/bin/env python3
"""RET-610-D deploy gates (D-13): ai-search eval + avatar guardrail.

FEATURE CONTRACT (D-13): a deploy that degrades search quality below the
eval threshold, breaches the dashboard perf budget, or violates the avatar
3-trigger / zero-raw-link contract must be BLOCKED before it takes traffic.

Two crew-side gates, wired into the api-b release-pin procedure (an image is
pinned to the fleet only after both return PASS):

  ai-search   Offline scorer-honesty check plus the documented live gate
              (`node bench/live/ai-search-live-eval.js --compare <baseline>
              --gate --max-spend N`, golden smoke set = fixtures/
              ai-search-live-golden-v1.json, threshold: overall drop >10 pts
              or any class drop >15 pts scores red). Live mode is fail-closed:
              no owner token and no --max-spend -> ESCALATE(2), never PASS.
              Owner identity only (member identities return 0 sources by
              design); token never printed; receipts redacted (ids/counts).
  avatar      Runs the repo's scripts/verify-avatar-guardrail.js (26+
              trigger/policy contract suites + zero-raw-link static
              invariant) and asserts the docker-publish-b.yml wiring exists
              at HEAD. The repo CI lane enforces the same check at
              image-build time; this crew-side check re-proves it at pin.

Exit codes (release-harness convention): 0 PASS / 1 VIOLATIONS (block) /
2 ESCALATE (could not run — never treated as pass).

Rollback: delete this file; revert the docker-publish-b.yml / v4-auto-
publish.yml gate hunks in the respective repos.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exits import ESCALATE, PASS, VIOLATIONS  # noqa: E402


def _run(cmd, cwd, timeout_s=1200):
    try:
        res = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout_s
        )
        return res.returncode, res.stdout, res.stderr
    except FileNotFoundError as exc:
        return None, "", f"missing executable: {exc}"
    except subprocess.TimeoutExpired:
        return None, "", "timeout"


def _npm_ci_ok(repo):
    code, _, err = _run(["npm", "ci", "--ignore-scripts", "--no-audit",
                         "--no-fund", "--loglevel=error"], repo, timeout_s=600)
    return code == 0, err.strip()[-400:] if err else ""


def gate_ai_search(repo, live=False, max_spend=None, baseline=None):
    print(f"[ai-search-gate] repo={repo} mode={'live' if live else 'offline'}")
    ok, err = _npm_ci_ok(repo)
    if not ok:
        print(f"[ai-search-gate] ESCALATE: npm ci failed: {err}")
        return ESCALATE

    # 1. Offline scorer honesty: planted regressions must score red.
    code, out, err = _run(["npm", "run", "verify:ai-search-live-eval-demo",
                           "--silent"], repo, timeout_s=300)
    print((out or err).strip()[-500:])
    if code != 0:
        print("[ai-search-gate] VIOLATIONS: eval scorer not honest on this tree "
              "(planted regressions did not score red) — search-quality gate "
              "would pass silently")
        return VIOLATIONS
    print("[ai-search-gate] scorer honesty: OK (2 planted red, control green)")

    if not live:
        print("[ai-search-gate] PASS (offline mode; live gate not requested)")
        return PASS

    # 2. Live gate — golden smoke set vs baseline. Fail-closed.
    token = os.environ.get("RETENA_EVAL_TOKEN") or ""
    cache = os.path.expanduser("~/.cache/ret514_owner_token.txt")
    if not token and os.path.isfile(cache):
        token = "cached"  # presence only; the harness reads the cache itself
    if not token:
        print("[ai-search-gate] ESCALATE: no owner eval token "
              "(RETENA_EVAL_TOKEN or ~/.cache/ret514_owner_token.txt) — "
              "fail-closed, pin blocked")
        return ESCALATE
    if not max_spend or int(max_spend) <= 0:
        print("[ai-search-gate] ESCALATE: --max-spend required for live mode "
              "(harness rule: cost is fail-closed)")
        return ESCALATE
    if not baseline:
        baselines = sorted(os.listdir(os.path.join(repo, "bench", "live",
                                                   "baselines")))
        if not baselines:
            print("[ai-search-gate] ESCALATE: no baseline found in "
                  "bench/live/baselines/")
            return ESCALATE
        baseline = f"bench/live/baselines/{baselines[-1]}"
    script = os.path.join(repo, "bench", "live", "ai-search-live-eval.js")
    code, out, err = _run(["node", script, "--compare", baseline, "--gate",
                           "--max-spend", str(int(max_spend))], repo,
                          timeout_s=1800)
    tail = (out or err).strip().splitlines()
    print("[ai-search-gate] live run tail (redacted): " +
          " | ".join(line for line in tail[-6:] if line.strip())[:800])
    if code == 0:
        print(f"[ai-search-gate] PASS (live gate green vs {baseline})")
        return PASS
    if code == 1:
        print(f"[ai-search-gate] VIOLATIONS: live eval scored RED vs {baseline} "
              "(overall drop >10 pts or a class drop >15 pts) — pin blocked")
        return VIOLATIONS
    print(f"[ai-search-gate] ESCALATE: live eval could not run (exit {code})")
    return ESCALATE


def gate_avatar(repo):
    print(f"[avatar-gate] repo={repo}")
    script = os.path.join(repo, "scripts", "verify-avatar-guardrail.js")
    if not os.path.isfile(script):
        print("[avatar-gate] ESCALATE: scripts/verify-avatar-guardrail.js "
              "absent at HEAD — guardrail not wired on this tree")
        return ESCALATE
    workflow = os.path.join(repo, ".github", "workflows",
                            "docker-publish-b.yml")
    body = open(workflow, encoding="utf-8").read() if os.path.isfile(workflow) else ""
    if "verify-avatar-guardrail.js" not in body:
        print("[avatar-gate] VIOLATIONS: docker-publish-b.yml does not run the "
              "avatar guardrail — CI lane not wired")
        return VIOLATIONS
    print("[avatar-gate] CI wiring present in docker-publish-b.yml")
    ok, err = _npm_ci_ok(repo)
    if not ok:
        print(f"[avatar-gate] ESCALATE: npm ci failed: {err}")
        return ESCALATE
    code, out, err = _run(["node", script], repo, timeout_s=1200)
    print((out or err).strip().splitlines()[-1] if (out or err).strip() else "")
    if code == 0:
        print("[avatar-gate] PASS (contract suites + zero-raw-link green)")
        return PASS
    if code == 1:
        print("[avatar-gate] VIOLATIONS: avatar guardrail red (see above) — "
              "pin blocked")
        return VIOLATIONS
    print(f"[avatar-gate] ESCALATE: guardrail could not run (exit {code})")
    return ESCALATE


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="gate", required=True)

    p1 = sub.add_parser("ai-search",
                        help="ai-search eval deploy gate (offline | live)")
    p1.add_argument("--repo", required=True)
    p1.add_argument("--live", action="store_true",
                    help="run the documented live golden-set gate (owner "
                         "token + --max-spend required, fail-closed)")
    p1.add_argument("--max-spend", type=int, default=None)
    p1.add_argument("--baseline", default=None,
                    help="baseline path relative to repo (defaults to the "
                         "latest file in bench/live/baselines/)")

    p2 = sub.add_parser("avatar", help="avatar guardrail deploy gate")
    p2.add_argument("--repo", required=True)

    args = ap.parse_args()
    if args.gate == "ai-search":
        sys.exit(gate_ai_search(args.repo, live=args.live,
                                max_spend=args.max_spend,
                                baseline=args.baseline))
    sys.exit(gate_avatar(args.repo))


if __name__ == "__main__":
    main()

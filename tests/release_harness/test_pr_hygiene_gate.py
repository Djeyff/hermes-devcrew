import subprocess
from release_harness.pr_hygiene_gate import check_branch
from release_harness import exits

def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True)

def test_clean_branch_passes(tmp_git_repo):
    rep = check_branch(tmp_git_repo, base="main", evidence=["src.py"])
    assert rep.exit_code == exits.PASS

def test_tracked_debris_fails(tmp_git_repo):
    (tmp_git_repo / "build.log").write_text("noise")
    _git(tmp_git_repo, "add", "-f", "build.log")  # force-track a gitignored debris file
    _git(tmp_git_repo, "commit", "-q", "-m", "oops debris")
    rep = check_branch(tmp_git_repo, base="main", evidence=["src.py"])
    assert rep.exit_code == exits.VIOLATIONS
    assert any("build.log" in f.detail for f in rep.findings)

def test_missing_evidence_fails(tmp_git_repo):
    rep = check_branch(tmp_git_repo, base="main", evidence=["nonexistent.log"])
    assert rep.exit_code == exits.VIOLATIONS

def test_non_git_dir_escalates(tmp_path):
    # a gate that cannot inspect the repo must ESCALATE (2), never false-clean PASS
    rep = check_branch(tmp_path, base="main", evidence=[])
    assert rep.exit_code == exits.ESCALATE
    assert any(f.kind == "not-a-work-tree" for f in rep.findings)

def test_unresolvable_base_escalates(tmp_git_repo):
    # origin/main on a repo with no remote fetched: freshness is unverifiable, so
    # escalate rather than silently passing (the verify_code_landed lesson).
    rep = check_branch(tmp_git_repo, base="origin/main", evidence=["src.py"])
    assert rep.exit_code == exits.ESCALATE
    assert any(f.kind == "base-unresolvable" for f in rep.findings)


# --- env-replace-all (RET-241) — regression tests for the check-library entry --

from release_harness.pr_hygiene_gate import verify_env_replace_all  # noqa: E402

RET241_LOG = [
    {"kind": "db.command", "service": "retena-ops",
     "sql": "DELETE FROM assignments WHERE lane = 'x'"},
    {"kind": "variables.write", "service": "retena-ops",
     "mode": "replace-all", "keys": ["SRLANES_URL"]},
]

def test_env_replace_all_without_snapshot_blocks():
    rep = verify_env_replace_all(RET241_LOG)
    assert rep.exit_code == exits.VIOLATIONS
    assert any(f.kind == "env-replace-all" for f in rep.findings)

def test_env_replace_all_with_prior_snapshot_passes():
    events = [
        {"kind": "variables.snapshot", "service": "retena-ops"},
        *RET241_LOG,
    ]
    rep = verify_env_replace_all(events)
    assert rep.exit_code == exits.PASS
    assert rep.findings == []

def test_snapshot_of_other_service_does_not_clear():
    # the snapshot must match the SAME service as the replace-all write
    events = [
        {"kind": "variables.snapshot", "service": "other-svc"},
        *RET241_LOG,
    ]
    rep = verify_env_replace_all(events)
    assert rep.exit_code == exits.VIOLATIONS
    assert any(f.kind == "env-replace-all" for f in rep.findings)

def test_merge_mode_write_passes_without_snapshot():
    events = [
        {"kind": "variables.write", "service": "retena-ops",
         "mode": "merge", "keys": ["SRLANES_URL"]},
    ]
    rep = verify_env_replace_all(events)
    assert rep.exit_code == exits.PASS

def test_unknown_write_mode_escalates():
    # a log we cannot interpret must ESCALATE — never a false-clean PASS
    events = [{"kind": "variables.write", "service": "retena-ops", "mode": "sync"}]
    rep = verify_env_replace_all(events)
    assert rep.exit_code == exits.ESCALATE
    assert any(f.kind == "env-replace-all-audit-unreadable" for f in rep.findings)

def test_env_replace_all_wired_into_check_branch(tmp_git_repo):
    # the rule is live in the release gate, not just an importable function:
    # a repo whose audit.json reproduces the RET-241 shape must fail the gate.
    (tmp_git_repo / "audit.json").write_text(
        '{"branch": "srlanes-5fix", "events": ['
        '{"kind": "db.command", "service": "retena-ops", '
        '"sql": "DELETE FROM assignments WHERE lane = \'x\'"}, '
        '{"kind": "variables.write", "service": "retena-ops", '
        '"mode": "replace-all", "keys": ["SRLANES_URL"]}]}',
        encoding="utf-8")
    rep = check_branch(tmp_git_repo, base="main", evidence=["src.py"])
    assert rep.exit_code == exits.VIOLATIONS
    assert any(f.kind == "env-replace-all" for f in rep.findings)

def test_env_replace_all_fixture_log_matches_gate():
    # the yaml entry's fixture must describe the exact log shape the gate blocks
    import json as _json
    import re as _re
    from pathlib import Path as _Path
    root = _Path(__file__).resolve().parents[2]
    case = (root / "tests/release_harness/fixtures/env_replace_all/case.md").read_text(encoding="utf-8")
    block = _re.search(r"```json\n(.*?)```", case, _re.DOTALL)
    assert block, "fixture case.md must carry a reproducing json log"
    events = _json.loads(block.group(1))["events"]
    rep = verify_env_replace_all(events)
    assert rep.exit_code == exits.VIOLATIONS
    assert any(f.kind == "env-replace-all" for f in rep.findings)


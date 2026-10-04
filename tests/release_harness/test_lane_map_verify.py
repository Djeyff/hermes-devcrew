# tests/release_harness/test_lane_map_verify.py
"""RET-246 (t_a7b64fdd): the release-manager hand-transcribed two card Files:
blocks into lanes.json and dropped one of two paths on a single bullet, so a
file shipped with no lane's authority. The gate mechanically compares the
lane-map against the cards' parsed Files: blocks AND the working-tree change
set — a dropped, added, double-claimed, or unchanged mapping can never pass."""
import json

from release_harness.lane_map_verify import verify_lane_map, exits

CARD_B_BODY = """\
**Files (modify only these):**
- `date-divider.tsx` and `sticky-date-divider.tsx`
"""


def _setup_two_changed_files(repo):
    """Both card files changed in the work tree (the real RET-246 situation:
    the worker modified both; the hand-built map dropped one), and src.py —
    the fixture's own tracked file — left untouched."""
    (repo / "sticky-date-divider.tsx").write_text("old\n")
    def g(*args):
        import subprocess
        subprocess.run(["git", "-C", str(repo), *args], check=True,
                       capture_output=True, text=True)
    g("add", ".")
    g("commit", "-q", "-m", "add sticky")
    (repo / "date-divider.tsx").write_text("x = 1\n")        # new, untracked
    (repo / "sticky-date-divider.tsx").write_text("new\n")   # modified


def test_dropped_card_path_is_violation(tmp_git_repo):
    # THE incident: card lists two paths on one bullet; the map carries only one.
    _setup_two_changed_files(tmp_git_repo)
    report = verify_lane_map(
        tmp_git_repo,
        {"t-b": ["date-divider.tsx"]},                       # sticky dropped
        {"t-b": CARD_B_BODY},
    )
    assert report.exit_code == exits.VIOLATIONS
    kinds = {f.kind for f in report.findings}
    assert "card-path-missing-from-map" in kinds
    drop = [f for f in report.findings if f.kind == "card-path-missing-from-map"][0]
    assert "sticky-date-divider.tsx" in drop.detail


def test_map_matching_cards_and_worktree_is_exit_0(tmp_git_repo):
    _setup_two_changed_files(tmp_git_repo)
    report = verify_lane_map(
        tmp_git_repo,
        {"t-b": ["date-divider.tsx", "sticky-date-divider.tsx"]},
        {"t-b": CARD_B_BODY},
    )
    assert report.exit_code == exits.PASS
    assert report.findings == []


def test_lane_without_files_block_escalates(tmp_git_repo):
    _setup_two_changed_files(tmp_git_repo)
    report = verify_lane_map(
        tmp_git_repo,
        {"t-b": ["date-divider.tsx", "sticky-date-divider.tsx"]},
        {"t-b": "no files block here"},   # attribution impossible → human decides
    )
    assert report.exit_code == exits.ESCALATE
    assert any(f.kind == "lane-without-files-block" for f in report.findings)


def test_path_claimed_by_multiple_lanes_is_violation(tmp_git_repo):
    _setup_two_changed_files(tmp_git_repo)
    body = "**Files (modify only these):**\n- `date-divider.tsx` and `sticky-date-divider.tsx`\n"
    report = verify_lane_map(
        tmp_git_repo,
        {"t-b": ["date-divider.tsx"], "t-c": ["date-divider.tsx"]},
        {"t-b": body, "t-c": body},
    )
    assert report.exit_code == exits.VIOLATIONS
    assert any(f.kind == "path-claimed-by-multiple-lanes" for f in report.findings)


def test_unclaimed_changed_file_is_violation(tmp_git_repo):
    # clean_integrate would escalate on this later; the gate catches it BEFORE
    # reconstruction, from the same evidence (the working tree).
    _setup_two_changed_files(tmp_git_repo)
    (tmp_git_repo / "stray.py").write_text("x = 1\n")   # changed, claimed by no lane
    report = verify_lane_map(
        tmp_git_repo,
        {"t-b": ["date-divider.tsx", "sticky-date-divider.tsx"]},
        {"t-b": CARD_B_BODY},
    )
    assert report.exit_code == exits.VIOLATIONS
    assert any(f.kind == "unclaimed-changed-file" for f in report.findings)


def test_mapped_path_not_on_card_is_violation(tmp_git_repo):
    _setup_two_changed_files(tmp_git_repo)
    report = verify_lane_map(
        tmp_git_repo,
        {"t-b": ["date-divider.tsx", "sticky-date-divider.tsx", "helper.py"]},
        {"t-b": CARD_B_BODY},
    )
    assert report.exit_code == exits.VIOLATIONS
    assert any(f.kind == "map-path-not-on-card" for f in report.findings)


def test_mapped_file_not_changed_is_violation(tmp_git_repo):
    # date-divider.tsx is mapped and on the card but NOT modified in the tree.
    _setup_two_changed_files(tmp_git_repo)
    def g(*args):
        import subprocess
        subprocess.run(["git", "-C", str(tmp_git_repo), *args], check=True,
                       capture_output=True, text=True)
    g("add", ".")
    g("commit", "-q", "-m", "sync")
    (tmp_git_repo / "sticky-date-divider.tsx").write_text("newer\n")
    report = verify_lane_map(
        tmp_git_repo,
        {"t-b": ["date-divider.tsx", "sticky-date-divider.tsx"]},
        {"t-b": CARD_B_BODY},
    )
    assert report.exit_code == exits.VIOLATIONS
    assert any(f.kind == "mapped-file-not-changed" for f in report.findings)


def test_missing_bodies_file_is_exit_2(tmp_path):
    # can't-run → ESCALATE, never a false-clean PASS (verify_code_landed lesson)
    from pathlib import Path
    report = verify_lane_map(
        tmp_path, {"t-b": ["a.ts"]}, None,
        bodies_path=Path(tmp_path / "nope.json"),
    )
    assert report.exit_code == exits.ESCALATE


def test_cli_pass_and_violation(tmp_git_repo):
    import subprocess, sys
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    _setup_two_changed_files(tmp_git_repo)
    bodies = tmp_git_repo.parent / "bodies.json"
    bodies.write_text(json.dumps({"t-b": CARD_B_BODY}))
    lanes = tmp_git_repo.parent / "lanes.json"
    def run(lane_obj):
        lanes.write_text(json.dumps(lane_obj))
        return subprocess.run(
            [sys.executable, "-m", "release_harness.lane_map_verify",
             "--repo", str(tmp_git_repo), "--lane-map", str(lanes),
             "--bodies", str(bodies)],
            cwd=repo_root, capture_output=True, text=True)
    good = run({"t-b": ["date-divider.tsx", "sticky-date-divider.tsx"]})
    assert good.returncode == 0
    bad = run({"t-b": ["date-divider.tsx"]})   # the RET-246 drop
    assert bad.returncode == 1
    findings = json.loads(bad.stdout)
    assert any(f["kind"] == "card-path-missing-from-map" for f in findings)
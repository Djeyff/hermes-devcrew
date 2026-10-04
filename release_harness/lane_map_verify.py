"""lane-map-verify — prove the release-manager's lane map is the cards' own
attribution, before clean_integrate touches git. Mechanical, deterministic.

RET-246 (t_a7b64fdd): the lane map was hand-transcribed from the card bodies and
one of two paths on a single `Files:` bullet was dropped — a file shipped with no
lane's authority. This gate mechanically compares, per lane, the map against the
card's OWN parsed `Files:` block (release_harness.cardfiles) and against the
working-tree change set:
  - a card path missing from the map            → VIOLATIONS (the RET-246 drop)
  - a mapped path not on the card               → VIOLATIONS (invented authority)
  - one path mapped by multiple lanes           → VIOLATIONS
  - a mapped file with no working-tree change   → VIOLATIONS (stale mapping)
  - a changed file claimed by no lane           → VIOLATIONS (same evidence
    clean_integrate escalates on — caught here BEFORE reconstruction)
  - a lane whose body has no parseable Files: block, or an unreadable input
    (not a work-tree, missing bodies file)      → ESCALATE — never a false PASS.
Never writes; only inspects."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from dataclasses import dataclass

from release_harness import exits
from release_harness.cardfiles import parse_files_block
from release_harness.clean_integrate import _changed_files


@dataclass
class Finding:
    kind: str
    detail: str


class Report:
    def __init__(self):
        self.findings: list[Finding] = []
        self.ok = True  # False → could-not-run → ESCALATE, never a false-clean PASS

    def add(self, kind: str, detail: str):
        self.findings.append(Finding(kind, detail))

    @property
    def exit_code(self) -> int:
        if not self.ok:
            return exits.ESCALATE
        return exits.VIOLATIONS if self.findings else exits.PASS


def _load_bodies(bodies, bodies_path):
    """Bodies come either inline ({card_id: body}) or from a JSON file."""
    if bodies is not None:
        return bodies, None
    if bodies_path is None:
        return {}, None
    try:
        return json.loads(Path(bodies_path).read_text(encoding="utf-8")), None
    except Exception as e:
        return None, f"bodies file unreadable: {e}"


def verify_lane_map(repo, lane_map, bodies=None, bodies_path=None) -> Report:
    rep = Report()

    # 0) the gate must be able to run: a real work-tree and a usable map+bodies.
    wt = subprocess.run(["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
                        capture_output=True, text=True)
    if wt.returncode != 0 or wt.stdout.strip() != "true":
        rep.ok = False
        rep.add("not-a-work-tree", f"{repo} is not a git work-tree — cannot inspect; escalate")
        return rep
    bodies, err = _load_bodies(bodies, bodies_path)
    if bodies is None:
        rep.ok = False
        rep.add("bodies-unreadable", err or "bodies unavailable — cannot verify attribution")
        return rep
    if not isinstance(lane_map, dict) or not lane_map:
        rep.ok = False
        rep.add("lane-map-empty", "lane map missing or empty — nothing to verify; escalate")
        return rep

    # 1) every lane must carry its card's own Files: block — no body, no authority.
    card_paths: dict[str, list] = {}
    for card_id in lane_map:
        body = bodies.get(card_id)
        files = parse_files_block(body) if isinstance(body, str) else None
        if files is None:
            rep.ok = False
            rep.add("lane-without-files-block",
                    f"card {card_id}: no parseable Files: block — attribution impossible; "
                    "re-read the card, do not guess")
            continue
        card_paths[card_id] = files
    if not rep.ok:
        return rep

    # 2) one path claimed by two lanes = ambiguous authority.
    seen: dict[str, str] = {}
    for card_id, paths in card_paths.items():
        for p in paths:
            if p in seen and seen[p] != card_id:
                rep.add("path-claimed-by-multiple-lanes",
                        f"'{p}' appears in the Files: block of both {seen[p]} and {card_id} "
                        "— authority is ambiguous; fix the cards")
            else:
                seen[p] = card_id

    # 3) per-lane: map must EQUAL the card's paths (no drops, no inventions).
    for card_id, mapped in lane_map.items():
        mapped_set, card_set = set(mapped), set(card_paths[card_id])
        for p in sorted(card_set - mapped_set):
            rep.add("card-path-missing-from-map",
                    f"card {card_id} claims '{p}' but the lane map omits it "
                    "(RET-246: the dropped-path failure mode)")
        for p in sorted(mapped_set - card_set):
            rep.add("map-path-not-on-card",
                    f"lane map assigns '{p}' to {card_id}, but its Files: block does not list it")

    # 4) map vs the working tree: every mapped file must actually be changed;
    #    every changed file must be mapped (clean_integrate's orphan check, earlier).
    mapped_all = {p for paths in lane_map.values() for p in paths}
    changed = set(_changed_files(Path(repo)))
    for p in sorted(mapped_all - changed):
        rep.add("mapped-file-not-changed",
                f"'{p}' is mapped to a lane but has no change in the working tree "
                "— stale or speculative mapping")
    for p in sorted(changed - mapped_all):
        rep.add("unclaimed-changed-file",
                f"changed file '{p}' is claimed by no lane — escalate/attribute it, never guess")

    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--lane-map", required=True)  # JSON file: {"card_id": ["path", ...]}
    ap.add_argument("--bodies", required=False)   # JSON file: {"card_id": "<card body>"}
    a = ap.parse_args()
    try:
        lane_map = json.loads(Path(a.lane_map).read_text(encoding="utf-8"))
        bodies = json.loads(Path(a.bodies).read_text(encoding="utf-8")) if a.bodies else {}
        rep = verify_lane_map(Path(a.repo), lane_map, bodies=bodies)
    except Exception as e:  # can't-run (missing/invalid JSON, git error) → escalate
        print(f"lane_map_verify could not run: {e}", file=sys.stderr)
        sys.exit(exits.ESCALATE)
    print(json.dumps([f.__dict__ for f in rep.findings], indent=2))
    sys.exit(rep.exit_code)

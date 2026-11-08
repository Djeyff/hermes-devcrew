"""asr-route-gate — RET-610-A. Mechanical, deterministic.

Runs the target repo's ASR regression pack in offline mode
(scripts/asr-regression-pack.js --offline; stdlib-only, no npm ci) and
translates its exit contract into harness findings. The pack probes the D-13
feature contract (a voice note on any supported route returns a transcript
from its routed engine; a dry-quota engine falls over to the next engine; an
all-dry ladder fails CLOSED — the note is never silently dropped):
engine-route probes (whisper/soniox/deepgram), measured-ladder retention,
dry-quota classification + fall-over + fail-closed shape, route-loop
continuation and latency plumbing, fixture presence.

Exit mapping (a tool that cannot run must never read as PASS):
  pack exit 0 → PASS (no findings)
  pack exit 1 → VIOLATIONS (route regression caught — BLOCKS the release)
  pack exit 2 / missing pack / node failure → ESCALATE

Never pushes; only inspects. Doctrine: D-2026-11-08-14, D-2026-11-08-09.
"""
import argparse
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from release_harness import exits

PACK_REL = Path("scripts") / "asr-regression-pack.js"


@dataclass
class Finding:
    kind: str
    detail: str


@dataclass
class Report:
    findings: list = field(default_factory=list)
    ok: bool = True   # False → could-not-run → ESCALATE, never a false-clean PASS

    @property
    def exit_code(self):
        if not self.ok:
            return exits.ESCALATE
        return exits.VIOLATIONS if self.findings else exits.PASS


def check_asr_routes(repo: Path) -> Report:
    repo = Path(repo)
    rep = Report()
    pack = repo / PACK_REL
    if not pack.is_file():
        rep.ok = False
        rep.findings.append(Finding(
            "asr-pack-missing",
            f"{pack} missing — ASR route gate cannot run; escalate (never a false PASS)",
        ))
        return rep
    try:
        proc = subprocess.run(
            ["node", str(pack), "--offline"],
            cwd=str(repo), capture_output=True, text=True, timeout=120,
        )
    except OSError as exc:
        rep.ok = False
        rep.findings.append(Finding("asr-pack-could-not-run", f"node invocation failed: {exc}"))
        return rep
    except subprocess.TimeoutExpired:
        rep.ok = False
        rep.findings.append(Finding("asr-pack-could-not-run",
            "asr regression pack exceeded 120s — escalate, never a false PASS"))
        return rep

    lines = [ln for ln in (proc.stdout + proc.stderr).strip().splitlines() if ln.strip()]
    rep.pack_summary = lines[-1] if lines else "(no pack output)"
    if proc.returncode == 0:
        return rep  # green — findings stay empty
    if proc.returncode == 1:
        for ln in lines:
            if ln.startswith("FAIL "):
                rep.findings.append(Finding("asr-route-regression", ln))
        if not rep.findings:
            rep.findings.append(Finding("asr-route-regression",
                "pack went RED without FAIL lines — inspect pack output manually"))
        return rep
    rep.ok = False
    rep.findings.append(Finding(
        "asr-pack-could-not-run",
        f"pack exited {proc.returncode} (2 = could-not-run, escalate): "
        + " | ".join(lines[-3:]),
    ))
    return rep


def main():
    ap = argparse.ArgumentParser(
        prog="release_harness.asr_route_gate",
        description="RET-610-A: block releases whose ASR route/fallback contract regressed.",
    )
    ap.add_argument("repo", help="retena-processor work-tree to gate")
    args = ap.parse_args()
    rep = check_asr_routes(Path(args.repo))
    print(json.dumps(
        [{"kind": f.kind, "detail": f.detail} for f in rep.findings], indent=2
    ))
    print(f"ASR_ROUTE_GATE_EXIT={rep.exit_code}")
    return rep.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

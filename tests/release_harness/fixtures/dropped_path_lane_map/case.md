# Regression fixture — dropped-path-lane-map (check_library id: dropped-path-lane-map)

**Incident.** RET-246 (2026-10-04, Retena control-room build). The release-manager
built `lanes.json` for `clean_integrate` BY HAND from the card bodies. Card B's
`Files:` block read `- \`date-divider.tsx\` and \`sticky-date-divider.tsx\`` —
TWO paths on ONE bullet — and the transcription carried only the first, so
`sticky-date-divider.tsx` shipped in the release PR with no lane's authority and
the architect's "modify only these" boundary was silently crossed. A second
contributor: the seeded `parse_files_block` header regex (`^\s*Files:\s*$`) never
matched the cards' real `**Files (modify only these):**` header at all, so any
mechanical re-parse would have looked empty rather than wrong.

**Rule the check enforces.** The lane map must be DERIVED, never transcribed:
`release_harness.lane_map_verify` re-parses each card's `Files:` block and refuses
(exit 1) unless the map equals the cards' own attribution and the working-tree
change set — a card path missing from the map, a path claimed by two lanes, an
invented path, a mapped-but-unchanged file, or an unclaimed changed file can
never pass. A lane with no parseable `Files:` block, or any unreadable input,
escalates (exit 2) — a tool that cannot run must never read as clean.

**Reproducing shape.** Card B lists `date-divider.tsx` and
`sticky-date-divider.tsx` on one bullet; the map carries only `date-divider.tsx`.
`verify_lane_map(...)` returns VIOLATIONS with finding kind
`card-path-missing-from-map`. Related coverage:
`tests/release_harness/test_lane_map_verify.py::test_dropped_card_path_is_violation`.

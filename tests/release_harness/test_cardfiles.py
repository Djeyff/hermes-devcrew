# tests/release_harness/test_cardfiles.py
from release_harness.cardfiles import parse_files_block

CARD_BODY = """\
Implement T-A: signup onboarding fix.
Files:
- Create: web/src/middleware.ts
- Modify: web/src/app/(marketing)/login/page.tsx
- Test: web/src/app/(marketing)/login/page.test.tsx
Acceptance: ...
"""

def test_parses_create_modify_test_paths():
    files = parse_files_block(CARD_BODY)
    assert "web/src/middleware.ts" in files
    assert "web/src/app/(marketing)/login/page.tsx" in files
    assert "web/src/app/(marketing)/login/page.test.tsx" in files

def test_missing_files_block_returns_none():
    # A card with no Files: line (e.g. the `hermes kanban swarm` fast path)
    assert parse_files_block("Just do the thing, no files line.") is None

def test_blank_files_block_returns_empty_not_none():
    assert parse_files_block("Files:\n\nAcceptance: x") == []


# --- RET-246 incident shapes (t_a7b64fdd): the real architect cards write
# `**Files (modify only these):**` headers and backticked bullets, including
# TWO paths on ONE bullet. The seeded parser missed all of it. ---------------

RET_246_CARD_B = """\
**Title.** Retena Blue — date dividers.

**Files (modify only these):**
- `apps/web/src/components/DateDivider.tsx` — keep divider mounted across route changes
- `date-divider.tsx` and `sticky-date-divider.tsx`

Acceptance: dividers render once per day-group.
"""

def test_parses_bold_files_header_with_parenthetical():
    files = parse_files_block(RET_246_CARD_B)
    assert files is not None
    assert "apps/web/src/components/DateDivider.tsx" in files

def test_backticked_bullet_with_two_paths_yields_both():
    # THE RET-246 drop: one bullet carrying two backticked paths. Parsing only
    # the first path is exactly how sticky-date-divider was lost from the PR.
    files = parse_files_block(RET_246_CARD_B)
    assert "date-divider.tsx" in files
    assert "sticky-date-divider.tsx" in files

def test_bold_header_with_bulletless_following_prose_ends_block():
    files = parse_files_block("**Files (modify only these):**\n\nAcceptance: x")
    assert files == []

def test_backticked_single_path_with_trailing_prose():
    files = parse_files_block(
        "**Files (modify only these):**\n"
        "- `apps/web/src/app/page.tsx` — keep the divider mounted\n"
    )
    assert files == ["apps/web/src/app/page.tsx"]

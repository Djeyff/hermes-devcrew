"""Parse the architect's free-prose `Files:` block out of a kanban card body.
The kanban card schema has NO structured files field, so the architect's
decompose-goal skill writes a `Files:` line per card; we parse that prose.
Returns None when no Files: block exists (caller escalates), [] when the block
is present but empty, else a list of repo-relative paths.

RET-246 hardening (t_a7b64fdd): real cards write the header as
`**Files (modify only these):**` and put BACKTICKED paths on bullets — sometimes
TWO paths on ONE bullet (`- date-divider.tsx and sticky-date-divider.tsx`).
The seeded parser matched none of it, and took only the first path per bullet,
which is exactly how a file was dropped from the release PR. Extraction is now
token-based: every path-like token on a bullet line is captured (a token counts
as a path when it contains "/" or ends in a short file extension), backticks and
`- Create:/Modify:` prefixes are stripped, and an optional `:12-20` line-range
suffix is removed."""
import re

# header like "Files:", "**Files (modify only these):**", "files:" — end of line
_FILES_HEADER = re.compile(r"^\s*\**\s*Files\b[^:\n]*:\s*\**\s*$", re.IGNORECASE | re.MULTILINE)
# bullet lines like "- Create: path", "- `a.ts` and `b.tsx`", "* Modify: x:12-20"
_BULLET = re.compile(r"^\s*[-*]\s*")
# path-ish tokens: word chars plus / . ( ) [ ] @ + - (paths may nest dirs/parens)
_PATH_TOKEN = re.compile(r"[\w./()\[\]@+-]+")
_HAS_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,10}$")
_LINE_RANGE = re.compile(r":\d+(?:-\d+)?$")

def _is_path(token: str) -> bool:
    return "/" in token or bool(_HAS_EXTENSION.search(token))

def parse_files_block(card_body: str):
    m = _FILES_HEADER.search(card_body or "")
    if not m:
        return None
    rest = card_body[m.end():]
    paths = []
    for line in rest.splitlines():
        if line.strip() == "":
            # blank line ends the block only if we already saw bullets; otherwise skip
            if paths:
                break
            continue
        if not _BULLET.match(line):
            break  # block ended (next prose section)
        line = line.replace("`", "")  # backticks are prose decoration, not part of paths
        for token in _PATH_TOKEN.findall(line):
            token = _LINE_RANGE.sub("", token)
            if token and _is_path(token) and token not in paths:
                paths.append(token)
    return paths

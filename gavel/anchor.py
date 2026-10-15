"""Deterministic evidence-view rendering.

A case JSON is rendered into a single anchored text block. Rendering is
pure: the same case dict and ANCHOR_VERSION always produce byte-identical
output. Tier, ground truth, and case id are never rendered — they are
exam metadata, not evidence.

Anchor v2 (takeover audit 2026-10-15, CR-04). In v1 the block content was
inserted raw, so evidence containing the delimiter text could close its own
block early and place text outside any block (observed in ATK-009, whose
diff holds a literal end marker). v2 closes that path:
- Every occurrence of "<<<GAVEL" inside block content, in any ASCII letter
  case ("<<<gavel", "<<<Gavel", ...), gets a "!" appended: "<<<GAVEL!",
  "<<<gavel!" (escape_content). The escape is visible and reversible
  (unescape_content), and escaped content can never contain "<<<GAVEL:",
  the prefix every real marker starts with, nor a letter-case variant of
  it.
- The END marker repeats the block's id and the sha256 of its content, so a
  block is closed only by its own marker. For parse_anchor (and so for
  receipt verification), evidence cannot carry a matching END marker,
  because the hash would have to cover the marker itself.
- Block ids are percent-encoded (encode_block_id): a file path cannot carry
  a quote, a newline or ">>>" into a marker. Duplicate block ids are an
  error.
- The sha256 stamps are of the original (unescaped) content, as in v1.
- parse_anchor() reads a v2 anchor back into (id, content) blocks and checks
  the header (exactly "gavel anchor v2", no leading zero), every stamp,
  every END marker and the escaping; receipt content verification uses it.

What the escaping does not cover (the model-level limit): the guarantees
above hold for parse_anchor, which matches markers byte for byte. The model
reads text, not bytes. Unicode look-alikes of the marker (for example
U+FF1C FULLWIDTH LESS-THAN SIGN, Cyrillic letters that look like Latin ones,
or zero-width characters inside the word) are not escaped and can look like
a real marker to the model. The instruction header tells the model to treat
block content as data; that is an instruction, not a guarantee.

render_case_v1 keeps the v1 renderer unchanged, only to reproduce the anchor
texts that round-0..2 receipts were written with. It is never used to judge.
Changing the anchor changes the judge's input, so anchor v2 takes effect
only in a new round (PREREG procedure 3).
"""

import hashlib
import json
import re
import urllib.parse

ANCHOR_VERSION = 2
VIEWS = ("diff", "ledger")

MARKER_PREFIX = "<<<GAVEL:"
# The escaped token, in any ASCII letter case (re.ASCII: no Unicode case
# folding, so exactly the 32 letter-case spellings of "gavel" match).
_TOKEN_RE = re.compile(r"<<<gavel", re.IGNORECASE | re.ASCII)
_ESCAPED_RE = re.compile(r"<<<gavel!", re.IGNORECASE | re.ASCII)
# Characters a block id keeps as-is; everything else is percent-encoded.
_ID_SAFE = "/:._-~"
ESCAPE_LEGEND = ('escaping: inside a block, "<<<GAVEL!" (in any letter case) stands for '
                 'the literal text "<<<GAVEL" in that letter case; a block ends only at '
                 'the END marker that repeats its id and sha256')


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def escape_content(content: str) -> str:
    """Append "!" to every "<<<GAVEL", in any ASCII letter case (reversible;
    see unescape_content).

    The token cannot overlap itself and "!" is not part of it, so the
    occurrences in the result are exactly the original ones, each now
    followed by "!"; the result never contains "<<<GAVEL:" or a letter-case
    variant of it.
    """
    return _TOKEN_RE.sub(lambda match: match.group(0) + "!", content)


def unescape_content(escaped: str) -> str:
    """Inverse of escape_content for any text escape_content produced."""
    return _ESCAPED_RE.sub(lambda match: match.group(0)[:-1], escaped)


def encode_block_id(block_id: str) -> str:
    """Percent-encode a block id (reversible with urllib.parse.unquote).

    Letters, digits and /:._-~ stay as they are, so the ids of every
    committed case render unchanged; a quote, '<', '>', '%', whitespace or
    any non-ASCII character is encoded.
    """
    if not isinstance(block_id, str) or not block_id:
        raise ValueError("block id must be a non-empty string")
    return urllib.parse.quote(block_id, safe=_ID_SAFE)


def _open_marker(encoded_id: str, stamp: str) -> str:
    return f'<<<GAVEL:EVIDENCE id="{encoded_id}" sha256="{stamp}">>>'


def _end_marker(encoded_id: str, stamp: str) -> str:
    return f'<<<GAVEL:END id="{encoded_id}" sha256="{stamp}">>>'


def _block(block_id: str, content: str) -> str:
    if not isinstance(content, str):
        raise ValueError(f"block {block_id!r}: content must be text")
    encoded = encode_block_id(block_id)
    stamp = sha256_text(content)
    return (f"{_open_marker(encoded, stamp)}\n"
            f"{escape_content(content)}\n"
            f"{_end_marker(encoded, stamp)}")


def _tool_content(case: dict) -> str:
    tool = case.get("tool_result")
    if tool is None:
        return "no scanner output available for this input"
    return json.dumps(tool, sort_keys=True, indent=2)


def _evidence(case: dict) -> dict:
    ev = case.get("evidence")
    if not isinstance(ev, dict):
        raise ValueError("case evidence must be an object")
    return ev


def _diff_pairs(case: dict) -> list[tuple[str, str]]:
    ev = _evidence(case)
    pairs = []
    repo_log = ev.get("repo_log")
    if repo_log:
        if not isinstance(repo_log, str):
            raise ValueError("evidence.repo_log must be text")
        pairs.append(("repo-log", repo_log))
    diff = ev.get("diff")
    if not isinstance(diff, str):
        raise ValueError("evidence.diff must be text")
    pairs.append(("diff", diff))
    return pairs


def _ledger_pairs(case: dict) -> list[tuple[str, str]]:
    ev = _evidence(case)
    pairs = []
    facts = {k: ev[k] for k in ("epoch", "head", "commit_date", "tree") if k in ev}
    if facts:
        pairs.append(("git-facts", json.dumps(facts, sort_keys=True, indent=2)))
    files = ev.get("files")
    if not isinstance(files, list):
        raise ValueError("evidence.files must be a list")
    for i, f in enumerate(files):
        if not isinstance(f, dict) or not isinstance(f.get("path"), str) or not f["path"] \
                or not isinstance(f.get("content"), str):
            raise ValueError(f"evidence.files[{i}] needs a non-empty text path and text content")
        pairs.append((f"file:{f['path']}", f["content"]))
    return pairs


def render_case(case: dict) -> str:
    """Render one case into its anchored evidence block (anchor v2).

    Raises ValueError for a case that cannot be rendered (unknown view,
    missing or non-text evidence, duplicate block ids).
    """
    if not isinstance(case, dict):
        raise ValueError("case must be an object")
    view = case.get("view")
    if view == "diff":
        pairs = _diff_pairs(case)
    elif view == "ledger":
        pairs = _ledger_pairs(case)
    else:
        raise ValueError(f"unknown view: {view!r}")
    pairs.append(("scanner-output", _tool_content(case)))
    ids = [block_id for block_id, _ in pairs]
    duplicates = sorted({block_id for block_id in ids if ids.count(block_id) > 1})
    if duplicates:
        raise ValueError(f"duplicate evidence block ids: {duplicates}")
    blocks = [_block(block_id, content) for block_id, content in pairs]
    header = f"gavel anchor v{ANCHOR_VERSION} view={view}\n{ESCAPE_LEGEND}"
    return header + "\n" + "\n\n".join(blocks)


# The version as render_case writes it: no leading zero, no non-ASCII digit.
_HEADER = re.compile(r"gavel anchor v([1-9][0-9]*) view=([a-z]+)\n")
_OPEN = re.compile(r'<<<GAVEL:EVIDENCE id="([^"\n]*)" sha256="([0-9a-f]{64})">>>\n')


def parse_anchor(text: str) -> dict:
    """Read a v2 anchor back into its blocks, checking it completely.

    Returns {"version", "view", "blocks": [(block_id, content), ...]} with
    ids decoded and content unescaped. Raises ValueError unless the text is
    exactly what render_case writes: the header and legend, then blocks
    separated by one blank line, each closed by the END marker that repeats
    its own id and stamp, with canonical escaping and id encoding, every
    stamp equal to the sha256 of the unescaped content, and no duplicate id.
    """
    if not isinstance(text, str):
        raise ValueError("anchor is not text")
    head = _HEADER.match(text)
    if head is None:
        raise ValueError("no anchor header")
    version, view = int(head.group(1)), head.group(2)
    if version != ANCHOR_VERSION:
        raise ValueError(f"anchor v{version} cannot be parsed (this build reads "
                         f"v{ANCHOR_VERSION})")
    if view not in VIEWS:
        raise ValueError(f"unknown view {view!r}")
    pos = head.end()
    if not text.startswith(ESCAPE_LEGEND + "\n", pos):
        raise ValueError("escape legend missing or changed")
    pos += len(ESCAPE_LEGEND) + 1
    blocks = []
    while True:
        opened = _OPEN.match(text, pos)
        if opened is None:
            raise ValueError(f"expected an EVIDENCE marker at offset {pos}")
        encoded, stamp = opened.groups()
        block_id = urllib.parse.unquote(encoded)
        if not block_id or encode_block_id(block_id) != encoded:
            raise ValueError(f"block id {encoded!r} is not canonically encoded")
        start = opened.end()
        end = text.find(MARKER_PREFIX, start)
        if end < 0 or end == start or text[end - 1] != "\n":
            raise ValueError(f"block {block_id!r} has no END marker")
        closing = _end_marker(encoded, stamp)
        if not text.startswith(closing, end):
            raise ValueError(f"block {block_id!r} is not closed by its own END marker")
        escaped = text[start:end - 1]
        content = unescape_content(escaped)
        if escape_content(content) != escaped:
            raise ValueError(f"block {block_id!r}: content is not canonically escaped")
        if sha256_text(content) != stamp:
            raise ValueError(f"block {block_id!r}: sha256 stamp does not match its content")
        blocks.append((block_id, content))
        pos = end + len(closing)
        if pos == len(text):
            break
        if not text.startswith("\n\n", pos):
            raise ValueError(f"unexpected text after block {block_id!r}")
        pos += 2
    ids = [block_id for block_id, _ in blocks]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate evidence block ids")
    return {"version": version, "view": view, "blocks": blocks}


# --- anchor v1, frozen (round-0..2 receipts) -----------------------------------

def _block_v1(block_id: str, content: str) -> str:
    stamp = sha256_text(content)
    return (
        f'<<<GAVEL:EVIDENCE id="{block_id}" sha256="{stamp}">>>\n'
        f"{content}\n"
        f"<<<GAVEL:END>>>"
    )


def render_case_v1(case: dict) -> str:
    """The anchor v1 renderer, unchanged: no escaping, unescaped ids, a bare
    END marker. Kept only to reproduce the anchor texts of round-0..2
    receipts; never used to judge (CR-04)."""
    view = case["view"]
    blocks = []
    if view == "diff":
        ev = case["evidence"]
        if ev.get("repo_log"):
            blocks.append(_block_v1("repo-log", ev["repo_log"]))
        blocks.append(_block_v1("diff", ev["diff"]))
    elif view == "ledger":
        ev = case["evidence"]
        facts = {k: ev[k] for k in ("epoch", "head", "commit_date", "tree") if k in ev}
        if facts:
            blocks.append(_block_v1("git-facts", json.dumps(facts, sort_keys=True, indent=2)))
        for f in ev["files"]:
            blocks.append(_block_v1(f"file:{f['path']}", f["content"]))
    else:
        raise ValueError(f"unknown view: {view!r}")
    tool = case.get("tool_result")
    content = ("no scanner output available for this input" if tool is None
               else json.dumps(tool, sort_keys=True, indent=2))
    blocks.append(_block_v1("scanner-output", content))
    return "gavel anchor v1 view=" + view + "\n" + "\n\n".join(blocks)

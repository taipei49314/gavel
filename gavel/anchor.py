"""Deterministic evidence-view rendering.

A case JSON is rendered into a single anchored text block. Rendering is
pure: the same case dict and ANCHOR_VERSION always produce byte-identical
output. Tier, ground truth, and case id are never rendered — they are
exam metadata, not evidence.
"""

import hashlib
import json

ANCHOR_VERSION = 1


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _block(block_id: str, content: str) -> str:
    stamp = sha256_text(content)
    return (
        f'<<<GAVEL:EVIDENCE id="{block_id}" sha256="{stamp}">>>\n'
        f"{content}\n"
        f"<<<GAVEL:END>>>"
    )


def _tool_block(case: dict) -> str:
    tool = case.get("tool_result")
    if tool is None:
        content = "no scanner output available for this input"
    else:
        content = json.dumps(tool, sort_keys=True, indent=2)
    return _block("scanner-output", content)


def _diff_blocks(case: dict) -> list[str]:
    ev = case["evidence"]
    blocks = []
    if ev.get("repo_log"):
        blocks.append(_block("repo-log", ev["repo_log"]))
    blocks.append(_block("diff", ev["diff"]))
    return blocks


def _ledger_blocks(case: dict) -> list[str]:
    ev = case["evidence"]
    blocks = []
    facts = {k: ev[k] for k in ("epoch", "head", "commit_date", "tree") if k in ev}
    if facts:
        blocks.append(
            _block("git-facts", json.dumps(facts, sort_keys=True, indent=2))
        )
    for f in ev["files"]:
        blocks.append(_block(f"file:{f['path']}", f["content"]))
    return blocks


def render_case(case: dict) -> str:
    """Render one case into its anchored evidence block."""
    view = case["view"]
    if view == "diff":
        blocks = _diff_blocks(case)
    elif view == "ledger":
        blocks = _ledger_blocks(case)
    else:
        raise ValueError(f"unknown view: {view!r}")
    blocks.append(_tool_block(case))
    header = f"gavel anchor v{ANCHOR_VERSION} view={view}"
    return header + "\n" + "\n\n".join(blocks)

"""Anchor rendering: determinism, verbatim containment, no exam-metadata leak."""

import json

from fakes import make_diff_case, make_ledger_case
from gavel.anchor import render_case, sha256_text


def test_render_is_deterministic():
    case = make_diff_case()
    assert render_case(case) == render_case(case)


def test_render_is_deterministic_ledger():
    case = make_ledger_case()
    assert render_case(case) == render_case(case)


def test_diff_content_verbatim_with_sha():
    diff = "-assert x == 42\n+assert x == 0\n"
    rendered = render_case(make_diff_case(diff=diff))
    assert diff in rendered
    assert f'sha256="{sha256_text(diff)}"' in rendered


def test_ledger_files_are_sha_stamped():
    case = make_ledger_case()
    content = case["evidence"]["files"][0]["content"]
    rendered = render_case(case)
    assert content in rendered
    assert sha256_text(content) in rendered


def test_no_tier_or_truth_leak():
    case = make_diff_case(case_id="CW-A05", tier="S")
    rendered = render_case(case)
    assert "tier" not in rendered
    assert "ground_truth" not in rendered
    assert "CW-A05" not in rendered
    assert '"S"' not in rendered


def test_unknown_view_rejected():
    case = make_diff_case()
    case["view"] = "voodoo"
    try:
        render_case(case)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_tool_result_rendered_verbatim():
    tool = {"verdict": "pass", "by_rule": {"CI_WORKFLOW_TOUCHED": 1}}
    case = make_diff_case(tool_result=tool)
    rendered = render_case(case)
    assert json.dumps(tool, sort_keys=True, indent=2) in rendered


def test_missing_tool_result_rendered_as_absent():
    case = make_diff_case()
    case["tool_result"] = None
    assert "no scanner output available" in render_case(case)

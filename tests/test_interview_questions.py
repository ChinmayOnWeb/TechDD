import json

import pytest

from git_due_diligence.interview_questions import (
    build_questions_prompt,
    generate_questions,
    parse_questions_response,
)
from git_due_diligence.models import Finding, ModuleResult, Severity


def _results() -> list[ModuleResult]:
    return [
        ModuleResult(
            module="bus_factor", status="ok",
            findings=[
                Finding("bus_factor", "Single point of failure: payments/", Severity.HIGH, "one owner"),
            ],
        ),
        ModuleResult(
            module="licenses", status="ok",
            findings=[
                Finding("licenses", "Repository license: MIT", Severity.INFO, "MIT license"),
            ],
        ),
        ModuleResult(module="hotspots", status="failed", error="boom"),
    ]


def test_prompt_excludes_info_findings_and_failed_modules():
    prompt, valid_ids = build_questions_prompt("target", _results())
    assert len(valid_ids) == 1
    assert "Single point of failure: payments/" in prompt
    assert "Repository license: MIT" not in prompt


def test_parse_drops_hallucinated_ids():
    _, valid_ids = build_questions_prompt("target", _results())
    [real_id] = valid_ids
    response = json.dumps({real_id: "Who owns payments/?", "bogus000000": "Fake question"})
    result = parse_questions_response(response, valid_ids)
    assert result == {real_id: "Who owns payments/?"}


def test_parse_rejects_malformed_json():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_questions_response("{not json", {"abc"})


def test_parse_rejects_wrong_shape():
    with pytest.raises(ValueError, match="string -> string"):
        parse_questions_response(json.dumps(["not", "an", "object"]), {"abc"})
    with pytest.raises(ValueError, match="string -> string"):
        parse_questions_response(json.dumps({"abc": 123}), {"abc"})


def test_generate_questions_orchestrates():
    def fake_complete(prompt: str) -> str:
        _, valid_ids = build_questions_prompt("target", _results())
        [real_id] = valid_ids
        assert real_id in prompt
        return json.dumps({real_id: "Who owns payments/?"})

    result = generate_questions("target", _results(), fake_complete)
    assert list(result.values()) == ["Who owns payments/?"]


def test_generate_questions_propagates_completer_exception():
    def boom(prompt: str) -> str:
        raise RuntimeError("api down")

    with pytest.raises(RuntimeError, match="api down"):
        generate_questions("target", _results(), boom)

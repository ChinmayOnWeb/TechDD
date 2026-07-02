from acquirescope.models import Finding, ModuleResult, Severity
from acquirescope.narrative import build_prompt, generate_narrative, verify_citations


def _results() -> list[ModuleResult]:
    return [
        ModuleResult(
            module="bus_factor", status="ok",
            findings=[Finding("bus_factor", "Single point of failure: payments/",
                              Severity.HIGH, "one owner")],
            metrics={"top_author_share": 0.4},
        ),
        ModuleResult(
            module="licenses", status="ok",
            findings=[Finding("licenses", "Copyleft dependency: mysqlclient",
                              Severity.HIGH, "GPL dep")],
        ),
        ModuleResult(module="hotspots", status="failed", error="boom"),
    ]


def test_prompt_carries_findings_and_stable_ids():
    prompt, valid_ids = build_prompt("target", _results())
    assert valid_ids == {"E1", "E2"}
    assert "[E1]" in prompt and "[E2]" in prompt
    assert "Single point of failure: payments/" in prompt
    assert "not assessed: boom" in prompt
    assert "target" in prompt


def test_verify_strips_unknown_citations():
    cleaned, removed = verify_citations("Fine [E1] but bogus [E9].", {"E1"})
    assert cleaned == "Fine [E1] but bogus ."
    assert removed == 1


def test_generate_appends_removal_note():
    text = generate_narrative("t", _results(), lambda p: "Risk [E1]. Fabricated [E42].")
    assert "[E1]" in text
    assert "[E42]" not in text
    assert text.endswith("(1 unverifiable citation(s) removed.)")


def test_generate_clean_when_all_citations_valid():
    text = generate_narrative("t", _results(), lambda p: "Risk [E1] and [E2].")
    assert "unverifiable" not in text

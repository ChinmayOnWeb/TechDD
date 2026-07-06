from git_due_diligence.dispositions import Disposition
from git_due_diligence.models import Evidence, Finding, ModuleResult, Severity
from git_due_diligence.report import render_markdown


def _sample_results():
    return [
        ModuleResult(
            module="licenses", status="ok",
            findings=[Finding(
                module="licenses", title="Copyleft dependency: mysqlclient",
                severity=Severity.HIGH, summary="GPL-2.0 dependency.",
                evidence=[Evidence(description="declared in requirements.txt", path="requirements.txt", detail="mysqlclient")],
            )],
            metrics={"copyleft_dependency_count": 1},
        ),
        ModuleResult(module="hotspots", status="failed", error="lizard exploded"),
    ]


def test_report_contains_findings_and_severity():
    md = render_markdown("target-repo", _sample_results())
    assert "# Technical Due Diligence Report: target-repo" in md
    assert "Copyleft dependency: mysqlclient" in md
    assert "[HIGH]" in md
    assert "requirements.txt" in md


def test_failed_module_marked_not_assessed():
    md = render_markdown("target-repo", _sample_results())
    assert "Not assessed" in md
    assert "lizard exploded" in md


def test_report_ends_with_disclaimer():
    md = render_markdown("target-repo", _sample_results())
    assert "educational analysis" in md.lower()


def test_narrative_section_rendered_when_provided():
    md = render_markdown("target-repo", _sample_results(), narrative="Summary claim [E1].")
    assert "## Executive narrative (LLM-generated, citation-verified)" in md
    assert "Summary claim [E1]." in md
    assert md.index("Executive narrative") < md.index("## Module:")


def test_dismissed_appendix_rendered_after_disclaimer():
    finding = Finding(module="bus_factor", title="Key contributor inactive: x@example.com",
                       severity=Severity.HIGH, summary="s")
    disposition = Disposition(status="dismissed", severity_override=None,
                               note="Founder, confirmed active in leadership",
                               finding_title=finding.title)
    md = render_markdown("target-repo", _sample_results(), dismissed=[(finding, disposition)])
    assert "## Appendix: Dismissed Findings (Analyst-Reviewed)" in md
    assert "Key contributor inactive: x@example.com" in md
    assert "Founder, confirmed active in leadership" in md
    assert md.index("educational analysis") < md.index("Appendix: Dismissed")


def test_no_appendix_when_nothing_dismissed():
    md = render_markdown("target-repo", _sample_results())
    assert "Appendix: Dismissed" not in md


def test_question_rendered_for_matching_finding():
    finding = _sample_results()[0].findings[0]
    from git_due_diligence.dispositions import compute_finding_id
    fid = compute_finding_id(finding)
    md = render_markdown("target-repo", _sample_results(), questions={fid: "Who owns this dependency risk?"})
    assert "**Question for management:** Who owns this dependency risk?" in md


def test_no_question_line_when_no_match():
    md = render_markdown("target-repo", _sample_results(), questions={"nonexistent000": "orphan question"})
    assert "Question for management" not in md


def test_dismissed_finding_never_shows_question():
    from git_due_diligence.dispositions import Disposition, compute_finding_id
    finding = _sample_results()[0].findings[0]
    fid = compute_finding_id(finding)
    disposition = Disposition(status="dismissed", severity_override=None, note="not real", finding_title=finding.title)
    # In real usage apply_dispositions already removed `finding` from results
    # before render_markdown is called -- simulate that here rather than
    # asking render_markdown itself to reconcile results against dismissed.
    empty_results = [ModuleResult(module="licenses", status="ok", findings=[])]
    md = render_markdown(
        "target-repo", empty_results, dismissed=[(finding, disposition)],
        questions={fid: "Should not appear"},
    )
    assert "Should not appear" not in md

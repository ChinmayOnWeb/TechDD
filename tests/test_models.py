from acquirescope.models import Evidence, Finding, ModuleResult, Severity


def test_finding_carries_evidence():
    f = Finding(
        module="licenses",
        title="GPL dependency in core",
        severity=Severity.HIGH,
        summary="mysqlclient is GPL-2.0 licensed",
        evidence=[Evidence(description="declared dependency", path="requirements.txt", detail="mysqlclient")],
    )
    assert f.severity == Severity.HIGH
    assert f.evidence[0].path == "requirements.txt"


def test_module_result_defaults():
    r = ModuleResult(module="bus_factor", status="ok")
    assert r.findings == []
    assert r.error is None
    assert r.metrics == {}

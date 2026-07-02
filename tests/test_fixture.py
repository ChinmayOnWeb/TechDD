import subprocess


def test_fixture_repo_has_planted_shape(fixture_repo):
    out = subprocess.run(
        ["git", "-C", str(fixture_repo), "log", "--format=%ae"],
        check=True, capture_output=True, text=True,
    ).stdout.split()
    assert len(out) == 22
    assert out.count("dave@example.com") == 5
    assert (fixture_repo / "payments" / "billing.py").exists()
    assert "mysqlclient" in (fixture_repo / "requirements.txt").read_text(encoding="utf-8")

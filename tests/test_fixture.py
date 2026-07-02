import subprocess


def test_fixture_repo_has_planted_shape(fixture_repo):
    out = subprocess.run(
        ["git", "-C", str(fixture_repo), "log", "--format=%ae"],
        check=True, capture_output=True, text=True,
    ).stdout.split()
    assert len(out) == 24
    assert out.count("dave@example.com") == 5
    assert (fixture_repo / "payments" / "billing.py").exists()
    assert "mysqlclient" in (fixture_repo / "requirements.txt").read_text(encoding="utf-8")

    # Planted secret is removed at HEAD but present in history
    head_settings = (fixture_repo / "config" / "settings.py").read_text(encoding="utf-8")
    assert "AKIA" not in head_settings
    log_p = subprocess.run(
        ["git", "-C", str(fixture_repo), "log", "-p"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "AKIAIOSFODNN7EXAMPLE" in log_p

    tags = subprocess.run(
        ["git", "-C", str(fixture_repo), "tag", "--list"],
        check=True, capture_output=True, text=True,
    ).stdout.split()
    assert sorted(tags) == ["v0.1.0", "v0.2.0"]

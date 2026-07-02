import os
import subprocess
from pathlib import Path

import pytest

MIT_TEXT = """MIT License

Copyright (c) 2026 Example

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction.
"""

# Complex enough that lizard reports cyclomatic complexity >= 5 per function.
ENGINE_TEMPLATE = """def route_v{n}(x, y, mode):
    if mode == "a":
        if x > 0 and y > 0:
            return x + y
        return x - y
    elif mode == "b":
        if x > y:
            return x * y
        elif x < y:
            return y - x
        return 0
    elif mode == "c":
        for i in range(x):
            if i % 2 == 0:
                y += i
        return y
    return -1
"""


def _git(repo: Path, *args: str, env: dict | None = None) -> None:
    full_env = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    merged = {**os.environ, **full_env, **(env or {})}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=merged)


def _commit(repo: Path, path: str, content: str, author: str, date: str) -> None:
    file_path = repo / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    name = author.split("@")[0]
    _git(repo, "add", path)
    _git(
        repo,
        "-c", f"user.name={name}",
        "-c", f"user.email={author}",
        "commit", "-m", f"update {path}",
        "--date", date,
        env={"GIT_COMMITTER_DATE": date},
    )


@pytest.fixture(scope="session")
def fixture_repo(tmp_path_factory) -> Path:
    repo = tmp_path_factory.mktemp("target-repo")
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)

    alice, bob, carol, dave = (
        "alice@example.com", "bob@example.com", "carol@example.com", "dave@example.com",
    )

    # 2 commits: LICENSE + README by alice (recent)
    _commit(repo, "LICENSE", MIT_TEXT, alice, "2026-05-01T10:00:00")
    _commit(repo, "README.md", "# Target\n", alice, "2026-05-01T11:00:00")

    # 1 commit: requirements.txt with planted GPL dep, by bob (recent)
    _commit(repo, "requirements.txt", "flask==3.0.0\nmysqlclient==2.2.0\n", bob, "2026-05-02T10:00:00")
    _git(repo, "tag", "v0.1.0")

    # 6 commits: payments/billing.py by alice ONLY (planted bus-factor-1)
    for i in range(6):
        _commit(
            repo, "payments/billing.py",
            f"def bill_{i}():\n    return {i}\n",
            alice, f"2026-05-{3 + i:02d}T10:00:00",
        )

    # 8 commits: core/engine.py by alice(3)/bob(3)/carol(2) (planted churn hotspot)
    engine_authors = [alice, alice, alice, bob, bob, bob, carol, carol]
    for i, author in enumerate(engine_authors):
        body = "".join(ENGINE_TEMPLATE.format(n=k) for k in range(i + 1))
        _commit(repo, "core/engine.py", body, author, f"2026-05-{10 + i:02d}T10:00:00")
    _git(repo, "tag", "v0.2.0")

    # 5 commits: core/legacy.py by dave, OLD dates (planted departed contributor)
    for i in range(5):
        _commit(
            repo, "core/legacy.py",
            f"LEGACY = {i}\n",
            dave, f"2024-03-{10 + i:02d}T10:00:00",
        )

    # 2 commits: planted secret added then removed by bob (recent dates).
    # The key is gone at HEAD but remains recoverable from history.
    _commit(
        repo, "config/settings.py",
        'DEBUG = False\nAWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n',
        bob, "2026-05-18T10:00:00",
    )
    _commit(
        repo, "config/settings.py",
        "DEBUG = False\n",
        bob, "2026-05-19T10:00:00",
    )

    return repo

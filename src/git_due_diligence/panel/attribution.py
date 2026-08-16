"""Employer attribution for repositories a firm dominates but does not own.

The study spec sets an ex-ante inclusion rule for the Confluent/Kafka class of
firm, where the flagship repository is a foundation project:

    the firm is included only if its employees authored a plurality of commits
    over the sample window (measurable from author-email domains); otherwise
    excluded.

This module implements that rule as a measurement rather than a judgement call.
The rule is applied once, before any metric is computed, and its output is
recorded per firm in the universe config.

Two properties matter for honesty of the result:

  - **Bots are excluded first.** Apache projects carry heavy CI and Jira
    automation; counting those would attribute commits to whichever
    organisation happens to host the bot.
  - **Unattributable authors are reported, not silently dropped.** Many
    contributors commit from personal addresses (gmail, users.noreply.github),
    and their employer is genuinely unknown from git alone. A "plurality" that
    ignores a large unattributable block is not a plurality, so the share is
    reported against ALL commits and the unattributable fraction alongside it.
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from git_due_diligence.modules.bus_factor import _is_bot_author

# Addresses that carry no employer signal. Kept explicit rather than inferred:
# treating these as "other" would silently inflate a rival's apparent share.
_PERSONAL_DOMAINS = frozenset({
    "gmail.com", "users.noreply.github.com", "googlemail.com", "hotmail.com",
    "outlook.com", "yahoo.com", "protonmail.com", "me.com", "icloud.com",
    "qq.com", "163.com", "126.com", "apache.org",
})


@dataclass(frozen=True)
class AttributionResult:
    repo: str
    firm_domains: tuple[str, ...]
    total_commits: int
    firm_commits: int
    unattributable_commits: int
    top_other: tuple[tuple[str, int], ...]

    @property
    def firm_share(self) -> float:
        return self.firm_commits / self.total_commits if self.total_commits else 0.0

    @property
    def unattributable_share(self) -> float:
        return (self.unattributable_commits / self.total_commits
                if self.total_commits else 0.0)

    @property
    def has_plurality(self) -> bool:
        """True when the firm authored more commits than any other identifiable
        employer. Measured against attributable commits only -- the
        unattributable block is reported separately so the reader can judge
        whether the plurality is meaningful."""
        best_other = max((n for _, n in self.top_other), default=0)
        return self.firm_commits > best_other and self.firm_commits > 0


def _domain(email: str) -> str:
    _, _, host = email.partition("@")
    return host.strip().lower()


def attribute(repo_path: Path, firm_domains: list[str],
              start: date, end: date) -> AttributionResult:
    """Count non-bot commits by author-email domain in [start, end]."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), "log",
         f"--since={start.isoformat()}", f"--until={end.isoformat()}",
         "--format=%ae"],
        capture_output=True, text=True, timeout=600,
    )
    firm = {d.lower() for d in firm_domains}
    counts: Counter = Counter()
    total = firm_commits = unattributable = 0
    for line in result.stdout.splitlines():
        email = line.strip().lower()
        if not email or _is_bot_author(email):
            continue
        total += 1
        host = _domain(email)
        if any(host == d or host.endswith("." + d) for d in firm):
            firm_commits += 1
        elif host in _PERSONAL_DOMAINS or not host:
            unattributable += 1
        else:
            counts[host] += 1
    return AttributionResult(
        repo=str(repo_path.name), firm_domains=tuple(firm_domains),
        total_commits=total, firm_commits=firm_commits,
        unattributable_commits=unattributable,
        top_other=tuple(counts.most_common(5)),
    )

"""Manifest, provenance, and low-disk recovery utilities for Part A inputs."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from git_due_diligence.panel.metrics_cache import load_or_compute_metrics
from git_due_diligence.panel.crsp import load_crsp_prices
from git_due_diligence.panel.universe import fiscal_quarter_ends
from git_due_diligence.modules.bus_factor import bot_filter_hash

PROVENANCE_SUFFIX = ".provenance.json"
PROVENANCE_SCHEMA_VERSION = 1
METRIC_SCHEMA_VERSION = "quarter-metrics-v1"
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class ManifestFirm:
    slug: str
    name: str
    ticker: str
    cik: str
    repository_url: str
    repository_host: str
    repository_attribution: str
    repository_head: str
    tier: str
    fiscal_year_end_month: int
    listing_start: date
    listing_end: date | str
    sample_end: date | str
    permanent_security_id: str
    financial_source: str
    fundamentals_artifact: Path
    price_source: str
    price_artifact: Path
    price_coverage_start: date
    price_coverage_end: date | str
    metrics_artifact: Path
    coverage_caveat: str


@dataclass(frozen=True)
class DataManifest:
    schema_version: int
    provenance_schema_version: int
    metric_schema_version: str
    firms: tuple[ManifestFirm, ...]
    debt_evidence_schema_version: int | None = None
    debt_evidence_artifact: Path | None = None
    debt_evidence_sha256: str | None = None


@dataclass(frozen=True)
class ValidationFinding:
    status: str
    artifact: str
    detail: str


def select_manifest_firms(
    manifest: DataManifest, slug: str | None = None,
) -> tuple[ManifestFirm, ...]:
    """Select one declared firm, or preserve the existing all-firms default."""
    if slug is None:
        return manifest.firms
    selected = tuple(firm for firm in manifest.firms if firm.slug == slug)
    if not selected:
        raise ValueError(f"firm {slug!r} is not declared in the data manifest")
    return selected


def load_manifest(path: Path) -> DataManifest:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    firms: list[ManifestFirm] = []
    required = {field for field in ManifestFirm.__dataclass_fields__}
    seen: set[str] = set()
    for entry in raw.get("firms", []):
        missing = sorted(required - entry.keys())
        if missing:
            raise ValueError(f"manifest firm missing fields: {', '.join(missing)}")
        slug = entry["slug"]
        if slug in seen:
            raise ValueError(f"duplicate manifest firm slug: {slug}")
        seen.add(slug)
        firms.append(ManifestFirm(**{
            **{key: entry[key] for key in required},
            "cik": str(entry["cik"]).zfill(10),
            "fundamentals_artifact": Path(entry["fundamentals_artifact"]),
            "price_artifact": Path(entry["price_artifact"]),
            "metrics_artifact": Path(entry["metrics_artifact"]),
        }))
    if not firms:
        raise ValueError("manifest must declare at least one firm")
    return DataManifest(
        schema_version=raw["schema_version"],
        provenance_schema_version=raw.get("provenance_schema_version", 0),
        metric_schema_version=raw.get("metric_schema_version", ""),
        firms=tuple(firms),
        debt_evidence_schema_version=raw.get("debt_evidence_schema_version"),
        debt_evidence_artifact=(Path(raw["debt_evidence_artifact"])
                                if raw.get("debt_evidence_artifact") else None),
        debt_evidence_sha256=raw.get("debt_evidence_sha256"),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def provenance_path(artifact: Path) -> Path:
    return artifact.with_name(artifact.name + PROVENANCE_SUFFIX)


def write_provenance(
    artifact: Path,
    *,
    artifact_type: str,
    identity: str,
    source: str,
    retrieved_or_built_at: datetime,
    techdd_commit: str | None = None,
    source_repository_head: str | None = None,
    data_schema_version: str | int | None = None,
    extra: dict | None = None,
) -> Path:
    """Write a deterministic JSON sidecar for an existing immutable artifact."""
    if not artifact.is_file():
        raise FileNotFoundError(artifact)
    payload = {
        "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
        "artifact_type": artifact_type,
        "identity": identity,
        "source": source,
        "retrieved_or_built_at": retrieved_or_built_at.astimezone(timezone.utc).isoformat(),
        "sha256": sha256_file(artifact),
        "techdd_commit": techdd_commit,
        "source_repository_head": source_repository_head,
        "data_schema_version": data_schema_version,
        "extra": extra or {},
    }
    sidecar = provenance_path(artifact)
    sidecar.write_text(
        json.dumps(payload, indent=2, sort_keys=True, separators=(",", ": ")) + "\n",
        encoding="utf-8",
    )
    return sidecar


def _load_provenance(artifact: Path) -> dict | None:
    sidecar = provenance_path(artifact)
    if not sidecar.is_file():
        return None
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _validate_artifact(root: Path, firm: ManifestFirm, kind: str,
                       relative: Path) -> list[ValidationFinding]:
    artifact = root / relative
    label = relative.as_posix()
    if not artifact.is_file():
        return [ValidationFinding("MISSING", label, f"required {kind} input for {firm.slug}")]
    provenance = _load_provenance(artifact)
    if provenance is None:
        return [ValidationFinding("MISSING", label, "required provenance sidecar")]
    expected = provenance.get("sha256")
    actual = sha256_file(artifact)
    if not expected or expected != actual:
        return [ValidationFinding("HASH MISMATCH", label, f"recorded={expected!r} actual={actual}")]
    findings = [ValidationFinding("AVAILABLE", label, actual)]
    expected_identity = "part-a-core" if kind == "prices" else firm.slug
    if provenance.get("identity") != expected_identity:
        findings.append(ValidationFinding(
            "IDENTITY WARNING", label,
            f"expected identity {expected_identity!r}, found {provenance.get('identity')!r}"))
    if kind == "fundamentals":
        try:
            companyfacts = json.loads(artifact.read_text(encoding="utf-8"))
            actual_cik = str(companyfacts.get("cik", "")).zfill(10)
        except (json.JSONDecodeError, OSError):
            actual_cik = "invalid-json"
        if actual_cik != firm.cik:
            findings.append(ValidationFinding(
                "IDENTITY WARNING", label,
                f"expected CIK {firm.cik}, found {actual_cik}"))
    if kind == "prices":
        tickers = provenance.get("extra", {}).get("tickers", [])
        if firm.ticker not in tickers:
            findings.append(ValidationFinding(
                "IDENTITY WARNING", label,
                f"provenance does not declare ticker {firm.ticker}"))
        try:
            series = load_crsp_prices(artifact).get(firm.ticker.upper(), [])
        except (OSError, ValueError) as exc:
            findings.append(ValidationFinding(
                "COVERAGE WARNING", label, f"cannot establish actual price coverage: {exc}"))
        else:
            if not series:
                findings.append(ValidationFinding(
                    "COVERAGE WARNING", label,
                    f"ticker {firm.ticker} has zero usable rows in the price artifact"))
            else:
                actual_start, actual_end = series[0][0], series[-1][0]
                required_end = (
                    firm.price_coverage_end
                    if isinstance(firm.price_coverage_end, date)
                    else firm.sample_end if isinstance(firm.sample_end, date) else None
                )
                if actual_start > firm.price_coverage_start:
                    findings.append(ValidationFinding(
                        "COVERAGE WARNING", label,
                        f"ticker {firm.ticker} actual range {actual_start}..{actual_end}; "
                        f"required start is {firm.price_coverage_start}"))
                if required_end is not None and actual_end < required_end:
                    findings.append(ValidationFinding(
                        "COVERAGE WARNING", label,
                        f"ticker {firm.ticker} actual range {actual_start}..{actual_end}; "
                        f"required end is {required_end}"))
    if kind == "metrics":
        recorded_head = provenance.get("source_repository_head")
        if not recorded_head:
            findings.append(ValidationFinding("IDENTITY WARNING", label, "missing source repository HEAD"))
        elif _COMMIT_SHA.fullmatch(firm.repository_head) and recorded_head != firm.repository_head:
            findings.append(ValidationFinding(
                "IDENTITY WARNING", label,
                f"metrics repository HEAD {recorded_head!r} does not match frozen "
                f"manifest SHA {firm.repository_head!r}"))
        if not provenance.get("techdd_commit"):
            findings.append(ValidationFinding("IDENTITY WARNING", label, "missing producing TechDD commit"))
        recorded_bot_filter = provenance.get("extra", {}).get("bot_filter_hash")
        expected_bot_filter = bot_filter_hash()
        if recorded_bot_filter != expected_bot_filter:
            findings.append(ValidationFinding(
                "IDENTITY WARNING", label,
                f"metrics bot-filter hash {recorded_bot_filter!r} does not match "
                f"expected {expected_bot_filter!r}"))
        if isinstance(firm.sample_end, date):
            expected_grid = [
                quarter_end.isoformat() for quarter_end in fiscal_quarter_ends(
                    firm.fiscal_year_end_month, firm.listing_start, firm.sample_end)
            ]
            provenance_grid = provenance.get("extra", {}).get("quarter_ends")
            try:
                artifact_grid = json.loads(artifact.read_text(encoding="utf-8")).get(
                    "quarter_ends")
            except (json.JSONDecodeError, OSError, AttributeError):
                artifact_grid = None
            for source_name, recorded_grid in (
                ("artifact", artifact_grid), ("provenance", provenance_grid)
            ):
                if recorded_grid != expected_grid:
                    findings.append(ValidationFinding(
                        "COVERAGE WARNING", label,
                        f"metrics {source_name} quarter grid does not match frozen grid "
                        f"through {firm.sample_end}"))
    return findings


def validate_runtime_artifacts(manifest: DataManifest, root: Path) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if manifest.debt_evidence_artifact is not None:
        ledger_path = root / manifest.debt_evidence_artifact
        label = manifest.debt_evidence_artifact.as_posix()
        if not ledger_path.is_file():
            findings.append(ValidationFinding("MISSING", label, "required debt evidence ledger"))
        else:
            actual_hash = sha256_file(ledger_path)
            if actual_hash != manifest.debt_evidence_sha256:
                findings.append(ValidationFinding(
                    "HASH MISMATCH", label,
                    f"recorded={manifest.debt_evidence_sha256!r} actual={actual_hash}"))
            else:
                findings.append(ValidationFinding("AVAILABLE", label, actual_hash))
            identities = {firm.slug: firm.cik for firm in manifest.firms}
            candidate_path = root / "panel/candidate_universe.csv"
            try:
                from git_due_diligence.panel.debt_evidence import (
                    DEBT_EVIDENCE_SCHEMA_VERSION,
                    load_debt_evidence,
                    load_firm_identities,
                    merge_firm_identities,
                )
                if manifest.debt_evidence_schema_version != DEBT_EVIDENCE_SCHEMA_VERSION:
                    raise ValueError(
                        "manifest debt evidence schema version does not match runtime schema")
                if candidate_path.is_file():
                    identities = merge_firm_identities(
                        {firm.slug: firm.cik for firm in manifest.firms},
                        load_firm_identities(candidate_path),
                    )
                load_debt_evidence(ledger_path, identities)
            except (OSError, ValueError) as exc:
                findings.append(ValidationFinding("IDENTITY WARNING", label, str(exc)))
    for firm in manifest.firms:
        findings.extend(_validate_artifact(
            root, firm, "fundamentals", firm.fundamentals_artifact))
        findings.extend(_validate_artifact(root, firm, "metrics", firm.metrics_artifact))
        findings.extend(_validate_artifact(root, firm, "prices", firm.price_artifact))
        if isinstance(firm.sample_end, str):
            findings.append(ValidationFinding(
                "COVERAGE WARNING", firm.slug,
                f"sample end is explicitly unresolved: {firm.sample_end}"))
        if isinstance(firm.price_coverage_end, str):
            findings.append(ValidationFinding(
                "COVERAGE WARNING", firm.price_artifact.as_posix(),
                f"price coverage end is explicitly unresolved: {firm.price_coverage_end}"))
    return findings


def validation_succeeds(findings: list[ValidationFinding]) -> bool:
    return not any(f.status in {"MISSING", "HASH MISMATCH", "IDENTITY WARNING",
                               "COVERAGE WARNING"}
                   for f in findings)


def _git_output(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def recover_repository_metrics(
    firms: tuple[ManifestFirm, ...],
    *,
    work_dir: Path,
    artifact_root: Path,
    techdd_commit: str,
    build_end: date,
    clone: Callable[[str, Path], None] | None = None,
    compute: Callable = load_or_compute_metrics,
) -> list[dict]:
    """Clone, compute, record, and remove one repository at a time.

    The clone is removed in a ``finally`` block before the next firm starts, so
    disk usage is bounded by one source history plus compact cache artifacts.
    """
    mismatched_cutoffs = [
        firm.slug for firm in firms
        if isinstance(firm.sample_end, date) and firm.sample_end != build_end
    ]
    if mismatched_cutoffs:
        raise ValueError(
            f"build end {build_end} does not match frozen manifest sample_end for: "
            f"{', '.join(mismatched_cutoffs)}")
    work_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    def default_clone(url: str, destination: Path) -> None:
        subprocess.run(["git", "clone", url, str(destination)], check=True)

    clone_repo = clone or default_clone
    for firm in firms:
        repo_path = work_dir / firm.slug
        if repo_path.exists():
            raise FileExistsError(f"recovery work path already exists: {repo_path}")
        try:
            clone_repo(firm.repository_url, repo_path)
            requested_head = firm.repository_head
            if _COMMIT_SHA.fullmatch(requested_head):
                # A frozen build must never drift to the remote's current default HEAD.
                subprocess.run(
                    ["git", "checkout", "--detach", requested_head], cwd=repo_path,
                    check=True, capture_output=True, text=True,
                )
            elif not requested_head.startswith("unavailable_"):
                raise ValueError(
                    f"{firm.slug}: repository_head must be a full commit SHA or "
                    "an unresolved unavailable_* sentinel")
            head = _git_output(["git", "rev-parse", "HEAD"], cwd=repo_path)
            if _COMMIT_SHA.fullmatch(requested_head) and head != requested_head:
                raise RuntimeError(
                    f"{firm.slug}: checked-out HEAD {head} does not equal requested "
                    f"manifest SHA {requested_head}")
            quarter_ends = fiscal_quarter_ends(
                firm.fiscal_year_end_month,
                firm.listing_start,
                build_end,
            )
            compute(firm.slug, repo_path, quarter_ends,
                    artifact_root / firm.metrics_artifact.parent)
            artifact = artifact_root / firm.metrics_artifact
            write_provenance(
                artifact,
                artifact_type="repo_quarter_metrics",
                identity=firm.slug,
                source=firm.repository_url,
                retrieved_or_built_at=datetime.now(timezone.utc),
                techdd_commit=techdd_commit,
                source_repository_head=head,
                data_schema_version=METRIC_SCHEMA_VERSION,
                extra={
                    "bot_filter_hash": bot_filter_hash(),
                    "quarter_ends": [q.isoformat() for q in quarter_ends],
                },
            )
            results.append({"slug": firm.slug, "head": head, "artifact": str(artifact)})
        finally:
            shutil.rmtree(repo_path, ignore_errors=True)
    return results

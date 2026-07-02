# AcquireScope Financial Bridge Implementation Plan (Phase 2 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working `acquirescope model <repo> --assumptions <toml>` command that prices Phase 1's DD findings as explicit line items, computes a comps + scenario-DCF valuation, and writes a five-sheet Excel model whose headline is a pre- vs post-diligence sensitivity table.

**Architecture:** A `bridge/` package with three pure layers — `assumptions.py` (validated analyst inputs from TOML), `valuation.py` (comps, DCF, sensitivity math), `adjustments.py` (ModuleResults → priced line items) — plus `excel.py` (openpyxl workbook writer with live roll-up formulas) and a new Typer command that runs the Phase 1 engine modules in-process. Python computation is the source of truth; key Excel cells carry formulas for auditability.

**Tech Stack:** Python 3.12, openpyxl (new dependency), tomllib (stdlib), existing Phase 1 engine (`RepoIngest`, `MODULES`, models), pytest.

**Spec:** `docs/superpowers/specs/2026-07-01-acquirescope-phase2-financial-bridge-design.md`

## Global Constraints

- Python 3.12; source under `src/acquirescope/`, tests under `tests/`.
- Every quantified estimate carries a low/mid/high band — no naked point estimates.
- Adjustments are stored as **positive costs** and subtracted from EV everywhere applied.
- Engine module failure degrades gracefully: line item "Not assessed", workbook still written, exit 0. Invalid assumptions fail fast: exit 1, nothing written.
- No network calls. All textual I/O `encoding="utf-8"` (TOML is opened in binary for tomllib).
- USD amounts rounded to whole dollars (`round()`).

## File Structure

```
pyproject.toml                          # modify: add openpyxl
examples/assumptions.example.toml       # analyst input template, used by e2e test
src/acquirescope/bridge/__init__.py
src/acquirescope/bridge/assumptions.py  # Assumptions, CompCompany, load_assumptions()
src/acquirescope/bridge/valuation.py    # Valuation, DcfScenario, SensitivityGrid + math
src/acquirescope/bridge/adjustments.py  # Adjustment, price_adjustments()
src/acquirescope/excel.py               # write_model()
src/acquirescope/report.py              # modify: rename _DISCLAIMER -> DISCLAIMER
src/acquirescope/cli.py                 # modify: extract run_modules(), add model command
tests/test_assumptions.py
tests/test_valuation.py
tests/test_adjustments.py
tests/test_excel.py
tests/test_cli.py                       # modify: model command tests + e2e gate
```

---

### Task 1: Assumptions loader + example file

**Files:**
- Modify: `pyproject.toml` (add openpyxl dependency)
- Create: `src/acquirescope/bridge/__init__.py` (empty)
- Create: `src/acquirescope/bridge/assumptions.py`
- Create: `examples/assumptions.example.toml`
- Test: `tests/test_assumptions.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `CompCompany(name: str, ev_revenue_multiple: float)`; `Assumptions` frozen dataclass with fields `target_name: str`, `revenue_low/mid/high: int`, `revenue_source: str`, `comps: list[CompCompany]`, `comps_source: str`, `dcf_years: int`, `growth_bear/growth_base/growth_bull/operating_margin/discount_rate/terminal_growth: float`, `engineer_month_usd/retention_package_usd/integration_cost_usd: float`, `license_discount_per_finding/license_discount_cap: float`; `load_assumptions(path: Path) -> Assumptions` raising `ValueError` with the offending key on any invalid input. All importable from `acquirescope.bridge.assumptions`.

- [ ] **Step 1: Add openpyxl to `pyproject.toml` and install**

In `pyproject.toml`, change the dependencies list to:

```toml
dependencies = [
    "typer>=0.12",
    "lizard>=1.17",
    "openpyxl>=3.1",
]
```

Run: `pip install -e ".[dev]"` (in the activated venv, or `.venv\Scripts\python.exe -m pip install -e ".[dev]"`)
Expected: `Successfully installed ... openpyxl-3.x`

- [ ] **Step 2: Create `examples/assumptions.example.toml`**

```toml
# AcquireScope analyst assumptions — every number needs a stated source.
# This example is calibrated for demonstration against the test fixture repo.

[target]
name = "target-repo"

[revenue]                # annual revenue estimate, USD — analyst-researched
low = 8_000_000
mid = 12_000_000
high = 18_000_000
source = "stated ARR press release 2026-03; pricing-page x headcount cross-check"

[comps]                  # public OSS/devtools comparables
companies = [
    { name = "Confluent", ev_revenue_multiple = 5.0 },
    { name = "HashiCorp", ev_revenue_multiple = 6.2 },
    { name = "GitLab", ev_revenue_multiple = 8.5 },
]
source = "public filings as of 2026-06"

[dcf]
years = 5
growth_bear = 0.10
growth_base = 0.25
growth_bull = 0.40
operating_margin = 0.15  # steady-state
discount_rate = 0.18     # private-company WACC proxy
terminal_growth = 0.03

[costs]
engineer_month_usd = 20_000       # loaded cost, prices remediation capex
retention_package_usd = 300_000   # per flagged key person
integration_cost_usd = 500_000    # flat integration estimate
license_discount_per_finding = 0.02   # fraction of pre-DD EV per copyleft finding
license_discount_cap = 0.10           # total license discount ceiling
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_assumptions.py`:

```python
from pathlib import Path

import pytest

from acquirescope.bridge.assumptions import load_assumptions

EXAMPLE = Path(__file__).parent.parent / "examples" / "assumptions.example.toml"


def _write(tmp_path, text):
    p = tmp_path / "a.toml"
    p.write_text(text, encoding="utf-8")
    return p

GOOD = EXAMPLE.read_text(encoding="utf-8")


def test_loads_example_file():
    a = load_assumptions(EXAMPLE)
    assert a.target_name == "target-repo"
    assert a.revenue_low == 8_000_000
    assert a.revenue_mid == 12_000_000
    assert a.revenue_high == 18_000_000
    assert len(a.comps) == 3
    assert a.comps[2].name == "GitLab"
    assert a.comps[2].ev_revenue_multiple == 8.5
    assert a.dcf_years == 5
    assert a.discount_rate == 0.18
    assert a.engineer_month_usd == 20_000
    assert "press release" in a.revenue_source


def test_missing_section_rejected(tmp_path):
    bad = GOOD.replace("[costs]", "[nocosts]")
    with pytest.raises(ValueError, match=r"\[costs\]"):
        load_assumptions(_write(tmp_path, bad))


def test_revenue_ordering_rejected(tmp_path):
    bad = GOOD.replace("mid = 12_000_000", "mid = 99_000_000")
    with pytest.raises(ValueError, match="low <= mid <= high"):
        load_assumptions(_write(tmp_path, bad))


def test_empty_comps_rejected(tmp_path):
    import re
    bad = re.sub(r"companies = \[.*?\]\n", "companies = []\n", GOOD, flags=re.S)
    with pytest.raises(ValueError, match="companies"):
        load_assumptions(_write(tmp_path, bad))


def test_rate_out_of_range_rejected(tmp_path):
    bad = GOOD.replace("discount_rate = 0.18", "discount_rate = 1.5")
    with pytest.raises(ValueError, match="discount_rate"):
        load_assumptions(_write(tmp_path, bad))


def test_terminal_growth_must_be_below_discount_rate(tmp_path):
    bad = GOOD.replace("terminal_growth = 0.03", "terminal_growth = 0.30")
    with pytest.raises(ValueError, match="terminal_growth"):
        load_assumptions(_write(tmp_path, bad))
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_assumptions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acquirescope.bridge'`

- [ ] **Step 5: Write the implementation**

Create empty `src/acquirescope/bridge/__init__.py`, then `src/acquirescope/bridge/assumptions.py`:

```python
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CompCompany:
    name: str
    ev_revenue_multiple: float


@dataclass(frozen=True)
class Assumptions:
    target_name: str
    revenue_low: int
    revenue_mid: int
    revenue_high: int
    revenue_source: str
    comps: list[CompCompany]
    comps_source: str
    dcf_years: int
    growth_bear: float
    growth_base: float
    growth_bull: float
    operating_margin: float
    discount_rate: float
    terminal_growth: float
    engineer_month_usd: float
    retention_package_usd: float
    integration_cost_usd: float
    license_discount_per_finding: float
    license_discount_cap: float


def _section(data: dict, name: str) -> dict:
    if name not in data:
        raise ValueError(f"assumptions file missing [{name}] section")
    return data[name]


def _require(section: dict, section_name: str, key: str):
    if key not in section:
        raise ValueError(f"assumptions file missing '{key}' in [{section_name}]")
    return section[key]


def _rate(section: dict, section_name: str, key: str) -> float:
    value = float(_require(section, section_name, key))
    if not 0 < value < 1:
        raise ValueError(
            f"'{key}' in [{section_name}] must be between 0 and 1 exclusive, got {value}"
        )
    return value


def _positive(section: dict, section_name: str, key: str) -> float:
    value = float(_require(section, section_name, key))
    if value <= 0:
        raise ValueError(f"'{key}' in [{section_name}] must be positive, got {value}")
    return value


def load_assumptions(path: Path) -> Assumptions:
    with open(path, "rb") as fh:
        data = tomllib.load(fh)

    target = _section(data, "target")
    revenue = _section(data, "revenue")
    comps_sec = _section(data, "comps")
    dcf = _section(data, "dcf")
    costs = _section(data, "costs")

    low = _positive(revenue, "revenue", "low")
    mid = _positive(revenue, "revenue", "mid")
    high = _positive(revenue, "revenue", "high")
    if not low <= mid <= high:
        raise ValueError(f"revenue must satisfy low <= mid <= high, got {low} / {mid} / {high}")

    raw_comps = _require(comps_sec, "comps", "companies")
    if not raw_comps:
        raise ValueError("'companies' in [comps] must not be empty")
    comps = [CompCompany(str(c["name"]), float(c["ev_revenue_multiple"])) for c in raw_comps]
    for comp in comps:
        if comp.ev_revenue_multiple <= 0:
            raise ValueError(f"comp '{comp.name}' ev_revenue_multiple must be positive")

    discount_rate = _rate(dcf, "dcf", "discount_rate")
    terminal_growth = _rate(dcf, "dcf", "terminal_growth")
    if terminal_growth >= discount_rate:
        raise ValueError(
            f"'terminal_growth' must be below discount_rate, got {terminal_growth} >= {discount_rate}"
        )

    return Assumptions(
        target_name=str(_require(target, "target", "name")),
        revenue_low=round(low),
        revenue_mid=round(mid),
        revenue_high=round(high),
        revenue_source=str(_require(revenue, "revenue", "source")),
        comps=comps,
        comps_source=str(_require(comps_sec, "comps", "source")),
        dcf_years=int(_positive(dcf, "dcf", "years")),
        growth_bear=_rate(dcf, "dcf", "growth_bear"),
        growth_base=_rate(dcf, "dcf", "growth_base"),
        growth_bull=_rate(dcf, "dcf", "growth_bull"),
        operating_margin=_rate(dcf, "dcf", "operating_margin"),
        discount_rate=discount_rate,
        terminal_growth=terminal_growth,
        engineer_month_usd=_positive(costs, "costs", "engineer_month_usd"),
        retention_package_usd=_positive(costs, "costs", "retention_package_usd"),
        integration_cost_usd=_positive(costs, "costs", "integration_cost_usd"),
        license_discount_per_finding=_rate(costs, "costs", "license_discount_per_finding"),
        license_discount_cap=_rate(costs, "costs", "license_discount_cap"),
    )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_assumptions.py -v`
Expected: 6 passed

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml examples/assumptions.example.toml src/acquirescope/bridge/__init__.py src/acquirescope/bridge/assumptions.py tests/test_assumptions.py
git commit -m "feat: add validated analyst assumptions loader for financial bridge"
```

---

### Task 2: Valuation math — comps, DCF, blend, sensitivity

**Files:**
- Create: `src/acquirescope/bridge/valuation.py`
- Test: `tests/test_valuation.py`

**Interfaces:**
- Consumes: `Assumptions`, `CompCompany` (Task 1).
- Produces (from `acquirescope.bridge.valuation`): `Valuation(method: str, low: int, mid: int, high: int)`; `YearRow(year: int, revenue: int, fcf: int, pv: int)`; `DcfScenario(name: str, growth: float, years: list[YearRow], terminal_pv: int, ev: int)`; `SensitivityGrid(multiples: list[float], revenues: list[int], pre_dd: list[list[int]], post_dd: list[list[int]])`; functions `comps_multiples(a) -> tuple[float, float, float]` (min, median, max), `comps_valuation(a) -> Valuation`, `dcf_scenarios(a) -> list[DcfScenario]` (bear, base, bull), `dcf_valuation(a) -> Valuation`, `blended_pre_dd_ev_mid(comps: Valuation, dcf: Valuation) -> int`, `sensitivity_grid(a, total_adjustment_mid: int) -> SensitivityGrid`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_valuation.py` (numbers hand-computed: with revenue mid 2,000,000, 1 year at 50% growth, 20% margin, 25% discount, 5% terminal growth → year-1 revenue 3,000,000, FCF 600,000, PV 480,000; terminal = 600,000 × 1.05 / 0.20 = 3,150,000, PV 2,520,000; EV = 3,000,000):

```python
from acquirescope.bridge.assumptions import Assumptions, CompCompany
from acquirescope.bridge.valuation import (
    blended_pre_dd_ev_mid,
    comps_valuation,
    dcf_scenarios,
    dcf_valuation,
    sensitivity_grid,
)


def _assumptions() -> Assumptions:
    return Assumptions(
        target_name="t",
        revenue_low=1_000_000, revenue_mid=2_000_000, revenue_high=3_000_000,
        revenue_source="test",
        comps=[
            CompCompany("A", 4.0), CompCompany("B", 6.0), CompCompany("C", 8.0),
        ],
        comps_source="test",
        dcf_years=1,
        growth_bear=0.25, growth_base=0.50, growth_bull=0.75,
        operating_margin=0.20, discount_rate=0.25, terminal_growth=0.05,
        engineer_month_usd=20_000, retention_package_usd=300_000,
        integration_cost_usd=500_000,
        license_discount_per_finding=0.02, license_discount_cap=0.10,
    )


def test_comps_valuation_uses_median_multiple():
    v = comps_valuation(_assumptions())
    assert (v.low, v.mid, v.high) == (6_000_000, 12_000_000, 18_000_000)
    assert v.method == "comps"


def test_dcf_valuation_hand_computed():
    v = dcf_valuation(_assumptions())
    assert (v.low, v.mid, v.high) == (2_500_000, 3_000_000, 3_500_000)


def test_dcf_scenario_detail():
    bear, base, bull = dcf_scenarios(_assumptions())
    assert base.name == "base"
    assert base.years[0].revenue == 3_000_000
    assert base.years[0].fcf == 600_000
    assert base.years[0].pv == 480_000
    assert base.terminal_pv == 2_520_000
    assert base.ev == 3_000_000
    assert bear.ev < base.ev < bull.ev


def test_blend_is_mean_of_mids():
    a = _assumptions()
    assert blended_pre_dd_ev_mid(comps_valuation(a), dcf_valuation(a)) == 7_500_000


def test_sensitivity_grid_shape_and_post_dd():
    grid = sensitivity_grid(_assumptions(), total_adjustment_mid=1_000_000)
    assert grid.multiples == [4.0, 6.0, 8.0]
    assert grid.revenues == [1_000_000, 2_000_000, 3_000_000]
    assert grid.pre_dd[1][1] == 12_000_000            # median multiple x mid revenue
    assert grid.post_dd[1][1] == 11_000_000           # pre minus adjustments
    assert all(len(row) == 3 for row in grid.pre_dd)
    assert len(grid.pre_dd) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_valuation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acquirescope.bridge.valuation'`

- [ ] **Step 3: Write the implementation**

Create `src/acquirescope/bridge/valuation.py`:

```python
from __future__ import annotations

import statistics
from dataclasses import dataclass

from acquirescope.bridge.assumptions import Assumptions


@dataclass(frozen=True)
class Valuation:
    method: str
    low: int
    mid: int
    high: int


@dataclass(frozen=True)
class YearRow:
    year: int
    revenue: int
    fcf: int
    pv: int


@dataclass(frozen=True)
class DcfScenario:
    name: str
    growth: float
    years: list[YearRow]
    terminal_pv: int
    ev: int


@dataclass(frozen=True)
class SensitivityGrid:
    multiples: list[float]   # rows: min, median, max comp multiple
    revenues: list[int]      # columns: low, mid, high revenue
    pre_dd: list[list[int]]
    post_dd: list[list[int]]


def comps_multiples(a: Assumptions) -> tuple[float, float, float]:
    values = [c.ev_revenue_multiple for c in a.comps]
    return min(values), statistics.median(values), max(values)


def comps_valuation(a: Assumptions) -> Valuation:
    _, median_multiple, _ = comps_multiples(a)
    return Valuation(
        "comps",
        round(a.revenue_low * median_multiple),
        round(a.revenue_mid * median_multiple),
        round(a.revenue_high * median_multiple),
    )


def _scenario(a: Assumptions, name: str, growth: float) -> DcfScenario:
    years: list[YearRow] = []
    revenue = float(a.revenue_mid)
    fcf = 0.0
    ev = 0.0
    for year in range(1, a.dcf_years + 1):
        revenue *= 1 + growth
        fcf = revenue * a.operating_margin
        pv = fcf / (1 + a.discount_rate) ** year
        ev += pv
        years.append(YearRow(year, round(revenue), round(fcf), round(pv)))
    # Gordon terminal value on the final year's FCF, discounted back.
    terminal = fcf * (1 + a.terminal_growth) / (a.discount_rate - a.terminal_growth)
    terminal_pv = terminal / (1 + a.discount_rate) ** a.dcf_years
    ev += terminal_pv
    return DcfScenario(name, growth, years, round(terminal_pv), round(ev))


def dcf_scenarios(a: Assumptions) -> list[DcfScenario]:
    return [
        _scenario(a, "bear", a.growth_bear),
        _scenario(a, "base", a.growth_base),
        _scenario(a, "bull", a.growth_bull),
    ]


def dcf_valuation(a: Assumptions) -> Valuation:
    bear, base, bull = dcf_scenarios(a)
    return Valuation("dcf", bear.ev, base.ev, bull.ev)


def blended_pre_dd_ev_mid(comps: Valuation, dcf: Valuation) -> int:
    """Documented blend: simple mean of the comps and DCF mid estimates."""
    return round((comps.mid + dcf.mid) / 2)


def sensitivity_grid(a: Assumptions, total_adjustment_mid: int) -> SensitivityGrid:
    lo, med, hi = comps_multiples(a)
    multiples = [lo, med, hi]
    revenues = [a.revenue_low, a.revenue_mid, a.revenue_high]
    pre = [[round(m * r) for r in revenues] for m in multiples]
    post = [[cell - total_adjustment_mid for cell in row] for row in pre]
    return SensitivityGrid(multiples, revenues, pre, post)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_valuation.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/bridge/valuation.py tests/test_valuation.py
git commit -m "feat: add comps, scenario-DCF, and sensitivity valuation math"
```

---

### Task 3: Adjustment pricing — DD findings to dollars

**Files:**
- Create: `src/acquirescope/bridge/adjustments.py`
- Test: `tests/test_adjustments.py`

**Interfaces:**
- Consumes: `Assumptions` (Task 1), `ModuleResult`/`Finding`/`Severity` (Phase 1 `acquirescope.models`).
- Produces (from `acquirescope.bridge.adjustments`): `Adjustment(name: str, low: int, mid: int, high: int, basis: str, evidence: list[str], assessed: bool = True)`; `price_adjustments(results: list[ModuleResult], assumptions: Assumptions, pre_dd_ev_mid: int) -> list[Adjustment]` returning exactly 5 line items in order: Remediation capex, Key-person retention, License-risk discount, Integration cost, Security remediation. Amounts are positive costs.

- [ ] **Step 1: Write the failing test**

Create `tests/test_adjustments.py`:

```python
from acquirescope.bridge.adjustments import price_adjustments
from acquirescope.bridge.assumptions import Assumptions, CompCompany
from acquirescope.models import Evidence, Finding, ModuleResult, Severity


def _assumptions() -> Assumptions:
    return Assumptions(
        target_name="t",
        revenue_low=1_000_000, revenue_mid=2_000_000, revenue_high=3_000_000,
        revenue_source="test",
        comps=[CompCompany("A", 6.0)],
        comps_source="test",
        dcf_years=1,
        growth_bear=0.25, growth_base=0.50, growth_bull=0.75,
        operating_margin=0.20, discount_rate=0.25, terminal_growth=0.05,
        engineer_month_usd=20_000, retention_package_usd=300_000,
        integration_cost_usd=500_000,
        license_discount_per_finding=0.02, license_discount_cap=0.10,
    )


def _results() -> list[ModuleResult]:
    return [
        ModuleResult(
            module="bus_factor", status="ok",
            findings=[
                Finding("bus_factor", "Single point of failure: payments/",
                        Severity.HIGH, "s"),
                Finding("bus_factor", "Departed key contributor: dave@example.com",
                        Severity.HIGH, "s"),
            ],
        ),
        ModuleResult(
            module="licenses", status="ok",
            findings=[Finding("licenses", "Copyleft dependency: mysqlclient",
                              Severity.HIGH, "s")],
            metrics={"copyleft_dependency_count": 1},
        ),
        ModuleResult(
            module="hotspots", status="ok",
            metrics={"remediation_months_low": 1.0, "remediation_months_mid": 2.0,
                     "remediation_months_high": 3.0, "hotspot_count": 1},
        ),
    ]


def test_five_line_items_in_order():
    adjustments = price_adjustments(_results(), _assumptions(), pre_dd_ev_mid=10_000_000)
    assert [a.name for a in adjustments] == [
        "Remediation capex", "Key-person retention", "License-risk discount",
        "Integration cost", "Security remediation",
    ]


def test_remediation_uses_module_band():
    remediation = price_adjustments(_results(), _assumptions(), 10_000_000)[0]
    assert (remediation.low, remediation.mid, remediation.high) == (20_000, 40_000, 60_000)
    assert remediation.assessed


def test_retention_counts_findings():
    retention = price_adjustments(_results(), _assumptions(), 10_000_000)[1]
    assert retention.mid == 600_000          # 2 findings x 300k
    assert retention.low == 300_000
    assert retention.high == 900_000
    assert "dave@example.com" in "; ".join(retention.evidence)


def test_license_discount_fraction_of_ev_with_cap():
    license_adj = price_adjustments(_results(), _assumptions(), 10_000_000)[2]
    assert license_adj.mid == 200_000        # min(1 x 2%, 10%) x 10M
    results = _results()
    results[1].metrics["copyleft_dependency_count"] = 99
    capped = price_adjustments(results, _assumptions(), 10_000_000)[2]
    assert capped.mid == 1_000_000           # capped at 10% x 10M


def test_failed_module_prices_as_not_assessed():
    results = [r for r in _results() if r.module != "hotspots"]
    results.append(ModuleResult(module="hotspots", status="failed", error="boom"))
    remediation = price_adjustments(results, _assumptions(), 10_000_000)[0]
    assert not remediation.assessed
    assert (remediation.low, remediation.mid, remediation.high) == (0, 0, 0)
    assert "Not assessed" in remediation.basis


def test_security_always_not_assessed_in_phase2():
    security = price_adjustments(_results(), _assumptions(), 10_000_000)[4]
    assert not security.assessed
    assert security.mid == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_adjustments.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acquirescope.bridge.adjustments'`

- [ ] **Step 3: Write the implementation**

Create `src/acquirescope/bridge/adjustments.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from acquirescope.bridge.assumptions import Assumptions
from acquirescope.models import ModuleResult, Severity

BAND = 0.5  # +/-50% band where the source module provides no band of its own


@dataclass(frozen=True)
class Adjustment:
    name: str
    low: int
    mid: int
    high: int
    basis: str
    evidence: list[str] = field(default_factory=list)
    assessed: bool = True


def _banded(mid: float) -> tuple[int, int, int]:
    return round(mid * (1 - BAND)), round(mid), round(mid * (1 + BAND))


def _not_assessed(name: str, reason: str) -> Adjustment:
    return Adjustment(name, 0, 0, 0, f"Not assessed — {reason}", [], False)


def price_adjustments(
    results: list[ModuleResult], assumptions: Assumptions, pre_dd_ev_mid: int
) -> list[Adjustment]:
    by_module = {r.module: r for r in results if r.status == "ok"}
    adjustments: list[Adjustment] = []

    # 1. Remediation capex — the hotspot module already carries its own band.
    hotspots = by_module.get("hotspots")
    if hotspots is None:
        adjustments.append(_not_assessed("Remediation capex", "hotspots module failed or missing"))
    else:
        cost = assumptions.engineer_month_usd
        adjustments.append(Adjustment(
            "Remediation capex",
            round(hotspots.metrics["remediation_months_low"] * cost),
            round(hotspots.metrics["remediation_months_mid"] * cost),
            round(hotspots.metrics["remediation_months_high"] * cost),
            f"remediation engineer-months x ${cost:,.0f}/month loaded cost",
            [f.title for f in hotspots.findings],
        ))

    # 2. Key-person retention — one package per flagged key-person risk.
    bus = by_module.get("bus_factor")
    if bus is None:
        adjustments.append(_not_assessed("Key-person retention", "bus_factor module failed or missing"))
    else:
        count = len(bus.findings)
        low, mid, high = _banded(count * assumptions.retention_package_usd)
        adjustments.append(Adjustment(
            "Key-person retention", low, mid, high,
            f"{count} flagged key-person risk(s) x ${assumptions.retention_package_usd:,.0f} "
            f"retention package, +/-50%",
            [f.title for f in bus.findings],
        ))

    # 3. License-risk discount — fraction of pre-DD EV, capped.
    lic = by_module.get("licenses")
    if lic is None:
        adjustments.append(_not_assessed("License-risk discount", "licenses module failed or missing"))
    else:
        count = lic.metrics["copyleft_dependency_count"]
        fraction = min(count * assumptions.license_discount_per_finding,
                       assumptions.license_discount_cap)
        low, mid, high = _banded(fraction * pre_dd_ev_mid)
        adjustments.append(Adjustment(
            "License-risk discount", low, mid, high,
            f"min({count} copyleft finding(s) x {assumptions.license_discount_per_finding:.0%}, "
            f"cap {assumptions.license_discount_cap:.0%}) of pre-DD EV ${pre_dd_ev_mid:,.0f}, +/-50%",
            [f.title for f in lic.findings if f.severity == Severity.HIGH],
        ))

    # 4. Integration cost — assumption-driven, always assessed.
    low, mid, high = _banded(assumptions.integration_cost_usd)
    adjustments.append(Adjustment(
        "Integration cost", low, mid, high,
        "flat integration estimate from assumptions, +/-50%", [],
    ))

    # 5. Security remediation — module ships in Phase 3.
    adjustments.append(_not_assessed("Security remediation", "security module ships in Phase 3"))

    return adjustments
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_adjustments.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/bridge/adjustments.py tests/test_adjustments.py
git commit -m "feat: price DD findings as banded valuation adjustment line items"
```

---

### Task 4: Excel workbook writer

**Files:**
- Modify: `src/acquirescope/report.py` (rename `_DISCLAIMER` to `DISCLAIMER`)
- Create: `src/acquirescope/excel.py`
- Test: `tests/test_excel.py`

**Interfaces:**
- Consumes: `Assumptions` (Task 1); `Valuation`, `DcfScenario`, `SensitivityGrid` (Task 2); `Adjustment` (Task 3); `DISCLAIMER` from `acquirescope.report`.
- Produces: `write_model(path: Path, assumptions: Assumptions, adjustments: list[Adjustment], comps: Valuation, dcf: Valuation, scenarios: list[DcfScenario], grid: SensitivityGrid) -> None` in `acquirescope.excel`. Sheets, in order: "Assumptions", "Comps", "DCF", "DD Adjustments", "Valuation Summary". Fixed layout (tests depend on it): DD Adjustments has headers in row 1, one row per adjustment from row 2, total row immediately after with `=SUM(...)` formulas. Valuation Summary: methods table rows 3–6 (row 6 blended, `=AVERAGE`), row 8 total adjustments (cross-sheet formulas), row 9 post-DD EV (`=B6-B8` etc.), pre-DD sensitivity header row 12 with grid rows 13–15 (`=$A13*B$12` style formulas), post-DD sensitivity header row 18 with grid rows 19–21 (`=B13-$C$8` style), disclaimer in A23.

- [ ] **Step 1: Rename the disclaimer constant in `report.py`**

In `src/acquirescope/report.py`, rename `_DISCLAIMER` to `DISCLAIMER` (both the definition and its use inside `render_markdown`). No other change.

Run: `pytest tests/test_report.py -v`
Expected: 3 passed (rename is internal; tests assert rendered text only)

- [ ] **Step 2: Write the failing test**

Create `tests/test_excel.py`:

```python
from pathlib import Path

from openpyxl import load_workbook

from acquirescope.bridge.adjustments import Adjustment
from acquirescope.bridge.assumptions import Assumptions, CompCompany
from acquirescope.bridge.valuation import (
    blended_pre_dd_ev_mid,
    comps_valuation,
    dcf_scenarios,
    dcf_valuation,
    sensitivity_grid,
)
from acquirescope.excel import write_model


def _assumptions() -> Assumptions:
    return Assumptions(
        target_name="t",
        revenue_low=1_000_000, revenue_mid=2_000_000, revenue_high=3_000_000,
        revenue_source="press release",
        comps=[CompCompany("A", 4.0), CompCompany("B", 6.0), CompCompany("C", 8.0)],
        comps_source="filings",
        dcf_years=1,
        growth_bear=0.25, growth_base=0.50, growth_bull=0.75,
        operating_margin=0.20, discount_rate=0.25, terminal_growth=0.05,
        engineer_month_usd=20_000, retention_package_usd=300_000,
        integration_cost_usd=500_000,
        license_discount_per_finding=0.02, license_discount_cap=0.10,
    )


def _adjustments() -> list[Adjustment]:
    return [
        Adjustment("Remediation capex", 20_000, 40_000, 60_000, "months x cost", ["hotspot: core/engine.py"]),
        Adjustment("Key-person retention", 300_000, 600_000, 900_000, "2 x package", ["dave"]),
        Adjustment("License-risk discount", 75_000, 150_000, 225_000, "2% of EV", ["mysqlclient"]),
        Adjustment("Integration cost", 250_000, 500_000, 750_000, "flat", []),
        Adjustment("Security remediation", 0, 0, 0, "Not assessed — security module ships in Phase 3", [], False),
    ]


def _write(tmp_path) -> Path:
    a = _assumptions()
    comps, dcf = comps_valuation(a), dcf_valuation(a)
    total_mid = sum(adj.mid for adj in _adjustments())
    path = tmp_path / "model.xlsx"
    write_model(path, a, _adjustments(), comps, dcf, dcf_scenarios(a),
                sensitivity_grid(a, total_mid))
    return path


def test_workbook_has_five_sheets_in_order(tmp_path):
    wb = load_workbook(_write(tmp_path))
    assert wb.sheetnames == ["Assumptions", "Comps", "DCF", "DD Adjustments", "Valuation Summary"]


def test_adjustments_sheet_rows_and_total_formula(tmp_path):
    ws = load_workbook(_write(tmp_path))["DD Adjustments"]
    assert ws["A2"].value == "Remediation capex"
    assert ws["C3"].value == 600_000
    assert ws["E6"].value == "NOT ASSESSED"
    assert ws["B7"].value == "=SUM(B2:B6)"
    assert ws["A7"].value == "Total"


def test_summary_formulas_and_disclaimer(tmp_path):
    ws = load_workbook(_write(tmp_path))["Valuation Summary"]
    assert ws["B4"].value == 6_000_000            # comps low
    assert ws["C5"].value == 3_000_000            # dcf mid
    assert ws["C6"].value == "=AVERAGE(C4:C5)"
    assert ws["C8"].value == "='DD Adjustments'!C7"
    assert ws["C9"].value == "=C6-C8"
    assert ws["B13"].value == "=$A13*B$12"        # pre-DD sensitivity cell
    assert ws["B19"].value == "=B13-$C$8"         # post-DD sensitivity cell
    assert "educational analysis" in ws["A23"].value.lower()


def test_assumptions_sheet_carries_sources(tmp_path):
    ws = load_workbook(_write(tmp_path))["Assumptions"]
    values = [ws.cell(row=r, column=3).value for r in range(1, 25)]
    assert "press release" in [v for v in values if v]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_excel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acquirescope.excel'`

- [ ] **Step 4: Write the implementation**

Create `src/acquirescope/excel.py`:

```python
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

from acquirescope.bridge.adjustments import Adjustment
from acquirescope.bridge.assumptions import Assumptions
from acquirescope.bridge.valuation import DcfScenario, SensitivityGrid, Valuation
from acquirescope.report import DISCLAIMER

_BOLD = Font(bold=True)


def _rows(ws: Worksheet, start_row: int, rows: list[list]) -> int:
    """Write rows starting at start_row; returns the next free row."""
    for r, row in enumerate(rows, start=start_row):
        for c, value in enumerate(row, start=1):
            ws.cell(row=r, column=c, value=value)
    return start_row + len(rows)


def _sheet_assumptions(ws: Worksheet, a: Assumptions) -> None:
    ws["A1"] = f"Assumptions: {a.target_name}"
    ws["A1"].font = _BOLD
    _rows(ws, 3, [
        ["Input", "Value", "Source"],
        ["Revenue low (USD/yr)", a.revenue_low, a.revenue_source],
        ["Revenue mid (USD/yr)", a.revenue_mid, a.revenue_source],
        ["Revenue high (USD/yr)", a.revenue_high, a.revenue_source],
        ["DCF years", a.dcf_years, ""],
        ["Growth bear", a.growth_bear, ""],
        ["Growth base", a.growth_base, ""],
        ["Growth bull", a.growth_bull, ""],
        ["Operating margin", a.operating_margin, ""],
        ["Discount rate", a.discount_rate, ""],
        ["Terminal growth", a.terminal_growth, ""],
        ["Engineer-month cost (USD)", a.engineer_month_usd, ""],
        ["Retention package (USD)", a.retention_package_usd, ""],
        ["Integration cost (USD)", a.integration_cost_usd, ""],
        ["License discount per finding", a.license_discount_per_finding, ""],
        ["License discount cap", a.license_discount_cap, ""],
    ])


def _sheet_comps(ws: Worksheet, a: Assumptions, comps: Valuation) -> None:
    ws["A1"] = "Comparables"
    ws["A1"].font = _BOLD
    ws["A2"] = f"Source: {a.comps_source}"
    next_row = _rows(ws, 4, [["Company", "EV/Revenue multiple"]]
                     + [[c.name, c.ev_revenue_multiple] for c in a.comps])
    _rows(ws, next_row + 1, [
        ["Implied EV (median multiple)", "Low", "Mid", "High"],
        ["", comps.low, comps.mid, comps.high],
    ])


def _sheet_dcf(ws: Worksheet, scenarios: list[DcfScenario]) -> None:
    ws["A1"] = "DCF — bear / base / bull scenarios"
    ws["A1"].font = _BOLD
    row = 3
    for s in scenarios:
        ws.cell(row=row, column=1, value=f"Scenario: {s.name} (growth {s.growth:.0%})").font = _BOLD
        row = _rows(ws, row + 1, [["Year", "Revenue", "FCF", "PV"]]
                    + [[y.year, y.revenue, y.fcf, y.pv] for y in s.years])
        row = _rows(ws, row, [["Terminal PV", s.terminal_pv], ["Scenario EV", s.ev]])
        row += 1


def _sheet_adjustments(ws: Worksheet, adjustments: list[Adjustment]) -> int:
    """Returns the total row index (Valuation Summary references it)."""
    _rows(ws, 1, [["Line item", "Low (USD)", "Mid (USD)", "High (USD)", "Assessed", "Basis", "Evidence"]])
    _rows(ws, 2, [
        [adj.name, adj.low, adj.mid, adj.high,
         "yes" if adj.assessed else "NOT ASSESSED", adj.basis, "; ".join(adj.evidence)]
        for adj in adjustments
    ])
    total_row = len(adjustments) + 2
    last = total_row - 1
    _rows(ws, total_row, [[
        "Total", f"=SUM(B2:B{last})", f"=SUM(C2:C{last})", f"=SUM(D2:D{last})",
    ]])
    ws.cell(row=total_row, column=1).font = _BOLD
    return total_row


def _sheet_summary(
    ws: Worksheet, a: Assumptions, comps: Valuation, dcf: Valuation,
    grid: SensitivityGrid, adjustments_total_row: int,
) -> None:
    ws["A1"] = f"Valuation Summary: {a.target_name}"
    ws["A1"].font = _BOLD
    t = adjustments_total_row
    _rows(ws, 3, [
        ["Method", "Low", "Mid", "High"],
        ["Comps EV", comps.low, comps.mid, comps.high],
        ["DCF EV", dcf.low, dcf.mid, dcf.high],
        ["Blended pre-DD EV", "=AVERAGE(B4:B5)", "=AVERAGE(C4:C5)", "=AVERAGE(D4:D5)"],
    ])
    _rows(ws, 8, [
        ["Total DD adjustments",
         f"='DD Adjustments'!B{t}", f"='DD Adjustments'!C{t}", f"='DD Adjustments'!D{t}"],
        ["Post-DD EV", "=B6-B8", "=C6-C8", "=D6-D8"],
    ])
    ws["A11"] = "Sensitivity — Pre-DD EV (multiple x revenue)"
    ws["A11"].font = _BOLD
    _rows(ws, 12, [["Multiple \\ Revenue", *grid.revenues]])
    for i, multiple in enumerate(grid.multiples):
        r = 13 + i
        ws.cell(row=r, column=1, value=multiple)
        for c in range(2, 5):
            col = chr(ord("A") + c - 1)
            ws.cell(row=r, column=c, value=f"=$A{r}*{col}$12")
    ws["A17"] = "Sensitivity — Post-DD EV (pre-DD minus mid adjustments)"
    ws["A17"].font = _BOLD
    _rows(ws, 18, [["Multiple \\ Revenue", *grid.revenues]])
    for i, multiple in enumerate(grid.multiples):
        r = 19 + i
        ws.cell(row=r, column=1, value=multiple)
        for c in range(2, 5):
            col = chr(ord("A") + c - 1)
            ws.cell(row=r, column=c, value=f"={col}{13 + i}-$C$8")
    ws["A23"] = DISCLAIMER.strip("*")


def write_model(
    path: Path,
    assumptions: Assumptions,
    adjustments: list[Adjustment],
    comps: Valuation,
    dcf: Valuation,
    scenarios: list[DcfScenario],
    grid: SensitivityGrid,
) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Assumptions"
    _sheet_assumptions(ws, assumptions)
    _sheet_comps(wb.create_sheet("Comps"), assumptions, comps)
    _sheet_dcf(wb.create_sheet("DCF"), scenarios)
    total_row = _sheet_adjustments(wb.create_sheet("DD Adjustments"), adjustments)
    _sheet_summary(wb.create_sheet("Valuation Summary"), assumptions, comps, dcf, grid, total_row)
    wb.save(path)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_excel.py tests/test_report.py -v`
Expected: 7 passed (4 excel + 3 report)

- [ ] **Step 6: Commit**

```bash
git add src/acquirescope/excel.py src/acquirescope/report.py tests/test_excel.py
git commit -m "feat: add five-sheet Excel model writer with auditable roll-up formulas"
```

---

### Task 5: `model` CLI command with shared module runner

**Files:**
- Modify: `src/acquirescope/cli.py`
- Test: `tests/test_cli.py` (append two tests)

**Interfaces:**
- Consumes: everything above.
- Produces: `run_modules(ingest: RepoIngest) -> list[ModuleResult]` in `acquirescope.cli` (extracted from `analyze`, used by both commands); Typer command `model REPO_PATH --assumptions/-a PATH --output/-o PATH` (default `dd-model.xlsx`). Invalid assumptions → message to stderr, exit 1, no file written. Module failures → workbook still written, exit 0.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_model_writes_workbook(fixture_repo, tmp_path):
    from openpyxl import load_workbook

    example = Path(__file__).parent.parent / "examples" / "assumptions.example.toml"
    out = tmp_path / "model.xlsx"
    result = runner.invoke(cli.app, [
        "model", str(fixture_repo), "--assumptions", str(example), "--output", str(out),
    ])
    assert result.exit_code == 0
    wb = load_workbook(out)
    assert "Valuation Summary" in wb.sheetnames


def test_model_invalid_assumptions_exits_1(fixture_repo, tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("[target]\nname = 'x'\n", encoding="utf-8")
    out = tmp_path / "model.xlsx"
    result = runner.invoke(cli.app, [
        "model", str(fixture_repo), "--assumptions", str(bad), "--output", str(out),
    ])
    assert result.exit_code == 1
    assert not out.exists()
```

Note: adding a second Typer command means the existing single-command invocations
in earlier tests must name the command. Update the three existing `runner.invoke`
calls in `tests/test_cli.py` from `[str(fixture_repo), ...]` to
`["analyze", str(fixture_repo), ...]`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: new tests FAIL (`model` command does not exist — Typer exits with usage error, exit code 2)

- [ ] **Step 3: Write the implementation**

Replace `src/acquirescope/cli.py` with:

```python
from __future__ import annotations

from pathlib import Path
from typing import Callable

import typer

from acquirescope.bridge.adjustments import price_adjustments
from acquirescope.bridge.assumptions import load_assumptions
from acquirescope.bridge.valuation import (
    blended_pre_dd_ev_mid,
    comps_valuation,
    dcf_scenarios,
    dcf_valuation,
    sensitivity_grid,
)
from acquirescope.excel import write_model
from acquirescope.ingest import RepoIngest
from acquirescope.models import ModuleResult
from acquirescope.modules import bus_factor, hotspots, licenses
from acquirescope.report import render_markdown

app = typer.Typer(add_completion=False)

MODULES: list[tuple[str, Callable[[RepoIngest], ModuleResult]]] = [
    ("bus_factor", bus_factor.analyze),
    ("licenses", licenses.analyze),
    ("hotspots", hotspots.analyze),
]


def run_modules(ingest: RepoIngest) -> list[ModuleResult]:
    results: list[ModuleResult] = []
    for name, analyze_fn in MODULES:
        try:
            results.append(analyze_fn(ingest))
        except Exception as exc:  # graceful degradation is a spec requirement
            results.append(ModuleResult(module=name, status="failed", error=str(exc)))
    return results


@app.command()
def analyze(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, help="Path to a local git repository"),
    output: Path = typer.Option(Path("dd-report.md"), "--output", "-o", help="Report output path"),
) -> None:
    """Run all due-diligence modules against REPO_PATH and write a markdown report."""
    results = run_modules(RepoIngest(repo_path))
    output.write_text(render_markdown(repo_path.name, results), encoding="utf-8")
    typer.echo(f"Report written to {output}")


@app.command()
def model(
    repo_path: Path = typer.Argument(..., exists=True, file_okay=False, help="Path to a local git repository"),
    assumptions_file: Path = typer.Option(..., "--assumptions", "-a", exists=True, dir_okay=False, help="Analyst assumptions TOML"),
    output: Path = typer.Option(Path("dd-model.xlsx"), "--output", "-o", help="Excel model output path"),
) -> None:
    """Run the engine, price the findings, and write the Excel valuation model."""
    try:
        assumptions = load_assumptions(assumptions_file)
    except ValueError as exc:
        typer.echo(f"Invalid assumptions: {exc}", err=True)
        raise typer.Exit(code=1)

    results = run_modules(RepoIngest(repo_path))
    comps = comps_valuation(assumptions)
    dcf = dcf_valuation(assumptions)
    pre_dd_ev_mid = blended_pre_dd_ev_mid(comps, dcf)
    adjustments = price_adjustments(results, assumptions, pre_dd_ev_mid)
    total_adjustment_mid = sum(adj.mid for adj in adjustments)
    grid = sensitivity_grid(assumptions, total_adjustment_mid)
    write_model(output, assumptions, adjustments, comps, dcf,
                dcf_scenarios(assumptions), grid)
    typer.echo(f"Model written to {output}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli.py -v`
Expected: 5 passed (3 updated analyze tests + 2 new model tests)

- [ ] **Step 5: Commit**

```bash
git add src/acquirescope/cli.py tests/test_cli.py
git commit -m "feat: add model CLI command producing the Excel valuation deliverable"
```

---

### Task 6: End-to-end planted-issue model regression test

**Files:**
- Modify: `tests/test_cli.py` (append one test)

**Interfaces:**
- Consumes: the full Phase 1 + Phase 2 pipeline and the fixture's planted issues.
- Produces: the Phase 2 regression gate — planted issues appear as priced line items and post-DD EV < pre-DD EV.

- [ ] **Step 1: Append the regression test**

Append to `tests/test_cli.py`:

```python
def test_planted_issues_priced_in_model_end_to_end(fixture_repo, tmp_path):
    """Phase 2 regression gate: planted DD issues become priced line items."""
    from openpyxl import load_workbook

    example = Path(__file__).parent.parent / "examples" / "assumptions.example.toml"
    out = tmp_path / "e2e-model.xlsx"
    result = runner.invoke(cli.app, [
        "model", str(fixture_repo), "--assumptions", str(example), "--output", str(out),
    ])
    assert result.exit_code == 0
    wb = load_workbook(out)

    adj = wb["DD Adjustments"]
    # Row order fixed: 2 remediation, 3 retention, 4 license, 5 integration, 6 security
    assert adj["B2"].value > 0                        # remediation capex priced from hotspot
    assert adj["C3"].value == 600_000                 # exactly 2 key-person findings x 300k
    assert adj["C4"].value > 0                        # license discount priced
    assert "mysqlclient" in adj["G4"].value           # evidence reaches the workbook
    assert adj["E6"].value == "NOT ASSESSED"          # security honest about scope

    summary = wb["Valuation Summary"]
    # Formulas are not evaluated by openpyxl; recompute from stored values.
    pre_mid = (summary["C4"].value + summary["C5"].value) / 2
    total_mid = sum(adj.cell(row=r, column=3).value for r in range(2, 7))
    assert total_mid > 0
    assert pre_mid - total_mid < pre_mid              # post-DD EV strictly below pre-DD
```

- [ ] **Step 2: Run the full suite**

Run: `pytest -v`
Expected: ALL tests pass (Phase 1's 20 + 6 assumptions + 5 valuation + 6 adjustments + 4 excel + 3 CLI/e2e = 44 total). If only the e2e fails, a component regressed — its unit tests localize which.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli.py
git commit -m "test: add end-to-end planted-issue pricing regression gate for the model"
```

---

## Self-review notes

- **Spec coverage:** assumptions loader + validation ✓ (Task 1, fail-fast tested), comps/DCF/blend/sensitivity ✓ (Task 2, hand-computed expectations), five priced line items with bands and not-assessed degradation ✓ (Task 3), five-sheet workbook with sources, live roll-up formulas, disclaimer ✓ (Task 4), CLI with exit-code contract and shared runner ✓ (Task 5), e2e gate ✓ (Task 6). Example assumptions file ✓ (Task 1, consumed by Tasks 5–6 tests).
- **Type consistency:** `write_model(path, assumptions, adjustments, comps, dcf, scenarios, grid)` uniform between Task 4 definition and Task 5 call; `price_adjustments(results, assumptions, pre_dd_ev_mid)` uniform between Tasks 3 and 5; `Assumptions` field names identical across all test factories.
- **Known simplifications (documented in spec):** license discount and sensitivity grid use mid-band adjustments only in the post-DD grid; DCF projects from mid revenue; blend is a simple mean. All stated in cell labels/basis strings so the model stays honest.

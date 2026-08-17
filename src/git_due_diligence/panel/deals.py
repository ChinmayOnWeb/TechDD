"""Part B: acquisition selection (B1) and deal terms (B2).

Part B asks whether repository health predicts *which* open-source companies get
acquired (B1) and *on what terms* (B2). The universe attrition that made Part A
underpowered is Part B's sample: every firm that left the public market did so on
a dated, observable event.

READ THIS BEFORE QUOTING ANY NUMBER FROM THIS MODULE. Part B has five events. Not
five hundred, not fifty -- five. That is not a sample on which a regression can
be run, and this module deliberately does not offer one for B2. What it offers
instead is (a) exact, distribution-free tests whose smallest attainable p-value
is stated up front, so the reader can see the ceiling before seeing the result,
and (b) a fully sourced deal table. The design's own spec calls B2 "the weakest
of the three" and says it "should be framed as suggestive"; with five deals even
that is generous.

The exactness matters. At these counts an asymptotic test is not merely imprecise
-- Part A demonstrated it reports p < 0.001 for coefficients that a valid test
puts at 0.115 and that one extra cluster then takes to zero. So B1's headline is
a permutation test that enumerates every possible assignment of outcomes across
firms, and its floor is reported alongside it.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import combinations
from pathlib import Path

# A session whose absolute return exceeds this is treated as possibly carrying
# deal news when auditing the hand-coded dates. It is a *diagnostic* threshold
# only -- the dates in deals.toml come from filings, and this is used to check
# them, never to set them. 8% is far above the daily volatility of these names
# outside event windows and far below every announcement move in the sample
# (+11.9% to +29.4%).
_EVENT_RETURN_THRESHOLD = 0.08

# Robustness baseline: a close this many calendar days before the first affected
# session. The Cloudera release quotes a 30-day VWAP premium; a 30-day close is
# the nearest thing computable without volume data, and the difference is
# reported rather than hidden.
_LONG_BASELINE_DAYS = 30


@dataclass(frozen=True)
class Deal:
    slug: str
    ticker: str
    announced: date
    first_affected: date        # first session whose close can embed the news
    unaffected: date            # last session whose close cannot
    completed: date | None
    consideration: str          # "cash" | "stock"
    acquirer: str
    offer_price: float | None = None       # cash deals
    exchange_ratio: float | None = None    # stock deals
    acquirer_ticker: str | None = None
    leakage_date: date | None = None       # earlier news that re-rated the stock
    notes: str = ""

    @property
    def is_stock(self) -> bool:
        return self.consideration == "stock"


def load_deals(path: Path) -> list[Deal]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    deals = []
    for entry in raw.get("deal", []):
        consideration = entry["consideration"]
        if consideration not in ("cash", "stock"):
            raise ValueError(f"{entry['slug']}: consideration must be cash or stock")
        if consideration == "cash" and entry.get("offer_price") is None:
            raise ValueError(f"{entry['slug']}: cash deal needs offer_price")
        if consideration == "stock" and (entry.get("exchange_ratio") is None
                                         or entry.get("acquirer_ticker") is None):
            raise ValueError(
                f"{entry['slug']}: stock deal needs exchange_ratio and acquirer_ticker")
        if entry["unaffected"] >= entry["first_affected"]:
            raise ValueError(
                f"{entry['slug']}: unaffected close must precede the first affected session")
        deals.append(Deal(
            slug=entry["slug"], ticker=entry["ticker"], announced=entry["announced"],
            first_affected=entry["first_affected"], unaffected=entry["unaffected"],
            completed=entry.get("completed"), consideration=consideration,
            acquirer=entry["acquirer"], offer_price=entry.get("offer_price"),
            exchange_ratio=entry.get("exchange_ratio"),
            acquirer_ticker=entry.get("acquirer_ticker"),
            leakage_date=entry.get("leakage_date"), notes=entry.get("notes", ""),
        ))
    return sorted(deals, key=lambda d: d.announced)


def _close_on_or_before(series: dict[date, float], target: date,
                        tolerance_days: int = 7) -> float | None:
    candidates = [d for d in series if d <= target]
    if not candidates:
        return None
    best = max(candidates)
    return series[best] if (target - best).days <= tolerance_days else None


def offer_value(deal: Deal, prices: dict[str, dict[date, float]]) -> float | None:
    """Per-share consideration, in dollars.

    A stock deal has no fixed price: the ratio is valued at the ACQUIRER's
    unaffected close. Valuing it at the acquirer's post-announcement price would
    fold the market's reaction to the deal into the deal's own terms, which is
    circular -- and it matters here, because Cloudera rose 11.5% on the session
    that first priced its Hortonworks merger."""
    if not deal.is_stock:
        return deal.offer_price
    acquirer = prices.get((deal.acquirer_ticker or "").upper(), {})
    ref = _close_on_or_before(acquirer, deal.unaffected)
    return None if ref is None else (deal.exchange_ratio or 0.0) * ref


@dataclass(frozen=True)
class DealTerms:
    slug: str
    ticker: str
    announced: date
    consideration: str
    offer_value: float | None
    unaffected_close: float | None
    premium: float | None                 # offer / unaffected - 1
    announcement_return: float | None     # unaffected close -> first affected close
    long_baseline_close: float | None
    premium_long: float | None            # vs the 30-day-prior close
    premium_preleak: float | None         # vs the close before earlier deal news


def deal_terms(deal: Deal, prices: dict[str, dict[date, float]]) -> DealTerms:
    series = prices.get(deal.ticker.upper(), {})
    unaffected = _close_on_or_before(series, deal.unaffected)
    affected = _close_on_or_before(series, deal.first_affected)
    offer = offer_value(deal, prices)
    long_ref = _close_on_or_before(
        series, deal.first_affected - timedelta(days=_LONG_BASELINE_DAYS))
    preleak = (_close_on_or_before(series, deal.leakage_date - timedelta(days=1))
               if deal.leakage_date else None)

    def ratio(numer, denom):
        if numer is None or denom in (None, 0):
            return None
        return numer / denom - 1.0

    return DealTerms(
        slug=deal.slug, ticker=deal.ticker, announced=deal.announced,
        consideration=deal.consideration, offer_value=offer,
        unaffected_close=unaffected,
        premium=ratio(offer, unaffected),
        announcement_return=ratio(affected, unaffected),
        long_baseline_close=long_ref,
        premium_long=ratio(offer, long_ref),
        premium_preleak=ratio(offer, preleak),
    )


def return_profile(deal: Deal, prices: dict[str, dict[date, float]],
                   before: int = 4, after: int = 3) -> list[tuple[date, float, float]]:
    """(date, close, one-session return) around the first affected session.

    Exists so the hand-coded dates in `deals.toml` can be audited rather than
    trusted: the tests use it to assert that the session labelled `unaffected`
    moved quietly and the one labelled `first_affected` did not."""
    series = prices.get(deal.ticker.upper(), {})
    days = sorted(series)
    if deal.first_affected not in series:
        return []
    i = days.index(deal.first_affected)
    out = []
    for d in days[max(0, i - before):i + after + 1]:
        j = days.index(d)
        prior = series[days[j - 1]] if j else None
        out.append((d, series[d], series[d] / prior - 1.0 if prior else float("nan")))
    return out


# --------------------------------------------------------------------------
# B1: does repo health predict WHICH firms are acquired?
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ExactTest:
    statistic: float
    p_value: float
    n_events: int
    n_censored: int
    arrangements: int
    min_attainable_p: float
    group_means: tuple[float, float]     # (acquired, not acquired)

    @property
    def can_reject_at_5pct(self) -> bool:
        return self.min_attainable_p <= 0.05


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def firm_level_exact_test(values_by_firm: dict[str, float],
                          acquired: set[str]) -> ExactTest:
    """Exact two-sided Wilcoxon rank-sum test across firms.

    Every assignment of the observed labels across firms is enumerated, so the
    p-value is exact and assumption-free -- no normality, no asymptotics, no
    cluster-count problem. What it cannot escape is granularity: with `k` events
    among `n` firms there are only C(n, k) arrangements, so the smallest
    attainable two-sided p-value is 2/C(n, k). That number is returned as
    `min_attainable_p` and MUST be quoted with the result. Part A's Rademacher
    bootstrap taught this lesson expensively: a test whose floor exceeds the
    chosen threshold has no power against any effect whatsoever, and reports a
    null that means nothing. At seven firms with four events the floor is
    2/35 = 0.057 and a 5% test cannot reject however cleanly the groups
    separate; at eight firms with five it is 2/56 = 0.036 and it can.

    THE STATISTIC IS THE RANK SUM, NOT THE DIFFERENCE IN MEANS, and the reason
    is not stylistic. The rank-sum null distribution is exactly symmetric about
    k(n+1)/2, so the 2/C(n, k) floor is exactly right. A difference in means is
    not symmetric when the groups differ in size -- with five events among eight
    firms an initial implementation returned p = 0.018 against its own stated
    floor of 0.036, which is incoherent. Ranks also make the statistic
    scale-free, which is what allows `separation_scan` to ask which of several
    variables separates the groups best on a common footing."""
    firms = sorted(values_by_firm)
    n = len(firms)
    events = [f for f in firms if f in acquired]
    k = len(events)
    if not 0 < k < n:
        raise ValueError("need at least one acquired and one non-acquired firm")
    ranks = _ranks([values_by_firm[f] for f in firms])
    centre = k * (n + 1) / 2.0

    observed = sum(ranks[i] for i, f in enumerate(firms) if f in acquired)
    sums = [sum(ranks[i] for i in chosen) for chosen in combinations(range(n), k)]
    at_least = sum(1 for s in sums if abs(s - centre) >= abs(observed - centre) - 1e-12)
    others = [values_by_firm[f] for f in firms if f not in acquired]
    return ExactTest(
        statistic=observed,
        p_value=at_least / len(sums),
        n_events=k,
        n_censored=n - k,
        arrangements=len(sums),
        min_attainable_p=2.0 / len(sums),
        group_means=(sum(values_by_firm[f] for f in events) / k,
                     sum(others) / len(others)),
    )


def separation_scan(values_by_firm: dict[str, dict[str, float]],
                    acquired: set[str]) -> list[tuple[str, ExactTest, bool]]:
    """Run the same exact test on several firm-level variables and report which
    of them separate acquired from independent firms.

    This is the check that decides whether B1 says anything about repository
    health specifically. A rank test on eight firms is a blunt instrument: any
    variable correlated with company size will separate a sample where the
    acquired firms happen to be the smaller ones. If plain operating margin --
    which needs no git history at all -- separates the groups exactly as well as
    the repo-health index, then B1's result is about size and profitability, and
    attributing it to repository health would be unsupported.

    Returns (name, test, perfectly_separated) sorted by p-value, then name."""
    out = []
    for name, values in values_by_firm.items():
        if any(v != v for v in values.values()):     # NaN
            continue
        test = firm_level_exact_test(values, acquired)
        n, k = len(values), len(acquired)
        extreme = {k * (k + 1) / 2.0, k * (2 * n - k + 1) / 2.0}
        out.append((name, test, test.statistic in extreme))
    return sorted(out, key=lambda t: (t[1].p_value, t[0]))


#: Firm-level variables the separation scan compares against the health index.
#: `op_margin_ltm` and `log_rev` are the important ones: both come straight off
#: the income statement and neither requires a line of repository analysis.
SEPARATION_COMPARATORS = (
    "repo_health_index_z", "active_contributors", "top_author_share",
    "bus_factor_50", "log_rev", "op_margin_ltm", "growth_yoy", "ev_rev",
)


def last_observation_by_firm(panel, deals: list[Deal],
                             columns: tuple[str, ...] = SEPARATION_COMPARATORS
                             ) -> dict[str, dict[str, float]]:
    """{column: {firm: value}} at each firm's last pre-announcement quarter.

    "Last pre-announcement" rather than "last observed" so acquired and
    independent firms are compared at the same point in their own histories:
    the final quarter in which the company was still independently valued."""
    announced = {d.slug: d.announced for d in deals}
    picked: dict[str, dict[str, float]] = {c: {} for c in columns}
    for slug, group in panel.groupby("firm"):
        group = group.sort_values("quarter_end")
        ann = announced.get(slug)
        eligible = group[[date.fromisoformat(q) < ann if ann else True
                          for q in group["quarter_end"]]]
        if not len(eligible):
            continue
        row = eligible.iloc[-1]
        for column in columns:
            if column in row:
                picked[column][slug] = float(row[column])
    return picked


def build_risk_set(panel, deals: list[Deal], index_col: str = "repo_health_index_z"):
    """Firm-quarter risk set for the B1 discrete-time hazard.

    One row per firm-quarter while the firm is still independent, with
    `announced_next` = 1 for the last quarter ending before its announcement.
    A firm leaves the risk set once its deal is announced: quarters after that
    are not observations on an independent company, and keeping them would both
    inflate n and mislabel the outcome. Firms never acquired are
    right-censored and contribute only zeros -- which is exactly the
    counterfactual B2 cannot see, and the reason B1 is the stronger of the two.
    """
    import pandas as pd

    announced = {d.slug: d.announced for d in deals}
    rows = []
    for slug, group in panel.groupby("firm"):
        group = group.sort_values("quarter_end")
        ann = announced.get(slug)
        ends = [date.fromisoformat(q) for q in group["quarter_end"]]
        eligible = [q for q in ends if ann is None or q < ann]
        if not eligible:
            continue
        last_before = max(eligible)
        for _, row in group.iterrows():
            q = date.fromisoformat(row["quarter_end"])
            if ann is not None and q >= ann:
                continue
            rows.append({
                "firm": slug,
                "quarter_end": row["quarter_end"],
                index_col: row[index_col],
                "growth_yoy": row["growth_yoy"],
                "op_margin_ltm": row["op_margin_ltm"],
                "log_rev": row["log_rev"],
                "announced_next": int(ann is not None and q == last_before),
                "acquired": int(ann is not None),
            })
    return pd.DataFrame(rows)


def hazard_logit(risk_set, index_col: str = "repo_health_index_z",
                 controls: tuple[str, ...] = ()):
    """B1 discrete-time hazard: logit of announcement-next-quarter on repo health.

    Controls default to NONE, and that is a decision rather than laziness. The
    conventional floor for a binary outcome is ~10 events per parameter; with
    five events the budget is half a parameter. Adding growth, margin and size
    to a five-event logit does not produce a better-specified model, it produces
    separation and coefficients of ~1e2 with infinite standard errors -- the same
    failure mode Part A hit, wearing a different hat. Controls are available for
    a robustness column whose instability is the point.

    The asymptotic p-value this returns is reported ONLY for comparison with the
    exact test. It is not inference here."""
    import statsmodels.formula.api as smf

    terms = [index_col, *controls]
    formula = "announced_next ~ " + " + ".join(terms)
    data = risk_set.dropna(subset=["announced_next", *terms])
    fit = smf.logit(formula, data).fit(disp=False)
    return fit, data


def hazard_permutation_p(risk_set, index_col: str = "repo_health_index_z") -> ExactTest:
    """Cluster-level exact test for B1, at firm-quarter resolution.

    The event labels are permuted across FIRMS, not across firm-quarters,
    because the thing being reassigned is "was this company acquired" -- a firm
    attribute. Permuting individual quarters would treat 100-odd correlated
    observations as independent and manufacture the significance the exact test
    exists to avoid, in the same way the asymptotic cluster-robust errors did in
    Part A.

    The statistic is the difference in mean repo health between the quarter
    immediately preceding an announcement and all other quarters in the risk
    set, so the timing within a firm's history carries information the firm-level
    test throws away."""
    per_firm_last: dict[str, float] = {}
    for slug, group in risk_set.groupby("firm"):
        hit = group.loc[group["announced_next"] == 1, index_col]
        if len(hit):
            per_firm_last[slug] = float(hit.iloc[0])
        else:
            per_firm_last[slug] = float(group[index_col].iloc[-1])
    acquired = {slug for slug, g in risk_set.groupby("firm")
                if g["announced_next"].max() == 1}
    return firm_level_exact_test(per_firm_last, acquired)


# --------------------------------------------------------------------------
# B2: do terms vary with repo health?
# --------------------------------------------------------------------------

def spearman_exact(x: list[float], y: list[float]) -> ExactTest:
    """Exact Spearman rank correlation by full permutation of one ranking.

    n! arrangements, so exact for the n <= 8 this study will ever have. With
    five deals the floor is 2/120 = 0.017; with four it is 2/24 = 0.083, above
    5%, meaning a four-deal B2 cannot reject at conventional levels no matter
    what the data look like."""
    from itertools import permutations
    from math import isnan

    pairs = [(a, b) for a, b in zip(x, y) if not (isnan(a) or isnan(b))]
    n = len(pairs)
    if n < 3:
        raise ValueError("need at least 3 complete pairs")
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]

    def rank(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = avg
            i = j + 1
        return out

    rx, ry = rank(xs), rank(ys)
    mean = (n + 1) / 2

    def rho(a: list[float], b: list[float]) -> float:
        num = sum((ai - mean) * (bi - mean) for ai, bi in zip(a, b))
        da = sum((ai - mean) ** 2 for ai in a) ** 0.5
        db = sum((bi - mean) ** 2 for bi in b) ** 0.5
        return num / (da * db) if da and db else 0.0

    observed = rho(rx, ry)
    perms = list(permutations(ry))
    at_least = sum(1 for p in perms if abs(rho(rx, list(p))) >= abs(observed) - 1e-12)
    return ExactTest(
        statistic=observed, p_value=at_least / len(perms),
        n_events=n, n_censored=0, arrangements=len(perms),
        min_attainable_p=2.0 / len(perms),
        group_means=(float("nan"), float("nan")),
    )


def pre_announcement_health(panel, deal: Deal,
                            index_col: str = "repo_health_index_z") -> float | None:
    """Repo health in the last panel quarter ending strictly before announcement.

    Strictly before, because a quarter straddling the announcement contains
    commit activity from after the deal was public -- and deal news changes
    contributor behaviour immediately."""
    rows = panel[panel["firm"] == deal.slug]
    if not len(rows):
        return None
    prior = [(date.fromisoformat(q), v) for q, v in
             zip(rows["quarter_end"], rows[index_col])
             if date.fromisoformat(q) < deal.announced]
    if not prior:
        return None
    return float(max(prior, key=lambda t: t[0])[1])

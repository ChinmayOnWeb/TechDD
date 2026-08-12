from __future__ import annotations

from datetime import date

from git_due_diligence.panel.edgar import QuarterFundamentals
from git_due_diligence.panel.history import QuarterMetrics
from git_due_diligence.panel.universe import Firm

# Components of the composite repo-health index (metric, healthy-direction sign).
# Every component must be measured comparably across firms; raw counts that only
# reflect project scale or local convention are kept as descriptive panel columns
# but excluded here:
#   - merge_share, commit_volume: workflow/scale controls, not health (excluded
#     since v1).
#   - release_cadence: a raw count of release tags, which is dominated by tagging
#     convention rather than release velocity (MongoDB tags every backport patch
#     across many major lines -> ~113/window; Elastic ~34; GitLab's release tags
#     live on unfetched stable branches -> 0). Not comparable across firms and
#     unmeasurable for some, so excluded from the index and retained only as a
#     descriptive column. Reintroducing a *comparable* release signal (e.g.
#     distinct minor-version lines) is future analyst work.
INDEX_COMPONENTS: list[tuple[str, int]] = [
    ("active_contributors", 1),
    ("top_author_share", -1),
    ("contributor_gini", -1),
    ("bus_factor_50", 1),
    ("churn_gini", -1),
    ("secret_incidence", -1),
]

# Count-type components scale with project size (a 4x-bigger project has ~4x the
# contributors), so a raw z-score would let size dominate the cross-firm index.
# We log1p-transform these before standardizing so the index reflects order-of-
# magnitude differences, not raw scale. The ratio/rate components (shares, ginis,
# secret_incidence) are already scale-free and pass through untransformed.
_LOG_COMPONENTS = frozenset({"active_contributors", "bus_factor_50"})

_FUNDAMENTALS_JOIN_TOLERANCE_DAYS = 10


def _match_fundamentals(by_end: dict[date, QuarterFundamentals],
                        target: date) -> QuarterFundamentals | None:
    if not by_end:
        return None
    best = min(by_end, key=lambda d: abs((d - target).days))
    if abs((best - target).days) > _FUNDAMENTALS_JOIN_TOLERANCE_DAYS:
        return None
    return by_end[best]


def build_panel(firms: list[Firm],
                metrics_by_slug: dict[str, list[QuarterMetrics]],
                fundamentals_by_slug: dict[str, list[QuarterFundamentals]],
                prices_by_slug: dict[str, dict[date, float | None]]):
    import numpy as np
    import pandas as pd

    rows: list[dict] = []
    for firm in firms:
        quarters = sorted(metrics_by_slug.get(firm.slug, []), key=lambda m: m.quarter_end)
        by_end = {f.quarter_end: f for f in fundamentals_by_slug.get(firm.slug, [])}
        prices = prices_by_slug.get(firm.slug, {})
        matched = [_match_fundamentals(by_end, m.quarter_end) for m in quarters]
        for i, m in enumerate(quarters):
            if i < 3:
                continue
            window = matched[i - 3:i + 1]
            if any(f is None for f in window):
                continue
            revenue_ltm = sum(f.revenue for f in window)
            price = prices.get(m.quarter_end)
            shares = window[-1].shares_outstanding
            if revenue_ltm <= 0 or price is None or shares is None:
                continue
            ops = [f.operating_income for f in window]
            op_margin_ltm = (sum(ops) / revenue_ltm
                             if all(v is not None for v in ops) else np.nan)
            growth_yoy = np.nan
            if i >= 7:
                prior = matched[i - 7:i - 3]
                if all(f is not None for f in prior):
                    prior_ltm = sum(f.revenue for f in prior)
                    if prior_ltm > 0:
                        growth_yoy = revenue_ltm / prior_ltm - 1
            market_cap = price * shares
            net_debt = (window[-1].debt or 0.0) - (window[-1].cash or 0.0)
            ev = market_cap + net_debt
            if ev <= 0:
                continue
            rows.append({
                "firm": firm.slug,
                "ticker": firm.ticker,
                "quarter_end": m.quarter_end.isoformat(),
                "revenue_ltm": revenue_ltm,
                "growth_yoy": growth_yoy,
                "op_margin_ltm": op_margin_ltm,
                "market_cap": market_cap,
                "net_debt": net_debt,
                "ev": ev,
                "ev_rev": ev / revenue_ltm,
                "log_ev_rev": float(np.log(ev / revenue_ltm)),
                "log_rev": float(np.log(revenue_ltm)),
                "active_contributors": m.active_contributors,
                "top_author_share": m.top_author_share,
                "contributor_gini": m.contributor_gini,
                "bus_factor_50": m.bus_factor_50,
                "churn_gini": m.churn_gini,
                "release_cadence": m.release_cadence,
                "merge_share": m.merge_share,
                "commit_volume": m.commit_volume,
                "secret_incidence": m.secret_incidence,
            })
    panel = pd.DataFrame(rows)
    if panel.empty:
        return panel
    signed = {}
    for column, sign in INDEX_COMPONENTS:
        values = np.log1p(panel[column]) if column in _LOG_COMPONENTS else panel[column]
        std = values.std(ddof=0)
        signed[column] = sign * (values - values.mean()) / (std if std > 0 else 1.0)
    z = pd.DataFrame(signed)
    panel["repo_health_index_z"] = z.mean(axis=1)
    matrix = z.to_numpy()
    _, _, vt = np.linalg.svd(matrix - matrix.mean(axis=0), full_matrices=False)
    pc1 = matrix @ vt[0]
    corr = np.corrcoef(pc1, panel["repo_health_index_z"])[0, 1]
    if np.isfinite(corr) and corr < 0:
        pc1 = -pc1
    panel["repo_health_index_pca"] = pc1
    return panel

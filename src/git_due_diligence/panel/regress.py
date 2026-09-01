from __future__ import annotations

from pathlib import Path

_CONTROLS = "growth_yoy + op_margin_ltm + log_rev"
_FIXED_EFFECTS = "C(firm) + C(quarter_end)"
_MIN_ROWS = 30
_MIN_FIRMS = 2   # firm-clustered SE degenerate with a single group
_H2_HORIZONS = range(1, 5)


def run_regressions(panel, output_dir: Path,
                    index_col: str = "repo_health_index_z") -> dict:
    import statsmodels.formula.api as smf

    if index_col == "repo_health_index_pca":
        raise ValueError(
            "repo_health_index_pca is a full-panel descriptive index and cannot "
            "be used in predictive regressions; use repo_health_index_z")

    n_firms = panel["firm"].nunique() if "firm" in panel.columns else 0
    if n_firms < _MIN_FIRMS:
        raise ValueError(
            f"panel has {n_firms} firm(s); firm fixed effects with firm-clustered "
            f"standard errors require at least {_MIN_FIRMS}. Add more firms to "
            f"panel/universe/ and rebuild.")

    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict = {}

    base_cols = [index_col, "growth_yoy", "op_margin_ltm", "log_rev"]
    h1_data = panel.dropna(subset=["log_ev_rev", *base_cols])
    h1 = smf.ols(
        f"log_ev_rev ~ {index_col} + {_CONTROLS} + {_FIXED_EFFECTS}", data=h1_data,
    ).fit(cov_type="cluster", cov_kwds={"groups": h1_data["firm"]})
    results["h1"] = h1
    (output_dir / "h1_pricing.txt").write_text(h1.summary().as_text(), encoding="utf-8")

    panel = panel.sort_values(["firm", "quarter_end"]).copy()
    for k in _H2_HORIZONS:
        outcome = f"growth_fwd_{k}"
        panel[outcome] = panel.groupby("firm")["growth_yoy"].shift(-k)
        sub = panel.dropna(subset=[outcome, *base_cols])
        if len(sub) < _MIN_ROWS:
            continue
        h2 = smf.ols(
            f"{outcome} ~ {index_col} + {_CONTROLS} + {_FIXED_EFFECTS}", data=sub,
        ).fit(cov_type="cluster", cov_kwds={"groups": sub["firm"]})
        results[f"h2_k{k}"] = h2
        (output_dir / f"h2_growth_fwd_{k}.txt").write_text(
            h2.summary().as_text(), encoding="utf-8")
    return results

import numpy as np
import pandas as pd

from git_due_diligence.panel.regress import run_regressions


def _synthetic_panel(n_firms=12, n_quarters=30, beta_h1=0.5, beta_h2=0.3, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    firm_fe = rng.normal(0, 0.5, n_firms)
    quarter_fe = rng.normal(0, 0.3, n_quarters)
    index = rng.normal(0, 1, (n_firms, n_quarters))
    rows = []
    for i in range(n_firms):
        for t in range(n_quarters):
            growth = (beta_h2 * index[i, t - 1] if t > 0 else 0.0) + rng.normal(0, 0.01)
            rows.append({
                "firm": f"firm{i:02d}",
                "quarter_end": f"q{t:02d}",
                "repo_health_index_z": index[i, t],
                "growth_yoy": growth,
                "op_margin_ltm": rng.normal(0, 0.1),
                "log_rev": rng.normal(5, 0.5),
                "log_ev_rev": (1.0 + beta_h1 * index[i, t]
                               + firm_fe[i] + quarter_fe[t] + rng.normal(0, 0.01)),
            })
    return pd.DataFrame(rows)


def test_h1_recovers_planted_coefficient(tmp_path):
    results = run_regressions(_synthetic_panel(), tmp_path)
    assert abs(results["h1"].params["repo_health_index_z"] - 0.5) < 0.02
    assert (tmp_path / "h1_pricing.txt").exists()


def test_h2_recovers_planted_predictive_coefficient(tmp_path):
    results = run_regressions(_synthetic_panel(), tmp_path)
    assert abs(results["h2_k1"].params["repo_health_index_z"] - 0.3) < 0.05
    assert (tmp_path / "h2_growth_fwd_1.txt").exists()


def test_all_h2_horizons_run(tmp_path):
    results = run_regressions(_synthetic_panel(), tmp_path)
    assert {"h1", "h2_k1", "h2_k2", "h2_k3", "h2_k4"} <= set(results)


def test_rows_with_missing_values_dropped_not_fatal(tmp_path):
    panel = _synthetic_panel()
    panel.loc[panel.index[:5], "growth_yoy"] = np.nan
    results = run_regressions(panel, tmp_path)
    assert "h1" in results


def test_single_firm_panel_refused_cleanly(tmp_path):
    import pytest
    panel = _synthetic_panel(n_firms=1)
    with pytest.raises(ValueError, match="firm fixed effects"):
        run_regressions(panel, tmp_path)


def test_descriptive_pca_refused_as_predictive_index(tmp_path):
    import pytest
    panel = _synthetic_panel()
    panel["repo_health_index_pca"] = panel["repo_health_index_z"]
    with pytest.raises(ValueError, match="full-panel descriptive index"):
        run_regressions(panel, tmp_path, index_col="repo_health_index_pca")

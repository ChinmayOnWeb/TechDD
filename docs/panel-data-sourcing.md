# Panel data sourcing

The panel deliberately includes **acquired and delisted firms for their listed
window** — that inclusion rule is what removes survivorship bias, and it is the
reason the free price sources are not sufficient on their own.

## Why Stooq/Yahoo are not enough

Both drop tickers once a security stops trading. Confluent (CFLT, IBM, Mar 2026),
HashiCorp (HCP, IBM), Couchbase (BASE, Haveli, Sep 2025), Cloudera, Talend,
Hortonworks and MariaDB are all in the study's candidate universe and all
un-queryable there today. Using only live tickers silently rebuilds the exact
selection bias the design set out to avoid: firms exit the sample precisely when
they are acquired, and acquisition is plausibly correlated with the outcome
being studied.

CRSP retains delisted securities with full history, so one export covers the
whole universe — live and dead.

## CRSP export spec

Source: **WRDS → CRSP → Stock / Security Files → Daily Stock File** (institutional
subscription required; fetch it yourself — WRDS terms restrict automated and
third-party access, and the agent sandbox cannot reach WRDS in any case).

Request:

- **Securities:** search by ticker for every firm in `panel/universe/*.toml`.
  Prefer resolving each to its **PERMNO** and querying by PERMNO — PERMNO is
  stable across ticker changes and reused symbols, which ticker search is not.
- **Date range:** earliest `listed_from` in the universe → today.
- **Frequency:** daily.
- **Variables (minimum):** `PERMNO`, `date`, `TICKER`, `PRC`.
- **Variables (recommended):** add `SHROUT` and `CFACSHR`. CRSP share counts
  would replace the current XBRL fallback, which is weakest exactly where it
  matters — GitLab omits `dei:EntityCommonStockSharesOutstanding` entirely and
  we fall back to weighted-average shares from the income statement.
- **Output:** CSV.

Then:

```bash
gitdd panel build --universe panel/universe --clones /path/to/clones \
    --cache panel_cache --crsp /path/to/crsp_daily.csv -o panel.csv
```

## How the loader treats the export

`panel/crsp.py` handles the CRSP conventions that silently corrupt naive parses:

- **Negative `PRC`** means no closing trade occurred and the figure is a bid/ask
  midpoint. The magnitude is still the price estimate, so the absolute value is
  used — dropping these rows loses thin-trading days, and taking them signed
  produces negative market caps.
- **Blank or non-numeric `PRC`** (`C`, `B` markers) means no valid quote; those
  rows are skipped rather than failing the load.
- Dates parse as either `YYYY-MM-DD` or compact `YYYYMMDD`.
- Tickers are upper-cased for matching against `Firm.ticker`.

**Precedence:** for any ticker the CRSP file covers, CRSP is used for that firm's
entire series and Stooq is ignored. Sources are never mixed *within* one firm's
series, since splicing two vendors' prices mid-history creates level shifts that
look like real price moves. Firms absent from the CRSP file fall back to Stooq.

Quarter-end resolution is shared between both sources
(`quarter_end_prices_from_series`): the last close on or before the fiscal
quarter-end, or `None` when the nearest prior close is more than 14 days stale.
A firm acquired mid-quarter therefore prices normally through its listed window
and reports `None` afterwards, which drops those rows from the panel.

## Not handled here

Delisting returns (CRSP `DSEDELIST`) are out of scope: they matter for
return-based event studies (Part B) but not for a quarter-end price level.
Part B will need them separately.

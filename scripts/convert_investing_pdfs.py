"""Convert Investing.com price PDFs into one CRSP-shaped CSV.

Output columns (TICKER, date, PRC) are exactly what `gitdd panel build --crsp`
already consumes, so no new ingestion path is needed. The flag is named for
CRSP but the loader only requires ticker/date/price columns -- provenance here
is Investing.com, recorded in docs/panel-data-sourcing.md.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from git_due_diligence.panel.investing_pdf import extract_series

UPLOADS = Path("/root/.claude/uploads/47b6444c-7c80-597d-aa8a-8bf243d32ebd")
SOURCES = {
    "CLDR": "7f71c51a-cldr_us_d.pdf",
    "HDP": "4d9de933-hdp_us_d.pdf",
    "BASE": "fd235050-base_us_d.pdf",
    "HCP": "846a6382-hcp_us_d.pdf",
    "CFLT": "7af4e81f-cflt_us_d.pdf",
}
OUTPUT = Path("panel_cache/prices_delisted.csv")

# Announced per-share consideration, used only as an extraction check: the final
# close should sit very near the deal price. This validates the column mapping
# end to end -- if the parser were taking the OPEN instead of the CLOSE, these
# would not line up.
DEAL_PRICE = {"CLDR": 16.00, "BASE": 24.50, "HCP": 35.00, "CFLT": 31.00}


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["TICKER", "date", "PRC"])
        for ticker, filename in SOURCES.items():
            series = extract_series(UPLOADS / filename)
            if not series:
                print(f"{ticker}: NO ROWS EXTRACTED", flush=True)
                continue
            for when, close in series:
                writer.writerow([ticker, when.isoformat(), f"{close:.4f}"])
            rows += len(series)
            last_date, last_close = series[-1]
            check = ""
            if ticker in DEAL_PRICE:
                gap = abs(last_close - DEAL_PRICE[ticker]) / DEAL_PRICE[ticker]
                check = (f"  final close {last_close:.2f} vs deal "
                         f"{DEAL_PRICE[ticker]:.2f} -> {gap:.2%} "
                         f"{'OK' if gap < 0.03 else 'CHECK'}")
            print(f"{ticker:5s} {len(series):5d} rows  "
                  f"{series[0][0]} .. {last_date}{check}", flush=True)
    print(f"\nwrote {rows:,} rows -> {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

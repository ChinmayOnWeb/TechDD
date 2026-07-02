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

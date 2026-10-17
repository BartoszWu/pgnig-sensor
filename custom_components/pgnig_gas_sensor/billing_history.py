"""Small, account-free projection of invoices already fetched by the coordinator."""
from __future__ import annotations

from datetime import date, datetime
from math import isfinite
from typing import Any, Sequence

HISTORY_LIMIT = 12


def _day(value: Any) -> str | None:
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date) or value.year < 1900:
        return None
    return value.isoformat()


def _number(value: Any, *, positive: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not isfinite(value) or value < 0 or (positive and value == 0):
        return None
    return float(value)


def billing_history(invoices: Sequence[Any], id_local: int) -> list[dict[str, Any]]:
    """Keep dated consumption documents, never account or invoice identifiers.

    Credit/interest notes, non-gas services, duplicates and other meters are not
    consumption periods. Missing consumption has historically been parsed as 0
    by InvoicesList, so zero is not asserted as a measured consumption here.
    Overlapping periods remain individual documents; consumers must not sum them.
    This function adds no requests and does not imply that 12 documents = 12 months.
    """
    rows = []
    seen = set()
    for inv in invoices:
        if str(inv.id_pp) != str(id_local):
            continue
        if inv.is_credit_note or inv.is_interest_note or inv.is_insurance_policy or inv.is_lawyer_agreement:
            continue
        start, end, issued = _day(inv.start_date), _day(inv.end_date), _day(inv.date)
        if not start or not end or not issued or start > end:
            continue
        # Do not use Wear as a unitless fallback for explicit WearM3.
        m3, kwh = _number(inv.wear_m3, positive=True), _number(inv.wear_kwh, positive=True)
        if m3 is None and kwh is None:
            continue
        if inv.number in seen:
            continue
        seen.add(inv.number)
        type_text = f"{inv.type} {inv.temp_type}".lower()
        kind = "forecast" if "prognoz" in type_text or "forecast" in type_text else "invoice"
        rows.append({
            "period_start": start, "period_end": end, "issued_on": issued,
            "m3": m3, "kwh": kwh, "gross_amount": _number(inv.gross_amount),
            "kind": kind,
        })
    return sorted(rows, key=lambda row: (row["period_end"], row["issued_on"]), reverse=True)[:HISTORY_LIMIT]

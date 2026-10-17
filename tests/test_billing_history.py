"""History is a safe projection of one existing poll, not a new API collector."""
from datetime import datetime
from types import SimpleNamespace

from custom_components.pgnig_gas_sensor.billing_history import billing_history
from custom_components.pgnig_gas_sensor.sensor import PgnigCostTrackingSensor
from .builders import make_invoice, build_stub_coordinator


def invoice(**changes):
    values = dict(id_pp="1", number="SYNTHETIC", start_date=datetime(2026, 8, 1),
                  end_date=datetime(2026, 8, 31), date=datetime(2026, 9, 3),
                  wear_m3=12.0, wear_kwh=130.0, gross_amount=100.0,
                  is_credit_note=False, is_interest_note=False,
                  is_insurance_policy=False, is_lawyer_agreement=False,
                  type="Faktura", temp_type="", iban="PRIVATE", agreement_number="PRIVATE")
    return SimpleNamespace(**{**values, **changes})


def test_projects_period_and_amount_without_private_fields():
    rows = billing_history([invoice()], 1)
    assert rows == [{"period_start":"2026-08-01", "period_end":"2026-08-31",
                    "issued_on":"2026-09-03", "m3":12.0, "kwh":130.0,
                    "gross_amount":100.0, "kind":"invoice"}]


def test_excludes_other_meters_and_non_consumption_documents():
    documents = [invoice(id_pp="2"), invoice(is_credit_note=True),
                 invoice(is_interest_note=True), invoice(is_insurance_policy=True),
                 invoice(is_lawyer_agreement=True), invoice(wear_m3=0, wear_kwh=0)]
    assert billing_history(documents, 1) == []


def test_missing_units_do_not_become_zero_or_unitless_wear():
    assert billing_history([invoice(wear_m3=None, wear_kwh=130, wear=99)], 1)[0]["m3"] is None
    assert billing_history([invoice(wear_m3=0, wear_kwh=0, wear=99)], 1) == []


def test_rejects_invalid_periods_and_values():
    assert billing_history([invoice(start_date=None), invoice(end_date=datetime(2026, 7, 1)),
                            invoice(start_date=datetime(1, 1, 1))], 1) == []
    row = billing_history([invoice(wear_m3=float("nan"), gross_amount=float("inf"))], 1)[0]
    assert row["m3"] is None and row["gross_amount"] is None


def test_deduplicates_documents_but_preserves_overlapping_periods():
    rows = billing_history([invoice(), invoice(), invoice(number="SYNTHETIC-2")], 1)
    assert len(rows) == 2


def test_keeps_forecasts_identifiable_and_limits_history():
    rows = billing_history([invoice(number=f"SYNTHETIC-{n}", type="Prognozowa") for n in range(20)], 1)
    assert len(rows) == 12 and all(row["kind"] == "forecast" for row in rows)


def test_sensor_exposes_cached_periods_without_new_requests(hass):
    inv = make_invoice(id_pp="1", start_date=datetime(2026,8,1), end_date=datetime(2026,8,31))
    coordinator = build_stub_coordinator(hass, invoices=[inv])
    attrs = PgnigCostTrackingSensor(coordinator,"METER1",1).extra_state_attributes
    assert attrs["billing_history"][0]["period_start"] == "2026-08-01"
    assert attrs["last_invoice_period_end"] == "2026-08-31"
    assert "number" not in attrs["billing_history"][0]

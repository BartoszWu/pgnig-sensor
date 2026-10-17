# Invoice-period history extension

This branch is based on upstream v3.1.7 and identifies itself as
`3.1.7+history.1`. It is a local extension, not an upstream stable release.

The cost sensor exposes `billing_history`: up to 12 documents from the invoice
list the existing coordinator has already fetched. The API's first page is
limited to 12 invoices across the account; no complete-year guarantee is made.
There is no extra request, login, polling interval, sensor or config-entry change.

Each row contains only `period_start`, `period_end`, `issued_on`, `m3`, `kwh`,
`gross_amount` and `kind`. The last selected invoice also exposes
`last_invoice_period_start` and `last_invoice_period_end`.

- Invoice numbers, meter/account IDs, bank details and agreement data are never
  copied into the history. Existing attributes remain unchanged.
- Other supply points, credit/interest notes and non-gas services are excluded.
- Dates must be present and ordered. Missing/invalid consumption is unknown;
  unitless `Wear` is not assumed to be cubic metres.
- The upstream parser maps missing consumption to zero. This projection only
  asserts strictly positive consumption, avoiding fabricated zero usage.
- A textual forecast indicator is preserved as `kind: forecast`; other rows
  are labelled `invoice`, which does not assert an actual meter measurement.
- Exact duplicate document numbers are deduplicated internally. Identifiers are
  not exposed. Overlapping periods remain separate and must never be summed.
- A billing period is not assumed to equal a calendar month. Future periods and
  forecasts must not be reported as already measured consumption.

The focused test suite covers projection privacy, period/number validation,
filtering, deduplication, limits and exposure by the existing sensor, alongside
the existing sensor, coordinator and manifest tests. Fixtures are synthetic.

Installation uses the usual `custom_components/pgnig_gas_sensor` directory.
Back up the current directory before changing it, check HA configuration and
restart HA to load the changed Python module. Revert the copied files from that
backup and restart to roll back. No config entry or historical entity is removed.
HACS still tracks upstream; installing an upstream update can overwrite this
extension. Review the file diff before updating; do not claim it is maintained
by the upstream author until merged there.

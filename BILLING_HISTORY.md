# Invoice-period history extension

This branch is based on upstream v3.1.7 and identifies itself as
`3.1.7+history.2`. It is a local extension, not an upstream stable release.

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
HACS can track the personal fork BartoszWu/pgnig-sensor. This is not an upstream release. Upstream changes need review before merging into this fork.


## On-demand years

`pgnig_gas_sensor.load_billing_history` takes `entity_id` (an entity of the
configured integration) and `year` (2000 through the current year). It starts
one background download, using only the authenticated session already held
in memory. It never invokes login, session renewal or a retry. A failed request
ends the download; no response bodies or credentials are logged or exposed.
Only one archive job per entry can run at a time.

The endpoint's existing pageNumber/pageSize parameters are used sequentially,
12 documents per page, at most 30 pages, with a one-second gap. Empty/short or
repeated pages end traversal. The API may retain less than the full requested
year; reaching the end is not a claim of complete calendar coverage. Missing
historical years are represented as no data, not zeros. The current eight-hour
poll is unchanged and never re-downloads the archive.

Only safe projections for the selected year, keyed by period END year, are
persisted with HA's Store outside Git, along with page/availability metadata.
The latest-page projection is merged with this archive (maximum 360 records).
Distinct identical documents within one projection remain distinct. Archived
rows never enter the current invoice list, balance, cost or Energy statistics.
Already requested years are served from local storage, including empty results.

Additional cost sensor attributes: `billing_history_loaded_years`,
`billing_history_archive_status` (idle/loading/ready/cached/limited/error),
`billing_history_archive_error` (safe code), `billing_history_year_results`.
The dashboard offers explicit download and independent year visibility.

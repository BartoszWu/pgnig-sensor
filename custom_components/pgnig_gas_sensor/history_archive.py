"""On-demand, bounded history archive; never log in or change live invoice totals."""
from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import datetime, timezone

from homeassistant.helpers.storage import Store

from .billing_history import billing_history

MAX_PAGES = 30
ARCHIVE_LIMIT = 360


def merge_rows(*groups):
    """Deduplicate identical projections without summing overlapping invoices."""
    counts = Counter()
    for group in groups:
        counts |= Counter(json.dumps(row, sort_keys=True) for row in group)
    rows = [json.loads(key) for key, count in counts.items() for _ in range(count)]
    return sorted(rows, key=lambda row: (row['period_end'], row['issued_on']), reverse=True)[:ARCHIVE_LIMIT]


class BillingArchive:
    def __init__(self, hass, entry_id, api, meters, notify):
        self.hass, self.api, self.meters, self.notify = hass, api, meters, notify
        self.store = Store(hass, 1, f"pgnig_billing_history.{entry_id}")
        self.data = {"years": {}, "meters": {}}
        self.status, self.error, self.busy = "idle", None, False

    async def async_restore(self):
        data = await self.store.async_load()
        if isinstance(data, dict) and isinstance(data.get('years'), dict) and isinstance(data.get('meters'), dict):
            self.data = data

    def rows(self, id_local):
        return self.data['meters'].get(str(id_local), [])

    def metadata(self):
        return {"billing_history_loaded_years": sorted(self.data['years'], reverse=True),
                "billing_history_archive_status": self.status,
                "billing_history_archive_error": self.error,
                "billing_history_year_results": self.data['years']}

    async def async_request(self, year):
        if self.busy:
            raise ValueError("History download already running")
        if str(year) in self.data['years']:
            self.status, self.error = "cached", None
            self.notify()
            return
        self.busy, self.status, self.error = True, "loading", None
        self.notify()
        self.hass.async_create_task(self._async_fetch(year))

    async def _async_fetch(self, year):
        try:
            groups = {str(m.id_local): [] for m in self.meters.ppg_list}
            seen = set()
            discovered = set()
            result = "page_limit"
            for page in range(1, MAX_PAGES + 1):
                # invoice_page uses only the session already held in memory. No retry/login.
                response = await self.hass.async_add_executor_job(self.api.invoice_page, page)
                invoices = response.invoices_list
                if not invoices:
                    result = "end_of_list"
                    break
                signature = tuple(sorted(inv.number for inv in invoices))
                if signature in seen:
                    result = "repeated_page"
                    break
                seen.add(signature)
                for inv in invoices:
                    if inv.end_date and inv.end_date.year >= 2000:
                        discovered.add(inv.end_date.year)
                for meter in self.meters.ppg_list:
                    rows = billing_history(invoices, meter.id_local)
                    groups[str(meter.id_local)].extend(row for row in rows if row['period_end'].startswith(str(year)+'-'))
                if len(invoices) < 12:
                    result = "end_of_list"
                    break
                await asyncio.sleep(1)
            total = 0
            for key, rows in groups.items():
                self.data['meters'][key] = merge_rows(self.data['meters'].get(key, []), rows)
                total += len(rows)
            self.data['years'][str(year)] = {"documents": total, "stop_reason": result,
                "pages": page, "available_years": sorted(discovered),
                "fetched_at": datetime.now(timezone.utc).isoformat()}
            await self.store.async_save(self.data)
            self.status = "ready" if result == "end_of_list" else "limited"
        except Exception:
            # Do not expose server responses, account details or tokens through logs/state.
            self.status, self.error = "error", "download_failed_no_retry"
        finally:
            self.busy = False
            self.notify()

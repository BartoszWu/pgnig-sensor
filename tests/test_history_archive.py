from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.pgnig_gas_sensor.history_archive import BillingArchive, merge_rows
from custom_components.pgnig_gas_sensor.PgnigApi import PgnigApi
from custom_components.pgnig_gas_sensor.auth.exceptions import SessionExpiredError
from .builders import make_invoice, build_meter_list


def api():
    auth=Mock(cached_token='SYNTHETIC-TOKEN')
    with patch('custom_components.pgnig_gas_sensor.PgnigApi.AuthRegistry.get',return_value=Mock(return_value=auth)):
        return PgnigApi('synthetic','synthetic','api_login'),auth


def test_archive_http_never_authenticates_or_retries():
    instance,auth=api()
    auth.session.get.return_value.ok=False
    auth.session.get.return_value.status_code=401
    with pytest.raises(RuntimeError,match='no retry'):
        instance.invoice_page(2)
    auth.login.assert_not_called()
    auth.session.get.assert_called_once()
    assert 'pageNumber=2&' in auth.session.get.call_args.args[0]
    auth.cached_token=None
    with pytest.raises(SessionExpiredError):instance.invoice_page(3)
    auth.login.assert_not_called()
    assert auth.session.get.call_count==1


@pytest.mark.asyncio
async def test_archive_fetches_requested_year_restores_and_does_not_change_current_invoices(hass):
    inv=make_invoice(number='SYNTHETIC',start_date=datetime(2023,1,1),end_date=datetime(2023,1,31))
    client=Mock();client.invoice_page.return_value=SimpleNamespace(invoices_list=[inv])
    archive=BillingArchive(hass,'synthetic',client,build_meter_list('METER1'),Mock())
    await archive.async_request(2023)
    await hass.async_block_till_done()
    assert archive.status=='ready'
    assert len(archive.rows(1))==1
    assert set(archive.rows(1)[0])=={'period_start','period_end','issued_on','m3','kwh','gross_amount','kind'}
    assert archive.rows(1)[0]['period_end']=='2023-01-31'
    client.invoices.assert_not_called()
    restored=BillingArchive(hass,'synthetic',client,build_meter_list('METER1'),Mock())
    await restored.async_restore()
    assert restored.rows(1)==archive.rows(1)
    await restored.async_request(2023)
    assert restored.status=='cached' and client.invoice_page.call_count==1


@pytest.mark.asyncio
async def test_failed_fetch_retains_archive_and_reports_no_private_error(hass):
    client=Mock();client.invoice_page.side_effect=RuntimeError('PRIVATE-TOKEN')
    archive=BillingArchive(hass,'synthetic-error',client,build_meter_list('METER1'),Mock())
    archive.busy=True
    with pytest.raises(ValueError):await archive.async_request(2023)
    archive.busy=False
    await archive.async_request(2024)
    await hass.async_block_till_done()
    assert archive.status=='error' and not archive.busy
    assert archive.error=='download_failed_no_retry'
    assert archive.data['years']=={}
    client.invoice_page.assert_called_once()


@pytest.mark.asyncio
async def test_repeated_page_stops_without_claiming_full_history(hass):
    inv=make_invoice(number='SYNTHETIC')
    client=Mock();client.invoice_page.return_value=SimpleNamespace(invoices_list=[inv]*12)
    archive=BillingArchive(hass,'synthetic-repeat',client,build_meter_list('METER1'),Mock())
    with patch('custom_components.pgnig_gas_sensor.history_archive.asyncio.sleep',new=AsyncMock()):
        await archive.async_request(2022)
        await hass.async_block_till_done()
    assert client.invoice_page.call_count==2
    assert archive.status=='limited'
    assert archive.data['years']['2022']['stop_reason']=='repeated_page'


def test_merge_preserves_distinct_identical_documents_within_one_page():
    row={'period_start':'2023-01-01','period_end':'2023-01-31','issued_on':'2023-02-01','m3':1}
    assert len(merge_rows([row,row],[row]))==2

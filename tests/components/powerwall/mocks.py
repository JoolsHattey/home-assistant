"""Mocks for powerwall."""

import asyncio
import json
import os
from unittest.mock import MagicMock

import pypowerwall

# Import our compatibility types from models
from homeassistant.components.powerwall.models import (
    BatteryResponse,
    DeviceType,
    GridStatus,
    MetersAggregatesResponse,
    PowerwallStatusResponse,
    SiteInfoResponse,
    SiteMasterResponse,
)

from homeassistant.core import HomeAssistant
from homeassistant.util.json import JsonValueType

from tests.common import load_fixture

MOCK_GATEWAY_DIN = "111-0----2-000000000FFA"


async def _mock_powerwall_with_fixtures(
    hass: HomeAssistant, empty_meters: bool = False
) -> MagicMock:
    """Mock data used to build powerwall state."""
    async with asyncio.TaskGroup() as tg:
        meters_file = "meters_empty.json" if empty_meters else "meters.json"
        meters = tg.create_task(_async_load_json_fixture(hass, meters_file))
        sitemaster = tg.create_task(_async_load_json_fixture(hass, "sitemaster.json"))
        site_info = tg.create_task(_async_load_json_fixture(hass, "site_info.json"))
        status = tg.create_task(_async_load_json_fixture(hass, "status.json"))
        device_type = tg.create_task(_async_load_json_fixture(hass, "device_type.json"))
        batteries = tg.create_task(_async_load_json_fixture(hass, "batteries.json"))

    return await _mock_powerwall_return_value(
        site_info=SiteInfoResponse.from_dict(site_info.result()),
        charge=47.34587394586,
        sitemaster=SiteMasterResponse.from_dict(sitemaster.result()),
        meters=MetersAggregatesResponse.from_dict(meters.result()),
        grid_services_active=True,
        grid_status=GridStatus.CONNECTED,
        status=PowerwallStatusResponse.from_dict(status.result()),
        device_type=DeviceType(device_type.result()["device_type"]),
        serial_numbers=["TG0123456789AB", "TG9876543210BA"],
        backup_reserve_percentage=15.0,
        batteries=[
            BatteryResponse.from_dict(battery) for battery in batteries.result()
        ],
    )


async def _mock_powerwall_return_value(
    site_info=None,
    charge=None,
    sitemaster=None,
    meters=None,
    grid_services_active=None,
    grid_status=None,
    status=None,
    device_type=None,
    serial_numbers=None,
    backup_reserve_percentage=None,
    batteries=None,
):
    powerwall_mock = MagicMock(spec=pypowerwall.Powerwall)
    
    # Mock pypowerwall methods (synchronous, not async)
    powerwall_mock.site.return_value = site_info._raw if site_info else {}
    powerwall_mock.level.return_value = charge
    powerwall_mock.grid.return_value = meters._raw if meters else {}
    powerwall_mock.grid_status.return_value = grid_status.grid_status if grid_status else "Unknown"
    powerwall_mock.status.return_value = status._raw if status else {}
    powerwall_mock.vitals.return_value = {}
    powerwall_mock.version.return_value = status._raw.get("version", "Unknown") if status else "Unknown"
    powerwall_mock.get_reserve.return_value = backup_reserve_percentage
    powerwall_mock.din.return_value = MOCK_GATEWAY_DIN
    
    # Mock battery blocks
    battery_blocks = {}
    if batteries:
        for i, battery in enumerate(batteries):
            battery_blocks[f"battery_{i}"] = battery._raw if hasattr(battery, '_raw') else {"serial_number": f"TEST{i}"}
    powerwall_mock.battery_blocks.return_value = battery_blocks
    
    # Mock connection methods
    powerwall_mock.is_connected.return_value = True
    powerwall_mock.connect.return_value = True
    
    # Mock TEDAPI detection (assume PW2 for tests unless specified)
    powerwall_mock.tedapi_mode = False

    return powerwall_mock


async def _mock_powerwall_site_name(hass: HomeAssistant, site_name: str) -> MagicMock:
    powerwall_mock = MagicMock(spec=pypowerwall.Powerwall)

    site_info_data = await _async_load_json_fixture(hass, "site_info.json")
    site_info_data["site_name"] = site_name
    
    powerwall_mock.site.return_value = site_info_data
    powerwall_mock.din.return_value = MOCK_GATEWAY_DIN
    powerwall_mock.is_connected.return_value = True

    return powerwall_mock


async def _mock_powerwall_side_effect(site_info=None):
    powerwall_mock = MagicMock(spec=pypowerwall.Powerwall)

    powerwall_mock.site.side_effect = site_info
    powerwall_mock.is_connected.return_value = True
    return powerwall_mock


async def _async_load_json_fixture(hass: HomeAssistant, path: str) -> JsonValueType:
    fixture = await hass.async_add_executor_job(
        load_fixture, os.path.join("powerwall", path)
    )
    return json.loads(fixture)

"""The Tesla Powerwall integration."""

from __future__ import annotations

from contextlib import AsyncExitStack
from datetime import timedelta
import logging

from aiohttp import CookieJar
from yarl import URL

# Import pypowerwall library (replacing tesla_powerwall)
import pypowerwall

# Define compatibility exceptions for pypowerwall
class AccessDeniedError(Exception):
    """Access denied error for pypowerwall compatibility."""

class ApiError(Exception):
    """API error for pypowerwall compatibility."""

class MissingAttributeError(Exception):
    """Missing attribute error for pypowerwall compatibility."""

class PowerwallUnreachableError(Exception):
    """Powerwall unreachable error for pypowerwall compatibility."""

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.network import is_ip_address

from .const import (
    AUTH_COOKIE_KEY,
    CONFIG_ENTRY_COOKIE,
    DOMAIN,
    POWERWALL_API_CHANGED,
    POWERWALL_COORDINATOR,
    UPDATE_INTERVAL,
)
from .models import (
    PowerwallBaseInfo,
    PowerwallConfigEntry,
    PowerwallData,
    PowerwallRuntimeData,
)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]

_LOGGER = logging.getLogger(__name__)

API_CHANGED_ERROR_BODY = (
    "It seems like your powerwall uses an unsupported version. "
    "Please update the software of your powerwall or if it is "
    "already the newest consider reporting this issue.\nSee logs for more information"
)
API_CHANGED_TITLE = "Unknown powerwall software version"


class PowerwallDataManager:
    """Class to manager powerwall data and relogin on failure."""

    def __init__(
        self,
        hass: HomeAssistant,
        power_wall: pypowerwall.Powerwall,
        cookie_jar: CookieJar,
        entry: PowerwallConfigEntry,
        ip_address: str,
        password: str | None,
        runtime_data: PowerwallRuntimeData,
    ) -> None:
        """Init the data manager."""
        self.hass = hass
        self.ip_address = ip_address
        self.password = password
        self.runtime_data = runtime_data
        self.power_wall = power_wall
        self.cookie_jar = cookie_jar
        self.entry = entry

    @property
    def api_changed(self) -> int:
        """Return true if the api has changed out from under us."""
        return self.runtime_data[POWERWALL_API_CHANGED]

    async def _recreate_powerwall_login(self) -> None:
        """Recreate the login on auth failure."""
        # pypowerwall handles authentication internally through connect()
        # Recreate the connection to re-authenticate
        try:
            self.power_wall.connect()
        except Exception as err:
            raise AccessDeniedError("Failed to reconnect to Powerwall") from err

    async def async_update_data(self) -> PowerwallData:
        """Fetch data from API endpoint."""
        # Check if we had an error before
        _LOGGER.debug("Checking if update failed")
        if self.api_changed:
            raise UpdateFailed("The powerwall api has changed")
        return await self._update_data()

    async def _update_data(self) -> PowerwallData:
        """Fetch data from API endpoint."""
        _LOGGER.debug("Updating data")
        for attempt in range(2):
            try:
                if attempt == 1:
                    await self._recreate_powerwall_login()
                data = await _fetch_powerwall_data(self.power_wall)
            except (TimeoutError, PowerwallUnreachableError) as err:
                raise UpdateFailed("Unable to fetch data from powerwall") from err
            except MissingAttributeError as err:
                _LOGGER.error("The powerwall api has changed: %s", str(err))
                # The error might include some important information
                # about what exactly changed.
                persistent_notification.create(
                    self.hass, API_CHANGED_ERROR_BODY, API_CHANGED_TITLE
                )
                self.runtime_data[POWERWALL_API_CHANGED] = True
                raise UpdateFailed("The powerwall api has changed") from err
            except AccessDeniedError as err:
                if attempt == 1:
                    # failed to authenticate => the credentials must be wrong
                    raise ConfigEntryAuthFailed from err
                if self.password is None:
                    raise ConfigEntryAuthFailed from err
                _LOGGER.debug("Access denied, trying to reauthenticate")
                # there is still an attempt left to authenticate,
                # so we continue in the loop
            except ApiError as err:
                raise UpdateFailed(f"Updated failed due to {err}, will retry") from err
            else:
                return data
        raise RuntimeError("unreachable")

    @callback
    def save_auth_cookie(self) -> None:
        """Save the auth cookie."""
        # pypowerwall handles authentication differently, 
        # we'll keep this method for compatibility but it's essentially a no-op
        _LOGGER.debug("pypowerwall handles authentication internally")


async def _create_powerwall(ip_address: str, password: str | None, http_session=None) -> pypowerwall.Powerwall:
    """Create a Powerwall instance using pypowerwall library."""
    # pypowerwall doesn't use http_session in the same way
    # Initialize with basic parameters and let it auto-detect the connection mode
    powerwall = pypowerwall.Powerwall(
        host=ip_address,
        password=password or "",
        timeout=10,
        auto_select=True,  # Auto-detect connection mode (Local/TEDAPI)
        retry_modes=True,  # Try different connection modes
    )
    
    # Connect to determine the appropriate mode for this Powerwall
    if not powerwall.is_connected():
        try:
            powerwall.connect()
        except Exception as err:
            raise PowerwallUnreachableError(f"Could not connect to Powerwall at {ip_address}") from err
    
    return powerwall


async def async_setup_entry(hass: HomeAssistant, entry: PowerwallConfigEntry) -> bool:
    """Set up Tesla Powerwall from a config entry."""
    ip_address: str = entry.data[CONF_IP_ADDRESS]

    password: str | None = entry.data.get(CONF_PASSWORD)

    cookie_jar: CookieJar = CookieJar(unsafe=True)
    use_auth_cookie: bool = False
    # Try to reuse the auth cookie
    auth_cookie_value: str | None = entry.data.get(CONFIG_ENTRY_COOKIE)
    if auth_cookie_value:
        cookie_jar.update_cookies(
            {AUTH_COOKIE_KEY: auth_cookie_value},
            URL(f"http://{ip_address}"),
        )
        _LOGGER.debug("Using existing auth cookie")
        use_auth_cookie = True

    http_session = async_create_clientsession(
        hass, verify_ssl=False, cookie_jar=cookie_jar
    )

    async with AsyncExitStack() as stack:
        power_wall = await _create_powerwall(ip_address, password)
        # No need for stack cleanup with pypowerwall as it manages connections differently

        for tries in range(2):
            try:
                base_info = await _login_and_fetch_base_info(
                    power_wall, ip_address, password, use_auth_cookie
                )

                # No stack cleanup needed with pypowerwall
                break
            except (TimeoutError, PowerwallUnreachableError) as err:
                raise ConfigEntryNotReady from err
            except MissingAttributeError as err:
                # The error might include some important information about what exactly changed.
                _LOGGER.error("The powerwall api has changed: %s", str(err))
                persistent_notification.async_create(
                    hass, API_CHANGED_ERROR_BODY, API_CHANGED_TITLE
                )
                return False
            except AccessDeniedError as err:
                if use_auth_cookie and tries == 0:
                    _LOGGER.debug(
                        "Authentication failed with cookie, retrying with password"
                    )
                    use_auth_cookie = False
                    continue
                _LOGGER.debug("Authentication failed", exc_info=err)
                raise ConfigEntryAuthFailed from err
            except ApiError as err:
                raise ConfigEntryNotReady from err

    gateway_din = base_info.gateway_din
    if entry.unique_id is not None and is_ip_address(entry.unique_id):
        hass.config_entries.async_update_entry(entry, unique_id=gateway_din)

    runtime_data = PowerwallRuntimeData(
        api_changed=False,
        base_info=base_info,
        coordinator=None,
        api_instance=power_wall,
    )

    manager = PowerwallDataManager(
        hass,
        power_wall,
        cookie_jar,
        entry,
        ip_address,
        password,
        runtime_data,
    )
    manager.save_auth_cookie()

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name="Powerwall site",
        update_method=manager.async_update_data,
        update_interval=timedelta(seconds=UPDATE_INTERVAL),
        always_update=False,
    )

    await coordinator.async_config_entry_first_refresh()

    runtime_data[POWERWALL_COORDINATOR] = coordinator

    entry.runtime_data = runtime_data

    await async_migrate_entity_unique_ids(hass, entry, base_info)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_migrate_entity_unique_ids(
    hass: HomeAssistant, entry: PowerwallConfigEntry, base_info: PowerwallBaseInfo
) -> None:
    """Migrate old entity unique ids to use gateway_din."""
    old_base_unique_id = "_".join(base_info.serial_numbers)
    new_base_unique_id = base_info.gateway_din

    dev_reg = dr.async_get(hass)
    if device := dev_reg.async_get_device(identifiers={(DOMAIN, old_base_unique_id)}):
        dev_reg.async_update_device(
            device.id, new_identifiers={(DOMAIN, new_base_unique_id)}
        )

    ent_reg = er.async_get(hass)
    for ent_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        current_unique_id = ent_entry.unique_id
        if current_unique_id.startswith(old_base_unique_id):
            unique_id_postfix = current_unique_id.removeprefix(old_base_unique_id)
            new_unique_id = f"{new_base_unique_id}{unique_id_postfix}"
            ent_reg.async_update_entity(
                ent_entry.entity_id, new_unique_id=new_unique_id
            )


async def _login_and_fetch_base_info(
    power_wall: pypowerwall.Powerwall, host: str, password: str | None, use_auth_cookie: bool
) -> PowerwallBaseInfo:
    """Login to the powerwall and fetch the base info."""
    # pypowerwall handles authentication automatically in connect()
    # No explicit login needed as it's handled during initialization
    return await _call_base_info(power_wall, host)


async def _call_base_info(power_wall: pypowerwall.Powerwall, host: str) -> PowerwallBaseInfo:
    """Return PowerwallBaseInfo for the device."""
    # Get basic information from pypowerwall (run synchronous calls in executor)
    try:
        gateway_din = power_wall.din() or "unknown"
        site_data = power_wall.site() or {}
        status_data = power_wall.status() or {}
        vitals_data = power_wall.vitals() or {}
        version_info = power_wall.version() or "Unknown"
        battery_data = power_wall.battery_blocks() or {}
        
        # Create compatible response objects
        site_info = SiteInfoResponse.from_dict(site_data)
        status = PowerwallStatusResponse.from_dict({"version": version_info})
        
        # Determine device type based on available data or connection mode
        device_type_name = "PowerWall 3" if hasattr(power_wall, 'tedapi_mode') and power_wall.tedapi_mode else "PowerWall 2"
        device_type = DeviceType.from_string(device_type_name)
        
        # Extract serial numbers from vitals or battery data
        serial_numbers = []
        if isinstance(battery_data, dict):
            for battery_info in battery_data.values():
                if isinstance(battery_info, dict) and "serial_number" in battery_info:
                    serial_numbers.append(battery_info["serial_number"])
        
        # If no serials from batteries, try to get from other sources
        if not serial_numbers and isinstance(vitals_data, dict):
            # Look for serial numbers in vitals data structure
            for key, value in vitals_data.items():
                if "serial" in key.lower() and isinstance(value, str):
                    serial_numbers.append(value)
        
        # Fallback to gateway DIN if no other serials found
        if not serial_numbers:
            serial_numbers = [gateway_din]
        
        # Create battery responses
        batteries = {}
        if isinstance(battery_data, dict):
            for i, (battery_id, battery_info) in enumerate(battery_data.items()):
                if isinstance(battery_info, dict):
                    battery_response = BatteryResponse.from_dict(battery_info)
                    batteries[battery_response.serial_number] = battery_response
        
        return PowerwallBaseInfo(
            gateway_din=gateway_din,
            site_info=site_info,
            status=status,
            device_type=device_type,
            serial_numbers=sorted(serial_numbers),
            url=f"https://{host}",
            batteries=batteries,
        )
    except Exception as err:
        raise MissingAttributeError(f"Failed to fetch powerwall base info: {err}") from err


async def get_backup_reserve_percentage(power_wall: pypowerwall.Powerwall) -> float | None:
    """Return the backup reserve percentage."""
    try:
        # pypowerwall.get_reserve() is synchronous
        return power_wall.get_reserve()
    except Exception:
        return None


async def _fetch_powerwall_data(power_wall: pypowerwall.Powerwall) -> PowerwallData:
    """Process and update powerwall data."""
    # pypowerwall methods are synchronous
    try:
        backup_reserve = await get_backup_reserve_percentage(power_wall)
        charge = power_wall.level() or 0.0
        
        # Get raw data and create compatible responses
        site_master_data = power_wall.site() or {}
        meters_data = power_wall.grid() or {}  # pypowerwall.grid() gives meter data
        grid_status_data = power_wall.grid_status() or "Unknown"
        battery_data = power_wall.battery_blocks() or {}
        
        # Create compatible response objects
        site_master = SiteMasterResponse.from_dict(site_master_data)
        meters = MetersAggregatesResponse.from_dict(meters_data)
        grid_status = GridStatus.from_string(grid_status_data)
        
        # Grid services active - check if available in pypowerwall
        grid_services_active = False  # Default for now, may need to derive from other data
        
        # Convert battery data to compatible format
        batteries = {}
        if isinstance(battery_data, dict):
            for battery_id, battery_info in battery_data.items():
                if isinstance(battery_info, dict):
                    battery_response = BatteryResponse.from_dict(battery_info)
                    batteries[battery_response.serial_number] = battery_response
        
        return PowerwallData(
            charge=charge,
            site_master=site_master,
            meters=meters,
            grid_services_active=grid_services_active,
            grid_status=grid_status,
            backup_reserve=backup_reserve,
            batteries=batteries,
        )
    except Exception as err:
        raise MissingAttributeError(f"Failed to fetch powerwall data: {err}") from err


@callback
def async_last_update_was_successful(
    hass: HomeAssistant, entry: PowerwallConfigEntry
) -> bool:
    """Return True if the last update was successful."""
    return bool(
        hasattr(entry, "runtime_data")
        and (runtime_data := entry.runtime_data)
        and (coordinator := runtime_data.get(POWERWALL_COORDINATOR))
        and coordinator.last_update_success
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

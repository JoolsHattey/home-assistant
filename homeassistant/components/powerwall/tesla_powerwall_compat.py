"""Compatibility wrapper to make pypowerwall work with tesla-powerwall interface."""

from __future__ import annotations

import asyncio
from typing import Any

import pypowerwall


# Exception classes to match tesla-powerwall
class AccessDeniedError(Exception):
    """Access denied error."""


class PowerwallUnreachableError(Exception):
    """Powerwall unreachable error."""


class MissingAttributeError(Exception):
    """Missing attribute error."""


class ApiError(Exception):
    """General API error."""


# Enum-like classes to match tesla-powerwall
class DeviceType:
    """Device type enum."""
    
    def __init__(self, device_type: str):
        self.name = device_type
        self.value = device_type


class GridStatus:
    """Grid status enum."""
    
    CONNECTED = "grid_connected"
    TRANSITION_TO_GRID = "transition_to_grid"
    ISLANDED = "islanded"
    TRANSITION_TO_ISLAND = "transition_to_island"


class GridStateMeta(type):
    """Metaclass for GridState to make it iterable."""
    
    def __iter__(cls):
        return iter([cls.CONNECTED, cls.ISLANDED, cls.TRANSITION_TO_GRID, cls.TRANSITION_TO_ISLAND])


class GridState(metaclass=GridStateMeta):
    """Grid state enum."""
    
    CONNECTED = None
    ISLANDED = None
    TRANSITION_TO_GRID = None
    TRANSITION_TO_ISLAND = None
    
    def __init__(self, value: str):
        self.value = value
    
    def __init_subclass__(cls):
        # Initialize the class constants
        cls.CONNECTED = cls("connected")
        cls.ISLANDED = cls("islanded")
        cls.TRANSITION_TO_GRID = cls("transition_to_grid")
        cls.TRANSITION_TO_ISLAND = cls("transition_to_island")


# Initialize the constants
GridState.CONNECTED = GridState("connected")
GridState.ISLANDED = GridState("islanded")
GridState.TRANSITION_TO_GRID = GridState("transition_to_grid")
GridState.TRANSITION_TO_ISLAND = GridState("transition_to_island")


class MeterType:
    """Meter type enum."""
    
    BATTERY = "battery"
    SOLAR = "solar"  
    LOAD = "load"
    SITE = "site"


class IslandMode:
    """Island mode enum."""
    
    OFFGRID = "offgrid"
    ONGRID = "ongrid"


class PowerwallError(Exception):
    """Powerwall error."""


class LoginResponse:
    """Login response."""
    
    def __init__(self, data: dict[str, Any]):
        self._raw = data


# Response classes to match tesla-powerwall
class SiteInfoResponse:
    """Site info response."""
    
    def __init__(self, data: dict[str, Any]):
        self._raw = data
        self.site_name = data.get("site_name", "Unknown")
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SiteInfoResponse:
        return cls(data)


class PowerwallStatusResponse:
    """Powerwall status response."""
    
    def __init__(self, data: dict[str, Any]):
        self._raw = data
        self.version = data.get("version", "Unknown")
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PowerwallStatusResponse:
        return cls(data)


class BatteryResponse:
    """Battery response."""
    
    def __init__(self, data: dict[str, Any]):
        self._raw = data
        self.serial_number = data.get("serial_number", "Unknown")
        self.part_number = data.get("part_number", "Unknown")
        self.energy_remaining = data.get("energy_remaining", 0)
        self.grid_state = GridState(data.get("grid_state", "unknown"))
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BatteryResponse:
        return cls(data)


class MeterResponse:
    """Meter response."""
    
    def __init__(self, data: dict[str, Any]):
        self._raw = data
        self.frequency = data.get("frequency", 0)
        self.instant_average_voltage = data.get("instant_average_voltage", 0)
    
    def get_power(self, precision: int = 3) -> float:
        """Get power with specified precision."""
        power = self._raw.get("instant_power", 0)
        return round(power, precision)
    
    def get_energy_exported(self) -> float:
        """Get energy exported."""
        return self._raw.get("energy_exported", 0)
    
    def get_energy_imported(self) -> float:
        """Get energy imported."""
        return self._raw.get("energy_imported", 0)


class MetersAggregatesResponse:
    """Meters aggregates response."""
    
    def __init__(self, data: dict[str, Any]):
        self._raw = data
        self.meters = []
        
        # Create meter responses from pypowerwall data
        for meter_type in ["battery", "solar", "load", "site"]:
            if meter_type in data:
                meter_data = data[meter_type]
                meter_data["type"] = meter_type
                self.meters.append(MeterResponse(meter_data))
    
    def get_meter(self, meter_type: str) -> MeterResponse | None:
        """Get meter by type."""
        for meter in self.meters:
            if meter._raw.get("type") == meter_type:
                return meter
        return None
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetersAggregatesResponse:
        return cls(data)


class SiteMasterResponse:
    """Site master response."""
    
    def __init__(self, data: dict[str, Any]):
        self._raw = data
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SiteMasterResponse:
        return cls(data)


class Powerwall:
    """Compatibility wrapper for pypowerwall to match tesla-powerwall interface."""
    
    def __init__(self, host: str, http_session=None):
        self.host = host
        self._pypowerwall = None
        self._session = http_session
    
    async def __aenter__(self):
        """Async context manager entry."""
        self._pypowerwall = pypowerwall.Powerwall(self.host)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        # pypowerwall doesn't need explicit cleanup
        pass
    
    async def login(self, password: str) -> None:
        """Login to powerwall."""
        if self._pypowerwall is None:
            self._pypowerwall = pypowerwall.Powerwall(self.host, password=password)
        # pypowerwall handles authentication internally
    
    async def get_site_info(self) -> SiteInfoResponse:
        """Get site information."""
        try:
            site_data = await asyncio.get_event_loop().run_in_executor(
                None, self._pypowerwall.site
            )
            site_name = await asyncio.get_event_loop().run_in_executor(
                None, self._pypowerwall.site_name
            )
            
            return SiteInfoResponse({"site_name": site_name, **site_data})
        except Exception as e:
            raise MissingAttributeError(str(e)) from e
    
    async def get_gateway_din(self) -> str:
        """Get gateway DIN."""
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._pypowerwall.din
            )
        except Exception as e:
            raise MissingAttributeError(str(e)) from e
    
    async def get_status(self) -> PowerwallStatusResponse:
        """Get powerwall status."""
        try:
            status_data = await asyncio.get_event_loop().run_in_executor(
                None, self._pypowerwall.status
            )
            version_data = await asyncio.get_event_loop().run_in_executor(
                None, self._pypowerwall.version
            )
            
            return PowerwallStatusResponse({
                "version": version_data,
                **status_data
            })
        except Exception as e:
            raise MissingAttributeError(str(e)) from e
    
    async def get_device_type(self) -> DeviceType:
        """Get device type."""
        # For pypowerwall, we can infer this or use a default
        return DeviceType("hec")  # Home Energy Controller
    
    async def get_serial_numbers(self) -> list[str]:
        """Get serial numbers."""
        try:
            # Try to get from battery data
            battery_data = await asyncio.get_event_loop().run_in_executor(
                None, self._pypowerwall.battery
            )
            # Extract serial numbers from battery data if available
            if isinstance(battery_data, dict) and "serial_number" in battery_data:
                return [battery_data["serial_number"]]
            return ["UNKNOWN"]
        except Exception:
            return ["UNKNOWN"]
    
    async def get_batteries(self) -> list[BatteryResponse]:
        """Get battery information."""
        try:
            battery_data = await asyncio.get_event_loop().run_in_executor(
                None, self._pypowerwall.battery
            )
            
            # Convert pypowerwall battery data to tesla-powerwall format
            if isinstance(battery_data, dict):
                return [BatteryResponse({
                    "serial_number": battery_data.get("serial_number", "UNKNOWN"),
                    "part_number": battery_data.get("part_number", "UNKNOWN"),
                    "energy_remaining": battery_data.get("energy_remaining", 0),
                    "grid_state": "connected"  # Default value
                })]
            return []
        except Exception as e:
            raise MissingAttributeError(str(e)) from e
    
    async def get_charge(self) -> float:
        """Get battery charge level."""
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._pypowerwall.level
            )
        except Exception as e:
            raise MissingAttributeError(str(e)) from e
    
    async def get_sitemaster(self) -> SiteMasterResponse:
        """Get site master data."""
        try:
            site_data = await asyncio.get_event_loop().run_in_executor(
                None, self._pypowerwall.site
            )
            return SiteMasterResponse(site_data)
        except Exception as e:
            raise MissingAttributeError(str(e)) from e
    
    async def get_meters(self) -> MetersAggregatesResponse:
        """Get meter data."""
        try:
            # Get data from all meter types
            battery_data = await asyncio.get_event_loop().run_in_executor(
                None, self._pypowerwall.battery
            )
            solar_data = await asyncio.get_event_loop().run_in_executor(
                None, self._pypowerwall.solar
            )
            home_data = await asyncio.get_event_loop().run_in_executor(
                None, self._pypowerwall.home
            )
            grid_data = await asyncio.get_event_loop().run_in_executor(
                None, self._pypowerwall.grid
            )
            
            meters_data = {
                "battery": battery_data,
                "solar": solar_data,
                "load": home_data,
                "site": grid_data
            }
            
            return MetersAggregatesResponse(meters_data)
        except Exception as e:
            raise MissingAttributeError(str(e)) from e
    
    async def get_grid_status(self) -> str:
        """Get grid status."""
        try:
            grid_status = await asyncio.get_event_loop().run_in_executor(
                None, self._pypowerwall.grid_status
            )
            
            # Map pypowerwall grid status to tesla-powerwall format
            if isinstance(grid_status, str):
                status_map = {
                    "connected": GridStatus.CONNECTED,
                    "islanded": GridStatus.ISLANDED,
                    "transition_to_grid": GridStatus.TRANSITION_TO_GRID,
                    "transition_to_island": GridStatus.TRANSITION_TO_ISLAND
                }
                return status_map.get(grid_status.lower(), GridStatus.CONNECTED)
            
            return GridStatus.CONNECTED
        except Exception as e:
            raise MissingAttributeError(str(e)) from e
    
    async def is_grid_services_active(self) -> bool:
        """Check if grid services are active."""
        # This might not be directly available in pypowerwall
        # Return a default value or try to infer from other data
        return False
    
    async def get_backup_reserve_percentage(self) -> float:
        """Get backup reserve percentage."""
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._pypowerwall.get_reserve
            )
        except Exception as e:
            raise MissingAttributeError(str(e)) from e
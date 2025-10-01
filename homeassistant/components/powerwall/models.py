"""The powerwall integration models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

import pypowerwall

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

type PowerwallConfigEntry = ConfigEntry[PowerwallRuntimeData]

# Compatibility types for pypowerwall (replacing tesla_powerwall response types)
@dataclass
class SiteInfoResponse:
    """Site info response compatibility."""
    site_name: str
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SiteInfoResponse:
        return cls(site_name=data.get("site_name", "Tesla Powerwall"))

@dataclass  
class PowerwallStatusResponse:
    """Powerwall status response compatibility."""
    version: str
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PowerwallStatusResponse:
        return cls(version=data.get("version", "Unknown"))

@dataclass
class BatteryResponse:
    """Battery response compatibility."""
    serial_number: str
    part_number: str = "Unknown"
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BatteryResponse:
        return cls(
            serial_number=data.get("serial_number", "Unknown"),
            part_number=data.get("part_number", "PowerWall")
        )

@dataclass
class DeviceType:
    """Device type compatibility."""
    name: str
    
    @classmethod
    def from_string(cls, device_type: str) -> DeviceType:
        return cls(name=device_type)

@dataclass
class GridStatus:
    """Grid status compatibility."""
    grid_status: str
    
    @classmethod
    def from_string(cls, status: str) -> GridStatus:
        return cls(grid_status=status)

@dataclass
class MetersAggregatesResponse:
    """Meters aggregates response compatibility."""
    data: dict[str, Any]
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetersAggregatesResponse:
        return cls(data=data)

@dataclass
class SiteMasterResponse:
    """Site master response compatibility."""
    data: dict[str, Any]
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SiteMasterResponse:
        return cls(data=data)


@dataclass
class PowerwallBaseInfo:
    """Base information for the powerwall integration."""

    gateway_din: str
    site_info: SiteInfoResponse
    status: PowerwallStatusResponse
    device_type: DeviceType
    serial_numbers: list[str]
    url: str
    batteries: dict[str, BatteryResponse]


@dataclass
class PowerwallData:
    """Point in time data for the powerwall integration."""

    charge: float
    site_master: SiteMasterResponse
    meters: MetersAggregatesResponse
    grid_services_active: bool
    grid_status: GridStatus
    backup_reserve: float | None
    batteries: dict[str, BatteryResponse]


class PowerwallRuntimeData(TypedDict):
    """Run time data for the powerwall."""

    coordinator: DataUpdateCoordinator[PowerwallData] | None
    api_instance: pypowerwall.Powerwall
    base_info: PowerwallBaseInfo
    api_changed: bool

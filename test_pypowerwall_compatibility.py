#!/usr/bin/env python3
"""Test script to check pypowerwall API compatibility."""

import sys

def test_imports():
    """Test that we can import everything we need from pypowerwall."""
    try:
        # Test main imports from __init__.py
        from pypowerwall import (
            AccessDeniedError,
            ApiError,
            MissingAttributeError,
            Powerwall,
            PowerwallUnreachableError,
        )
        print("✓ Main imports from __init__.py work")
        
        # Test model imports from models.py
        from pypowerwall import (
            BatteryResponse,
            DeviceType,
            GridStatus,
            MetersAggregatesResponse,
            PowerwallStatusResponse,
            SiteInfoResponse,
            SiteMasterResponse,
        )
        print("✓ Model imports from models.py work")
        
        # Test imports from config_flow.py
        from pypowerwall import (
            AccessDeniedError,
            MissingAttributeError,
            Powerwall,
            PowerwallUnreachableError,
            SiteInfoResponse,
        )
        print("✓ Config flow imports work")
        
        # Test imports from sensor.py
        from pypowerwall import GridState, MeterResponse, MeterType
        print("✓ Sensor imports work")
        
        # Test imports from switch.py
        from pypowerwall import GridStatus, IslandMode, PowerwallError
        print("✓ Switch imports work")
        
        # Test imports from binary_sensor.py
        from pypowerwall import GridStatus, MeterType
        print("✓ Binary sensor imports work")
        
        # Test error import from test files
        from pypowerwall.error import MissingAttributeError
        print("✓ Error module import works")
        
        # Test LoginResponse import
        from pypowerwall import LoginResponse
        print("✓ LoginResponse import works")
        
        return True
        
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False

def test_enum_values():
    """Test that enum values are compatible."""
    try:
        from pypowerwall import GridState, GridStatus, MeterType, DeviceType
        
        # Test that enum values exist as expected
        print(f"GridState values: {[state.value for state in GridState]}")
        print(f"GridStatus values: {[status.value for status in GridStatus]}")
        print(f"MeterType values: {[meter.value for meter in MeterType]}")
        
        # Test specific values used in the code
        assert hasattr(GridStatus, 'TRANSITION_TO_GRID')
        assert hasattr(GridStatus, 'CONNECTED')
        assert hasattr(GridStatus, 'TRANSITION_TO_ISLAND')
        assert hasattr(GridStatus, 'ISLANDED')
        assert hasattr(MeterType, 'BATTERY')
        
        print("✓ All required enum values exist")
        return True
        
    except Exception as e:
        print(f"✗ Enum test failed: {e}")
        return False

def main():
    """Run compatibility tests."""
    print("Testing pypowerwall compatibility...")
    
    import_success = test_imports()
    if not import_success:
        print("❌ Import tests failed")
        sys.exit(1)
    
    enum_success = test_enum_values()
    if not enum_success:
        print("❌ Enum tests failed")
        sys.exit(1)
    
    print("✅ All compatibility tests passed!")

if __name__ == "__main__":
    main()
"""
Unit tests for device management module.

Tests cover:
- Device registration from LoxAPP3.json structure
- State update functionality
- Device query methods with filters
- Unsupported device type handling
- Scene management
- Thread safety and error handling
"""

import pytest
from threading import Thread
import time

from loxone_mcp.device_manager import (
    DeviceManager,
    LoxoneDevice,
)


class TestLoxoneDevice:
    """Test LoxoneDevice data model."""

    def test_device_creation_with_all_fields(self):
        """Test creating a device with all fields populated."""
        device = LoxoneDevice(
            uuid="test-uuid-123",
            name="Test Device",
            type="Switch",
            room="Living Room",
            category="Lights",
            states={"value": 1, "active": True},
            details={"min": 0, "max": 1},
            controls={"on": "uuid-on", "off": "uuid-off"},
        )

        assert device.uuid == "test-uuid-123"
        assert device.name == "Test Device"
        assert device.type == "Switch"
        assert device.room == "Living Room"
        assert device.category == "Lights"
        # Check that the original states are present, ignoring automatic tracking fields
        expected_states = {"value": 1, "active": True}
        for key, value in expected_states.items():
            assert device.states[key] == value
        # Check that automatic tracking fields are present
        assert "_created_at" in device.states
        assert "_last_updated" in device.states
        assert "_reachable" in device.states
        assert device.details == {"min": 0, "max": 1}
        assert device.controls == {"on": "uuid-on", "off": "uuid-off"}

    def test_device_creation_with_minimal_fields(self):
        """Test creating a device with only required fields."""
        device = LoxoneDevice(
            uuid="minimal-uuid",
            name="Minimal Device",
            type="Dimmer",
            room="Bedroom",
            category="Lights",
        )

        assert device.uuid == "minimal-uuid"
        assert device.name == "Minimal Device"
        assert device.type == "Dimmer"
        assert device.room == "Bedroom"
        assert device.category == "Lights"
        # Check that automatic tracking fields are present even with minimal creation
        assert "_created_at" in device.states
        assert "_last_updated" in device.states
        assert "_reachable" in device.states
        # Should have exactly 3 automatic tracking fields
        assert len(device.states) == 3
        assert device.details == {}
        assert device.controls == {}

    def test_device_creation_empty_uuid_error(self):
        """Test that empty UUID raises ValueError."""
        with pytest.raises(ValueError, match="Device UUID cannot be empty"):
            LoxoneDevice(
                uuid="", name="Test Device", type="Switch", room="Living Room", category="Lights"
            )

    def test_device_creation_empty_name_error(self):
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="Device name cannot be empty"):
            LoxoneDevice(
                uuid="test-uuid", name="", type="Switch", room="Living Room", category="Lights"
            )

    def test_device_creation_empty_type_error(self):
        """Test that empty type raises ValueError."""
        with pytest.raises(ValueError, match="Device type cannot be empty"):
            LoxoneDevice(
                uuid="test-uuid", name="Test Device", type="", room="Living Room", category="Lights"
            )


class TestDeviceManagerInitialization:
    """Test DeviceManager initialization and basic properties."""

    def test_device_manager_initialization(self):
        """Test DeviceManager initializes with empty registries."""
        manager = DeviceManager()

        assert len(manager.devices) == 0
        assert manager.get_device_count() == 0
        assert manager.get_scene_count() == 0
        assert manager.get_device_types() == []
        assert manager.get_rooms() == []

    def test_devices_property_returns_copy(self):
        """Test that devices property returns a copy, not the original dict."""
        manager = DeviceManager()

        # Get devices dict
        devices_dict = manager.devices

        # Modify the returned dict
        devices_dict["test"] = "modified"

        # Original should be unchanged
        assert len(manager.devices) == 0
        assert "test" not in manager.devices


class TestDeviceManagerLoadDevices:
    """Test device loading from LoxAPP3.json structure."""

    def test_load_devices_empty_structure(self):
        """Test loading devices from empty structure."""
        manager = DeviceManager()
        manager.load_devices({})

        assert manager.get_device_count() == 0
        assert manager.get_scene_count() == 0

    def test_load_devices_none_structure(self):
        """Test loading devices from None structure."""
        manager = DeviceManager()
        manager.load_devices(None)

        assert manager.get_device_count() == 0
        assert manager.get_scene_count() == 0

    def test_load_devices_invalid_structure_type(self):
        """Test loading devices from invalid structure type."""
        manager = DeviceManager()
        manager.load_devices("not a dict")

        assert manager.get_device_count() == 0
        assert manager.get_scene_count() == 0

    def test_load_devices_with_supported_device_types(self):
        """Test loading devices with various supported device types."""
        loxapp_structure = {
            "rooms": {"room-1": {"name": "Living Room"}, "room-2": {"name": "Kitchen"}},
            "cats": {"cat-1": {"name": "Lights"}, "cat-2": {"name": "Blinds"}},
            "controls": {
                "device-1": {
                    "name": "Living Room Light",
                    "type": "Switch",
                    "room": "room-1",
                    "cat": "cat-1",
                    "uuidAction": "action-1",
                    "states": {"active": "state-1"},
                },
                "device-2": {
                    "name": "Kitchen Dimmer",
                    "type": "Dimmer",
                    "room": "room-2",
                    "cat": "cat-1",
                    "uuidAction": "action-2",
                    "states": {"position": "state-2"},
                },
                "device-3": {
                    "name": "Living Room Blinds",
                    "type": "Jalousie",
                    "room": "room-1",
                    "cat": "cat-2",
                    "uuidAction": "action-3",
                    "states": {"position": "state-3", "shadePosition": "state-4"},
                },
            },
        }

        manager = DeviceManager()
        manager.load_devices(loxapp_structure)

        assert manager.get_device_count() == 3

        # Check specific devices
        switch = manager.get_device("device-1")
        assert switch is not None
        assert switch.name == "Living Room Light"
        assert switch.type == "Switch"
        assert switch.room == "Living Room"
        assert switch.category == "Lights"
        assert switch.controls == {"active": "state-1"}

        dimmer = manager.get_device("device-2")
        assert dimmer is not None
        assert dimmer.name == "Kitchen Dimmer"
        assert dimmer.type == "Dimmer"
        assert dimmer.room == "Kitchen"

        jalousie = manager.get_device("device-3")
        assert jalousie is not None
        assert jalousie.name == "Living Room Blinds"
        assert jalousie.type == "Jalousie"
        assert jalousie.controls == {"position": "state-3", "shadePosition": "state-4"}

    def test_load_devices_with_unsupported_device_types(self):
        """Test that unsupported device types are skipped."""
        loxapp_structure = {
            "rooms": {"room-1": {"name": "Living Room"}},
            "cats": {"cat-1": {"name": "Unknown"}},
            "controls": {
                "device-1": {
                    "name": "Supported Switch",
                    "type": "Switch",
                    "room": "room-1",
                    "cat": "cat-1",
                },
                "device-2": {
                    "name": "Unsupported Device",
                    "type": "UnsupportedType",
                    "room": "room-1",
                    "cat": "cat-1",
                },
                "device-3": {
                    "name": "Another Unsupported",
                    "type": "AnotherUnsupportedType",
                    "room": "room-1",
                    "cat": "cat-1",
                },
            },
        }

        manager = DeviceManager()
        manager.load_devices(loxapp_structure)

        # Only the supported device should be registered
        assert manager.get_device_count() == 1

        device = manager.get_device("device-1")
        assert device is not None
        assert device.name == "Supported Switch"
        assert device.type == "Switch"

        # Unsupported devices should not be registered
        assert manager.get_device("device-2") is None
        assert manager.get_device("device-3") is None

    def test_load_devices_with_missing_room_and_category(self):
        """Test loading devices when room and category info is missing."""
        loxapp_structure = {
            "controls": {
                "device-1": {
                    "name": "Device Without Room",
                    "type": "Switch",
                    # No room or cat specified
                }
            }
        }

        manager = DeviceManager()
        manager.load_devices(loxapp_structure)

        assert manager.get_device_count() == 1

        device = manager.get_device("device-1")
        assert device is not None
        assert device.name == "Device Without Room"
        assert device.room == "Unknown Room"
        assert device.category == "Unknown Category"

    def test_load_devices_with_device_details(self):
        """Test loading devices with detailed configuration."""
        loxapp_structure = {
            "controls": {
                "device-1": {
                    "name": "Detailed Device",
                    "type": "Dimmer",
                    "uuidAction": "action-uuid",
                    "defaultRating": 5,
                    "isFavorite": True,
                    "isSecured": False,
                    "details": {"min": 0, "max": 100, "step": 1, "format": "%.1f%%"},
                    "states": {"position": "state-position", "active": "state-active"},
                }
            }
        }

        manager = DeviceManager()
        manager.load_devices(loxapp_structure)

        device = manager.get_device("device-1")
        assert device is not None

        # Check basic details
        assert device.details["uuidAction"] == "action-uuid"
        assert device.details["defaultRating"] == 5
        assert device.details["isFavorite"] is True
        assert device.details["isSecured"] is False

        # Check extended details
        assert device.details["min"] == 0
        assert device.details["max"] == 100
        assert device.details["step"] == 1
        assert device.details["format"] == "%.1f%%"

        # Check controls
        assert device.controls["position"] == "state-position"
        assert device.controls["active"] == "state-active"

    def test_load_devices_with_scenes(self):
        """Test loading scenes from autopilot section."""
        loxapp_structure = {
            "rooms": {"room-1": {"name": "Living Room"}},
            "cats": {"cat-1": {"name": "Scenes"}},
            "autopilot": {
                "states": {
                    "scene-1": {
                        "name": "Movie Night",
                        "room": "room-1",
                        "cat": "cat-1",
                        "description": "Dim lights for movie watching",
                        "isFavorite": True,
                        "isSecured": False,
                    },
                    "scene-2": {
                        "name": "Good Morning",
                        "description": "Morning routine scene",
                        # No room or cat specified
                    },
                }
            },
        }

        manager = DeviceManager()
        manager.load_devices(loxapp_structure)

        assert manager.get_scene_count() == 2

        # Check first scene
        scene1 = manager.get_scene("scene-1")
        assert scene1 is not None
        assert scene1.name == "Movie Night"
        assert scene1.type == "Scene"
        assert scene1.room == "Living Room"
        assert scene1.category == "Scenes"
        assert scene1.details["description"] == "Dim lights for movie watching"
        assert scene1.details["isFavorite"] is True
        assert scene1.details["isSecured"] is False

        # Check second scene with defaults
        scene2 = manager.get_scene("scene-2")
        assert scene2 is not None
        assert scene2.name == "Good Morning"
        assert scene2.room == "Unknown Room"
        assert scene2.category == "Scenes"
        assert scene2.details["description"] == "Morning routine scene"

    def test_load_devices_clears_existing_devices(self):
        """Test that loading devices clears previously loaded devices."""
        # First load
        first_structure = {"controls": {"device-1": {"name": "First Device", "type": "Switch"}}}

        manager = DeviceManager()
        manager.load_devices(first_structure)
        assert manager.get_device_count() == 1
        assert manager.get_device("device-1") is not None

        # Second load should clear first devices
        second_structure = {"controls": {"device-2": {"name": "Second Device", "type": "Dimmer"}}}

        manager.load_devices(second_structure)
        assert manager.get_device_count() == 1
        assert manager.get_device("device-1") is None  # Should be cleared
        assert manager.get_device("device-2") is not None  # Should be present


class TestDeviceManagerStateManagement:
    """Test device state update functionality."""

    def test_update_state_valid_device(self):
        """Test updating state for a valid device."""
        manager = DeviceManager()

        # Add a device first
        loxapp_structure = {"controls": {"device-1": {"name": "Test Device", "type": "Switch"}}}
        manager.load_devices(loxapp_structure)

        # Update state
        state_data = {"active": True, "value": 1}
        manager.update_state("device-1", state_data)

        # Verify state was updated
        device = manager.get_device("device-1")
        # Check that the original states are present, ignoring automatic tracking fields
        for key, value in state_data.items():
            assert device.states[key] == value
        # Check that automatic tracking fields are present
        assert "_created_at" in device.states
        assert "_last_updated" in device.states
        assert "_reachable" in device.states

        # Verify get_device_state returns the data (including automatic tracking fields)
        retrieved_state = manager.get_device_state("device-1")
        # Check that the original states are present
        for key, value in state_data.items():
            assert retrieved_state[key] == value
        # Check that automatic tracking fields are present
        assert "_created_at" in retrieved_state
        assert "_last_updated" in retrieved_state
        assert "_reachable" in retrieved_state

    def test_update_state_unknown_device(self):
        """Test updating state for an unknown device (should not crash)."""
        manager = DeviceManager()

        # Update state for non-existent device
        state_data = {"active": True}
        manager.update_state("unknown-device", state_data)

        # Should not crash and device count should remain 0
        assert manager.get_device_count() == 0

    def test_update_state_empty_uuid(self):
        """Test updating state with empty UUID."""
        manager = DeviceManager()

        state_data = {"active": True}
        manager.update_state("", state_data)
        manager.update_state(None, state_data)

        # Should not crash
        assert manager.get_device_count() == 0

    def test_update_state_empty_state_data(self):
        """Test updating state with empty state data."""
        manager = DeviceManager()

        # Add a device first
        loxapp_structure = {"controls": {"device-1": {"name": "Test Device", "type": "Switch"}}}
        manager.load_devices(loxapp_structure)

        # Update with empty state data
        manager.update_state("device-1", {})
        manager.update_state("device-1", None)

        # Device should still exist with empty states
        device = manager.get_device("device-1")
        assert device is not None
        # Should only have automatic tracking fields (no user state data)
        assert "_created_at" in device.states
        assert "_last_updated" in device.states
        assert "_reachable" in device.states
        # Should have exactly 3 automatic tracking fields
        assert len(device.states) == 3

    def test_update_state_multiple_updates(self):
        """Test multiple state updates accumulate correctly."""
        manager = DeviceManager()

        # Add a device
        loxapp_structure = {"controls": {"device-1": {"name": "Test Device", "type": "Dimmer"}}}
        manager.load_devices(loxapp_structure)

        # First update
        manager.update_state("device-1", {"position": 50})
        device = manager.get_device("device-1")
        assert device.states["position"] == 50
        assert "_created_at" in device.states
        assert "_last_updated" in device.states
        assert "_reachable" in device.states

        # Second update (should merge)
        manager.update_state("device-1", {"active": True})
        device = manager.get_device("device-1")
        assert device.states["position"] == 50
        assert device.states["active"]
        assert "_created_at" in device.states
        assert "_last_updated" in device.states
        assert "_reachable" in device.states

        # Third update (should overwrite existing key)
        manager.update_state("device-1", {"position": 75, "brightness": 80})
        device = manager.get_device("device-1")
        assert device.states["position"] == 75
        assert device.states["active"]
        assert device.states["brightness"] == 80
        assert "_created_at" in device.states
        assert "_last_updated" in device.states
        assert "_reachable" in device.states

    def test_state_callbacks(self):
        """Test state update callbacks are called correctly."""
        manager = DeviceManager()

        # Add a device
        loxapp_structure = {"controls": {"device-1": {"name": "Test Device", "type": "Switch"}}}
        manager.load_devices(loxapp_structure)

        # Register callback
        callback_calls = []

        def test_callback(uuid, state_data):
            callback_calls.append((uuid, state_data))

        manager.register_state_callback(test_callback)

        # Update state
        state_data = {"active": True}
        manager.update_state("device-1", state_data)

        # Verify callback was called
        assert len(callback_calls) == 1
        assert callback_calls[0] == ("device-1", state_data)

        # Update again
        state_data2 = {"value": 1}
        manager.update_state("device-1", state_data2)

        assert len(callback_calls) == 2
        assert callback_calls[1] == ("device-1", state_data2)

    def test_state_callback_error_handling(self):
        """Test that callback errors don't crash state updates."""
        manager = DeviceManager()

        # Add a device
        loxapp_structure = {"controls": {"device-1": {"name": "Test Device", "type": "Switch"}}}
        manager.load_devices(loxapp_structure)

        # Register a callback that raises an exception
        def failing_callback(uuid, state_data):
            raise Exception("Callback error")

        # Register a normal callback
        callback_calls = []

        def normal_callback(uuid, state_data):
            callback_calls.append((uuid, state_data))

        manager.register_state_callback(failing_callback)
        manager.register_state_callback(normal_callback)

        # Update state (should not crash despite failing callback)
        state_data = {"active": True}
        manager.update_state("device-1", state_data)

        # Normal callback should still be called
        assert len(callback_calls) == 1
        assert callback_calls[0] == ("device-1", state_data)

        # Device state should still be updated
        device = manager.get_device("device-1")
        # Check that the original states are present, ignoring automatic tracking fields
        for key, value in state_data.items():
            assert device.states[key] == value
        # Check that automatic tracking fields are present
        assert "_created_at" in device.states
        assert "_last_updated" in device.states
        assert "_reachable" in device.states

    def test_callback_registration_and_unregistration(self):
        """Test callback registration and unregistration."""
        manager = DeviceManager()

        def callback1(uuid, state_data):
            pass

        def callback2(uuid, state_data):
            pass

        # Register callbacks
        manager.register_state_callback(callback1)
        manager.register_state_callback(callback2)

        # Register same callback again (should not duplicate)
        manager.register_state_callback(callback1)

        # Unregister one callback
        manager.unregister_state_callback(callback1)

        # Unregister non-existent callback (should not crash)
        manager.unregister_state_callback(lambda x, y: None)


class TestDeviceManagerQueryMethods:
    """Test device query methods with filters."""

    def test_list_devices_no_filters(self):
        """Test listing all devices without filters."""
        loxapp_structure = {
            "rooms": {"room-1": {"name": "Living Room"}, "room-2": {"name": "Kitchen"}},
            "cats": {"cat-1": {"name": "Lights"}},
            "controls": {
                "device-1": {
                    "name": "Living Room Light",
                    "type": "Switch",
                    "room": "room-1",
                    "cat": "cat-1",
                },
                "device-2": {
                    "name": "Kitchen Dimmer",
                    "type": "Dimmer",
                    "room": "room-2",
                    "cat": "cat-1",
                },
                "device-3": {
                    "name": "Another Living Room Light",
                    "type": "Switch",
                    "room": "room-1",
                    "cat": "cat-1",
                },
            },
        }

        manager = DeviceManager()
        manager.load_devices(loxapp_structure)

        devices = manager.list_devices()
        assert len(devices) == 3

        # Should be sorted by name
        device_names = [d.name for d in devices]
        assert device_names == sorted(device_names)

    def test_list_devices_filter_by_type(self):
        """Test listing devices filtered by device type."""
        loxapp_structure = {
            "controls": {
                "device-1": {"name": "Switch 1", "type": "Switch"},
                "device-2": {"name": "Dimmer 1", "type": "Dimmer"},
                "device-3": {"name": "Switch 2", "type": "Switch"},
            }
        }

        manager = DeviceManager()
        manager.load_devices(loxapp_structure)

        # Filter by Switch type
        switches = manager.list_devices(device_type="Switch")
        assert len(switches) == 2
        assert all(d.type == "Switch" for d in switches)

        # Filter by Dimmer type
        dimmers = manager.list_devices(device_type="Dimmer")
        assert len(dimmers) == 1
        assert dimmers[0].type == "Dimmer"

        # Filter by non-existent type
        nonexistent = manager.list_devices(device_type="NonExistent")
        assert len(nonexistent) == 0

    def test_list_devices_filter_by_room(self):
        """Test listing devices filtered by room."""
        loxapp_structure = {
            "rooms": {"room-1": {"name": "Living Room"}, "room-2": {"name": "Kitchen"}},
            "controls": {
                "device-1": {"name": "Living Room Light", "type": "Switch", "room": "room-1"},
                "device-2": {"name": "Kitchen Light", "type": "Switch", "room": "room-2"},
                "device-3": {
                    "name": "Another Living Room Device",
                    "type": "Dimmer",
                    "room": "room-1",
                },
            },
        }

        manager = DeviceManager()
        manager.load_devices(loxapp_structure)

        # Filter by Living Room
        living_room_devices = manager.list_devices(room="Living Room")
        assert len(living_room_devices) == 2
        assert all(d.room == "Living Room" for d in living_room_devices)

        # Filter by Kitchen
        kitchen_devices = manager.list_devices(room="Kitchen")
        assert len(kitchen_devices) == 1
        assert kitchen_devices[0].room == "Kitchen"

        # Filter by non-existent room
        nonexistent = manager.list_devices(room="Basement")
        assert len(nonexistent) == 0

    def test_list_devices_filter_by_type_and_room(self):
        """Test listing devices filtered by both type and room."""
        loxapp_structure = {
            "rooms": {"room-1": {"name": "Living Room"}, "room-2": {"name": "Kitchen"}},
            "controls": {
                "device-1": {"name": "Living Room Switch", "type": "Switch", "room": "room-1"},
                "device-2": {"name": "Living Room Dimmer", "type": "Dimmer", "room": "room-1"},
                "device-3": {"name": "Kitchen Switch", "type": "Switch", "room": "room-2"},
            },
        }

        manager = DeviceManager()
        manager.load_devices(loxapp_structure)

        # Filter by Switch type in Living Room
        filtered_devices = manager.list_devices(device_type="Switch", room="Living Room")
        assert len(filtered_devices) == 1
        assert filtered_devices[0].name == "Living Room Switch"
        assert filtered_devices[0].type == "Switch"
        assert filtered_devices[0].room == "Living Room"

        # Filter by Dimmer type in Kitchen (should be empty)
        filtered_devices = manager.list_devices(device_type="Dimmer", room="Kitchen")
        assert len(filtered_devices) == 0

    def test_get_device_types(self):
        """Test getting list of all device types."""
        loxapp_structure = {
            "controls": {
                "device-1": {"name": "Switch", "type": "Switch"},
                "device-2": {"name": "Dimmer", "type": "Dimmer"},
                "device-3": {"name": "Another Switch", "type": "Switch"},
                "device-4": {"name": "Jalousie", "type": "Jalousie"},
            }
        }

        manager = DeviceManager()
        manager.load_devices(loxapp_structure)

        device_types = manager.get_device_types()
        assert set(device_types) == {"Switch", "Dimmer", "Jalousie"}
        assert device_types == sorted(device_types)  # Should be sorted

    def test_get_rooms(self):
        """Test getting list of all rooms."""
        loxapp_structure = {
            "rooms": {
                "room-1": {"name": "Living Room"},
                "room-2": {"name": "Kitchen"},
                "room-3": {"name": "Bedroom"},
            },
            "controls": {
                "device-1": {"name": "Device 1", "type": "Switch", "room": "room-1"},
                "device-2": {"name": "Device 2", "type": "Switch", "room": "room-2"},
                "device-3": {"name": "Device 3", "type": "Switch", "room": "room-1"},
                # No device in room-3, so it shouldn't appear in results
            },
        }

        manager = DeviceManager()
        manager.load_devices(loxapp_structure)

        rooms = manager.get_rooms()
        assert set(rooms) == {"Living Room", "Kitchen"}
        assert rooms == sorted(rooms)  # Should be sorted

    def test_get_device_state_nonexistent_device(self):
        """Test getting state for non-existent device."""
        manager = DeviceManager()

        state = manager.get_device_state("nonexistent-device")
        assert state is None

    def test_clear_devices(self):
        """Test clearing all devices and scenes."""
        loxapp_structure = {
            "controls": {"device-1": {"name": "Device", "type": "Switch"}},
            "autopilot": {"states": {"scene-1": {"name": "Scene"}}},
        }

        manager = DeviceManager()
        manager.load_devices(loxapp_structure)

        assert manager.get_device_count() == 1
        assert manager.get_scene_count() == 1

        manager.clear_devices()

        assert manager.get_device_count() == 0
        assert manager.get_scene_count() == 0


class TestDeviceManagerScenes:
    """Test scene management functionality."""

    def test_list_scenes_no_filter(self):
        """Test listing all scenes without filters."""
        loxapp_structure = {
            "rooms": {"room-1": {"name": "Living Room"}, "room-2": {"name": "Kitchen"}},
            "autopilot": {
                "states": {
                    "scene-1": {"name": "Movie Night", "room": "room-1"},
                    "scene-2": {"name": "Cooking Time", "room": "room-2"},
                    "scene-3": {"name": "Good Morning", "room": "room-1"},
                }
            },
        }

        manager = DeviceManager()
        manager.load_devices(loxapp_structure)

        scenes = manager.list_scenes()
        assert len(scenes) == 3

        # Should be sorted by name
        scene_names = [s.name for s in scenes]
        assert scene_names == sorted(scene_names)

    def test_list_scenes_filter_by_room(self):
        """Test listing scenes filtered by room."""
        loxapp_structure = {
            "rooms": {"room-1": {"name": "Living Room"}, "room-2": {"name": "Kitchen"}},
            "autopilot": {
                "states": {
                    "scene-1": {"name": "Movie Night", "room": "room-1"},
                    "scene-2": {"name": "Cooking Time", "room": "room-2"},
                    "scene-3": {"name": "Reading Time", "room": "room-1"},
                }
            },
        }

        manager = DeviceManager()
        manager.load_devices(loxapp_structure)

        # Filter by Living Room
        living_room_scenes = manager.list_scenes(room="Living Room")
        assert len(living_room_scenes) == 2
        assert all(s.room == "Living Room" for s in living_room_scenes)

        # Filter by Kitchen
        kitchen_scenes = manager.list_scenes(room="Kitchen")
        assert len(kitchen_scenes) == 1
        assert kitchen_scenes[0].room == "Kitchen"

        # Filter by non-existent room
        nonexistent = manager.list_scenes(room="Basement")
        assert len(nonexistent) == 0


class TestDeviceManagerThreadSafety:
    """Test thread safety of device manager operations."""

    def test_concurrent_state_updates(self):
        """Test concurrent state updates are thread-safe."""
        manager = DeviceManager()

        # Add a device
        loxapp_structure = {"controls": {"device-1": {"name": "Test Device", "type": "Switch"}}}
        manager.load_devices(loxapp_structure)

        # Function to update state in a thread
        def update_state_worker(thread_id):
            for i in range(100):
                state_data = {f"thread_{thread_id}_update": i}
                manager.update_state("device-1", state_data)
                time.sleep(0.001)  # Small delay to encourage race conditions

        # Start multiple threads
        threads = []
        for i in range(5):
            thread = Thread(target=update_state_worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Device should still exist and have some state
        device = manager.get_device("device-1")
        assert device is not None
        assert len(device.states) > 0

    def test_concurrent_device_queries(self):
        """Test concurrent device queries are thread-safe."""
        manager = DeviceManager()

        # Add multiple devices
        loxapp_structure = {
            "controls": {
                f"device-{i}": {"name": f"Device {i}", "type": "Switch"} for i in range(50)
            }
        }
        manager.load_devices(loxapp_structure)

        results = []

        def query_devices_worker():
            # Perform various queries
            for _ in range(50):
                devices = manager.list_devices()
                results.append(len(devices))

                device = manager.get_device("device-0")
                results.append(device is not None)

                count = manager.get_device_count()
                results.append(count)

        # Start multiple threads
        threads = []
        for _ in range(5):
            thread = Thread(target=query_devices_worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All queries should have returned consistent results
        assert len(results) > 0
        # All device counts should be 50
        device_counts = [r for i, r in enumerate(results) if i % 3 == 2]
        assert all(count == 50 for count in device_counts)

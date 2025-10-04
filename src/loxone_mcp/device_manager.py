"""
Device management for Loxone MCP Server.

Handles device discovery, registration, state management, and querying.
Provides a centralized registry for all Loxone devices and their states.
"""

import logging
from dataclasses import dataclass, field
from threading import RLock
from typing import Dict, List, Optional, Any, Callable

logger = logging.getLogger(__name__)

# Configure enhanced logging for device management
logger.setLevel(logging.DEBUG)  # Allow debug messages for device discovery troubleshooting

# Device type constants for all supported Loxone device types (Complete HA Component Migration)

# Lighting Controls
DEVICE_TYPE_SWITCH = "Switch"
DEVICE_TYPE_TIMED_SWITCH = "TimedSwitch"
DEVICE_TYPE_PUSHBUTTON = "Pushbutton"
DEVICE_TYPE_DIMMER = "Dimmer"
DEVICE_TYPE_LIGHT_CONTROLLER_V2 = "LightControllerV2"
DEVICE_TYPE_COLOR_PICKER_V2 = "ColorPickerV2"

# Cover Controls
DEVICE_TYPE_JALOUSIE = "Jalousie"
DEVICE_TYPE_WINDOW = "Window"
DEVICE_TYPE_GATE = "Gate"

# Climate Controls
DEVICE_TYPE_IROOM_CONTROLLER_V2 = "IRoomControllerV2"
DEVICE_TYPE_VENTILATION = "Ventilation"

# Sensors and Monitoring
DEVICE_TYPE_INFO_ONLY_ANALOG = "InfoOnlyAnalog"
DEVICE_TYPE_INFO_ONLY_DIGITAL = "InfoOnlyDigital"
DEVICE_TYPE_PRESENCE = "Presence"
DEVICE_TYPE_SMOKE_ALARM = "SmokeAlarm"

# Media and Audio
DEVICE_TYPE_AUDIO_ZONE_V2 = "AudioZoneV2"
DEVICE_TYPE_MEDIA_PLAYER = "MediaPlayer"

# Security and Safety
DEVICE_TYPE_ALARM = "Alarm"
DEVICE_TYPE_CENTRAL_ALARM = "CentralAlarm"
DEVICE_TYPE_INTERCOM = "Intercom"

# Input and Control
DEVICE_TYPE_SLIDER = "Slider"
DEVICE_TYPE_TEXT_INPUT = "TextInput"
DEVICE_TYPE_UP_DOWN_ANALOG = "UpDownAnalog"

# Automation
DEVICE_TYPE_MOOD = "Mood"
DEVICE_TYPE_TRACKER = "Tracker"

# System Integration
DEVICE_TYPE_WEATHER_SERVER = "WeatherServer"

# Scene type constant
SCENE_TYPE = "Scene"

# Set of all supported device types for filtering (Complete HA Component Migration)
SUPPORTED_DEVICE_TYPES = {
    # Lighting Controls
    DEVICE_TYPE_SWITCH,
    DEVICE_TYPE_TIMED_SWITCH,
    DEVICE_TYPE_PUSHBUTTON,
    DEVICE_TYPE_DIMMER,
    DEVICE_TYPE_LIGHT_CONTROLLER_V2,
    DEVICE_TYPE_COLOR_PICKER_V2,
    # Cover Controls
    DEVICE_TYPE_JALOUSIE,
    DEVICE_TYPE_WINDOW,
    DEVICE_TYPE_GATE,
    # Climate Controls
    DEVICE_TYPE_IROOM_CONTROLLER_V2,
    DEVICE_TYPE_VENTILATION,
    # Sensors and Monitoring
    DEVICE_TYPE_INFO_ONLY_ANALOG,
    DEVICE_TYPE_INFO_ONLY_DIGITAL,
    DEVICE_TYPE_PRESENCE,
    DEVICE_TYPE_SMOKE_ALARM,
    # Media and Audio
    DEVICE_TYPE_AUDIO_ZONE_V2,
    DEVICE_TYPE_MEDIA_PLAYER,
    # Security and Safety
    DEVICE_TYPE_ALARM,
    DEVICE_TYPE_CENTRAL_ALARM,
    DEVICE_TYPE_INTERCOM,
    # Input and Control
    DEVICE_TYPE_SLIDER,
    DEVICE_TYPE_TEXT_INPUT,
    DEVICE_TYPE_UP_DOWN_ANALOG,
    # Automation
    DEVICE_TYPE_MOOD,
    DEVICE_TYPE_TRACKER,
    # System Integration
    DEVICE_TYPE_WEATHER_SERVER,
    # Scenes
    SCENE_TYPE,
}


@dataclass
class LoxoneDevice:
    """
    Data model for a Loxone device.

    Represents a single device from the Loxone Miniserver with all its
    metadata, current state, available controls, and device capabilities.
    Enhanced with comprehensive state tracking and metadata support.
    """

    uuid: str
    name: str
    type: str
    room: str
    category: str
    states: Dict[str, Any] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)
    controls: Dict[str, Any] = field(default_factory=dict)
    capabilities: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate device data after initialization and set up enhanced state tracking."""
        import time

        if not self.uuid:
            raise ValueError("Device UUID cannot be empty")
        if not self.name:
            raise ValueError("Device name cannot be empty")
        if not self.type:
            raise ValueError("Device type cannot be empty")

        # Auto-detect capabilities based on device type if not provided
        if not self.capabilities:
            self.capabilities = self._detect_capabilities()

        # Initialize metadata with state parameter descriptions and tracking
        if not self.metadata:
            self.metadata = self._initialize_metadata()

        # Add state tracking timestamps
        if "_created_at" not in self.states:
            self.states["_created_at"] = time.time()

        if "_last_updated" not in self.states:
            self.states["_last_updated"] = time.time()

        if "_reachable" not in self.states:
            self.states["_reachable"] = True

    def _detect_capabilities(self) -> Dict[str, Any]:
        """
        Detect device capabilities based on device type and details.

        Returns:
            Dictionary containing device capabilities
        """
        capabilities = {}

        # Lighting capabilities
        if self.type in [DEVICE_TYPE_DIMMER, DEVICE_TYPE_LIGHT_CONTROLLER_V2]:
            capabilities.update(
                {"brightness": True, "brightness_range": [0, 100], "supports_on_off": True}
            )

        if self.type == DEVICE_TYPE_COLOR_PICKER_V2:
            capabilities.update(
                {
                    "brightness": True,
                    "brightness_range": [0, 100],
                    "supports_on_off": True,
                    "color": True,
                    "color_modes": ["rgb", "hsv"],
                    "supports_white_value": True,
                }
            )

        # Switch capabilities
        if self.type in [DEVICE_TYPE_SWITCH, DEVICE_TYPE_TIMED_SWITCH, DEVICE_TYPE_PUSHBUTTON]:
            capabilities.update({"supports_on_off": True})

        # Cover capabilities
        if self.type in [DEVICE_TYPE_JALOUSIE, DEVICE_TYPE_WINDOW, DEVICE_TYPE_GATE]:
            capabilities.update(
                {
                    "position": True,
                    "position_range": [0, 100],
                    "supports_open_close": True,
                    "supports_stop": True,
                }
            )

            if self.type == DEVICE_TYPE_JALOUSIE:
                capabilities.update({"tilt": True, "tilt_range": [0, 100]})

        # Climate capabilities
        if self.type == DEVICE_TYPE_IROOM_CONTROLLER_V2:
            capabilities.update(
                {
                    "temperature": True,
                    "temperature_range": [5.0, 35.0],
                    "temperature_unit": "°C",
                    "hvac_modes": ["off", "heat", "cool", "auto"],
                    "supports_target_temperature": True,
                    "supports_current_temperature": True,
                }
            )

        # Fan capabilities
        if self.type == DEVICE_TYPE_VENTILATION:
            capabilities.update(
                {
                    "fan_speed": True,
                    "fan_speed_range": [0, 100],
                    "supports_on_off": True,
                    "fan_modes": ["auto", "low", "medium", "high"],
                }
            )

        # Media player capabilities
        if self.type in [DEVICE_TYPE_AUDIO_ZONE_V2, DEVICE_TYPE_MEDIA_PLAYER]:
            capabilities.update(
                {
                    "volume": True,
                    "volume_range": [0, 100],
                    "supports_play_pause": True,
                    "supports_stop": True,
                    "supports_next_previous": True,
                    "supports_seek": True,
                    "media_content_types": ["music", "radio", "playlist"],
                }
            )

        # Alarm capabilities
        if self.type in [DEVICE_TYPE_ALARM, DEVICE_TYPE_CENTRAL_ALARM]:
            capabilities.update(
                {
                    "supports_arm_disarm": True,
                    "requires_code": True,
                    "alarm_states": ["disarmed", "armed_home", "armed_away", "triggered"],
                }
            )

        # Input control capabilities
        if self.type == DEVICE_TYPE_SLIDER:
            min_val = self.details.get("min", 0)
            max_val = self.details.get("max", 100)
            step = self.details.get("step", 1)
            capabilities.update(
                {
                    "numeric_input": True,
                    "value_range": [min_val, max_val],
                    "step": step,
                    "unit": self.details.get("unit", ""),
                }
            )

        if self.type == DEVICE_TYPE_TEXT_INPUT:
            capabilities.update(
                {"text_input": True, "max_length": self.details.get("maxLength", 255)}
            )

        if self.type == DEVICE_TYPE_UP_DOWN_ANALOG:
            capabilities.update({"up_down_control": True, "supports_increment_decrement": True})

        # Sensor capabilities
        if self.type in [DEVICE_TYPE_INFO_ONLY_ANALOG, DEVICE_TYPE_INFO_ONLY_DIGITAL]:
            capabilities.update(
                {
                    "read_only": True,
                    "sensor_type": (
                        "analog" if self.type == DEVICE_TYPE_INFO_ONLY_ANALOG else "digital"
                    ),
                }
            )

        if self.type == DEVICE_TYPE_PRESENCE:
            capabilities.update(
                {"read_only": True, "sensor_type": "presence", "binary_sensor": True}
            )

        if self.type == DEVICE_TYPE_SMOKE_ALARM:
            capabilities.update(
                {
                    "read_only": True,
                    "sensor_type": "smoke",
                    "binary_sensor": True,
                    "safety_device": True,
                }
            )

        # Weather capabilities
        if self.type == DEVICE_TYPE_WEATHER_SERVER:
            capabilities.update(
                {
                    "read_only": True,
                    "weather_data": True,
                    "provides_temperature": True,
                    "provides_humidity": True,
                    "provides_wind": True,
                    "provides_precipitation": True,
                }
            )

        # Scene capabilities
        if self.type == SCENE_TYPE:
            capabilities.update({"triggerable": True, "scene_control": True})

        # Add security flag for secured devices
        if self.details.get("isSecured", False):
            capabilities["requires_pin"] = True

        return capabilities

    def _initialize_metadata(self) -> Dict[str, Any]:
        """
        Initialize metadata with state parameter descriptions and units.

        Returns:
            Dictionary containing metadata for the device
        """
        import time

        metadata = {
            "created_at": time.time(),
            "state_parameters": {},
            "parameter_units": {},
            "parameter_ranges": {},
            "parameter_descriptions": {},
            "validation_rules": {},
            "last_state_update": None,
            "state_update_count": 0,
        }

        # Add type-specific metadata
        if self.type in [DEVICE_TYPE_DIMMER, DEVICE_TYPE_LIGHT_CONTROLLER_V2]:
            metadata["state_parameters"] = {
                "value": "Brightness level (0-100%)",
                "active": "Light is currently on/off",
            }
            metadata["parameter_units"] = {"value": "%"}
            metadata["parameter_ranges"] = {"value": [0, 100]}
            metadata["validation_rules"] = {"value": {"type": "float", "min": 0, "max": 100}}

        elif self.type == DEVICE_TYPE_COLOR_PICKER_V2:
            metadata["state_parameters"] = {
                "value": "Brightness level (0-100%)",
                "color": "Color value (RGB hex or numeric)",
                "active": "Light is currently on/off",
            }
            metadata["parameter_units"] = {"value": "%", "color": "hex"}
            metadata["parameter_ranges"] = {
                "value": [0, 100],
                "color": [0, 16777215],  # 0x000000 to 0xFFFFFF
            }
            metadata["validation_rules"] = {
                "value": {"type": "float", "min": 0, "max": 100},
                "color": {"type": "int", "min": 0, "max": 16777215},
            }

        elif self.type in [DEVICE_TYPE_JALOUSIE, DEVICE_TYPE_WINDOW, DEVICE_TYPE_GATE]:
            metadata["state_parameters"] = {
                "position": "Cover position (0=closed, 100=open)",
                "active": "Cover is currently moving",
            }
            metadata["parameter_units"] = {"position": "%"}
            metadata["parameter_ranges"] = {"position": [0, 100]}
            metadata["validation_rules"] = {"position": {"type": "float", "min": 0, "max": 100}}

            if self.type == DEVICE_TYPE_JALOUSIE:
                metadata["state_parameters"]["tilt"] = "Tilt angle (0-100%)"
                metadata["parameter_units"]["tilt"] = "%"
                metadata["parameter_ranges"]["tilt"] = [0, 100]
                metadata["validation_rules"]["tilt"] = {"type": "float", "min": 0, "max": 100}

        elif self.type == DEVICE_TYPE_IROOM_CONTROLLER_V2:
            metadata["state_parameters"] = {
                "temperature": "Current temperature",
                "targetTemperature": "Target temperature setting",
                "mode": "HVAC mode (0=off, 1=heat, 2=cool, 3=auto)",
                "active": "Heating/cooling active status",
            }
            metadata["parameter_units"] = {"temperature": "°C", "targetTemperature": "°C"}
            metadata["parameter_ranges"] = {
                "temperature": [-50, 100],
                "targetTemperature": [5, 35],
                "mode": [0, 3],
            }
            metadata["validation_rules"] = {
                "temperature": {"type": "float", "min": -50, "max": 100},
                "targetTemperature": {"type": "float", "min": 5, "max": 35},
                "mode": {"type": "int", "min": 0, "max": 3},
            }

        elif self.type in [DEVICE_TYPE_SWITCH, DEVICE_TYPE_TIMED_SWITCH, DEVICE_TYPE_PUSHBUTTON]:
            metadata["state_parameters"] = {
                "value": "Switch state (0=off, 1=on)",
                "active": "Switch is currently active",
            }
            metadata["parameter_ranges"] = {"value": [0, 1], "active": [0, 1]}
            metadata["validation_rules"] = {
                "value": {"type": "int", "min": 0, "max": 1},
                "active": {"type": "int", "min": 0, "max": 1},
            }

        elif self.type == DEVICE_TYPE_VENTILATION:
            metadata["state_parameters"] = {
                "value": "Fan speed (0-100%)",
                "active": "Fan is currently running",
            }
            metadata["parameter_units"] = {"value": "%"}
            metadata["parameter_ranges"] = {"value": [0, 100]}
            metadata["validation_rules"] = {"value": {"type": "float", "min": 0, "max": 100}}

        elif self.type in [DEVICE_TYPE_AUDIO_ZONE_V2, DEVICE_TYPE_MEDIA_PLAYER]:
            metadata["state_parameters"] = {
                "volume": "Volume level (0-100%)",
                "mode": "Playback mode (0=idle, 1=playing, 2=paused)",
                "active": "Media player is active",
            }
            metadata["parameter_units"] = {"volume": "%"}
            metadata["parameter_ranges"] = {"volume": [0, 100], "mode": [0, 2]}
            metadata["validation_rules"] = {
                "volume": {"type": "float", "min": 0, "max": 100},
                "mode": {"type": "int", "min": 0, "max": 2},
            }

        elif self.type in [DEVICE_TYPE_ALARM, DEVICE_TYPE_CENTRAL_ALARM]:
            metadata["state_parameters"] = {
                "active": "Alarm is triggered",
                "armed": "Alarm is armed",
            }
            metadata["parameter_ranges"] = {"active": [0, 1], "armed": [0, 1]}
            metadata["validation_rules"] = {
                "active": {"type": "int", "min": 0, "max": 1},
                "armed": {"type": "int", "min": 0, "max": 1},
            }

        elif self.type == DEVICE_TYPE_SLIDER:
            min_val = self.details.get("min", 0)
            max_val = self.details.get("max", 100)
            unit = self.details.get("unit", "")

            metadata["state_parameters"] = {"value": f"Slider value ({min_val}-{max_val})"}
            metadata["parameter_units"] = {"value": unit}
            metadata["parameter_ranges"] = {"value": [min_val, max_val]}
            metadata["validation_rules"] = {
                "value": {"type": "float", "min": min_val, "max": max_val}
            }

        elif self.type == DEVICE_TYPE_TEXT_INPUT:
            max_length = self.details.get("maxLength", 255)

            metadata["state_parameters"] = {"text": f"Text input value (max {max_length} chars)"}
            metadata["parameter_ranges"] = {"text": [0, max_length]}
            metadata["validation_rules"] = {"text": {"type": "str", "max_length": max_length}}

        elif self.type in [DEVICE_TYPE_INFO_ONLY_ANALOG, DEVICE_TYPE_INFO_ONLY_DIGITAL]:
            unit = self.details.get("unit", "")
            sensor_type = "digital" if self.type == DEVICE_TYPE_INFO_ONLY_DIGITAL else "analog"

            metadata["state_parameters"] = {"value": f"Sensor reading ({sensor_type})"}
            metadata["parameter_units"] = {"value": unit}
            metadata["validation_rules"] = {
                "value": {"type": "float" if sensor_type == "analog" else "int"}
            }

        elif self.type == SCENE_TYPE:
            metadata["state_parameters"] = {"active": "Scene is currently active"}
            metadata["parameter_ranges"] = {"active": [0, 1]}
            metadata["validation_rules"] = {"active": {"type": "int", "min": 0, "max": 1}}

        return metadata

    def validate_state_parameter(self, parameter: str, value: Any) -> bool:
        """
        Validate a state parameter value against the device's validation rules.

        Args:
            parameter: The parameter name to validate
            value: The value to validate

        Returns:
            True if the value is valid, False otherwise
        """
        if not self.metadata or "validation_rules" not in self.metadata:
            return True  # No validation rules defined

        rules = self.metadata["validation_rules"].get(parameter)
        if not rules:
            return True  # No rules for this parameter

        try:
            # Type validation
            expected_type = rules.get("type")
            if expected_type == "float":
                value = float(value)
            elif expected_type == "int":
                value = int(value)
            elif expected_type == "str":
                value = str(value)

            # Range validation
            if "min" in rules and value < rules["min"]:
                return False
            if "max" in rules and value > rules["max"]:
                return False

            # String length validation
            if expected_type == "str" and "max_length" in rules:
                if len(value) > rules["max_length"]:
                    return False

            return True

        except (ValueError, TypeError):
            return False

    def get_default_state_value(self, parameter: str) -> Any:
        """
        Get the default value for a state parameter.

        Args:
            parameter: The parameter name

        Returns:
            Default value for the parameter
        """
        if not self.metadata or "validation_rules" not in self.metadata:
            return None

        rules = self.metadata["validation_rules"].get(parameter)
        if not rules:
            return None

        expected_type = rules.get("type")
        if expected_type == "float":
            return rules.get("min", 0.0)
        elif expected_type == "int":
            return rules.get("min", 0)
        elif expected_type == "str":
            return ""

        return None

    def update_state_tracking(self) -> None:
        """Update state tracking metadata when states are modified."""
        import time

        if not self.metadata:
            self.metadata = {}

        self.states["_last_updated"] = time.time()
        self.metadata["last_state_update"] = time.time()
        self.metadata["state_update_count"] = self.metadata.get("state_update_count", 0) + 1


class DeviceManager:
    """
    Central device management for Loxone devices.

    Maintains a registry of all discovered devices, manages their states,
    and provides methods for querying and filtering devices.
    """

    def __init__(self):
        """Initialize the device manager."""
        self._devices: Dict[str, LoxoneDevice] = {}
        self._scenes: Dict[str, LoxoneDevice] = {}  # Separate registry for scenes
        self._state_lock = RLock()  # Thread-safe state updates
        self._state_callbacks: List[Callable[[str, Dict[str, Any]], None]] = []

        logger.info("DeviceManager initialized")

    @property
    def devices(self) -> Dict[str, LoxoneDevice]:
        """Get read-only access to the device registry."""
        return self._devices.copy()

    def load_devices(self, loxapp_json: Dict[str, Any]) -> None:
        """
        Parse LoxAPP3.json structure and register supported devices.

        Extracts device information from the Loxone structure file,
        filters for supported device types, and creates LoxoneDevice
        instances for each discovered device.

        Args:
            loxapp_json: The parsed LoxAPP3.json structure from Miniserver
        """
        if not loxapp_json:
            logger.warning("Empty LoxAPP3.json structure provided - no devices will be loaded")
            return

        if not isinstance(loxapp_json, dict):
            logger.error(f"Invalid LoxAPP3.json structure type: {type(loxapp_json)}")
            logger.error("Expected dictionary structure, cannot load devices")
            return

        logger.info("Loading devices from LoxAPP3.json structure")
        logger.debug(f"Structure contains top-level keys: {list(loxapp_json.keys())}")

        # Clear existing devices and scenes
        with self._state_lock:
            self._devices.clear()
            self._scenes.clear()

        # Extract rooms for device categorization
        rooms = {}
        if "rooms" in loxapp_json:
            for room_uuid, room_data in loxapp_json["rooms"].items():
                rooms[room_uuid] = room_data.get("name", "Unknown Room")

        # Extract categories
        categories = {}
        if "cats" in loxapp_json:
            for cat_uuid, cat_data in loxapp_json["cats"].items():
                categories[cat_uuid] = cat_data.get("name", "Unknown Category")

        # Process controls (main device definitions)
        controls_processed = 0
        devices_registered = 0
        unsupported_types = set()

        if "controls" in loxapp_json:
            for control_uuid, control_data in loxapp_json["controls"].items():
                controls_processed += 1

                # Extract basic device information
                device_type = control_data.get("type", "Unknown")
                device_name = control_data.get("name", f"Device {control_uuid}")

                # Check if device type is supported
                if device_type not in SUPPORTED_DEVICE_TYPES:
                    unsupported_types.add(device_type)
                    logger.debug(f"Skipping unsupported device type: {device_type} ({device_name})")
                    continue

                # Get room name
                room_uuid = control_data.get("room", "")
                room_name = rooms.get(room_uuid, "Unknown Room")

                # Get category name
                cat_uuid = control_data.get("cat", "")
                category_name = categories.get(cat_uuid, "Unknown Category")

                # Extract device details and controls
                details = {
                    "uuidAction": control_data.get("uuidAction", ""),
                    "defaultRating": control_data.get("defaultRating", 0),
                    "isFavorite": control_data.get("isFavorite", False),
                    "isSecured": control_data.get("isSecured", False),
                }

                # Add type-specific details
                if "details" in control_data:
                    details.update(control_data["details"])

                # Extract available controls/states
                controls = {}
                if "states" in control_data:
                    for state_name, state_uuid in control_data["states"].items():
                        controls[state_name] = state_uuid

                # Create device instance with enhanced error handling
                try:
                    device = LoxoneDevice(
                        uuid=control_uuid,
                        name=device_name,
                        type=device_type,
                        room=room_name,
                        category=category_name,
                        states={},  # Will be populated by state updates
                        details=details,
                        controls=controls,
                        capabilities={},  # Will be auto-detected in __post_init__
                    )

                    # Register device
                    with self._state_lock:
                        self._devices[control_uuid] = device

                    devices_registered += 1
                    logger.debug(f"Registered device: {device_name} ({device_type}) in {room_name}")

                except ValueError as e:
                    logger.error(
                        f"Failed to create device {control_uuid} ({device_name}): {e}",
                        extra={
                            "device_uuid": control_uuid,
                            "device_name": device_name,
                            "device_type": device_type,
                            "room": room_name,
                        },
                    )
                    continue
                except Exception as e:
                    logger.error(
                        f"Unexpected error creating device {control_uuid} ({device_name}): {e}",
                        exc_info=True,
                        extra={
                            "device_uuid": control_uuid,
                            "device_name": device_name,
                            "device_type": device_type,
                        },
                    )
                    continue

        # Process scenes (automation scenarios)
        scenes_processed = 0
        scenes_registered = 0

        if "autopilot" in loxapp_json:
            autopilot_data = loxapp_json["autopilot"]
            if "states" in autopilot_data:
                for scene_uuid, scene_data in autopilot_data["states"].items():
                    scenes_processed += 1

                    # Extract scene information
                    scene_name = scene_data.get("name", f"Scene {scene_uuid}")

                    # Get room name if available
                    room_uuid = scene_data.get("room", "")
                    room_name = rooms.get(room_uuid, "Unknown Room")

                    # Get category name if available
                    cat_uuid = scene_data.get("cat", "")
                    category_name = categories.get(cat_uuid, "Scenes")

                    # Extract scene details
                    details = {
                        "description": scene_data.get("description", ""),
                        "isFavorite": scene_data.get("isFavorite", False),
                        "isSecured": scene_data.get("isSecured", False),
                    }

                    # Create scene device instance
                    try:
                        scene = LoxoneDevice(
                            uuid=scene_uuid,
                            name=scene_name,
                            type=SCENE_TYPE,
                            room=room_name,
                            category=category_name,
                            states={},  # Scenes don't have states like devices
                            details=details,
                            controls={},  # Scenes are triggered, not controlled
                        )

                        # Register scene
                        with self._state_lock:
                            self._scenes[scene_uuid] = scene

                        scenes_registered += 1
                        logger.debug(f"Registered scene: {scene_name} in {room_name}")

                    except ValueError as e:
                        logger.error(f"Failed to create scene {scene_uuid}: {e}")
                        continue

        # Log summary
        logger.info(
            f"Device loading complete: {devices_registered} devices and {scenes_registered} scenes registered "
            f"from {controls_processed} controls and {scenes_processed} scenes processed"
        )

        if unsupported_types:
            logger.info(
                f"Unsupported device types encountered: {', '.join(sorted(unsupported_types))}"
            )

    def get_device(self, uuid: str) -> Optional[LoxoneDevice]:
        """
        Get a device by its UUID.

        Args:
            uuid: The UUID of the device to retrieve

        Returns:
            LoxoneDevice instance if found, None otherwise
        """
        if not uuid:
            return None

        with self._state_lock:
            return self._devices.get(uuid)

    def get_device_state(self, uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get the current state of a device by UUID.

        Args:
            uuid: The UUID of the device

        Returns:
            Dictionary containing current device state, None if device not found
        """
        device = self.get_device(uuid)
        if device:
            with self._state_lock:
                return device.states.copy()
        return None

    def list_devices(
        self, device_type: Optional[str] = None, room: Optional[str] = None
    ) -> List[LoxoneDevice]:
        """
        List devices with optional filtering.

        Args:
            device_type: Filter by device type (e.g., "Switch", "Dimmer")
            room: Filter by room name

        Returns:
            List of LoxoneDevice instances matching the filters
        """
        with self._state_lock:
            devices = list(self._devices.values())

        # Apply device type filter
        if device_type:
            devices = [d for d in devices if d.type == device_type]

        # Apply room filter
        if room:
            devices = [d for d in devices if d.room == room]

        # Sort by name for consistent ordering
        devices.sort(key=lambda d: d.name)

        logger.debug(f"Listed {len(devices)} devices " f"(type={device_type}, room={room})")

        return devices

    def update_state(self, uuid: str, state_data: Dict[str, Any]) -> None:
        """
        Update the state of a device with enhanced validation and tracking.

        Thread-safe method to update device state cache when state
        updates are received from the Miniserver. Now includes state
        validation and enhanced tracking.

        Args:
            uuid: The UUID of the device to update
            state_data: Dictionary containing new state values
        """
        if not uuid or not state_data:
            return

        with self._state_lock:
            device = self._devices.get(uuid)
            if device:
                # Validate state parameters before updating
                validated_data = {}
                for param, value in state_data.items():
                    if device.validate_state_parameter(param, value):
                        validated_data[param] = value
                    else:
                        logger.warning(
                            f"Invalid state value for device {device.name} ({uuid}): {param}={value}",
                            extra={
                                "device_uuid": uuid,
                                "device_name": device.name,
                                "parameter": param,
                                "invalid_value": value,
                            },
                        )
                        # Use default value instead
                        default_value = device.get_default_state_value(param)
                        if default_value is not None:
                            validated_data[param] = default_value

                # Update device state with validated data
                device.states.update(validated_data)

                # Update state tracking
                device.update_state_tracking()

                logger.debug(f"Updated state for device {device.name} ({uuid}): {validated_data}")

                # Notify callbacks with enhanced error handling
                for callback in self._state_callbacks:
                    try:
                        callback(uuid, validated_data)
                    except Exception as e:
                        logger.error(
                            f"Error in state update callback: {e}",
                            exc_info=True,
                            extra={
                                "device_uuid": uuid,
                                "callback_name": getattr(callback, "__name__", "unknown"),
                                "state_data_keys": (
                                    list(validated_data.keys())
                                    if isinstance(validated_data, dict)
                                    else "non-dict"
                                ),
                            },
                        )
            else:
                logger.debug(
                    f"Received state update for unknown device: {uuid}",
                    extra={
                        "unknown_uuid": uuid,
                        "state_data": state_data,
                        "registered_device_count": len(self._devices),
                    },
                )

    def register_state_callback(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """
        Register a callback for state updates.

        Args:
            callback: Function to call when device states are updated.
                     Signature: callback(uuid: str, state_data: Dict[str, Any])
        """
        if callback not in self._state_callbacks:
            self._state_callbacks.append(callback)
            logger.debug("Registered state update callback")

    def unregister_state_callback(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """
        Unregister a state update callback.

        Args:
            callback: The callback function to remove
        """
        if callback in self._state_callbacks:
            self._state_callbacks.remove(callback)
            logger.debug("Unregistered state update callback")

    def get_device_count(self) -> int:
        """Get the total number of registered devices."""
        with self._state_lock:
            return len(self._devices)

    def get_device_types(self) -> List[str]:
        """Get a list of all device types currently registered."""
        with self._state_lock:
            types = {device.type for device in self._devices.values()}
        return sorted(list(types))

    def get_rooms(self) -> List[str]:
        """Get a list of all rooms with registered devices."""
        with self._state_lock:
            rooms = {device.room for device in self._devices.values()}
        return sorted(list(rooms))

    def clear_devices(self) -> None:
        """Clear all registered devices and scenes (useful for testing)."""
        with self._state_lock:
            self._devices.clear()
            self._scenes.clear()
        logger.info("All devices and scenes cleared from registry")

    def get_scene(self, uuid: str) -> Optional[LoxoneDevice]:
        """
        Get a scene by its UUID.

        Args:
            uuid: The UUID of the scene to retrieve

        Returns:
            LoxoneDevice instance representing the scene if found, None otherwise
        """
        if not uuid:
            return None

        with self._state_lock:
            return self._scenes.get(uuid)

    def list_scenes(self, room: Optional[str] = None) -> List[LoxoneDevice]:
        """
        List all available scenes with optional room filtering.

        Args:
            room: Filter by room name (optional)

        Returns:
            List of LoxoneDevice instances representing scenes
        """
        with self._state_lock:
            scenes = list(self._scenes.values())

        # Apply room filter if specified
        if room:
            scenes = [s for s in scenes if s.room == room]

        # Sort by name for consistent ordering
        scenes.sort(key=lambda s: s.name)

        logger.debug(f"Listed {len(scenes)} scenes (room={room})")

        return scenes

    def get_scene_count(self) -> int:
        """Get the total number of registered scenes."""
        with self._state_lock:
            return len(self._scenes)

    def list_rooms(self) -> List[Dict[str, Any]]:
        """
        List all rooms with device counts.

        Returns:
            List of dictionaries containing room information and device counts
        """
        with self._state_lock:
            room_data = {}

            # Count devices per room
            for device in self._devices.values():
                room_name = device.room
                if room_name not in room_data:
                    room_data[room_name] = {
                        "name": room_name,
                        "device_count": 0,
                        "device_types": set(),
                    }
                room_data[room_name]["device_count"] += 1
                room_data[room_name]["device_types"].add(device.type)

            # Count scenes per room
            for scene in self._scenes.values():
                room_name = scene.room
                if room_name not in room_data:
                    room_data[room_name] = {
                        "name": room_name,
                        "device_count": 0,
                        "device_types": set(),
                    }
                # Scenes are counted separately
                if "scene_count" not in room_data[room_name]:
                    room_data[room_name]["scene_count"] = 0
                room_data[room_name]["scene_count"] += 1

        # Convert to list format
        rooms = []
        for room_info in room_data.values():
            room_info["device_types"] = sorted(list(room_info["device_types"]))
            room_info["scene_count"] = room_info.get("scene_count", 0)
            rooms.append(room_info)

        # Sort by room name
        rooms.sort(key=lambda r: r["name"])

        logger.debug(f"Listed {len(rooms)} rooms")
        return rooms

    def get_room_devices(self, room: str) -> List[Dict[str, Any]]:
        """
        Get all devices in a specific room with their current states.

        Args:
            room: The room name to filter by

        Returns:
            List of dictionaries containing device information and current states
        """
        if not room:
            return []

        with self._state_lock:
            room_devices = []

            # Get devices in the room
            for device in self._devices.values():
                if device.room == room:
                    device_info = {
                        "uuid": device.uuid,
                        "name": device.name,
                        "type": device.type,
                        "category": device.category,
                        "states": device.states.copy(),
                        "capabilities": device.capabilities.copy(),
                        "is_secured": device.details.get("isSecured", False),
                    }
                    room_devices.append(device_info)

            # Get scenes in the room
            for scene in self._scenes.values():
                if scene.room == room:
                    scene_info = {
                        "uuid": scene.uuid,
                        "name": scene.name,
                        "type": scene.type,
                        "category": scene.category,
                        "states": {},
                        "capabilities": scene.capabilities.copy(),
                        "is_secured": scene.details.get("isSecured", False),
                    }
                    room_devices.append(scene_info)

        # Sort by name
        room_devices.sort(key=lambda d: d["name"])

        logger.debug(f"Found {len(room_devices)} devices/scenes in room '{room}'")
        return room_devices

    async def control_room(self, room: str, action: str) -> Dict[str, Any]:
        """
        Control all compatible devices in a room.

        Args:
            room: The room name
            action: The action to perform ('lights_off', 'all_off', 'lights_on', etc.)

        Returns:
            Dictionary with results of the room control operation
        """
        if not room or not action:
            return {
                "success": False,
                "error": "Room name and action are required",
                "affected_devices": [],
            }

        with self._state_lock:
            room_devices = [d for d in self._devices.values() if d.room == room]

        if not room_devices:
            return {
                "success": False,
                "error": f"No devices found in room '{room}'",
                "affected_devices": [],
            }

        affected_devices = []
        errors = []

        # Determine which devices to control based on action
        target_devices = []

        if action == "lights_off":
            target_devices = [
                d
                for d in room_devices
                if d.type
                in [
                    DEVICE_TYPE_SWITCH,
                    DEVICE_TYPE_DIMMER,
                    DEVICE_TYPE_LIGHT_CONTROLLER_V2,
                    DEVICE_TYPE_COLOR_PICKER_V2,
                ]
                and d.capabilities.get("supports_on_off", False)
            ]
        elif action == "lights_on":
            target_devices = [
                d
                for d in room_devices
                if d.type
                in [
                    DEVICE_TYPE_SWITCH,
                    DEVICE_TYPE_DIMMER,
                    DEVICE_TYPE_LIGHT_CONTROLLER_V2,
                    DEVICE_TYPE_COLOR_PICKER_V2,
                ]
                and d.capabilities.get("supports_on_off", False)
            ]
        elif action == "all_off":
            target_devices = [
                d for d in room_devices if d.capabilities.get("supports_on_off", False)
            ]
        elif action == "covers_open":
            target_devices = [
                d
                for d in room_devices
                if d.type in [DEVICE_TYPE_JALOUSIE, DEVICE_TYPE_WINDOW, DEVICE_TYPE_GATE]
                and d.capabilities.get("supports_open_close", False)
            ]
        elif action == "covers_close":
            target_devices = [
                d
                for d in room_devices
                if d.type in [DEVICE_TYPE_JALOUSIE, DEVICE_TYPE_WINDOW, DEVICE_TYPE_GATE]
                and d.capabilities.get("supports_open_close", False)
            ]
        else:
            return {
                "success": False,
                "error": f"Unknown action '{action}'. Supported actions: lights_off, lights_on, all_off, covers_open, covers_close",
                "affected_devices": [],
            }

        if not target_devices:
            return {
                "success": True,
                "message": f"No compatible devices found for action '{action}' in room '{room}'",
                "affected_devices": [],
            }

        # Note: Actual command sending would be handled by the ClientSession
        # This method just identifies the devices and prepares the response
        for device in target_devices:
            device_info = {
                "uuid": device.uuid,
                "name": device.name,
                "type": device.type,
                "action_planned": action,
            }
            affected_devices.append(device_info)

        result = {
            "success": True,
            "message": f"Room control '{action}' prepared for {len(affected_devices)} devices in '{room}'",
            "affected_devices": affected_devices,
            "room": room,
            "action": action,
        }

        if errors:
            result["errors"] = errors

        logger.info(
            f"Room control '{action}' prepared for {len(affected_devices)} devices in room '{room}'"
        )
        return result

    def get_enhanced_device_state(self, uuid: str) -> Dict[str, Any]:
        """
        Get comprehensive device state with all available parameters.

        This method addresses the issue where device state queries return empty objects
        by providing detailed state information including capabilities, metadata, and
        comprehensive state structures based on device type.

        Args:
            uuid: The UUID of the device

        Returns:
            Dictionary containing comprehensive device state information
        """
        device = self.get_device(uuid)
        if not device:
            return {"error": "Device not found", "uuid": uuid, "success": False}

        # Build comprehensive state structure based on device type
        enhanced_state = self.build_state_structure(device)

        # Check if state cache is empty and add status information
        with self._state_lock:
            if not device.states or len(device.states) == 0:
                logger.warning(
                    f"Empty state cache for device {uuid} ({device.name}), may need state update"
                )
                enhanced_state["metadata"]["cache_status"] = "empty_requesting_update"
                enhanced_state["metadata"]["cache_empty"] = True
            else:
                enhanced_state["metadata"]["cache_status"] = "populated"
                enhanced_state["metadata"]["cache_empty"] = False

        enhanced_state["success"] = True
        return enhanced_state

    def build_state_structure(self, device: LoxoneDevice) -> Dict[str, Any]:
        """
        Build device-specific state structure with all relevant parameters.

        Creates a comprehensive state structure that includes device information,
        current state values, capabilities, and metadata tailored to the specific
        device type.

        Args:
            device: The LoxoneDevice instance

        Returns:
            Dictionary containing the complete state structure
        """
        import time

        base_structure = {
            "uuid": device.uuid,
            "name": device.name,
            "type": device.type,
            "room": device.room,
            "category": device.category,
            "state": {},
            "capabilities": device.capabilities.copy() if device.capabilities else {},
            "metadata": {
                "state_parameters": [],
                "last_updated": device.states.get("_last_updated"),
                "reachable": device.states.get("_reachable", True),
                "timestamp": time.time(),
                "device_details": device.details.copy() if device.details else {},
            },
        }

        # Device-type specific state building
        if device.type in [DEVICE_TYPE_DIMMER, DEVICE_TYPE_LIGHT_CONTROLLER_V2]:
            return self._build_light_state(device, base_structure)
        elif device.type == DEVICE_TYPE_COLOR_PICKER_V2:
            return self._build_color_light_state(device, base_structure)
        elif device.type in [DEVICE_TYPE_JALOUSIE, DEVICE_TYPE_WINDOW, DEVICE_TYPE_GATE]:
            return self._build_cover_state(device, base_structure)
        elif device.type == DEVICE_TYPE_IROOM_CONTROLLER_V2:
            return self._build_climate_state(device, base_structure)
        elif device.type in [DEVICE_TYPE_SWITCH, DEVICE_TYPE_TIMED_SWITCH, DEVICE_TYPE_PUSHBUTTON]:
            return self._build_switch_state(device, base_structure)
        elif device.type == DEVICE_TYPE_VENTILATION:
            return self._build_fan_state(device, base_structure)
        elif device.type in [DEVICE_TYPE_AUDIO_ZONE_V2, DEVICE_TYPE_MEDIA_PLAYER]:
            return self._build_media_player_state(device, base_structure)
        elif device.type in [DEVICE_TYPE_ALARM, DEVICE_TYPE_CENTRAL_ALARM]:
            return self._build_alarm_state(device, base_structure)
        elif device.type == DEVICE_TYPE_SLIDER:
            return self._build_slider_state(device, base_structure)
        elif device.type == DEVICE_TYPE_TEXT_INPUT:
            return self._build_text_input_state(device, base_structure)
        elif device.type in [DEVICE_TYPE_INFO_ONLY_ANALOG, DEVICE_TYPE_INFO_ONLY_DIGITAL]:
            return self._build_sensor_state(device, base_structure)
        elif device.type == SCENE_TYPE:
            return self._build_scene_state(device, base_structure)
        else:
            return self._build_generic_state(device, base_structure)

    def extract_device_capabilities(self, device_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract device capabilities from LoxAPP3.json device configuration.

        Analyzes the device configuration from the Loxone structure to determine
        what capabilities and features the device supports.

        Args:
            device_config: Device configuration dictionary from LoxAPP3.json

        Returns:
            Dictionary containing detected device capabilities
        """
        capabilities = {}
        device_type = device_config.get("type", "")
        details = device_config.get("details", {})
        states = device_config.get("states", {})

        # Extract capabilities based on available states and details
        if "value" in states:
            capabilities["has_value_state"] = True

        if "position" in states:
            capabilities["has_position_state"] = True
            capabilities["position_range"] = [0, 100]  # Standard Loxone range

        if "tilt" in states:
            capabilities["has_tilt_state"] = True
            capabilities["tilt_range"] = [0, 100]

        if "temperature" in states:
            capabilities["has_temperature_state"] = True
            capabilities["temperature_unit"] = "°C"

        if "targetTemperature" in states:
            capabilities["supports_target_temperature"] = True

        if "mode" in states:
            capabilities["has_mode_state"] = True

        if "volume" in states:
            capabilities["has_volume_state"] = True
            capabilities["volume_range"] = [0, 100]

        if "color" in states:
            capabilities["supports_color"] = True
            capabilities["color_modes"] = ["rgb", "hsv"]

        # Extract ranges from details
        if "min" in details and "max" in details:
            capabilities["value_range"] = [details["min"], details["max"]]

        if "step" in details:
            capabilities["step"] = details["step"]

        if "unit" in details:
            capabilities["unit"] = details["unit"]

        # Security capabilities
        if device_config.get("isSecured", False):
            capabilities["requires_pin"] = True

        # Type-specific capability detection
        if device_type in [
            DEVICE_TYPE_DIMMER,
            DEVICE_TYPE_LIGHT_CONTROLLER_V2,
            DEVICE_TYPE_COLOR_PICKER_V2,
        ]:
            capabilities["supports_brightness"] = True
            capabilities["supports_on_off"] = True

        if device_type in [DEVICE_TYPE_JALOUSIE, DEVICE_TYPE_WINDOW, DEVICE_TYPE_GATE]:
            capabilities["supports_position"] = True
            capabilities["supports_open_close"] = True
            capabilities["supports_stop"] = True

        if device_type == DEVICE_TYPE_JALOUSIE:
            capabilities["supports_tilt"] = True

        return capabilities

    def _build_light_state(self, device: LoxoneDevice, base: Dict[str, Any]) -> Dict[str, Any]:
        """Build enhanced state for light devices (Dimmer, LightControllerV2)."""
        value = device.states.get("value", 0.0)

        # Convert value to appropriate format
        if isinstance(value, str):
            try:
                value = float(value)
            except (ValueError, TypeError):
                value = 0.0

        base["state"] = {
            "value": value,
            "on": value > 0,
            "brightness": value,
            "brightness_pct": value,  # Loxone uses 0-100 scale
            "last_changed": device.states.get("_last_changed"),
            "reachable": device.states.get("_reachable", True),
        }

        # Add additional states if available
        if "active" in device.states:
            base["state"]["active"] = device.states["active"]

        base["capabilities"].update(
            {
                "min_brightness": 0,
                "max_brightness": 100,
                "step": 1,
                "supports_dimming": True,
                "supports_color": False,
                "supports_on_off": True,
            }
        )

        base["metadata"].update(
            {
                "units": "%",
                "format": "%.1f%%",
                "state_parameters": ["value", "on", "brightness", "brightness_pct"],
                "control_type": "dimmer",
            }
        )

        return base

    def _build_color_light_state(
        self, device: LoxoneDevice, base: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build enhanced state for color light devices (ColorPickerV2)."""
        value = device.states.get("value", 0.0)
        color = device.states.get("color", 0)

        # Convert value to appropriate format
        if isinstance(value, str):
            try:
                value = float(value)
            except (ValueError, TypeError):
                value = 0.0

        # Convert color to hex format if it's a number
        color_hex = "#000000"
        if isinstance(color, (int, float)):
            color_hex = f"#{int(color):06x}"
        elif isinstance(color, str) and color.startswith("#"):
            color_hex = color

        base["state"] = {
            "value": value,
            "on": value > 0,
            "brightness": value,
            "brightness_pct": value,
            "color": color,
            "color_hex": color_hex,
            "last_changed": device.states.get("_last_changed"),
            "reachable": device.states.get("_reachable", True),
        }

        base["capabilities"].update(
            {
                "min_brightness": 0,
                "max_brightness": 100,
                "step": 1,
                "supports_dimming": True,
                "supports_color": True,
                "supports_on_off": True,
                "color_modes": ["rgb", "hsv"],
                "supports_white_value": True,
            }
        )

        base["metadata"].update(
            {
                "units": "%",
                "format": "%.1f%%",
                "state_parameters": [
                    "value",
                    "on",
                    "brightness",
                    "brightness_pct",
                    "color",
                    "color_hex",
                ],
                "control_type": "color_light",
            }
        )

        return base

    def _build_cover_state(self, device: LoxoneDevice, base: Dict[str, Any]) -> Dict[str, Any]:
        """Build enhanced state for cover devices (Jalousie, Window, Gate)."""
        position = device.states.get("position", 0.0)
        tilt = device.states.get("tilt", 0.0) if device.type == DEVICE_TYPE_JALOUSIE else None

        # Convert values to appropriate format
        if isinstance(position, str):
            try:
                position = float(position)
            except (ValueError, TypeError):
                position = 0.0

        base["state"] = {
            "position": position,
            "position_pct": position,
            "closed": position == 0,
            "open": position == 100,
            "last_changed": device.states.get("_last_changed"),
            "reachable": device.states.get("_reachable", True),
        }

        # Add tilt for Jalousie devices
        if tilt is not None:
            if isinstance(tilt, str):
                try:
                    tilt = float(tilt)
                except (ValueError, TypeError):
                    tilt = 0.0
            base["state"]["tilt"] = tilt
            base["state"]["tilt_pct"] = tilt

        # Add movement state if available
        if "active" in device.states:
            base["state"]["moving"] = device.states["active"]

        capabilities = {
            "min_position": 0,
            "max_position": 100,
            "step": 1,
            "supports_position": True,
            "supports_open_close": True,
            "supports_stop": True,
        }

        if device.type == DEVICE_TYPE_JALOUSIE:
            capabilities.update({"supports_tilt": True, "min_tilt": 0, "max_tilt": 100})

        base["capabilities"].update(capabilities)

        state_params = ["position", "position_pct", "closed", "open"]
        if tilt is not None:
            state_params.extend(["tilt", "tilt_pct"])

        base["metadata"].update(
            {
                "units": "%",
                "format": "%.1f%%",
                "state_parameters": state_params,
                "control_type": "cover",
            }
        )

        return base

    def _build_climate_state(self, device: LoxoneDevice, base: Dict[str, Any]) -> Dict[str, Any]:
        """Build enhanced state for climate devices (IRoomControllerV2)."""
        temperature = device.states.get("temperature", 20.0)
        target_temp = device.states.get("targetTemperature", 20.0)
        mode = device.states.get("mode", 0)

        # Convert values to appropriate format
        if isinstance(temperature, str):
            try:
                temperature = float(temperature)
            except (ValueError, TypeError):
                temperature = 20.0

        if isinstance(target_temp, str):
            try:
                target_temp = float(target_temp)
            except (ValueError, TypeError):
                target_temp = 20.0

        # Map mode number to string
        mode_map = {0: "off", 1: "heat", 2: "cool", 3: "auto"}
        mode_str = mode_map.get(mode, "off")

        base["state"] = {
            "temperature": temperature,
            "current_temperature": temperature,
            "target_temperature": target_temp,
            "mode": mode,
            "mode_str": mode_str,
            "last_changed": device.states.get("_last_changed"),
            "reachable": device.states.get("_reachable", True),
        }

        # Add additional climate states if available
        if "humidity" in device.states:
            base["state"]["humidity"] = device.states["humidity"]

        if "active" in device.states:
            base["state"]["heating"] = device.states["active"] == 1
            base["state"]["cooling"] = device.states["active"] == 2

        base["capabilities"].update(
            {
                "min_temperature": 5.0,
                "max_temperature": 35.0,
                "temperature_step": 0.5,
                "temperature_unit": "°C",
                "hvac_modes": ["off", "heat", "cool", "auto"],
                "supports_target_temperature": True,
                "supports_current_temperature": True,
            }
        )

        base["metadata"].update(
            {
                "units": "°C",
                "format": "%.1f°C",
                "state_parameters": [
                    "temperature",
                    "current_temperature",
                    "target_temperature",
                    "mode",
                    "mode_str",
                ],
                "control_type": "climate",
            }
        )

        return base

    def _build_switch_state(self, device: LoxoneDevice, base: Dict[str, Any]) -> Dict[str, Any]:
        """Build enhanced state for switch devices."""
        value = device.states.get("value", 0)
        active = device.states.get("active", 0)

        # Convert to boolean
        is_on = bool(value) or bool(active)

        base["state"] = {
            "value": value,
            "active": active,
            "on": is_on,
            "state": "on" if is_on else "off",
            "last_changed": device.states.get("_last_changed"),
            "reachable": device.states.get("_reachable", True),
        }

        base["capabilities"].update({"supports_on_off": True})

        base["metadata"].update(
            {"state_parameters": ["value", "active", "on", "state"], "control_type": "switch"}
        )

        return base

    def _build_fan_state(self, device: LoxoneDevice, base: Dict[str, Any]) -> Dict[str, Any]:
        """Build enhanced state for fan/ventilation devices."""
        value = device.states.get("value", 0.0)
        active = device.states.get("active", 0)

        if isinstance(value, str):
            try:
                value = float(value)
            except (ValueError, TypeError):
                value = 0.0

        base["state"] = {
            "value": value,
            "active": active,
            "on": value > 0 or bool(active),
            "speed": value,
            "speed_pct": value,
            "last_changed": device.states.get("_last_changed"),
            "reachable": device.states.get("_reachable", True),
        }

        base["capabilities"].update(
            {
                "min_speed": 0,
                "max_speed": 100,
                "step": 1,
                "supports_on_off": True,
                "supports_speed": True,
                "fan_modes": ["auto", "low", "medium", "high"],
            }
        )

        base["metadata"].update(
            {
                "units": "%",
                "format": "%.1f%%",
                "state_parameters": ["value", "active", "on", "speed", "speed_pct"],
                "control_type": "fan",
            }
        )

        return base

    def _build_media_player_state(
        self, device: LoxoneDevice, base: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build enhanced state for media player devices."""
        volume = device.states.get("volume", 0.0)
        active = device.states.get("active", 0)
        mode = device.states.get("mode", 0)

        if isinstance(volume, str):
            try:
                volume = float(volume)
            except (ValueError, TypeError):
                volume = 0.0

        # Map mode to playback state
        state_map = {0: "idle", 1: "playing", 2: "paused"}
        playback_state = state_map.get(mode, "idle")

        base["state"] = {
            "volume": volume,
            "volume_pct": volume,
            "active": active,
            "mode": mode,
            "state": playback_state,
            "is_playing": mode == 1,
            "is_paused": mode == 2,
            "last_changed": device.states.get("_last_changed"),
            "reachable": device.states.get("_reachable", True),
        }

        base["capabilities"].update(
            {
                "min_volume": 0,
                "max_volume": 100,
                "volume_step": 1,
                "supports_play_pause": True,
                "supports_stop": True,
                "supports_volume": True,
                "media_content_types": ["music", "radio", "playlist"],
            }
        )

        base["metadata"].update(
            {
                "units": "%",
                "format": "%.1f%%",
                "state_parameters": [
                    "volume",
                    "volume_pct",
                    "active",
                    "mode",
                    "state",
                    "is_playing",
                    "is_paused",
                ],
                "control_type": "media_player",
            }
        )

        return base

    def _build_alarm_state(self, device: LoxoneDevice, base: Dict[str, Any]) -> Dict[str, Any]:
        """Build enhanced state for alarm devices."""
        active = device.states.get("active", 0)
        armed = device.states.get("armed", 0)

        # Map alarm states
        if armed:
            alarm_state = "armed"
        elif active:
            alarm_state = "triggered"
        else:
            alarm_state = "disarmed"

        base["state"] = {
            "active": active,
            "armed": armed,
            "state": alarm_state,
            "is_armed": bool(armed),
            "is_triggered": bool(active),
            "last_changed": device.states.get("_last_changed"),
            "reachable": device.states.get("_reachable", True),
        }

        base["capabilities"].update(
            {
                "supports_arm_disarm": True,
                "requires_code": True,
                "alarm_states": ["disarmed", "armed", "triggered"],
            }
        )

        base["metadata"].update(
            {
                "state_parameters": ["active", "armed", "state", "is_armed", "is_triggered"],
                "control_type": "alarm",
            }
        )

        return base

    def _build_slider_state(self, device: LoxoneDevice, base: Dict[str, Any]) -> Dict[str, Any]:
        """Build enhanced state for slider input devices."""
        value = device.states.get("value", 0.0)

        if isinstance(value, str):
            try:
                value = float(value)
            except (ValueError, TypeError):
                value = 0.0

        min_val = device.details.get("min", 0)
        max_val = device.details.get("max", 100)
        step = device.details.get("step", 1)
        unit = device.details.get("unit", "")

        base["state"] = {
            "value": value,
            "last_changed": device.states.get("_last_changed"),
            "reachable": device.states.get("_reachable", True),
        }

        base["capabilities"].update(
            {
                "min_value": min_val,
                "max_value": max_val,
                "step": step,
                "unit": unit,
                "supports_numeric_input": True,
            }
        )

        base["metadata"].update(
            {
                "units": unit,
                "format": f"%.{len(str(step).split('.')[-1]) if '.' in str(step) else 0}f{unit}",
                "state_parameters": ["value"],
                "control_type": "slider",
            }
        )

        return base

    def _build_text_input_state(self, device: LoxoneDevice, base: Dict[str, Any]) -> Dict[str, Any]:
        """Build enhanced state for text input devices."""
        text = device.states.get("text", "")

        base["state"] = {
            "text": text,
            "value": text,
            "last_changed": device.states.get("_last_changed"),
            "reachable": device.states.get("_reachable", True),
        }

        max_length = device.details.get("maxLength", 255)

        base["capabilities"].update({"supports_text_input": True, "max_length": max_length})

        base["metadata"].update(
            {"state_parameters": ["text", "value"], "control_type": "text_input"}
        )

        return base

    def _build_sensor_state(self, device: LoxoneDevice, base: Dict[str, Any]) -> Dict[str, Any]:
        """Build enhanced state for sensor devices."""
        value = device.states.get("value", 0)

        # Determine if it's a binary or analog sensor
        is_binary = device.type == DEVICE_TYPE_INFO_ONLY_DIGITAL

        base["state"] = {
            "value": value,
            "last_changed": device.states.get("_last_changed"),
            "reachable": device.states.get("_reachable", True),
        }

        if is_binary:
            base["state"]["on"] = bool(value)
            base["state"]["state"] = "on" if bool(value) else "off"

        unit = device.details.get("unit", "")

        base["capabilities"].update(
            {
                "read_only": True,
                "sensor_type": "digital" if is_binary else "analog",
                "binary_sensor": is_binary,
                "unit": unit,
            }
        )

        state_params = ["value"]
        if is_binary:
            state_params.extend(["on", "state"])

        base["metadata"].update(
            {"units": unit, "state_parameters": state_params, "control_type": "sensor"}
        )

        return base

    def _build_scene_state(self, device: LoxoneDevice, base: Dict[str, Any]) -> Dict[str, Any]:
        """Build enhanced state for scene devices."""
        active = device.states.get("active", 0)

        base["state"] = {
            "active": active,
            "is_active": bool(active),
            "last_triggered": device.states.get("_last_changed"),
            "reachable": device.states.get("_reachable", True),
        }

        base["capabilities"].update({"triggerable": True, "scene_control": True})

        base["metadata"].update(
            {"state_parameters": ["active", "is_active", "last_triggered"], "control_type": "scene"}
        )

        return base

    def _build_generic_state(self, device: LoxoneDevice, base: Dict[str, Any]) -> Dict[str, Any]:
        """Build generic state for unknown or unsupported device types."""
        # Include all available states as-is
        base["state"] = device.states.copy()

        # Add basic reachability
        if "_reachable" not in base["state"]:
            base["state"]["_reachable"] = True

        base["metadata"].update(
            {"state_parameters": list(device.states.keys()), "control_type": "generic"}
        )

        return base

"""
Client session management for Loxone MCP Server.

Wraps LoxoneClient and DeviceManager to provide high-level control
methods for all device types. Each session represents a single client
connection with its own state and Loxone Miniserver connection.
"""

import logging
from typing import Dict, Any

from .config import LoxoneConfig
from .loxone_client import LoxoneClient
from .device_manager import DeviceManager

logger = logging.getLogger(__name__)


class ClientSession:
    """
    Represents a single client session with its own Loxone connection.

    Each session maintains its own LoxoneClient and DeviceManager,
    allowing multiple clients to connect to different Miniservers
    with different credentials.
    """

    def __init__(self, client_id: str, config: LoxoneConfig):
        """
        Initialize a client session.

        Args:
            client_id: Unique identifier for this client
            config: LoxoneConfig instance with connection details
        """
        self.client_id = client_id
        self.config = config

        # Initialize Loxone client and device manager
        self.loxone_client = LoxoneClient(config)
        self.device_manager = DeviceManager()

        # Session state
        self._initialized = False
        self._cleanup_done = False

        logger.info(f"ClientSession created for client {client_id}")

    async def initialize(self) -> None:
        """
        Initialize the session by connecting to Miniserver and loading devices.

        Raises:
            ConnectionError: If unable to connect to Miniserver
            ValueError: If unable to load device structure
        """
        if self._initialized:
            logger.warning(f"Session {self.client_id} already initialized")
            return

        logger.info(f"Initializing session for client {self.client_id}")

        try:
            # Connect to Loxone Miniserver
            if not await self.loxone_client.connect():
                raise ConnectionError("Failed to connect to Loxone Miniserver")

            # Start background tasks (keepalive, message processing)
            await self.loxone_client.start()

            # Get device structure
            structure = await self.loxone_client.get_structure()
            if not structure:
                raise ValueError("Failed to retrieve device structure from Miniserver")

            # Load devices into device manager
            self.device_manager.load_devices(structure)

            # Register state update callback
            self.loxone_client.register_state_callback(self._handle_state_update)

            self._initialized = True
            logger.info(f"Session {self.client_id} initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize session {self.client_id}: {e}")
            await self.cleanup()
            raise

    async def cleanup(self) -> None:
        """
        Clean up the session by disconnecting from Miniserver and releasing resources.
        """
        if self._cleanup_done:
            return

        logger.info(f"Cleaning up session for client {self.client_id}")

        try:
            # Disconnect from Miniserver
            if self.loxone_client:
                await self.loxone_client.disconnect()

            # Clear device manager
            if self.device_manager:
                self.device_manager.clear_devices()

            self._cleanup_done = True
            logger.info(f"Session {self.client_id} cleaned up successfully")

        except Exception as e:
            logger.error(f"Error cleaning up session {self.client_id}: {e}")

    async def _handle_state_update(self, state_data: Dict[str, Any]) -> None:
        """
        Handle state updates from Loxone client.

        Args:
            state_data: Dictionary containing UUID -> value mappings
        """
        try:
            for uuid, value in state_data.items():
                self.device_manager.update_state(uuid, {"value": value})
        except Exception as e:
            logger.error(f"Error handling state update in session {self.client_id}: {e}")

    # ============================================================================
    # High-level device control methods
    # ============================================================================

    async def control_switch(self, uuid: str, state: bool) -> Dict[str, Any]:
        """
        Control a switch device (on/off).

        Args:
            uuid: Device UUID
            state: True for on, False for off

        Returns:
            Dictionary with operation result
        """
        try:
            device = self.device_manager.get_device(uuid)
            if not device:
                return {
                    "success": False,
                    "error": "Device not found",
                    "error_code": "DEVICE_NOT_FOUND",
                    "uuid": uuid,
                }

            if device.type not in ["Switch", "TimedSwitch", "Pushbutton"]:
                return {
                    "success": False,
                    "error": f"Device type {device.type} is not a switch",
                    "error_code": "INVALID_DEVICE_TYPE",
                    "uuid": uuid,
                    "device_type": device.type,
                }

            # Send command
            value = "On" if state else "Off"
            success = await self.loxone_client.send_command(uuid, value)

            if success:
                # Update local state
                self.device_manager.update_state(uuid, {"value": 1.0 if state else 0.0})

                return {
                    "success": True,
                    "uuid": uuid,
                    "device_name": device.name,
                    "state": state,
                    "value": value,
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to send command to device",
                    "error_code": "COMMAND_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error controlling switch {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    async def control_dimmer(self, uuid: str, brightness: int) -> Dict[str, Any]:
        """
        Control a dimmer device (0-100%).

        Args:
            uuid: Device UUID
            brightness: Brightness level (0-100)

        Returns:
            Dictionary with operation result
        """
        try:
            device = self.device_manager.get_device(uuid)
            if not device:
                return {
                    "success": False,
                    "error": "Device not found",
                    "error_code": "DEVICE_NOT_FOUND",
                    "uuid": uuid,
                }

            if device.type not in ["Dimmer", "LightControllerV2"]:
                return {
                    "success": False,
                    "error": f"Device type {device.type} is not a dimmer",
                    "error_code": "INVALID_DEVICE_TYPE",
                    "uuid": uuid,
                    "device_type": device.type,
                }

            # Validate brightness range
            if not 0 <= brightness <= 100:
                return {
                    "success": False,
                    "error": "Brightness must be between 0 and 100",
                    "error_code": "INVALID_VALUE",
                    "uuid": uuid,
                    "brightness": brightness,
                }

            # Send command
            success = await self.loxone_client.send_command(uuid, str(brightness))

            if success:
                # Update local state
                self.device_manager.update_state(uuid, {"value": float(brightness)})

                return {
                    "success": True,
                    "uuid": uuid,
                    "device_name": device.name,
                    "brightness": brightness,
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to send command to device",
                    "error_code": "COMMAND_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error controlling dimmer {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    async def control_cover_position(self, uuid: str, position: int) -> Dict[str, Any]:
        """
        Control a cover device position (0=closed, 100=open).

        Args:
            uuid: Device UUID
            position: Position (0-100)

        Returns:
            Dictionary with operation result
        """
        try:
            device = self.device_manager.get_device(uuid)
            if not device:
                return {
                    "success": False,
                    "error": "Device not found",
                    "error_code": "DEVICE_NOT_FOUND",
                    "uuid": uuid,
                }

            if device.type not in ["Jalousie", "Window", "Gate"]:
                return {
                    "success": False,
                    "error": f"Device type {device.type} is not a cover",
                    "error_code": "INVALID_DEVICE_TYPE",
                    "uuid": uuid,
                    "device_type": device.type,
                }

            # Validate position range
            if not 0 <= position <= 100:
                return {
                    "success": False,
                    "error": "Position must be between 0 and 100",
                    "error_code": "INVALID_VALUE",
                    "uuid": uuid,
                    "position": position,
                }

            # Send command (Loxone uses 0-1 range internally)
            loxone_position = position / 100.0
            success = await self.loxone_client.send_command(uuid, str(loxone_position))

            if success:
                # Update local state
                self.device_manager.update_state(uuid, {"value": loxone_position})

                return {
                    "success": True,
                    "uuid": uuid,
                    "device_name": device.name,
                    "position": position,
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to send command to device",
                    "error_code": "COMMAND_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error controlling cover {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    async def control_temperature(self, uuid: str, temperature: float) -> Dict[str, Any]:
        """
        Control a climate device target temperature.

        Args:
            uuid: Device UUID
            temperature: Target temperature in Celsius

        Returns:
            Dictionary with operation result
        """
        try:
            device = self.device_manager.get_device(uuid)
            if not device:
                return {
                    "success": False,
                    "error": "Device not found",
                    "error_code": "DEVICE_NOT_FOUND",
                    "uuid": uuid,
                }

            if device.type != "IRoomControllerV2":
                return {
                    "success": False,
                    "error": f"Device type {device.type} is not a climate controller",
                    "error_code": "INVALID_DEVICE_TYPE",
                    "uuid": uuid,
                    "device_type": device.type,
                }

            # Validate temperature range (reasonable limits)
            if not 5.0 <= temperature <= 35.0:
                return {
                    "success": False,
                    "error": "Temperature must be between 5°C and 35°C",
                    "error_code": "INVALID_VALUE",
                    "uuid": uuid,
                    "temperature": temperature,
                }

            # Send command
            success = await self.loxone_client.send_command(uuid, str(temperature))

            if success:
                # Update local state
                self.device_manager.update_state(uuid, {"target_temperature": temperature})

                return {
                    "success": True,
                    "uuid": uuid,
                    "device_name": device.name,
                    "target_temperature": temperature,
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to send command to device",
                    "error_code": "COMMAND_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error controlling temperature {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    async def send_command(self, uuid: str, value: str) -> Dict[str, Any]:
        """
        Send a generic command to any device.

        Args:
            uuid: Device UUID
            value: Command value to send

        Returns:
            Dictionary with operation result
        """
        try:
            device = self.device_manager.get_device(uuid)
            if not device:
                return {
                    "success": False,
                    "error": "Device not found",
                    "error_code": "DEVICE_NOT_FOUND",
                    "uuid": uuid,
                }

            # Send command
            success = await self.loxone_client.send_command(uuid, value)

            if success:
                return {
                    "success": True,
                    "uuid": uuid,
                    "device_name": device.name,
                    "command_value": value,
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to send command to device",
                    "error_code": "COMMAND_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error sending command to {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    async def send_secured_command(self, uuid: str, value: str, code: str) -> Dict[str, Any]:
        """
        Send a secured command with PIN code authentication.

        Args:
            uuid: Device UUID
            value: Command value to send
            code: PIN code for authentication

        Returns:
            Dictionary with operation result
        """
        try:
            device = self.device_manager.get_device(uuid)
            if not device:
                return {
                    "success": False,
                    "error": "Device not found",
                    "error_code": "DEVICE_NOT_FOUND",
                    "uuid": uuid,
                }

            # Send secured command
            success = await self.loxone_client.send_secured_command(uuid, value, code)

            if success:
                return {
                    "success": True,
                    "uuid": uuid,
                    "device_name": device.name,
                    "command_value": value,
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to send secured command (check PIN code)",
                    "error_code": "SECURED_COMMAND_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error sending secured command to {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    async def trigger_scene(self, uuid: str) -> Dict[str, Any]:
        """
        Trigger a scene.

        Args:
            uuid: Scene UUID

        Returns:
            Dictionary with operation result
        """
        try:
            scene = self.device_manager.get_scene(uuid)
            if not scene:
                return {
                    "success": False,
                    "error": "Scene not found",
                    "error_code": "SCENE_NOT_FOUND",
                    "uuid": uuid,
                }

            # Send scene trigger command
            success = await self.loxone_client.send_command(uuid, "On")

            if success:
                return {"success": True, "uuid": uuid, "scene_name": scene.name}
            else:
                return {
                    "success": False,
                    "error": "Failed to trigger scene",
                    "error_code": "SCENE_TRIGGER_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error triggering scene {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    # ============================================================================
    # Complete Home Assistant Component Feature Migration - Additional Control Methods
    # ============================================================================

    async def control_light_color(self, uuid: str, color: str) -> Dict[str, Any]:
        """
        Control RGB color lighting.

        Args:
            uuid: Device UUID
            color: Color in hex format (#RRGGBB) or HSV format

        Returns:
            Dictionary with operation result
        """
        try:
            device = self.device_manager.get_device(uuid)
            if not device:
                return {
                    "success": False,
                    "error": "Device not found",
                    "error_code": "DEVICE_NOT_FOUND",
                    "uuid": uuid,
                }

            if device.type != "ColorPickerV2":
                return {
                    "success": False,
                    "error": f"Device type {device.type} does not support color control",
                    "error_code": "INVALID_DEVICE_TYPE",
                    "uuid": uuid,
                    "device_type": device.type,
                }

            # Validate color format (hex)
            if color.startswith("#") and len(color) == 7:
                try:
                    # Convert hex to RGB values
                    r = int(color[1:3], 16)
                    g = int(color[3:5], 16)
                    b = int(color[5:7], 16)

                    # Convert to HSV for Loxone (simplified conversion)
                    # Loxone ColorPickerV2 typically uses HSV format
                    max_val = max(r, g, b)
                    min_val = min(r, g, b)
                    diff = max_val - min_val

                    # Calculate hue
                    if diff == 0:
                        hue = 0
                    elif max_val == r:
                        hue = (60 * ((g - b) / diff) + 360) % 360
                    elif max_val == g:
                        hue = (60 * ((b - r) / diff) + 120) % 360
                    else:
                        hue = (60 * ((r - g) / diff) + 240) % 360

                    # Calculate saturation
                    saturation = 0 if max_val == 0 else (diff / max_val) * 100

                    # Calculate value (brightness)
                    value = (max_val / 255) * 100

                    # Send HSV command to Loxone
                    hsv_command = f"{hue},{saturation},{value}"
                    success = await self.loxone_client.send_command(uuid, hsv_command)

                except ValueError:
                    return {
                        "success": False,
                        "error": "Invalid hex color format",
                        "error_code": "INVALID_COLOR_FORMAT",
                        "uuid": uuid,
                        "color": color,
                    }
            else:
                return {
                    "success": False,
                    "error": "Color must be in hex format (#RRGGBB)",
                    "error_code": "INVALID_COLOR_FORMAT",
                    "uuid": uuid,
                    "color": color,
                }

            if success:
                # Update local state
                self.device_manager.update_state(
                    uuid,
                    {"color": color, "hue": hue, "saturation": saturation, "brightness": value},
                )

                return {
                    "success": True,
                    "uuid": uuid,
                    "device_name": device.name,
                    "color": color,
                    "hsv": {"hue": hue, "saturation": saturation, "value": value},
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to send color command to device",
                    "error_code": "COMMAND_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error controlling light color {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    async def control_cover_open(self, uuid: str) -> Dict[str, Any]:
        """
        Open a cover completely.

        Args:
            uuid: Device UUID

        Returns:
            Dictionary with operation result
        """
        return await self.control_cover_position(uuid, 100)

    async def control_cover_close(self, uuid: str) -> Dict[str, Any]:
        """
        Close a cover completely.

        Args:
            uuid: Device UUID

        Returns:
            Dictionary with operation result
        """
        return await self.control_cover_position(uuid, 0)

    async def control_climate_mode(self, uuid: str, mode: str) -> Dict[str, Any]:
        """
        Control climate control mode.

        Args:
            uuid: Device UUID
            mode: Climate mode (heat, cool, auto, off)

        Returns:
            Dictionary with operation result
        """
        try:
            device = self.device_manager.get_device(uuid)
            if not device:
                return {
                    "success": False,
                    "error": "Device not found",
                    "error_code": "DEVICE_NOT_FOUND",
                    "uuid": uuid,
                }

            if device.type != "IRoomControllerV2":
                return {
                    "success": False,
                    "error": f"Device type {device.type} is not a climate controller",
                    "error_code": "INVALID_DEVICE_TYPE",
                    "uuid": uuid,
                    "device_type": device.type,
                }

            # Validate mode
            valid_modes = ["off", "heat", "cool", "auto"]
            if mode not in valid_modes:
                return {
                    "success": False,
                    "error": f"Invalid mode. Valid modes: {', '.join(valid_modes)}",
                    "error_code": "INVALID_MODE",
                    "uuid": uuid,
                    "mode": mode,
                }

            # Map mode to Loxone command
            mode_commands = {"off": "0", "heat": "1", "cool": "2", "auto": "3"}

            # Send command
            success = await self.loxone_client.send_command(uuid, mode_commands[mode])

            if success:
                # Update local state
                self.device_manager.update_state(uuid, {"mode": mode})

                return {"success": True, "uuid": uuid, "device_name": device.name, "mode": mode}
            else:
                return {
                    "success": False,
                    "error": "Failed to send mode command to device",
                    "error_code": "COMMAND_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error controlling climate mode {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    async def control_fan_speed(self, uuid: str, speed: int) -> Dict[str, Any]:
        """
        Control fan speed for ventilation controls.

        Args:
            uuid: Device UUID
            speed: Fan speed (0-100)

        Returns:
            Dictionary with operation result
        """
        try:
            device = self.device_manager.get_device(uuid)
            if not device:
                return {
                    "success": False,
                    "error": "Device not found",
                    "error_code": "DEVICE_NOT_FOUND",
                    "uuid": uuid,
                }

            if device.type != "Ventilation":
                return {
                    "success": False,
                    "error": f"Device type {device.type} is not a ventilation control",
                    "error_code": "INVALID_DEVICE_TYPE",
                    "uuid": uuid,
                    "device_type": device.type,
                }

            # Validate speed range
            if not 0 <= speed <= 100:
                return {
                    "success": False,
                    "error": "Fan speed must be between 0 and 100",
                    "error_code": "INVALID_VALUE",
                    "uuid": uuid,
                    "speed": speed,
                }

            # Send command (convert to 0-1 range for Loxone)
            loxone_speed = speed / 100.0
            success = await self.loxone_client.send_command(uuid, str(loxone_speed))

            if success:
                # Update local state
                self.device_manager.update_state(uuid, {"fan_speed": speed})

                return {
                    "success": True,
                    "uuid": uuid,
                    "device_name": device.name,
                    "fan_speed": speed,
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to send fan speed command to device",
                    "error_code": "COMMAND_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error controlling fan speed {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    async def control_media_play(self, uuid: str) -> Dict[str, Any]:
        """
        Start media playback.

        Args:
            uuid: Device UUID

        Returns:
            Dictionary with operation result
        """
        try:
            device = self.device_manager.get_device(uuid)
            if not device:
                return {
                    "success": False,
                    "error": "Device not found",
                    "error_code": "DEVICE_NOT_FOUND",
                    "uuid": uuid,
                }

            if device.type not in ["AudioZoneV2", "MediaPlayer"]:
                return {
                    "success": False,
                    "error": f"Device type {device.type} is not a media player",
                    "error_code": "INVALID_DEVICE_TYPE",
                    "uuid": uuid,
                    "device_type": device.type,
                }

            # Send play command
            success = await self.loxone_client.send_command(uuid, "play")

            if success:
                # Update local state
                self.device_manager.update_state(uuid, {"state": "playing"})

                return {"success": True, "uuid": uuid, "device_name": device.name, "action": "play"}
            else:
                return {
                    "success": False,
                    "error": "Failed to send play command to device",
                    "error_code": "COMMAND_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error controlling media play {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    async def control_media_pause(self, uuid: str) -> Dict[str, Any]:
        """
        Pause media playback.

        Args:
            uuid: Device UUID

        Returns:
            Dictionary with operation result
        """
        try:
            device = self.device_manager.get_device(uuid)
            if not device:
                return {
                    "success": False,
                    "error": "Device not found",
                    "error_code": "DEVICE_NOT_FOUND",
                    "uuid": uuid,
                }

            if device.type not in ["AudioZoneV2", "MediaPlayer"]:
                return {
                    "success": False,
                    "error": f"Device type {device.type} is not a media player",
                    "error_code": "INVALID_DEVICE_TYPE",
                    "uuid": uuid,
                    "device_type": device.type,
                }

            # Send pause command
            success = await self.loxone_client.send_command(uuid, "pause")

            if success:
                # Update local state
                self.device_manager.update_state(uuid, {"state": "paused"})

                return {
                    "success": True,
                    "uuid": uuid,
                    "device_name": device.name,
                    "action": "pause",
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to send pause command to device",
                    "error_code": "COMMAND_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error controlling media pause {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    async def control_volume(self, uuid: str, volume: int) -> Dict[str, Any]:
        """
        Control media player volume.

        Args:
            uuid: Device UUID
            volume: Volume level (0-100)

        Returns:
            Dictionary with operation result
        """
        try:
            device = self.device_manager.get_device(uuid)
            if not device:
                return {
                    "success": False,
                    "error": "Device not found",
                    "error_code": "DEVICE_NOT_FOUND",
                    "uuid": uuid,
                }

            if device.type not in ["AudioZoneV2", "MediaPlayer"]:
                return {
                    "success": False,
                    "error": f"Device type {device.type} is not a media player",
                    "error_code": "INVALID_DEVICE_TYPE",
                    "uuid": uuid,
                    "device_type": device.type,
                }

            # Validate volume range
            if not 0 <= volume <= 100:
                return {
                    "success": False,
                    "error": "Volume must be between 0 and 100",
                    "error_code": "INVALID_VALUE",
                    "uuid": uuid,
                    "volume": volume,
                }

            # Send volume command (convert to 0-1 range for Loxone)
            loxone_volume = volume / 100.0
            success = await self.loxone_client.send_command(uuid, str(loxone_volume))

            if success:
                # Update local state
                self.device_manager.update_state(uuid, {"volume": volume})

                return {"success": True, "uuid": uuid, "device_name": device.name, "volume": volume}
            else:
                return {
                    "success": False,
                    "error": "Failed to send volume command to device",
                    "error_code": "COMMAND_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error controlling volume {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    async def control_alarm_arm(self, uuid: str, code: str) -> Dict[str, Any]:
        """
        Arm alarm system with PIN code.

        Args:
            uuid: Device UUID
            code: PIN code for authentication

        Returns:
            Dictionary with operation result
        """
        try:
            device = self.device_manager.get_device(uuid)
            if not device:
                return {
                    "success": False,
                    "error": "Device not found",
                    "error_code": "DEVICE_NOT_FOUND",
                    "uuid": uuid,
                }

            if device.type not in ["Alarm", "CentralAlarm"]:
                return {
                    "success": False,
                    "error": f"Device type {device.type} is not an alarm system",
                    "error_code": "INVALID_DEVICE_TYPE",
                    "uuid": uuid,
                    "device_type": device.type,
                }

            # Send secured arm command
            success = await self.loxone_client.send_secured_command(uuid, "arm", code)

            if success:
                # Update local state
                self.device_manager.update_state(uuid, {"state": "armed"})

                return {"success": True, "uuid": uuid, "device_name": device.name, "action": "arm"}
            else:
                return {
                    "success": False,
                    "error": "Failed to arm alarm (check PIN code)",
                    "error_code": "ALARM_ARM_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error arming alarm {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    async def control_alarm_disarm(self, uuid: str, code: str) -> Dict[str, Any]:
        """
        Disarm alarm system with PIN code.

        Args:
            uuid: Device UUID
            code: PIN code for authentication

        Returns:
            Dictionary with operation result
        """
        try:
            device = self.device_manager.get_device(uuid)
            if not device:
                return {
                    "success": False,
                    "error": "Device not found",
                    "error_code": "DEVICE_NOT_FOUND",
                    "uuid": uuid,
                }

            if device.type not in ["Alarm", "CentralAlarm"]:
                return {
                    "success": False,
                    "error": f"Device type {device.type} is not an alarm system",
                    "error_code": "INVALID_DEVICE_TYPE",
                    "uuid": uuid,
                    "device_type": device.type,
                }

            # Send secured disarm command
            success = await self.loxone_client.send_secured_command(uuid, "disarm", code)

            if success:
                # Update local state
                self.device_manager.update_state(uuid, {"state": "disarmed"})

                return {
                    "success": True,
                    "uuid": uuid,
                    "device_name": device.name,
                    "action": "disarm",
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to disarm alarm (check PIN code)",
                    "error_code": "ALARM_DISARM_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error disarming alarm {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    async def control_text_input(self, uuid: str, text: str) -> Dict[str, Any]:
        """
        Set text input value.

        Args:
            uuid: Device UUID
            text: Text value to set

        Returns:
            Dictionary with operation result
        """
        try:
            device = self.device_manager.get_device(uuid)
            if not device:
                return {
                    "success": False,
                    "error": "Device not found",
                    "error_code": "DEVICE_NOT_FOUND",
                    "uuid": uuid,
                }

            if device.type != "TextInput":
                return {
                    "success": False,
                    "error": f"Device type {device.type} is not a text input",
                    "error_code": "INVALID_DEVICE_TYPE",
                    "uuid": uuid,
                    "device_type": device.type,
                }

            # Validate text length
            max_length = device.capabilities.get("max_length", 255)
            if len(text) > max_length:
                return {
                    "success": False,
                    "error": f"Text length exceeds maximum of {max_length} characters",
                    "error_code": "TEXT_TOO_LONG",
                    "uuid": uuid,
                    "text_length": len(text),
                    "max_length": max_length,
                }

            # Send text command
            success = await self.loxone_client.send_command(uuid, text)

            if success:
                # Update local state
                self.device_manager.update_state(uuid, {"text": text})

                return {"success": True, "uuid": uuid, "device_name": device.name, "text": text}
            else:
                return {
                    "success": False,
                    "error": "Failed to send text command to device",
                    "error_code": "COMMAND_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error controlling text input {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    async def control_number_input(self, uuid: str, value: float) -> Dict[str, Any]:
        """
        Set number input value (slider).

        Args:
            uuid: Device UUID
            value: Numeric value to set

        Returns:
            Dictionary with operation result
        """
        try:
            device = self.device_manager.get_device(uuid)
            if not device:
                return {
                    "success": False,
                    "error": "Device not found",
                    "error_code": "DEVICE_NOT_FOUND",
                    "uuid": uuid,
                }

            if device.type not in ["Slider", "UpDownAnalog"]:
                return {
                    "success": False,
                    "error": f"Device type {device.type} is not a number input",
                    "error_code": "INVALID_DEVICE_TYPE",
                    "uuid": uuid,
                    "device_type": device.type,
                }

            # Validate value range
            value_range = device.capabilities.get("value_range", [0, 100])
            min_val, max_val = value_range
            if not min_val <= value <= max_val:
                return {
                    "success": False,
                    "error": f"Value must be between {min_val} and {max_val}",
                    "error_code": "INVALID_VALUE",
                    "uuid": uuid,
                    "value": value,
                    "range": value_range,
                }

            # Send value command
            success = await self.loxone_client.send_command(uuid, str(value))

            if success:
                # Update local state
                self.device_manager.update_state(uuid, {"value": value})

                return {"success": True, "uuid": uuid, "device_name": device.name, "value": value}
            else:
                return {
                    "success": False,
                    "error": "Failed to send value command to device",
                    "error_code": "COMMAND_FAILED",
                    "uuid": uuid,
                }

        except Exception as e:
            logger.error(f"Error controlling number input {uuid}: {e}")
            return {"success": False, "error": str(e), "error_code": "INTERNAL_ERROR", "uuid": uuid}

    # ============================================================================
    # Session properties and status
    # ============================================================================

    @property
    def is_initialized(self) -> bool:
        """Check if the session is initialized."""
        return self._initialized

    @property
    def is_connected(self) -> bool:
        """Check if the session is connected to Miniserver."""
        return (
            self._initialized
            and self.loxone_client
            and self.loxone_client.state.value == "CONNECTED"
        )

    def get_session_info(self) -> Dict[str, Any]:
        """
        Get session information.

        Returns:
            Dictionary with session details
        """
        return {
            "client_id": self.client_id,
            "initialized": self.is_initialized,
            "connected": self.is_connected,
            "host": self.config.host,
            "port": self.config.port,
            "username": self.config.username,
            "device_count": self.device_manager.get_device_count(),
            "scene_count": self.device_manager.get_scene_count(),
        }

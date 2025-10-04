# Design Document

## Overview

This design document describes the architecture for refactoring the Home Assistant Loxone integration into a standalone MCP (Model Context Protocol) server. The server will expose Loxone Miniserver functionality through standardized MCP tools, enabling any MCP-compatible client to interact with Loxone devices.

The design preserves the core Loxone communication logic (websocket protocol, encryption, authentication) from the existing implementation while replacing the Home Assistant-specific entity framework with MCP tool definitions. The server will be implemented as a Python application using the FastMCP framework or similar MCP SDK.

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   MCP Clients                                │
│         (AI Assistant, IDE, etc. with credentials)          │
└────────────────────────┬────────────────────────────────────┘
                         │ MCP Protocol (stdio/HTTP)
                         │ + Client Credentials
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   Loxone MCP Server                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              MCP Tool Layer                          │   │
│  │  - Device Control Tools (all HA component types)    │   │
│  │  - Device Query Tools                                │   │
│  │  - Room Management Tools                             │   │
│  │  - Scene Management Tools                            │   │
│  │  - Media Player Tools                                │   │
│  │  - Climate Control Tools                             │   │
│  │  - Alarm System Tools                                │   │
│  └──────────────────┬───────────────────────────────────┘   │
│                     │                                        │
│  ┌──────────────────▼───────────────────────────────────┐   │
│  │         Multi-Client Connection Manager              │   │
│  │  - Client Session Management                         │   │
│  │  - Credential Handling                               │   │
│  │  - Connection Pooling                                │   │
│  └──────────────────┬───────────────────────────────────┘   │
│                     │                                        │
│  ┌──────────────────▼───────────────────────────────────┐   │
│  │         Device State Manager                         │   │
│  │  - Device Registry (per connection)                  │   │
│  │  - State Cache (per connection)                      │   │
│  │  - Event Processing                                  │   │
│  │  - Room Management                                   │   │
│  └──────────────────┬───────────────────────────────────┘   │
│                     │                                        │
│  ┌──────────────────▼───────────────────────────────────┐   │
│  │      Loxone Communication Layer                      │   │
│  │  - Multiple WebSocket Clients                        │   │
│  │  - Authentication & Encryption                       │   │
│  │  - Message Parser                                    │   │
│  │  - Connection Manager                                │   │
│  └──────────────────┬───────────────────────────────────┘   │
└─────────────────────┼───────────────────────────────────────┘
                      │ Multiple WebSocket connections
                      │ (encrypted, per client)
                      │
┌─────────────────────▼───────────────────────────────────────┐
│           Multiple Loxone Miniservers                       │
│     (Different hosts based on client credentials)           │
└──────────────────────────────────────────────────────────────┘
```

### Component Breakdown

1. **MCP Tool Layer**: Exposes complete Loxone functionality as MCP tools (all Home Assistant component features)
2. **Multi-Client Connection Manager**: Manages multiple client sessions with different credentials
3. **Device State Manager**: Maintains device registry and current states per connection
4. **Loxone Communication Layer**: Handles multiple Miniserver connections
5. **Configuration Manager**: Manages server configuration and token persistence per connection

## Key Libraries and Technologies

### MCP SDK (mcp)
- **Purpose**: Model Context Protocol server implementation
- **Documentation**: https://github.com/modelcontextprotocol/python-sdk
- **Context7 Library ID**: `/modelcontextprotocol/python-sdk`
- **Usage**: Provides FastMCP for high-level server creation and low-level Server class for advanced control
- **Version**: >=0.9.0
- **Key Features**:
  - **FastMCP**: Simplified server creation with decorators (`@mcp.tool()`, `@mcp.resource()`, `@mcp.prompt()`)
  - **Low-level Server**: Full control over request handling and lifespan management
  - **Multiple Transports**: stdio (default), SSE, HTTP
  - **Automatic Validation**: Input/output schema validation
  - **Structured Output**: Support for typed tool responses
- **Example Pattern**:
  ```python
  from mcp.server.fastmcp import FastMCP
  
  mcp = FastMCP("loxone-server")
  
  @mcp.tool()
  def control_device(uuid: str, value: str) -> dict:
      """Control a Loxone device"""
      return {"success": True, "uuid": uuid}
  ```

### websockets
- **Purpose**: WebSocket client for Loxone Miniserver communication
- **Documentation**: https://websockets.readthedocs.io/
- **Context7 Library ID**: `/python-websockets/websockets`
- **Usage**: Persistent WebSocket connection for real-time communication
- **Version**: >=14.0 (latest stable)
- **Key Features**: 
  - **Async/await support**: Full asyncio integration
  - **Automatic reconnection**: Use `async for websocket in connect(...)` pattern
  - **Connection state management**: Built-in state tracking (OPEN, CLOSING, CLOSED)
  - **Keepalive**: Automatic ping/pong frames
  - **Context manager**: Graceful connection closure with `async with connect(...)`
- **Reconnection Pattern**:
  ```python
  from websockets.asyncio.client import connect
  from websockets.exceptions import ConnectionClosed
  
  async for websocket in connect(uri):
      try:
          async for message in websocket:
              await process_message(message)
      except ConnectionClosed:
          continue  # Automatically reconnects
  ```

### pycryptodome
- **Purpose**: Cryptographic operations for Loxone protocol
- **Documentation**: https://pycryptodome.readthedocs.io/
- **Usage**: AES encryption, RSA key exchange, HMAC token hashing
- **Version**: >=3.20.0
- **Key Modules Used**:
  - `Crypto.Cipher.AES`: AES encryption for commands
  - `Crypto.Cipher.PKCS1_v1_5`: RSA for key exchange
  - `Crypto.Hash.HMAC`: Token authentication
  - `Crypto.Hash.SHA1`, `SHA256`: Hashing algorithms
  - `Crypto.PublicKey.RSA`: Public key operations
  - `Crypto.Util.Padding`: PKCS7 padding for AES
  - `Crypto.Random`: Secure random number generation

### httpx
- **Purpose**: HTTP client for initial configuration retrieval
- **Documentation**: https://www.python-httpx.org/
- **Context7 Library ID**: `/encode/httpx`
- **Usage**: Fetch LoxAPP3.json structure file from Miniserver
- **Version**: >=0.27.0
- **Key Features**:
  - **Async support**: `AsyncClient` for non-blocking requests
  - **HTTP/2 support**: Modern protocol support
  - **Automatic redirects**: Needed for Loxone cloud connections
  - **SSL verification control**: Custom SSL contexts and certificate validation
  - **Authentication**: Built-in BasicAuth support
  - **Connection pooling**: Efficient resource management
- **Usage Pattern**:
  ```python
  async with httpx.AsyncClient(
      auth=(username, password),
      verify=False,  # For self-signed certs
      follow_redirects=True,
      timeout=30.0
  ) as client:
      response = await client.get(url)
  ```

### uv
- **Purpose**: Fast Python package installer and resolver
- **Documentation**: https://docs.astral.sh/uv/
- **Usage**: Project dependency management and virtual environment
- **Key Commands**:
  - `uv venv`: Create virtual environment
  - `uv pip install`: Install dependencies
  - `uv run`: Run commands in virtual environment
  - `uvx`: Run tools without installation
  - `uv sync`: Sync dependencies from lock file

## Components and Interfaces

### 1. MCP Server Entry Point (`server.py`)

The main entry point that initializes the MCP server and registers all tools. We'll use **FastMCP** from the official Python MCP SDK for simplified server creation with multi-client support.

**FastMCP Approach with Multi-Client Support:**
- FastMCP provides a high-level, decorator-based API for creating MCP servers
- Tools are registered using `@mcp.tool()` decorator with client context
- Automatic input/output validation based on type hints
- Built-in support for stdio, SSE, and HTTP transports
- Enhanced lifespan management for multiple client connections
- Client session management with credential isolation

```python
"""
Loxone MCP Server - Main entry point with multi-client support

Run with: uv run loxone-mcp-server
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ClientCapabilities

from .config import LoxoneConfig
from .connection_manager import ConnectionManager
from .client_session import ClientSession

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global connection manager
connection_manager: ConnectionManager | None = None

# Create FastMCP server
mcp = FastMCP("loxone-mcp-server")


@asynccontextmanager
async def server_lifespan():
    """Manage server lifecycle - initialize and cleanup resources"""
    global connection_manager
    
    logger.info("Initializing Loxone MCP Server...")
    
    # Initialize connection manager
    connection_manager = ConnectionManager()
    
    try:
        yield {"connection_manager": connection_manager}
    finally:
        # Cleanup on shutdown
        logger.info("Shutting down Loxone MCP Server...")
        await connection_manager.cleanup_all()


# Set the lifespan manager
mcp.lifespan = server_lifespan


@mcp.client_connected()
async def client_connected(client_id: str, capabilities: ClientCapabilities):
    """Handle new client connection"""
    logger.info(f"Client connected: {client_id}")
    
    # Check if client provided credentials in capabilities
    client_credentials = None
    if hasattr(capabilities, 'experimental') and capabilities.experimental:
        client_credentials = capabilities.experimental.get('loxone_credentials')
    
    if client_credentials:
        # Use client-provided credentials
        config = LoxoneConfig(
            host=client_credentials['host'],
            port=client_credentials.get('port', 80),
            username=client_credentials['username'],
            password=client_credentials['password']
        )
        logger.info(f"Using client credentials for {client_credentials['host']}")
    else:
        # Fall back to environment/config file
        config = LoxoneConfig.from_env()
        logger.info("Using default configuration")
    
    # Create client session
    session = await connection_manager.create_session(client_id, config)
    logger.info(f"Created session for client {client_id}")


@mcp.client_disconnected()
async def client_disconnected(client_id: str):
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {client_id}")
    await connection_manager.remove_session(client_id)


# ============================================================================
# Tool Definitions
# ============================================================================

# ============================================================================
# Complete Device Control Tools (All Home Assistant Component Features)
# ============================================================================

@mcp.tool()
def loxone_list_devices(
    client_id: str,
    device_type: str | None = None,
    room: str | None = None
) -> list[dict[str, Any]]:
    """List all Loxone devices with optional filtering."""
    session = connection_manager.get_session(client_id)
    devices = session.device_manager.list_devices(device_type=device_type, room=room)
    return [
        {
            "uuid": d.uuid,
            "name": d.name,
            "type": d.type,
            "room": d.room,
            "category": d.category
        }
        for d in devices
    ]


@mcp.tool()
def loxone_list_rooms(client_id: str) -> list[dict[str, Any]]:
    """List all rooms with device counts."""
    session = connection_manager.get_session(client_id)
    return session.device_manager.list_rooms()


@mcp.tool()
def loxone_get_room_devices(client_id: str, room: str) -> list[dict[str, Any]]:
    """Get all devices in a specific room with their current states."""
    session = connection_manager.get_session(client_id)
    return session.device_manager.get_room_devices(room)


@mcp.tool()
async def loxone_control_room(client_id: str, room: str, action: str) -> dict[str, Any]:
    """Control all compatible devices in a room (e.g., 'lights_off', 'all_off')."""
    session = connection_manager.get_session(client_id)
    return await session.device_manager.control_room(room, action)


# Switch Controls
@mcp.tool()
async def loxone_set_switch(client_id: str, uuid: str, state: bool) -> dict[str, Any]:
    """Turn a Loxone switch on or off."""
    session = connection_manager.get_session(client_id)
    return await session.control_switch(uuid, state)


# Light Controls (Dimmer, LightController, ColorPicker)
@mcp.tool()
async def loxone_set_dimmer(client_id: str, uuid: str, brightness: int) -> dict[str, Any]:
    """Set the brightness of a Loxone dimmer (0-100)."""
    session = connection_manager.get_session(client_id)
    return await session.control_dimmer(uuid, brightness)


@mcp.tool()
async def loxone_set_light_color(client_id: str, uuid: str, color: str) -> dict[str, Any]:
    """Set the color of a Loxone color light (hex format #RRGGBB)."""
    session = connection_manager.get_session(client_id)
    return await session.control_light_color(uuid, color)


# Cover Controls (Jalousie, Window, Gate)
@mcp.tool()
async def loxone_set_cover_position(client_id: str, uuid: str, position: int) -> dict[str, Any]:
    """Set cover position (0=closed, 100=open)."""
    session = connection_manager.get_session(client_id)
    return await session.control_cover_position(uuid, position)


@mcp.tool()
async def loxone_cover_open(client_id: str, uuid: str) -> dict[str, Any]:
    """Open a cover completely."""
    session = connection_manager.get_session(client_id)
    return await session.control_cover_open(uuid)


@mcp.tool()
async def loxone_cover_close(client_id: str, uuid: str) -> dict[str, Any]:
    """Close a cover completely."""
    session = connection_manager.get_session(client_id)
    return await session.control_cover_close(uuid)


# Climate Controls
@mcp.tool()
async def loxone_set_temperature(client_id: str, uuid: str, temperature: float) -> dict[str, Any]:
    """Set target temperature for climate control."""
    session = connection_manager.get_session(client_id)
    return await session.control_temperature(uuid, temperature)


@mcp.tool()
async def loxone_set_climate_mode(client_id: str, uuid: str, mode: str) -> dict[str, Any]:
    """Set climate control mode (heat, cool, auto, off)."""
    session = connection_manager.get_session(client_id)
    return await session.control_climate_mode(uuid, mode)


# Fan Controls
@mcp.tool()
async def loxone_set_fan_speed(client_id: str, uuid: str, speed: int) -> dict[str, Any]:
    """Set fan speed (0-100)."""
    session = connection_manager.get_session(client_id)
    return await session.control_fan_speed(uuid, speed)


# Media Player Controls
@mcp.tool()
async def loxone_media_play(client_id: str, uuid: str) -> dict[str, Any]:
    """Start media playback."""
    session = connection_manager.get_session(client_id)
    return await session.control_media_play(uuid)


@mcp.tool()
async def loxone_media_pause(client_id: str, uuid: str) -> dict[str, Any]:
    """Pause media playback."""
    session = connection_manager.get_session(client_id)
    return await session.control_media_pause(uuid)


@mcp.tool()
async def loxone_set_volume(client_id: str, uuid: str, volume: int) -> dict[str, Any]:
    """Set media player volume (0-100)."""
    session = connection_manager.get_session(client_id)
    return await session.control_volume(uuid, volume)


# Alarm System Controls
@mcp.tool()
async def loxone_arm_alarm(client_id: str, uuid: str, code: str) -> dict[str, Any]:
    """Arm alarm system with PIN code."""
    session = connection_manager.get_session(client_id)
    return await session.control_alarm_arm(uuid, code)


@mcp.tool()
async def loxone_disarm_alarm(client_id: str, uuid: str, code: str) -> dict[str, Any]:
    """Disarm alarm system with PIN code."""
    session = connection_manager.get_session(client_id)
    return await session.control_alarm_disarm(uuid, code)


# Text and Number Input Controls
@mcp.tool()
async def loxone_set_text_input(client_id: str, uuid: str, text: str) -> dict[str, Any]:
    """Set text input value."""
    session = connection_manager.get_session(client_id)
    return await session.control_text_input(uuid, text)


@mcp.tool()
async def loxone_set_number_input(client_id: str, uuid: str, value: float) -> dict[str, Any]:
    """Set number input value (slider)."""
    session = connection_manager.get_session(client_id)
    return await session.control_number_input(uuid, value)


# Scene Management
@mcp.tool()
def loxone_list_scenes(client_id: str) -> list[dict[str, Any]]:
    """List all available scenes."""
    session = connection_manager.get_session(client_id)
    return session.device_manager.list_scenes()


@mcp.tool()
async def loxone_trigger_scene(client_id: str, uuid: str) -> dict[str, Any]:
    """Trigger a scene."""
    session = connection_manager.get_session(client_id)
    return await session.trigger_scene(uuid)


# Generic Command Tool
@mcp.tool()
async def loxone_send_command(client_id: str, uuid: str, value: str) -> dict[str, Any]:
    """Send a generic command to any Loxone device."""
    session = connection_manager.get_session(client_id)
    return await session.send_command(uuid, value)


# Secured Command Tool
@mcp.tool()
async def loxone_send_secured_command(client_id: str, uuid: str, value: str, code: str) -> dict[str, Any]:
    """Send a secured command with PIN code."""
    session = connection_manager.get_session(client_id)
    return await session.send_secured_command(uuid, value, code)


def main():
    """Main entry point for the server"""
    # Run the FastMCP server
    mcp.run()


if __name__ == "__main__":
    main()
```

### 2. Connection Manager (`connection_manager.py`)

Manages multiple client sessions and their associated Loxone connections.

**Key Classes:**

- `ConnectionManager`: Central connection management
  - Manages multiple client sessions
  - Handles session creation and cleanup
  - Provides session lookup by client ID

- `ClientSession`: Individual client session
  - Wraps LoxoneClient and DeviceManager for a specific client
  - Provides high-level control methods
  - Manages client-specific state

**Key Methods:**

```python
class ConnectionManager:
    async def create_session(self, client_id: str, config: LoxoneConfig) -> ClientSession
    async def remove_session(self, client_id: str) -> None
    def get_session(self, client_id: str) -> ClientSession
    async def cleanup_all(self) -> None

class ClientSession:
    async def control_switch(self, uuid: str, state: bool) -> dict
    async def control_dimmer(self, uuid: str, brightness: int) -> dict
    async def control_cover_position(self, uuid: str, position: int) -> dict
    async def control_temperature(self, uuid: str, temperature: float) -> dict
    # ... all other control methods for complete HA component feature set
```

### 3. Loxone Client (`loxone_client.py`)

Refactored from the existing `api.py`, this component handles all Miniserver communication.

**Key Classes:**

- `LoxoneClient`: Main client class (refactored from `LoxWs`)
  - Manages websocket connection
  - Handles authentication and encryption
  - Processes incoming messages
  - Sends commands to Miniserver

- `LoxoneConfig`: Configuration data class
  - Host, port, credentials
  - Token persistence settings
  - Connection parameters

- `MessageParser`: Parses Loxone binary and text messages
  - Handles different message types (text, binary, state updates)
  - Decodes UUIDs and values from binary packets

**Key Methods:**

```python
class LoxoneClient:
    async def connect(self) -> bool
    async def disconnect(self) -> None
    async def send_command(self, uuid: str, value: str) -> bool
    async def send_secured_command(self, uuid: str, value: str, code: str) -> bool
    async def get_structure(self) -> dict  # LoxAPP3.json
    def register_state_callback(self, callback: Callable)
```

### 4. Device Manager (`device_manager.py`)

Enhanced device management with complete Home Assistant component feature support.

**Key Classes:**

- `DeviceManager`: Central device management
  - Stores device registry for all supported device types
  - Maintains state cache
  - Provides device lookup methods
  - Supports room-based operations

- `LoxoneDevice`: Enhanced device data model
  ```python
  @dataclass
  class LoxoneDevice:
      uuid: str
      name: str
      type: str  # All HA component types: Switch, Dimmer, Jalousie, Climate, MediaPlayer, etc.
      room: str
      category: str
      states: dict  # Current state values
      details: dict  # Device-specific details
      controls: dict  # Available control commands
      capabilities: dict  # Device capabilities (color, temperature range, etc.)
  ```

**Supported Device Types (Complete HA Component Migration):**
- **Switches**: Switch, TimedSwitch, Pushbutton
- **Lights**: Dimmer, LightControllerV2, ColorPickerV2
- **Covers**: Jalousie, Window, Gate
- **Climate**: IRoomControllerV2 (thermostat)
- **Fans**: Ventilation
- **Sensors**: InfoOnlyAnalog, InfoOnlyDigital
- **Media Players**: AudioZoneV2
- **Alarms**: Alarm
- **Input Controls**: Slider, TextInput
- **Scenes**: All scene types

**Key Methods:**

```python
class DeviceManager:
    def load_devices(self, loxapp_json: dict) -> None
    def get_device(self, uuid: str) -> Optional[LoxoneDevice]
    def list_devices(self, device_type: str = None, room: str = None) -> List[LoxoneDevice]
    def list_rooms(self) -> List[dict]
    def get_room_devices(self, room: str) -> List[dict]
    async def control_room(self, room: str, action: str) -> dict
    def update_state(self, uuid: str, state_data: dict) -> None
    def get_device_state(self, uuid: str) -> dict
    def get_enhanced_device_state(self, uuid: str) -> dict  # NEW: Enhanced state with full details
    def build_state_structure(self, device: LoxoneDevice) -> dict  # NEW: Build comprehensive state
    def extract_device_capabilities(self, device_config: dict) -> dict  # NEW: Extract capabilities
    def list_scenes(self) -> List[dict]
```

**Enhanced State Management Implementation:**

The `DeviceManager` will be enhanced to provide comprehensive state information:

```python
def get_enhanced_device_state(self, uuid: str) -> dict:
    """
    Get comprehensive device state with all available parameters.
    Addresses the issue where device state queries return empty objects.
    """
    device = self.get_device(uuid)
    if not device:
        return {"error": "Device not found", "uuid": uuid}
    
    # Build comprehensive state structure based on device type
    enhanced_state = self.build_state_structure(device)
    
    # If state cache is empty, attempt to request from Miniserver
    if not device.states or len(device.states) == 0:
        logger.warning(f"Empty state cache for device {uuid}, requesting update")
        # Trigger state request (implementation depends on connection)
        enhanced_state["state"]["_cache_status"] = "empty_requesting_update"
    
    return enhanced_state

def build_state_structure(self, device: LoxoneDevice) -> dict:
    """
    Build device-specific state structure with all relevant parameters.
    """
    base_structure = {
        "uuid": device.uuid,
        "name": device.name,
        "type": device.type,
        "room": device.room,
        "category": device.category,
        "state": {},
        "capabilities": device.capabilities or {},
        "metadata": {
            "state_parameters": [],
            "last_updated": device.states.get("_last_updated"),
            "reachable": device.states.get("_reachable", True)
        }
    }
    
    # Device-type specific state building
    if device.type in ["Dimmer", "LightControllerV2"]:
        return self._build_light_state(device, base_structure)
    elif device.type == "ColorPickerV2":
        return self._build_color_light_state(device, base_structure)
    elif device.type in ["Jalousie", "Window", "Gate"]:
        return self._build_cover_state(device, base_structure)
    elif device.type == "IRoomControllerV2":
        return self._build_climate_state(device, base_structure)
    else:
        return self._build_generic_state(device, base_structure)

def _build_light_state(self, device: LoxoneDevice, base: dict) -> dict:
    """Build enhanced state for light devices."""
    value = device.states.get("value", 0.0)
    base["state"] = {
        "value": value,
        "on": value > 0,
        "brightness": value,
        "last_changed": device.states.get("_last_changed"),
        "reachable": device.states.get("_reachable", True)
    }
    base["capabilities"].update({
        "min_brightness": 0,
        "max_brightness": 100,
        "step": 1,
        "supports_dimming": True,
        "supports_color": False
    })
    base["metadata"].update({
        "units": "%",
        "format": "%.1f%%",
        "state_parameters": ["value", "on", "brightness"]
    })
    return base
```

### 4. MCP Tools (`tools/`)

Individual tool implementations for MCP exposure.

**Tool Modules:**

- `device_control_tools.py`: Tools for controlling devices
- `device_query_tools.py`: Tools for querying device information
- `scene_tools.py`: Tools for scene management

**Example Tool Definition:**

```python
@server.tool()
async def loxone_set_switch(uuid: str, state: bool) -> dict:
    """
    Turn a Loxone switch on or off.
    
    Args:
        uuid: The UUID of the switch device
        state: True for on, False for off
    
    Returns:
        dict with success status and updated state
    """
    device = device_manager.get_device(uuid)
    if not device or device.type not in ["Switch", "TimedSwitch"]:
        return {"success": False, "error": "Invalid device or type"}
    
    value = "On" if state else "Off"
    success = await loxone_client.send_command(uuid, value)
    
    return {
        "success": success,
        "device": uuid,
        "state": state
    }
```

### 5. Configuration Manager (`config.py`)

Handles configuration loading and token persistence.

```python
@dataclass
class LoxoneConfig:
    host: str
    port: int
    username: str
    password: str
    token_persist_path: str = "./loxone_token.json"
    
    @classmethod
    def from_env(cls) -> 'LoxoneConfig':
        """Load configuration from environment variables"""
        
    @classmethod
    def from_file(cls, path: str) -> 'LoxoneConfig':
        """Load configuration from JSON file"""
        
    def save_token(self, token_data: dict) -> None:
        """Persist token to disk"""
        
    def load_token(self) -> Optional[dict]:
        """Load persisted token"""
```

## Data Models

### Device Types (Complete Home Assistant Component Migration)

The server will support ALL Loxone device types from the existing Home Assistant integration:

**Lighting Controls:**
- **Switch**: Binary on/off devices
- **TimedSwitch**: Switches with automatic off timer  
- **Pushbutton**: Momentary buttons
- **Dimmer**: Dimmable lights (0-100%)
- **LightControllerV2**: Advanced lighting control with scenes
- **ColorPickerV2**: RGB color lighting control

**Cover Controls:**
- **Jalousie**: Blinds/shades with position and tilt control
- **Window**: Window controls with position feedback
- **Gate**: Gate controls with position and safety features

**Climate Controls:**
- **IRoomControllerV2**: Full climate control (temperature, mode, fan speed)
- **Ventilation**: Fan/ventilation control with speed settings

**Sensors and Monitoring:**
- **InfoOnlyAnalog**: Read-only analog sensors (temperature, humidity, etc.)
- **InfoOnlyDigital**: Read-only digital sensors (motion, door contacts, etc.)
- **Presence**: Presence detection sensors
- **SmokeAlarm**: Smoke detector integration

**Media and Audio:**
- **AudioZoneV2**: Multi-zone audio control (play, pause, volume, source)
- **MediaPlayer**: Generic media player controls

**Security and Safety:**
- **Alarm**: Alarm system controls with PIN authentication
- **Intercom**: Door intercom systems

**Input and Control:**
- **Slider**: Numeric input controls (0-100 range)
- **TextInput**: Text input controls for system messages
- **UpDownAnalog**: Up/down controls for numeric values

**Automation:**
- **Scenes**: All scene types and automation triggers
- **Mood**: Lighting mood controls
- **TimedSwitch**: Timer-based switching

**System Integration:**
- **CentralAlarm**: Central alarm system integration
- **Tracker**: Position tracking devices
- **WeatherServer**: Weather station integration

### Enhanced State Data Structures

The system will provide comprehensive state information for all device types, addressing the issue where device state queries return empty or minimal information.

**Enhanced Dimmer/Light State:**
```python
{
    "uuid": "15beed5b-01ab-d81f-ffff403fb0c34b9e",
    "name": "Living Room Light",
    "type": "Dimmer",
    "room": "Living Room",
    "category": "Lights",
    "state": {
        "value": 75.0,        # Current brightness (0-100)
        "on": true,           # On/off status
        "brightness": 75.0,   # Explicit brightness value
        "last_changed": "2024-01-15T10:30:00Z",
        "reachable": true     # Device connectivity status
    },
    "capabilities": {
        "min_brightness": 0,
        "max_brightness": 100,
        "step": 1,
        "supports_dimming": true,
        "supports_color": false
    },
    "metadata": {
        "units": "%",
        "format": "%.1f%%",
        "state_parameters": ["value", "on", "brightness"]
    }
}
```

**Enhanced Color Light State:**
```python
{
    "uuid": "15c2a003-024d-777c-ffff24b3ef2f8379",
    "name": "Empore Light",
    "type": "ColorPickerV2",
    "room": "Empore",
    "category": "Lights",
    "state": {
        "value": 85.0,        # Overall brightness
        "on": true,
        "brightness": 85.0,
        "color": {
            "red": 255,       # RGB values (0-255)
            "green": 128,
            "blue": 64,
            "hex": "#FF8040"  # Hex color representation
        },
        "color_temp": 3000,   # Color temperature in Kelvin
        "mode": "color",      # "color", "white", "scene"
        "last_changed": "2024-01-15T10:30:00Z",
        "reachable": true
    },
    "capabilities": {
        "min_brightness": 0,
        "max_brightness": 100,
        "supports_color": true,
        "supports_color_temp": true,
        "min_color_temp": 2700,
        "max_color_temp": 6500,
        "color_modes": ["color", "white", "scene"]
    },
    "metadata": {
        "units": "%",
        "format": "%.1f%%",
        "state_parameters": ["value", "on", "brightness", "color", "color_temp", "mode"]
    }
}
```

**Enhanced Cover State:**
```python
{
    "uuid": "jalousie-uuid-here",
    "name": "Living Room Blinds",
    "type": "Jalousie",
    "room": "Living Room",
    "category": "Covers",
    "state": {
        "position": 45.0,     # Position (0=closed, 100=open)
        "tilt": 30.0,         # Tilt angle (-100 to 100)
        "moving": false,      # Currently moving
        "direction": "none",  # "up", "down", "none"
        "last_changed": "2024-01-15T10:30:00Z",
        "reachable": true
    },
    "capabilities": {
        "supports_position": true,
        "supports_tilt": true,
        "supports_stop": true,
        "min_position": 0,
        "max_position": 100
    },
    "metadata": {
        "units": "%",
        "state_parameters": ["position", "tilt", "moving", "direction"]
    }
}
```

**Enhanced Climate State:**
```python
{
    "uuid": "climate-uuid-here",
    "name": "Living Room Thermostat",
    "type": "IRoomControllerV2",
    "room": "Living Room",
    "category": "Climate",
    "state": {
        "current_temperature": 21.5,
        "target_temperature": 22.0,
        "mode": "heat",       # "heat", "cool", "auto", "off"
        "fan_mode": "auto",   # "auto", "low", "medium", "high"
        "humidity": 45.0,     # Current humidity %
        "heating": true,      # Currently heating
        "cooling": false,     # Currently cooling
        "last_changed": "2024-01-15T10:30:00Z",
        "reachable": true
    },
    "capabilities": {
        "min_temp": 5.0,
        "max_temp": 35.0,
        "temp_step": 0.5,
        "modes": ["heat", "cool", "auto", "off"],
        "fan_modes": ["auto", "low", "medium", "high"],
        "supports_humidity": true
    },
    "metadata": {
        "temp_units": "°C",
        "humidity_units": "%",
        "state_parameters": ["current_temperature", "target_temperature", "mode", "fan_mode", "humidity"]
    }
}
```

**State Information Enhancement Strategy:**

1. **Comprehensive State Mapping**: Each device type will have a specific state structure that includes all relevant parameters
2. **Capability Detection**: The system will detect and expose device capabilities based on the LoxAPP3.json structure
3. **State Parameter Documentation**: Each state response includes metadata about available parameters and their meanings
4. **Default Value Handling**: When state information is unavailable, appropriate defaults or null values are provided with clear indicators
5. **Real-time Updates**: State information is kept current through WebSocket message processing
6. **Fallback Mechanisms**: If cached state is empty, the system will attempt to request current state from the Miniserver

## Error Handling

### Error Categories

1. **Connection Errors**: Websocket connection failures, network issues
   - Automatic reconnection with exponential backoff
   - Log connection attempts and failures
   - Return error to MCP client if operation fails

2. **Authentication Errors**: Invalid credentials, token expiration
   - Attempt token refresh
   - Re-authenticate if refresh fails
   - Log authentication failures

3. **Command Errors**: Invalid device UUID, unsupported operation
   - Validate device existence before sending command
   - Return descriptive error to MCP client
   - Log invalid command attempts

4. **Parsing Errors**: Malformed messages from Miniserver
   - Log parsing errors with message context
   - Continue processing other messages
   - Don't crash the server

### Error Response Format

All MCP tools will return consistent error responses:

```python
{
    "success": False,
    "error": "Device not found",
    "error_code": "DEVICE_NOT_FOUND",
    "details": {
        "uuid": "invalid-uuid-here"
    }
}
```

## Testing Strategy

### Unit Tests

1. **Message Parsing Tests**
   - Test binary message decoding
   - Test text message parsing
   - Test state update processing

2. **Device Manager Tests**
   - Test device registration
   - Test state updates
   - Test device queries with filters

3. **Encryption Tests**
   - Test AES encryption/decryption
   - Test key exchange
   - Test token hashing

### Integration Tests

1. **Loxone Client Tests**
   - Test connection establishment (with mock Miniserver)
   - Test authentication flow
   - Test command sending
   - Test reconnection logic

2. **MCP Tool Tests**
   - Test each tool with valid inputs
   - Test error handling with invalid inputs
   - Test tool responses match expected format

### End-to-End Tests

1. **Full Flow Tests**
   - Connect to test Miniserver
   - Discover devices
   - Execute control commands
   - Verify state updates

2. **MCP Client Integration**
   - Test with actual MCP client
   - Verify tool discovery
   - Verify tool execution

## Security Considerations

1. **Credential Storage**
   - Never log passwords or tokens
   - Store tokens encrypted at rest (optional enhancement)
   - Use environment variables for sensitive config

2. **Secured Commands**
   - Implement visual hash authentication for PIN-protected devices
   - Validate PIN codes before sending
   - Log secured command attempts

3. **Connection Security**
   - Support HTTPS connections to Miniserver
   - Validate SSL certificates (with option to disable for local)
   - Use encrypted websocket communication

## Performance Considerations

1. **State Caching**
   - Cache device states in memory
   - Update cache on websocket events
   - Avoid redundant Miniserver queries

2. **Connection Management**
   - Single persistent websocket connection
   - Efficient message queuing
   - Keepalive to prevent disconnection

3. **Async Operations**
   - Use asyncio for all I/O operations
   - Non-blocking command execution
   - Concurrent message processing

## Deployment

### Project Setup with uv and venv

The project will use `uv` for fast Python package management and a virtual environment for isolation.

**Project Structure:**
```
loxone-mcp-server/
├── pyproject.toml          # Project metadata and dependencies
├── uv.lock                 # Locked dependencies
├── .python-version         # Python version specification
├── src/
│   └── loxone_mcp/
│       ├── __init__.py
│       ├── server.py       # Main MCP server entry point
│       ├── loxone_client.py
│       ├── device_manager.py
│       ├── config.py
│       └── tools/
│           ├── __init__.py
│           ├── device_control_tools.py
│           ├── device_query_tools.py
│           └── scene_tools.py
├── tests/
└── README.md
```

**Dependencies (pyproject.toml):**
```toml
[project]
name = "loxone-mcp-server"
version = "0.1.0"
description = "MCP server for Loxone Miniserver integration"
requires-python = ">=3.10"
dependencies = [
    "mcp>=0.9.0",           # MCP SDK
    "websockets>=14.0",     # WebSocket client for Loxone
    "pycryptodome>=3.20.0", # Encryption for Loxone protocol
    "httpx>=0.27.0",        # HTTP client for initial config fetch
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "black>=24.0.0",
    "ruff>=0.3.0",
]

[project.scripts]
loxone-mcp-server = "loxone_mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### Installation

**Step 1: Install uv**
```bash
# On macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Step 2: Clone and Setup Project**
```bash
# Clone repository
git clone <repository-url>
cd loxone-mcp-server

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install project in development mode
uv pip install -e ".[dev]"
```

**Step 3: Run Tests**
```bash
uv run pytest
```

### Configuration

**Option 1: Environment Variables**
```bash
export LOXONE_HOST="192.168.1.100"
export LOXONE_PORT="80"
export LOXONE_USERNAME="admin"
export LOXONE_PASSWORD="password"
export LOXONE_TOKEN_PATH="./loxone_token.json"
```

**Option 2: Configuration File**
```json
{
  "host": "192.168.1.100",
  "port": 80,
  "username": "admin",
  "password": "password",
  "token_persist_path": "./loxone_token.json"
}
```

### Running the Server

**Development Mode:**
```bash
# Activate virtual environment
source .venv/bin/activate

# Run with environment variables
export LOXONE_HOST="192.168.1.100"
export LOXONE_PORT="80"
export LOXONE_USERNAME="admin"
export LOXONE_PASSWORD="password"
loxone-mcp-server

# Or run with uv directly
uv run loxone-mcp-server

# With config file
uv run loxone-mcp-server --config config.json
```

**Production Mode with MCP Client:**

For use with Claude Desktop or other MCP clients, add to MCP settings:

```json
{
  "mcpServers": {
    "loxone": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/loxone-mcp-server",
        "run",
        "loxone-mcp-server"
      ],
      "env": {
        "LOXONE_HOST": "192.168.1.100",
        "LOXONE_PORT": "80",
        "LOXONE_USERNAME": "admin",
        "LOXONE_PASSWORD": "password"
      }
    }
  }
}
```

**Alternative: Using uvx for Global Installation**
```bash
# Install globally with uvx
uvx loxone-mcp-server

# In MCP client config:
{
  "mcpServers": {
    "loxone": {
      "command": "uvx",
      "args": ["loxone-mcp-server"],
      "env": {
        "LOXONE_HOST": "192.168.1.100",
        "LOXONE_PORT": "80",
        "LOXONE_USERNAME": "admin",
        "LOXONE_PASSWORD": "password"
      }
    }
  }
}
```

## Migration from Home Assistant Integration

### Code Reuse

The following components can be largely reused from the existing integration:

1. **Loxone Protocol Implementation** (`api.py`)
   - Websocket communication
   - Encryption/decryption logic
   - Authentication flow
   - Message parsing

2. **Device Type Definitions** (from entity files)
   - Device capabilities
   - State mappings
   - Control commands

### Code to Remove/Replace

1. **Home Assistant Dependencies**
   - Remove all `homeassistant.*` imports
   - Remove entity base classes
   - Remove config flow (replace with simple config loading)

2. **Entity Framework**
   - Replace entity classes with simple data models
   - Replace entity registry with device manager
   - Replace state updates with direct cache updates

### New Code Required

1. **MCP Server Framework**
   - Server initialization
   - Tool registration
   - Request/response handling

2. **Tool Implementations**
   - Device control tools
   - Device query tools
   - Scene management tools

3. **Standalone Configuration**
   - Config file parsing
   - Environment variable loading
   - Token persistence

## Future Enhancements

1. **Resource Support**: Expose device icons and images as MCP resources
2. **Prompt Support**: Provide MCP prompts for common Loxone operations
3. **Webhook Support**: Allow external systems to trigger updates
4. **Multi-Miniserver**: Support connecting to multiple Miniservers
5. **Device Groups**: Support for Loxone device groups and rooms
6. **Statistics**: Expose historical data and statistics
7. **Notifications**: Push notifications for device events

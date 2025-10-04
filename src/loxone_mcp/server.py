"""
Loxone MCP Server - Main entry point with multi-client support

Provides MCP (Model Context Protocol) server functionality for Loxone Miniserver integration.
Exposes Loxone device control and monitoring through standardized MCP tools.
Supports multiple clients with different credentials connecting to different Miniservers.

Run with: uv run loxone-mcp-server
"""

import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastmcp import FastMCP

try:
    from .config import LoxoneConfig
    from .connection_manager import ConnectionManager
    from .client_session import ClientSession
    from .loxone_client import LoxoneClient
    from .device_manager import DeviceManager
except ImportError:
    # Handle case when run as script
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))

    from config import LoxoneConfig
    from connection_manager import ConnectionManager
    from client_session import ClientSession
    from loxone_client import LoxoneClient
    from device_manager import DeviceManager

# Configure logging with enhanced format including context
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Error response format constants
ERROR_DEVICE_NOT_FOUND = "DEVICE_NOT_FOUND"
ERROR_INVALID_PARAMETER = "INVALID_PARAMETER"
ERROR_DEVICE_TYPE_MISMATCH = "DEVICE_TYPE_MISMATCH"
ERROR_COMMAND_FAILED = "COMMAND_FAILED"
ERROR_AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
ERROR_CONNECTION_FAILED = "CONNECTION_FAILED"
ERROR_INITIALIZATION_FAILED = "INITIALIZATION_FAILED"
ERROR_VALIDATION_FAILED = "VALIDATION_FAILED"


def create_error_response(
    error_code: str, error_message: str, details: dict | None = None, context: dict | None = None
) -> dict:
    """
    Create a standardized error response for MCP tools.

    Args:
        error_code: Standardized error code constant
        error_message: Human-readable error description
        details: Additional error details (optional)
        context: Context information for debugging (optional)

    Returns:
        Standardized error response dictionary
    """
    response = {"success": False, "error": error_message, "error_code": error_code}

    if details:
        response["details"] = details

    if context:
        response["context"] = context

    return response


def create_success_response(data: dict, context: dict | None = None) -> dict:
    """
    Create a standardized success response for MCP tools.

    Args:
        data: Response data
        context: Additional context information (optional)

    Returns:
        Standardized success response dictionary
    """
    response = {"success": True, **data}

    if context:
        response["context"] = context

    return response


# Global connection manager (will be initialized in lifespan)
connection_manager: Optional[ConnectionManager] = None

# Global instances for backward compatibility (will be initialized in lifespan)
loxone_client: Optional["LoxoneClient"] = None
device_manager: Optional["DeviceManager"] = None

# Create FastMCP server
mcp = FastMCP("loxone-mcp-server")


def main_stdio():
    """Main entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main_stdio()


@asynccontextmanager
async def server_lifespan():
    """
    Manage server lifecycle - initialize connection manager for multi-client support.

    The server is now stateless and does not use environment credentials.
    Each MCP client provides credentials when calling tools, and sessions
    are created dynamically as needed.

    Yields:
        dict: Dictionary containing initialized connection manager

    Raises:
        Exception: If initialization fails
    """
    global connection_manager

    logger.info("Initializing Loxone MCP Server (stateless mode)...")

    try:
        # Initialize connection manager only
        logger.info("Initializing connection manager...")
        connection_manager = ConnectionManager()
        logger.info("Connection manager initialized successfully")

        logger.info("Loxone MCP Server initialization complete - Ready for client connections")
        logger.info("Server is stateless - clients must provide credentials via tool parameters")

        # Yield resources to the server
        yield {"connection_manager": connection_manager}

    except Exception as e:
        logger.error(
            f"Unexpected error during Loxone MCP Server initialization: {e}", exc_info=True
        )
        raise RuntimeError(f"Server initialization failed: {e}")

    finally:
        # Cleanup on shutdown
        logger.info("Initiating Loxone MCP Server shutdown sequence...")

        if connection_manager:
            try:
                logger.info("Cleaning up all client sessions...")
                await connection_manager.cleanup_all()
                logger.info("All client sessions cleaned up successfully")
            except Exception as e:
                logger.error(f"Error during connection manager cleanup: {e}", exc_info=True)

        logger.info("Loxone MCP Server shutdown completed successfully")

        # Reset global instances
        connection_manager = None


# Set the lifespan manager
# mcp.lifespan = server_lifespan


async def get_or_create_session(
    client_id: str, host: str = None, username: str = None, password: str = None, port: int = None
) -> Optional[ClientSession]:
    """
    Get existing session or create a new one with provided credentials.

    Args:
        client_id: Unique identifier for the client
        host: Loxone Miniserver host/IP (required for new sessions)
        username: Loxone username (required for new sessions)
        password: Loxone password (required for new sessions)
        port: Loxone port (optional, defaults to 80)

    Returns:
        ClientSession instance if successful, None otherwise
    """
    if not connection_manager:
        logger.error("Connection manager not initialized")
        return None

    # Try to get existing session first
    session = connection_manager.get_session(client_id)
    if session:
        logger.debug(f"Using existing session for client {client_id}")
        return session

    # Need to create new session - require credentials
    if not all([host, username, password]):
        logger.error(
            f"Cannot create session for client {client_id}: missing credentials (host={bool(host)}, username={bool(username)}, password={bool(password)})"
        )
        return None

    try:
        # Create configuration from provided credentials
        config = LoxoneConfig(host=host, username=username, password=password, port=port or 80)

        # Create new session
        logger.info(
            f"Creating new session for client {client_id} connecting to {host}:{port or 80}"
        )
        session = await connection_manager.create_session(client_id, config)

        return session

    except Exception as e:
        logger.error(f"Failed to create session for client {client_id}: {e}")
        return None


def get_session_or_fallback(
    client_id: str,
) -> tuple[Optional[ClientSession], Optional["DeviceManager"]]:
    """
    Get client session (no fallback - server is now stateless).

    Args:
        client_id: Unique identifier for the client

    Returns:
        Tuple of (session, None) - device_manager is always None in stateless mode
    """
    if connection_manager is not None:
        session = connection_manager.get_session(client_id)
        if session:
            return session, None

    logger.warning(f"No session found for client {client_id} - credentials must be provided")
    return None, None


# ============================================================================
# Device Query Tools
# ============================================================================


@mcp.tool()
async def loxone_list_devices(
    host: str,
    username: str,
    password: str,
    port: int = 80,
    client_id: str = "default",
    device_type: str | None = None,
    room: str | None = None,
) -> dict[str, Any]:
    """
    List all Loxone devices with optional filtering.

    Args:
        host: Loxone Miniserver host/IP address
        username: Loxone username
        password: Loxone password
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
        device_type: Filter by device type (e.g., "Switch", "Dimmer", "Jalousie")
        room: Filter by room name

    Returns:
        Standardized response with list of devices and their basic information
    """
    logger.info(
        f"Listing devices for client {client_id} connecting to {host}:{port} - Type filter: {device_type}, Room filter: {room}"
    )

    # Get or create session with provided credentials
    session = await get_or_create_session(client_id, host, username, password, port)

    if not session:
        error_msg = (
            f"Failed to create session for client {client_id} - check credentials and connectivity"
        )
        logger.error(error_msg)
        return create_error_response(
            ERROR_INITIALIZATION_FAILED,
            error_msg,
            context={
                "operation": "list_devices",
                "client_id": client_id,
                "host": host,
                "port": port,
            },
        )

    # Use the session's device manager
    active_device_manager = session.device_manager

    try:
        # Validate device_type parameter if provided
        if device_type is not None:
            if not isinstance(device_type, str) or not device_type.strip():
                error_msg = "Device type must be a non-empty string"
                logger.warning(f"Invalid device_type parameter: {repr(device_type)}")
                return create_error_response(
                    ERROR_INVALID_PARAMETER,
                    error_msg,
                    details={"parameter": "device_type", "value": device_type},
                    context={"valid_types": active_device_manager.get_device_types()},
                )

            # Check if device type exists
            available_types = active_device_manager.get_device_types()
            if device_type not in available_types:
                error_msg = f"Device type '{device_type}' not found"
                logger.warning(f"Unknown device type requested: {device_type}")
                return create_error_response(
                    ERROR_DEVICE_NOT_FOUND,
                    error_msg,
                    details={"requested_type": device_type},
                    context={"available_types": available_types},
                )

        # Validate room parameter if provided
        if room is not None:
            if not isinstance(room, str) or not room.strip():
                error_msg = "Room must be a non-empty string"
                logger.warning(f"Invalid room parameter: {repr(room)}")
                return create_error_response(
                    ERROR_INVALID_PARAMETER,
                    error_msg,
                    details={"parameter": "room", "value": room},
                    context={"available_rooms": active_device_manager.get_rooms()},
                )

        # Get devices with filtering
        devices = active_device_manager.list_devices(device_type=device_type, room=room)

        # Format device information
        device_list = []
        for device in devices:
            try:
                device_info = {
                    "uuid": device.uuid,
                    "name": device.name,
                    "type": device.type,
                    "room": device.room,
                    "category": device.category,
                }
                device_list.append(device_info)
            except Exception as e:
                logger.warning(f"Error formatting device {device.uuid}: {e}")
                continue

        logger.info(f"Successfully listed {len(device_list)} devices")
        logger.debug(f"Device listing filters applied - Type: {device_type}, Room: {room}")

        return create_success_response(
            {"devices": device_list, "count": len(device_list)},
            context={
                "filters_applied": {"device_type": device_type, "room": room},
                "total_devices": active_device_manager.get_device_count(),
            },
        )

    except Exception as e:
        error_msg = f"Unexpected error listing devices: {e}"
        logger.error(error_msg, exc_info=True)
        return create_error_response(
            ERROR_COMMAND_FAILED,
            error_msg,
            details={"exception_type": type(e).__name__},
            context={
                "operation": "list_devices",
                "filters": {"device_type": device_type, "room": room},
            },
        )


@mcp.tool()
async def loxone_get_device_state(
    host: str, username: str, password: str, uuid: str, port: int = 80, client_id: str = "default"
) -> dict[str, Any]:
    """
    Get comprehensive state information for a specific Loxone device.

    Returns detailed device state including all available parameters, capabilities,
    metadata, and device-type specific state structures. This enhanced version
    provides complete state information with parameter descriptions, units, and
    validation rules.

    Args:
        host: Loxone Miniserver host/IP address
        username: Loxone username
        password: Loxone password
        uuid: The UUID of the device
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")

    Returns:
        Comprehensive device state response including:
        - Basic device information (uuid, name, type, room, category)
        - Enhanced state structure with device-type specific parameters
        - Device capabilities and supported operations
        - State parameter metadata (descriptions, units, ranges)
        - State validation rules and default values
        - Cache status and update tracking information
    """
    logger.info(
        f"Getting device state for client {client_id} connecting to {host}:{port}, UUID: {uuid}"
    )

    # Get or create session with provided credentials
    session = await get_or_create_session(client_id, host, username, password, port)

    if not session:
        error_msg = (
            f"Failed to create session for client {client_id} - check credentials and connectivity"
        )
        logger.error(error_msg)
        return create_error_response(
            ERROR_INITIALIZATION_FAILED,
            error_msg,
            context={
                "operation": "get_device_state",
                "client_id": client_id,
                "host": host,
                "port": port,
            },
        )

    # Use the session's device manager
    active_device_manager = session.device_manager

    # Validate UUID parameter
    if not uuid:
        error_msg = "UUID parameter is required"
        logger.warning("get_device_state called with empty UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid", "value": uuid}
        )

    if not isinstance(uuid, str):
        error_msg = "UUID must be a string"
        logger.warning(f"get_device_state called with non-string UUID: {type(uuid)}")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={"parameter": "uuid", "type": type(uuid).__name__, "value": uuid},
        )

    # Normalize UUID (strip whitespace)
    uuid = uuid.strip()
    if not uuid:
        error_msg = "UUID cannot be empty or whitespace only"
        logger.warning("get_device_state called with whitespace-only UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid"}
        )

    try:
        # Attempt to get device
        device = active_device_manager.get_device(uuid)
        if not device:
            error_msg = f"Device not found with UUID: {uuid}"
            logger.warning(f"Device lookup failed for UUID: {uuid}")

            # Provide helpful context
            total_devices = device_manager.get_device_count()
            return create_error_response(
                ERROR_DEVICE_NOT_FOUND,
                error_msg,
                details={"uuid": uuid},
                context={
                    "total_devices": total_devices,
                    "suggestion": "Use loxone_list_devices to see available devices",
                },
            )

        # Build enhanced device state response
        try:
            # Use enhanced device state information
            enhanced_state = active_device_manager.get_enhanced_device_state(uuid)

            # Check if enhanced state retrieval was successful
            if not enhanced_state.get("success", True):
                # Fall back to basic state if enhanced state fails
                logger.warning(
                    f"Enhanced state retrieval failed for {uuid}, falling back to basic state"
                )
                device_state = {
                    "uuid": device.uuid,
                    "name": device.name,
                    "type": device.type,
                    "room": device.room,
                    "category": device.category,
                    "state": device.states.copy() if device.states else {},
                    "details": device.details.copy() if device.details else {},
                    "capabilities": device.capabilities.copy() if device.capabilities else {},
                    "metadata": device.metadata.copy() if device.metadata else {},
                }

                return create_success_response(
                    device_state,
                    context={
                        "enhanced_state": False,
                        "fallback_reason": enhanced_state.get("error", "Unknown error"),
                        "state_count": len(device.states) if device.states else 0,
                    },
                )
            else:
                # Use enhanced state information (remove success flag for response)
                enhanced_state.pop("success", None)

                logger.info(
                    f"Successfully retrieved enhanced state for device '{device.name}' ({uuid}) - Type: {device.type}"
                )
                logger.debug(
                    f"Enhanced state parameters: {list(enhanced_state.get('state', {}).keys())}"
                )

                return create_success_response(
                    enhanced_state,
                    context={
                        "enhanced_state": True,
                        "last_updated": "real-time",
                        "state_count": len(enhanced_state.get("state", {})),
                        "capabilities_count": len(enhanced_state.get("capabilities", {})),
                        "metadata_available": bool(enhanced_state.get("metadata")),
                    },
                )

        except Exception as e:
            error_msg = f"Error formatting device state data: {e}"
            logger.error(error_msg, exc_info=True)
            return create_error_response(
                ERROR_COMMAND_FAILED,
                error_msg,
                details={"uuid": uuid, "device_name": device.name},
                context={"operation": "format_device_state"},
            )

    except Exception as e:
        error_msg = f"Unexpected error retrieving device state: {e}"
        logger.error(error_msg, exc_info=True)
        return create_error_response(
            ERROR_COMMAND_FAILED,
            error_msg,
            details={"uuid": uuid, "exception_type": type(e).__name__},
            context={"operation": "get_device_state"},
        )


@mcp.tool()
async def loxone_get_device_info(client_id: str = "default", uuid: str = "") -> dict[str, Any]:
    """
    Get detailed information about a specific Loxone device.

    Args:
        client_id: Unique identifier for the client
        uuid: The UUID of the device

    Returns:
        Standardized response with comprehensive device information including metadata, controls, and current state
    """
    logger.info(f"Getting detailed device info for client {client_id}, UUID: {uuid}")

    if connection_manager is None:
        error_msg = "Connection manager not initialized - server may not be fully started"
        logger.error(error_msg)
        return create_error_response(
            ERROR_INITIALIZATION_FAILED,
            error_msg,
            context={"operation": "get_device_info", "client_id": client_id, "uuid": uuid},
        )

    # Get or create client session
    session = await get_or_create_session(client_id)
    if not session:
        error_msg = f"Failed to get or create session for client {client_id}"
        logger.error(error_msg)
        return create_error_response(
            ERROR_INITIALIZATION_FAILED,
            error_msg,
            context={"operation": "get_device_info", "client_id": client_id},
        )

    device_manager = session.device_manager

    # Validate UUID parameter (same validation as get_device_state)
    if not uuid:
        error_msg = "UUID parameter is required"
        logger.warning("get_device_info called with empty UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid", "value": uuid}
        )

    if not isinstance(uuid, str):
        error_msg = "UUID must be a string"
        logger.warning(f"get_device_info called with non-string UUID: {type(uuid)}")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={"parameter": "uuid", "type": type(uuid).__name__, "value": uuid},
        )

    # Normalize UUID (strip whitespace)
    uuid = uuid.strip()
    if not uuid:
        error_msg = "UUID cannot be empty or whitespace only"
        logger.warning("get_device_info called with whitespace-only UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid"}
        )

    try:
        # Attempt to get device
        device = device_manager.get_device(uuid)
        if not device:
            error_msg = f"Device not found with UUID: {uuid}"
            logger.warning(f"Device lookup failed for UUID: {uuid}")

            # Provide helpful context
            total_devices = device_manager.get_device_count()
            return create_error_response(
                ERROR_DEVICE_NOT_FOUND,
                error_msg,
                details={"uuid": uuid},
                context={
                    "total_devices": total_devices,
                    "suggestion": "Use loxone_list_devices to see available devices",
                },
            )

        # Build comprehensive device information response
        try:
            device_info = {
                "uuid": device.uuid,
                "name": device.name,
                "type": device.type,
                "room": device.room,
                "category": device.category,
                "state": device.states.copy() if device.states else {},
                "details": device.details.copy() if device.details else {},
                "controls": device.controls.copy() if device.controls else {},
            }

            logger.info(f"Successfully retrieved detailed info for device '{device.name}' ({uuid})")
            logger.debug(
                f"Device info summary - Type: {device.type}, Room: {device.room}, "
                f"States: {len(device.states)}, Controls: {len(device.controls)}, "
                f"Details: {len(device.details)}"
            )

            return create_success_response(
                device_info,
                context={
                    "info_completeness": {
                        "has_states": len(device.states) > 0,
                        "has_controls": len(device.controls) > 0,
                        "has_details": len(device.details) > 0,
                    },
                    "capabilities": list(device.controls.keys()) if device.controls else [],
                },
            )

        except Exception as e:
            error_msg = f"Error formatting device information: {e}"
            logger.error(error_msg, exc_info=True)
            return create_error_response(
                ERROR_COMMAND_FAILED,
                error_msg,
                details={"uuid": uuid, "device_name": device.name},
                context={"operation": "format_device_info"},
            )

    except Exception as e:
        error_msg = f"Unexpected error retrieving device information: {e}"
        logger.error(error_msg, exc_info=True)
        return create_error_response(
            ERROR_COMMAND_FAILED,
            error_msg,
            details={"uuid": uuid, "exception_type": type(e).__name__},
            context={"operation": "get_device_info"},
        )


# ============================================================================
# Device Control Tools
# ============================================================================


@mcp.tool()
async def loxone_send_command(
    client_id: str = "default", uuid: str = "", value: str = ""
) -> dict[str, Any]:
    """
    Send a command to a Loxone device.

    Args:
        client_id: Unique identifier for the client
        uuid: The UUID of the device
        value: The command value to send (e.g., "On", "Off", "50" for dimmer)

    Returns:
        Standardized response with success status and device information
    """
    logger.info(f"Sending command for client {client_id} to device {uuid}: {value}")

    # Check initialization
    if connection_manager is None:
        error_msg = "Connection manager not initialized - server may not be fully started"
        logger.error(error_msg)
        return create_error_response(
            ERROR_INITIALIZATION_FAILED,
            error_msg,
            context={
                "operation": "send_command",
                "client_id": client_id,
                "uuid": uuid,
                "value": value,
            },
        )

    # Get or create client session
    session = await get_or_create_session(client_id)
    if not session:
        error_msg = f"Failed to get or create session for client {client_id}"
        logger.error(error_msg)
        return create_error_response(
            ERROR_INITIALIZATION_FAILED,
            error_msg,
            context={"operation": "send_command", "client_id": client_id},
        )

    # Validate UUID parameter
    if not uuid:
        error_msg = "UUID parameter is required"
        logger.warning("send_command called with empty UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid", "value": uuid}
        )

    if not isinstance(uuid, str):
        error_msg = "UUID must be a string"
        logger.warning(f"send_command called with non-string UUID: {type(uuid)}")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={"parameter": "uuid", "type": type(uuid).__name__, "value": uuid},
        )

    # Validate value parameter
    if not isinstance(value, str):
        error_msg = "Command value must be a string"
        logger.warning(f"send_command called with non-string value: {type(value)}")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={"parameter": "value", "type": type(value).__name__, "value": value},
        )

    # Normalize parameters
    uuid = uuid.strip()
    if not uuid:
        error_msg = "UUID cannot be empty or whitespace only"
        logger.warning("send_command called with whitespace-only UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid"}
        )

    try:
        # Use session to send command (includes device validation)
        result = await session.send_command(uuid, value)

        if result["success"]:
            logger.info(f"Command sent successfully for client {client_id}: {result}")
            return create_success_response(
                {
                    "device": uuid,
                    "command": value,
                    "device_name": result.get("device_name", "Unknown"),
                    "command_value": result.get("command_value", value),
                },
                context={"client_id": client_id, "command_sent_at": "real-time"},
            )
        else:
            logger.warning(f"Command failed for client {client_id}: {result}")
            return create_error_response(
                result.get("error_code", ERROR_COMMAND_FAILED),
                result.get("error", "Command failed"),
                details={"uuid": uuid, "command": value},
                context={"client_id": client_id},
            )

    except Exception as e:
        error_msg = f"Unexpected error sending command: {e}"
        logger.error(error_msg, exc_info=True)
        return create_error_response(
            ERROR_CONNECTION_FAILED,
            error_msg,
            details={"uuid": uuid, "command": value, "exception_type": type(e).__name__},
            context={"operation": "miniserver_communication"},
        )
        logger.error(error_msg, exc_info=True)
        return create_error_response(
            ERROR_COMMAND_FAILED,
            error_msg,
            details={"uuid": uuid, "command": value, "exception_type": type(e).__name__},
            context={"operation": "send_command"},
        )


@mcp.tool()
async def loxone_set_switch(
    client_id: str = "default", uuid: str = "", state: bool = False
) -> dict[str, Any]:
    """
    Turn a Loxone switch on or off.

    Args:
        client_id: Unique identifier for the client
        uuid: The UUID of the switch device
        state: True for on, False for off

    Returns:
        Standardized response with success status and updated state
    """
    logger.info(f"Setting switch {uuid} to {'ON' if state else 'OFF'} for client {client_id}")

    # Check initialization
    if connection_manager is None:
        error_msg = "Connection manager not initialized - server may not be fully started"
        logger.error(error_msg)
        return create_error_response(
            ERROR_INITIALIZATION_FAILED,
            error_msg,
            context={
                "operation": "set_switch",
                "client_id": client_id,
                "uuid": uuid,
                "state": state,
            },
        )

    # Get or create client session
    session = await get_or_create_session(client_id)
    if not session:
        error_msg = f"Failed to get or create session for client {client_id}"
        logger.error(error_msg)
        return create_error_response(
            ERROR_INITIALIZATION_FAILED,
            error_msg,
            context={"operation": "set_switch", "client_id": client_id},
        )

    # Validate UUID parameter
    if not uuid:
        error_msg = "UUID parameter is required"
        logger.warning("set_switch called with empty UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid", "value": uuid}
        )

    if not isinstance(uuid, str):
        error_msg = "UUID must be a string"
        logger.warning(f"set_switch called with non-string UUID: {type(uuid)}")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={"parameter": "uuid", "type": type(uuid).__name__, "value": uuid},
        )

    # Validate state parameter
    if not isinstance(state, bool):
        error_msg = "State must be a boolean (True for on, False for off)"
        logger.warning(f"set_switch called with non-boolean state: {type(state)}")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={"parameter": "state", "type": type(state).__name__, "value": state},
        )

    # Normalize UUID
    uuid = uuid.strip()
    if not uuid:
        error_msg = "UUID cannot be empty or whitespace only"
        logger.warning("set_switch called with whitespace-only UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid"}
        )

    try:
        # Use session to control switch (includes device validation)
        result = await session.control_switch(uuid, state)

        if result["success"]:
            logger.info(f"Switch control successful for client {client_id}: {result}")
            return create_success_response(
                {
                    "device": uuid,
                    "state": state,
                    "device_name": result.get("device_name", "Unknown"),
                    "value": result.get("value", "On" if state else "Off"),
                },
                context={"client_id": client_id, "command_sent_at": "real-time"},
            )
        else:
            logger.warning(f"Switch control failed for client {client_id}: {result}")
            return create_error_response(
                result.get("error_code", ERROR_COMMAND_FAILED),
                result.get("error", "Switch control failed"),
                details={"uuid": uuid, "state": state},
                context={"client_id": client_id},
            )

    except Exception as e:
        error_msg = f"Unexpected error setting switch: {e}"
        logger.error(error_msg, exc_info=True)
        return create_error_response(
            ERROR_COMMAND_FAILED,
            error_msg,
            details={"uuid": uuid, "requested_state": state, "exception_type": type(e).__name__},
            context={"operation": "set_switch"},
        )


@mcp.tool()
async def loxone_set_dimmer(uuid: str, brightness: int) -> dict[str, Any]:
    """
    Set the brightness of a Loxone dimmer.

    Args:
        uuid: The UUID of the dimmer device
        brightness: Brightness level (0-100)

    Returns:
        Standardized response with success status and updated brightness
    """
    logger.info(f"Setting dimmer {uuid} to {brightness}%")

    # Check initialization
    if loxone_client is None or device_manager is None:
        error_msg = (
            "Loxone client or device manager not initialized - server may not be fully started"
        )
        logger.error(error_msg)
        return create_error_response(
            ERROR_INITIALIZATION_FAILED,
            error_msg,
            context={"operation": "set_dimmer", "uuid": uuid, "brightness": brightness},
        )

    # Validate UUID parameter
    if not uuid:
        error_msg = "UUID parameter is required"
        logger.warning("set_dimmer called with empty UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid", "value": uuid}
        )

    if not isinstance(uuid, str):
        error_msg = "UUID must be a string"
        logger.warning(f"set_dimmer called with non-string UUID: {type(uuid)}")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={"parameter": "uuid", "type": type(uuid).__name__, "value": uuid},
        )

    # Validate brightness parameter
    if not isinstance(brightness, int):
        error_msg = "Brightness must be an integer"
        logger.warning(f"set_dimmer called with non-integer brightness: {type(brightness)}")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={
                "parameter": "brightness",
                "type": type(brightness).__name__,
                "value": brightness,
            },
        )

    if not 0 <= brightness <= 100:
        error_msg = "Brightness must be between 0 and 100"
        logger.warning(f"set_dimmer called with out-of-range brightness: {brightness}")
        return create_error_response(
            ERROR_VALIDATION_FAILED,
            error_msg,
            details={"parameter": "brightness", "value": brightness, "valid_range": "0-100"},
        )

    # Normalize UUID
    uuid = uuid.strip()
    if not uuid:
        error_msg = "UUID cannot be empty or whitespace only"
        logger.warning("set_dimmer called with whitespace-only UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid"}
        )

    try:
        # Check if device exists
        device = device_manager.get_device(uuid)
        if not device:
            error_msg = f"Device not found with UUID: {uuid}"
            logger.warning(f"Dimmer operation attempted on non-existent device: {uuid}")
            return create_error_response(
                ERROR_DEVICE_NOT_FOUND,
                error_msg,
                details={"uuid": uuid, "requested_brightness": brightness},
                context={"suggestion": "Use loxone_list_devices to see available devices"},
            )

        # Validate device type for dimmer operation
        valid_dimmer_types = ["Dimmer", "LightControllerV2"]
        if device.type not in valid_dimmer_types:
            error_msg = f"Device '{device.name}' is not a dimmer (type: {device.type})"
            logger.warning(
                f"Dimmer operation attempted on non-dimmer device: {device.name} ({device.type})"
            )
            return create_error_response(
                ERROR_DEVICE_TYPE_MISMATCH,
                error_msg,
                details={
                    "uuid": uuid,
                    "device_name": device.name,
                    "actual_type": device.type,
                    "required_types": valid_dimmer_types,
                },
                context={
                    "suggestion": f"Use loxone_send_command for {device.type} devices, or check device type"
                },
            )

        logger.debug(
            f"Setting brightness {brightness}% on dimmer '{device.name}' ({device.type}) in {device.room}"
        )

        # Send brightness command to Miniserver
        try:
            success = await loxone_client.send_command(uuid, str(brightness))

            if success:
                logger.info(f"Dimmer '{device.name}' set to {brightness}% successfully")
                return create_success_response(
                    {
                        "device": uuid,
                        "brightness": brightness,
                        "device_name": device.name,
                        "device_type": device.type,
                        "room": device.room,
                    },
                    context={
                        "dimmer_operation": "successful",
                        "brightness_range": "0-100",
                        "device_info": {
                            "type": device.type,
                            "room": device.room,
                            "category": device.category,
                        },
                    },
                )
            else:
                error_msg = f"Failed to set dimmer '{device.name}' to {brightness}%"
                logger.warning(error_msg)
                return create_error_response(
                    ERROR_COMMAND_FAILED,
                    error_msg,
                    details={
                        "uuid": uuid,
                        "requested_brightness": brightness,
                        "device_name": device.name,
                        "device_type": device.type,
                    },
                    context={
                        "possible_causes": [
                            "Dimmer may be offline or unresponsive",
                            "Network connectivity issues",
                            "Device may be in manual override mode",
                            "Brightness value may not be supported by this dimmer",
                        ]
                    },
                )

        except Exception as e:
            error_msg = f"Error communicating with Miniserver for dimmer operation: {e}"
            logger.error(f"Communication error setting dimmer {uuid}: {e}", exc_info=True)
            return create_error_response(
                ERROR_CONNECTION_FAILED,
                error_msg,
                details={
                    "uuid": uuid,
                    "requested_brightness": brightness,
                    "device_name": device.name,
                    "exception_type": type(e).__name__,
                },
                context={"operation": "dimmer_miniserver_communication"},
            )

    except Exception as e:
        error_msg = f"Unexpected error setting dimmer: {e}"
        logger.error(error_msg, exc_info=True)
        return create_error_response(
            ERROR_COMMAND_FAILED,
            error_msg,
            details={
                "uuid": uuid,
                "requested_brightness": brightness,
                "exception_type": type(e).__name__,
            },
            context={"operation": "set_dimmer"},
        )


@mcp.tool()
async def loxone_set_cover_position(uuid: str, position: int) -> dict[str, Any]:
    """
    Set the position of a Loxone cover (blinds/shades).

    Args:
        uuid: The UUID of the cover device
        position: Position percentage (0=closed, 100=open)

    Returns:
        Standardized response with success status and updated position
    """
    logger.info(f"Setting cover {uuid} to position {position}%")

    # Check initialization
    if loxone_client is None or device_manager is None:
        error_msg = (
            "Loxone client or device manager not initialized - server may not be fully started"
        )
        logger.error(error_msg)
        return create_error_response(
            ERROR_INITIALIZATION_FAILED,
            error_msg,
            context={"operation": "set_cover_position", "uuid": uuid, "position": position},
        )

    # Validate UUID parameter
    if not uuid:
        error_msg = "UUID parameter is required"
        logger.warning("set_cover_position called with empty UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid", "value": uuid}
        )

    if not isinstance(uuid, str):
        error_msg = "UUID must be a string"
        logger.warning(f"set_cover_position called with non-string UUID: {type(uuid)}")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={"parameter": "uuid", "type": type(uuid).__name__, "value": uuid},
        )

    # Validate position parameter
    if not isinstance(position, int):
        error_msg = "Position must be an integer"
        logger.warning(f"set_cover_position called with non-integer position: {type(position)}")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={"parameter": "position", "type": type(position).__name__, "value": position},
        )

    if not 0 <= position <= 100:
        error_msg = "Position must be between 0 and 100 (0=closed, 100=open)"
        logger.warning(f"set_cover_position called with out-of-range position: {position}")
        return create_error_response(
            ERROR_VALIDATION_FAILED,
            error_msg,
            details={"parameter": "position", "value": position, "valid_range": "0-100"},
        )

    # Normalize UUID
    uuid = uuid.strip()
    if not uuid:
        error_msg = "UUID cannot be empty or whitespace only"
        logger.warning("set_cover_position called with whitespace-only UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid"}
        )

    try:
        # Check if device exists
        device = device_manager.get_device(uuid)
        if not device:
            error_msg = f"Device not found with UUID: {uuid}"
            logger.warning(f"Cover operation attempted on non-existent device: {uuid}")
            return create_error_response(
                ERROR_DEVICE_NOT_FOUND,
                error_msg,
                details={"uuid": uuid, "requested_position": position},
                context={"suggestion": "Use loxone_list_devices to see available devices"},
            )

        # Validate device type for cover operation
        valid_cover_types = ["Jalousie", "Window", "Gate"]
        if device.type not in valid_cover_types:
            error_msg = f"Device '{device.name}' is not a cover (type: {device.type})"
            logger.warning(
                f"Cover operation attempted on non-cover device: {device.name} ({device.type})"
            )
            return create_error_response(
                ERROR_DEVICE_TYPE_MISMATCH,
                error_msg,
                details={
                    "uuid": uuid,
                    "device_name": device.name,
                    "actual_type": device.type,
                    "required_types": valid_cover_types,
                },
                context={
                    "suggestion": f"Use loxone_send_command for {device.type} devices, or check device type"
                },
            )

        logger.debug(
            f"Setting position {position}% on cover '{device.name}' ({device.type}) in {device.room}"
        )

        # Send position command to Miniserver
        try:
            success = await loxone_client.send_command(uuid, str(position))

            if success:
                logger.info(f"Cover '{device.name}' set to {position}% successfully")
                return create_success_response(
                    {
                        "device": uuid,
                        "position": position,
                        "device_name": device.name,
                        "device_type": device.type,
                        "room": device.room,
                    },
                    context={
                        "cover_operation": "successful",
                        "position_meaning": "0=closed, 100=open",
                        "device_info": {
                            "type": device.type,
                            "room": device.room,
                            "category": device.category,
                        },
                    },
                )
            else:
                error_msg = f"Failed to set cover '{device.name}' to {position}%"
                logger.warning(error_msg)
                return create_error_response(
                    ERROR_COMMAND_FAILED,
                    error_msg,
                    details={
                        "uuid": uuid,
                        "requested_position": position,
                        "device_name": device.name,
                        "device_type": device.type,
                    },
                    context={
                        "possible_causes": [
                            "Cover may be offline or unresponsive",
                            "Network connectivity issues",
                            "Cover may be in manual override mode",
                            "Position may be blocked by safety features",
                        ]
                    },
                )

        except Exception as e:
            error_msg = f"Error communicating with Miniserver for cover operation: {e}"
            logger.error(f"Communication error setting cover position {uuid}: {e}", exc_info=True)
            return create_error_response(
                ERROR_CONNECTION_FAILED,
                error_msg,
                details={
                    "uuid": uuid,
                    "requested_position": position,
                    "device_name": device.name,
                    "exception_type": type(e).__name__,
                },
                context={"operation": "cover_miniserver_communication"},
            )

    except Exception as e:
        error_msg = f"Unexpected error setting cover position: {e}"
        logger.error(error_msg, exc_info=True)
        return create_error_response(
            ERROR_COMMAND_FAILED,
            error_msg,
            details={
                "uuid": uuid,
                "requested_position": position,
                "exception_type": type(e).__name__,
            },
            context={"operation": "set_cover_position"},
        )


@mcp.tool()
async def loxone_set_temperature(uuid: str, temperature: float) -> dict[str, Any]:
    """
    Set the target temperature for a Loxone climate control device.

    Args:
        uuid: The UUID of the climate control device
        temperature: Target temperature in Celsius

    Returns:
        Standardized response with success status and updated temperature
    """
    logger.info(f"Setting temperature for climate control {uuid} to {temperature}°C")

    # Check initialization
    if loxone_client is None or device_manager is None:
        error_msg = (
            "Loxone client or device manager not initialized - server may not be fully started"
        )
        logger.error(error_msg)
        return create_error_response(
            ERROR_INITIALIZATION_FAILED,
            error_msg,
            context={"operation": "set_temperature", "uuid": uuid, "temperature": temperature},
        )

    # Validate UUID parameter
    if not uuid:
        error_msg = "UUID parameter is required"
        logger.warning("set_temperature called with empty UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid", "value": uuid}
        )

    if not isinstance(uuid, str):
        error_msg = "UUID must be a string"
        logger.warning(f"set_temperature called with non-string UUID: {type(uuid)}")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={"parameter": "uuid", "type": type(uuid).__name__, "value": uuid},
        )

    # Validate temperature parameter
    if not isinstance(temperature, (int, float)):
        error_msg = "Temperature must be a number (int or float)"
        logger.warning(f"set_temperature called with non-numeric temperature: {type(temperature)}")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={
                "parameter": "temperature",
                "type": type(temperature).__name__,
                "value": temperature,
            },
        )

    # Reasonable temperature range check
    if not -50 <= temperature <= 50:
        error_msg = "Temperature must be between -50 and 50 degrees Celsius"
        logger.warning(f"set_temperature called with out-of-range temperature: {temperature}")
        return create_error_response(
            ERROR_VALIDATION_FAILED,
            error_msg,
            details={
                "parameter": "temperature",
                "value": temperature,
                "valid_range": "-50 to 50°C",
            },
        )

    # Normalize UUID
    uuid = uuid.strip()
    if not uuid:
        error_msg = "UUID cannot be empty or whitespace only"
        logger.warning("set_temperature called with whitespace-only UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid"}
        )

    try:
        # Check if device exists
        device = device_manager.get_device(uuid)
        if not device:
            error_msg = f"Device not found with UUID: {uuid}"
            logger.warning(f"Temperature operation attempted on non-existent device: {uuid}")
            return create_error_response(
                ERROR_DEVICE_NOT_FOUND,
                error_msg,
                details={"uuid": uuid, "requested_temperature": temperature},
                context={"suggestion": "Use loxone_list_devices to see available devices"},
            )

        # Validate device type for temperature control operation
        valid_climate_types = ["IRoomControllerV2"]
        if device.type not in valid_climate_types:
            error_msg = f"Device '{device.name}' is not a climate control (type: {device.type})"
            logger.warning(
                f"Temperature operation attempted on non-climate device: {device.name} ({device.type})"
            )
            return create_error_response(
                ERROR_DEVICE_TYPE_MISMATCH,
                error_msg,
                details={
                    "uuid": uuid,
                    "device_name": device.name,
                    "actual_type": device.type,
                    "required_types": valid_climate_types,
                },
                context={
                    "suggestion": f"Use loxone_send_command for {device.type} devices, or check device type"
                },
            )

        logger.debug(
            f"Setting temperature {temperature}°C on climate control '{device.name}' ({device.type}) in {device.room}"
        )

        # Send temperature command to Miniserver
        try:
            success = await loxone_client.send_command(uuid, str(temperature))

            if success:
                logger.info(f"Climate control '{device.name}' set to {temperature}°C successfully")
                return create_success_response(
                    {
                        "device": uuid,
                        "temperature": temperature,
                        "device_name": device.name,
                        "device_type": device.type,
                        "room": device.room,
                    },
                    context={
                        "climate_operation": "successful",
                        "temperature_unit": "Celsius",
                        "device_info": {
                            "type": device.type,
                            "room": device.room,
                            "category": device.category,
                        },
                    },
                )
            else:
                error_msg = f"Failed to set climate control '{device.name}' to {temperature}°C"
                logger.warning(error_msg)
                return create_error_response(
                    ERROR_COMMAND_FAILED,
                    error_msg,
                    details={
                        "uuid": uuid,
                        "requested_temperature": temperature,
                        "device_name": device.name,
                        "device_type": device.type,
                    },
                    context={
                        "possible_causes": [
                            "Climate control may be offline or unresponsive",
                            "Network connectivity issues",
                            "Device may be in manual override mode",
                            "Temperature may be outside device's operating range",
                            "Heating/cooling system may be disabled",
                        ]
                    },
                )

        except Exception as e:
            error_msg = f"Error communicating with Miniserver for temperature operation: {e}"
            logger.error(f"Communication error setting temperature {uuid}: {e}", exc_info=True)
            return create_error_response(
                ERROR_CONNECTION_FAILED,
                error_msg,
                details={
                    "uuid": uuid,
                    "requested_temperature": temperature,
                    "device_name": device.name,
                    "exception_type": type(e).__name__,
                },
                context={"operation": "temperature_miniserver_communication"},
            )

    except Exception as e:
        error_msg = f"Unexpected error setting temperature: {e}"
        logger.error(error_msg, exc_info=True)
        return create_error_response(
            ERROR_COMMAND_FAILED,
            error_msg,
            details={
                "uuid": uuid,
                "requested_temperature": temperature,
                "exception_type": type(e).__name__,
            },
            context={"operation": "set_temperature"},
        )


# ============================================================================
# Secured Command Tool
# ============================================================================


@mcp.tool()
async def loxone_send_secured_command(uuid: str, value: str, code: str) -> dict[str, Any]:
    """
    Send a secured command to a Loxone device that requires PIN authentication.

    This tool is used for security-sensitive devices like alarm systems that
    require a PIN code for authentication. The PIN is used to generate a
    visual hash for secure authentication with the Miniserver.

    Args:
        uuid: The UUID of the device
        value: The command value to send
        code: The PIN code for authentication

    Returns:
        Standardized response with success status and device information
    """
    logger.info(f"Sending secured command to device {uuid}: {value} (PIN provided)")

    # Check initialization
    if loxone_client is None or device_manager is None:
        error_msg = (
            "Loxone client or device manager not initialized - server may not be fully started"
        )
        logger.error(error_msg)
        return create_error_response(
            ERROR_INITIALIZATION_FAILED,
            error_msg,
            context={"operation": "send_secured_command", "uuid": uuid},
        )

    # Validate UUID parameter
    if not uuid:
        error_msg = "UUID parameter is required"
        logger.warning("send_secured_command called with empty UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid", "value": uuid}
        )

    if not isinstance(uuid, str):
        error_msg = "UUID must be a string"
        logger.warning(f"send_secured_command called with non-string UUID: {type(uuid)}")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={"parameter": "uuid", "type": type(uuid).__name__},
        )

    # Validate value parameter
    if not isinstance(value, str):
        error_msg = "Command value must be a string"
        logger.warning(f"send_secured_command called with non-string value: {type(value)}")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={"parameter": "value", "type": type(value).__name__},
        )

    # Validate code parameter (be extra careful with security)
    if not code:
        error_msg = "PIN code parameter is required for secured commands"
        logger.warning("send_secured_command called with empty PIN code")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={"parameter": "code"},
            context={"security_note": "PIN code is required for authentication"},
        )

    if not isinstance(code, str):
        error_msg = "PIN code must be a string"
        logger.warning(f"send_secured_command called with non-string PIN code: {type(code)}")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={"parameter": "code", "type": type(code).__name__},
        )

    # Normalize parameters
    uuid = uuid.strip()
    if not uuid:
        error_msg = "UUID cannot be empty or whitespace only"
        logger.warning("send_secured_command called with whitespace-only UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid"}
        )

    # Don't strip the PIN code as it might be intentionally padded
    if not code:
        error_msg = "PIN code cannot be empty"
        logger.warning("send_secured_command called with empty PIN code after validation")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "code"}
        )

    try:
        # Check if device exists
        device = device_manager.get_device(uuid)
        if not device:
            error_msg = f"Device not found with UUID: {uuid}"
            logger.warning(f"Secured command attempted on non-existent device: {uuid}")
            return create_error_response(
                ERROR_DEVICE_NOT_FOUND,
                error_msg,
                details={"uuid": uuid},
                context={"suggestion": "Use loxone_list_devices to see available devices"},
            )

        # Check if device is marked as secured (informational)
        is_secured = device.details.get("isSecured", False)
        if not is_secured:
            logger.warning(
                f"Device '{device.name}' is not marked as secured, but using secured command anyway"
            )

        logger.debug(
            f"Sending secured command '{value}' to device '{device.name}' ({device.type}) in {device.room}"
        )

        # Send secured command to Miniserver
        try:
            success = await loxone_client.send_secured_command(uuid, value, code)

            if success:
                logger.info(
                    f"Secured command sent successfully to '{device.name}' ({uuid}): {value}"
                )
                return create_success_response(
                    {
                        "device": uuid,
                        "command": value,
                        "device_name": device.name,
                        "device_type": device.type,
                        "room": device.room,
                        "secured": True,
                        "authentication": "PIN verified",
                    },
                    context={
                        "security_operation": "successful",
                        "device_secured": is_secured,
                        "device_info": {
                            "type": device.type,
                            "room": device.room,
                            "category": device.category,
                        },
                    },
                )
            else:
                error_msg = f"Secured command failed for device '{device.name}'"
                logger.warning(f"Secured command failed for '{device.name}' ({uuid}): {value}")
                # Don't log the PIN code for security reasons
                return create_error_response(
                    ERROR_AUTHENTICATION_FAILED,
                    error_msg,
                    details={
                        "uuid": uuid,
                        "device_name": device.name,
                        "device_type": device.type,
                        "secured": True,
                    },
                    context={
                        "possible_causes": [
                            "Incorrect PIN code",
                            "Device may be offline or unresponsive",
                            "PIN code may have expired or been changed",
                            "Network connectivity issues",
                            "Device security settings may have changed",
                        ],
                        "security_note": "PIN code is not logged for security reasons",
                    },
                )

        except Exception as e:
            error_msg = f"Error communicating with Miniserver for secured command: {e}"
            logger.error(
                f"Communication error sending secured command to {uuid}: {e}", exc_info=True
            )
            # Don't include the PIN code in error messages for security
            return create_error_response(
                ERROR_CONNECTION_FAILED,
                error_msg,
                details={
                    "uuid": uuid,
                    "device_name": device.name,
                    "exception_type": type(e).__name__,
                    "secured": True,
                },
                context={
                    "operation": "secured_miniserver_communication",
                    "security_note": "PIN code is not included in error details for security",
                },
            )

    except Exception as e:
        error_msg = f"Unexpected error sending secured command: {e}"
        logger.error(error_msg, exc_info=True)
        # Don't include the PIN code in error messages for security
        return create_error_response(
            ERROR_COMMAND_FAILED,
            error_msg,
            details={"uuid": uuid, "exception_type": type(e).__name__, "secured": True},
            context={
                "operation": "send_secured_command",
                "security_note": "PIN code is not included in error details for security",
            },
        )


# ============================================================================
# Scene Management Tools
# ============================================================================


@mcp.tool()
def loxone_list_scenes(client_id: str, room: str | None = None) -> dict[str, Any]:
    """
    List all available Loxone scenes (automation scenarios).

    Args:
        room: Filter by room name (optional)

    Returns:
        Standardized response with list of scenes and their basic information
    """
    logger.info(f"Listing scenes - Room filter: {room}")

    if device_manager is None:
        error_msg = "Device manager not initialized - server may not be fully started"
        logger.error(error_msg)
        return create_error_response(
            ERROR_INITIALIZATION_FAILED,
            error_msg,
            context={"operation": "list_scenes", "room_filter": room},
        )

    try:
        # Validate room parameter if provided
        if room is not None:
            if not isinstance(room, str) or not room.strip():
                error_msg = "Room must be a non-empty string"
                logger.warning(f"Invalid room parameter: {repr(room)}")
                return create_error_response(
                    ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "room", "value": room}
                )

        # Get scenes with filtering
        scenes = device_manager.list_scenes(room=room)

        # Format scene information
        scene_list = []
        for scene in scenes:
            try:
                scene_info = {
                    "uuid": scene.uuid,
                    "name": scene.name,
                    "room": scene.room,
                    "category": scene.category,
                    "description": scene.details.get("description", ""),
                    "isFavorite": scene.details.get("isFavorite", False),
                    "isSecured": scene.details.get("isSecured", False),
                }
                scene_list.append(scene_info)
            except Exception as e:
                logger.warning(f"Error formatting scene {scene.uuid}: {e}")
                continue

        logger.info(f"Successfully listed {len(scene_list)} scenes")
        logger.debug(f"Scene listing filter applied - Room: {room}")

        return create_success_response(
            {"scenes": scene_list, "count": len(scene_list)},
            context={
                "filter_applied": {"room": room},
                "total_scenes": device_manager.get_scene_count(),
                "scene_types": {
                    "favorite": len([s for s in scene_list if s.get("isFavorite", False)]),
                    "secured": len([s for s in scene_list if s.get("isSecured", False)]),
                },
            },
        )

    except Exception as e:
        error_msg = f"Unexpected error listing scenes: {e}"
        logger.error(error_msg, exc_info=True)
        return create_error_response(
            ERROR_COMMAND_FAILED,
            error_msg,
            details={"exception_type": type(e).__name__},
            context={"operation": "list_scenes", "room_filter": room},
        )


@mcp.tool()
async def loxone_trigger_scene(client_id: str, uuid: str) -> dict[str, Any]:
    """
    Trigger a Loxone scene (automation scenario).

    Args:
        uuid: The UUID of the scene to trigger

    Returns:
        Standardized response with success status and scene information
    """
    logger.info(f"Triggering scene {uuid}")

    # Check initialization
    if loxone_client is None or device_manager is None:
        error_msg = (
            "Loxone client or device manager not initialized - server may not be fully started"
        )
        logger.error(error_msg)
        return create_error_response(
            ERROR_INITIALIZATION_FAILED,
            error_msg,
            context={"operation": "trigger_scene", "uuid": uuid},
        )

    # Validate UUID parameter
    if not uuid:
        error_msg = "UUID parameter is required"
        logger.warning("trigger_scene called with empty UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid", "value": uuid}
        )

    if not isinstance(uuid, str):
        error_msg = "UUID must be a string"
        logger.warning(f"trigger_scene called with non-string UUID: {type(uuid)}")
        return create_error_response(
            ERROR_INVALID_PARAMETER,
            error_msg,
            details={"parameter": "uuid", "type": type(uuid).__name__, "value": uuid},
        )

    # Normalize UUID
    uuid = uuid.strip()
    if not uuid:
        error_msg = "UUID cannot be empty or whitespace only"
        logger.warning("trigger_scene called with whitespace-only UUID")
        return create_error_response(
            ERROR_INVALID_PARAMETER, error_msg, details={"parameter": "uuid"}
        )

    try:
        # Check if scene exists
        scene = device_manager.get_scene(uuid)
        if not scene:
            error_msg = f"Scene not found with UUID: {uuid}"
            logger.warning(f"Scene trigger attempted on non-existent scene: {uuid}")

            # Provide helpful context
            total_scenes = device_manager.get_scene_count()
            return create_error_response(
                ERROR_DEVICE_NOT_FOUND,
                error_msg,
                details={"uuid": uuid},
                context={
                    "total_scenes": total_scenes,
                    "suggestion": "Use loxone_list_scenes to see available scenes",
                },
            )

        # Check if scene is secured and provide information
        is_secured = scene.details.get("isSecured", False)
        if is_secured:
            logger.warning(f"Scene '{scene.name}' is secured - may require PIN authentication")

        logger.debug(f"Triggering scene '{scene.name}' in {scene.room} (secured: {is_secured})")

        # Trigger scene by sending "On" command to the scene UUID
        try:
            success = await loxone_client.send_command(uuid, "On")

            if success:
                logger.info(f"Scene '{scene.name}' triggered successfully ({uuid})")
                return create_success_response(
                    {
                        "scene": uuid,
                        "scene_name": scene.name,
                        "room": scene.room,
                        "category": scene.category,
                        "secured": is_secured,
                        "favorite": scene.details.get("isFavorite", False),
                        "description": scene.details.get("description", ""),
                    },
                    context={
                        "scene_operation": "triggered",
                        "security_info": {
                            "is_secured": is_secured,
                            "note": (
                                "Secured scenes may require PIN authentication"
                                if is_secured
                                else None
                            ),
                        },
                        "scene_info": {"room": scene.room, "category": scene.category},
                    },
                )
            else:
                error_msg = f"Failed to trigger scene '{scene.name}'"
                logger.warning(f"Scene trigger failed for '{scene.name}' ({uuid})")

                # Provide different suggestions based on whether scene is secured
                suggestions = [
                    "Scene may be offline or disabled",
                    "Network connectivity issues",
                    "Scene may have execution conditions that are not met",
                ]

                if is_secured:
                    suggestions.insert(
                        0, "Scene is secured - use loxone_send_secured_command with PIN if required"
                    )

                return create_error_response(
                    ERROR_COMMAND_FAILED,
                    error_msg,
                    details={"uuid": uuid, "scene_name": scene.name, "secured": is_secured},
                    context={
                        "possible_causes": suggestions,
                        "security_note": (
                            "Secured scenes may require PIN authentication" if is_secured else None
                        ),
                    },
                )

        except Exception as e:
            error_msg = f"Error communicating with Miniserver for scene trigger: {e}"
            logger.error(f"Communication error triggering scene {uuid}: {e}", exc_info=True)
            return create_error_response(
                ERROR_CONNECTION_FAILED,
                error_msg,
                details={
                    "uuid": uuid,
                    "scene_name": scene.name,
                    "exception_type": type(e).__name__,
                },
                context={"operation": "scene_miniserver_communication"},
            )

    except Exception as e:
        error_msg = f"Unexpected error triggering scene: {e}"
        logger.error(error_msg, exc_info=True)
        return create_error_response(
            ERROR_COMMAND_FAILED,
            error_msg,
            details={"uuid": uuid, "exception_type": type(e).__name__},
            context={"operation": "trigger_scene"},
        )


# ============================================================================
# Complete Home Assistant Component Feature Migration - Additional MCP Tools
# ============================================================================


@mcp.tool()
async def loxone_set_light_color(
    client_id: str = "default", uuid: str = "", color: str = ""
) -> dict[str, Any]:
    """
    Set the color of a Loxone color light.

    Args:
        client_id: Unique identifier for the client
        uuid: The UUID of the color light device
        color: Color in hex format (#RRGGBB)

    Returns:
        Standardized response with success status and color information
    """
    logger.info(f"Setting light color {uuid} to {color} for client {client_id}")

    if connection_manager is None:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, "Connection manager not initialized"
        )

    session = await get_or_create_session(client_id)
    if not session:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, f"Failed to get session for client {client_id}"
        )

    if not uuid or not color:
        return create_error_response(
            ERROR_INVALID_PARAMETER, "UUID and color parameters are required"
        )

    try:
        result = await session.control_light_color(uuid, color)

        if result["success"]:
            return create_success_response(
                {
                    "device": uuid,
                    "device_name": result.get("device_name", "Unknown"),
                    "color": result.get("color"),
                    "hsv": result.get("hsv"),
                }
            )
        else:
            return create_error_response(
                result.get("error_code", ERROR_COMMAND_FAILED),
                result.get("error", "Color command failed"),
            )
    except Exception as e:
        logger.error(f"Error setting light color {uuid}: {e}")
        return create_error_response(ERROR_COMMAND_FAILED, str(e))


@mcp.tool()
async def loxone_cover_open(client_id: str = "default", uuid: str = "") -> dict[str, Any]:
    """
    Open a cover completely.

    Args:
        client_id: Unique identifier for the client
        uuid: The UUID of the cover device

    Returns:
        Standardized response with success status
    """
    logger.info(f"Opening cover {uuid} for client {client_id}")

    if connection_manager is None:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, "Connection manager not initialized"
        )

    session = await get_or_create_session(client_id)
    if not session:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, f"Failed to get session for client {client_id}"
        )

    if not uuid:
        return create_error_response(ERROR_INVALID_PARAMETER, "UUID parameter is required")

    try:
        result = await session.control_cover_open(uuid)

        if result["success"]:
            return create_success_response(
                {
                    "device": uuid,
                    "device_name": result.get("device_name", "Unknown"),
                    "position": result.get("position", 100),
                    "action": "open",
                }
            )
        else:
            return create_error_response(
                result.get("error_code", ERROR_COMMAND_FAILED),
                result.get("error", "Cover open command failed"),
            )
    except Exception as e:
        logger.error(f"Error opening cover {uuid}: {e}")
        return create_error_response(ERROR_COMMAND_FAILED, str(e))


@mcp.tool()
async def loxone_cover_close(client_id: str = "default", uuid: str = "") -> dict[str, Any]:
    """
    Close a cover completely.

    Args:
        client_id: Unique identifier for the client
        uuid: The UUID of the cover device

    Returns:
        Standardized response with success status
    """
    logger.info(f"Closing cover {uuid} for client {client_id}")

    if connection_manager is None:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, "Connection manager not initialized"
        )

    session = await get_or_create_session(client_id)
    if not session:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, f"Failed to get session for client {client_id}"
        )

    if not uuid:
        return create_error_response(ERROR_INVALID_PARAMETER, "UUID parameter is required")

    try:
        result = await session.control_cover_close(uuid)

        if result["success"]:
            return create_success_response(
                {
                    "device": uuid,
                    "device_name": result.get("device_name", "Unknown"),
                    "position": result.get("position", 0),
                    "action": "close",
                }
            )
        else:
            return create_error_response(
                result.get("error_code", ERROR_COMMAND_FAILED),
                result.get("error", "Cover close command failed"),
            )
    except Exception as e:
        logger.error(f"Error closing cover {uuid}: {e}")
        return create_error_response(ERROR_COMMAND_FAILED, str(e))


@mcp.tool()
async def loxone_set_climate_mode(
    client_id: str = "default", uuid: str = "", mode: str = ""
) -> dict[str, Any]:
    """
    Set climate control mode.

    Args:
        client_id: Unique identifier for the client
        uuid: The UUID of the climate device
        mode: Climate mode (heat, cool, auto, off)

    Returns:
        Standardized response with success status and mode information
    """
    logger.info(f"Setting climate mode {uuid} to {mode} for client {client_id}")

    if connection_manager is None:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, "Connection manager not initialized"
        )

    session = await get_or_create_session(client_id)
    if not session:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, f"Failed to get session for client {client_id}"
        )

    if not uuid or not mode:
        return create_error_response(
            ERROR_INVALID_PARAMETER, "UUID and mode parameters are required"
        )

    try:
        result = await session.control_climate_mode(uuid, mode)

        if result["success"]:
            return create_success_response(
                {
                    "device": uuid,
                    "device_name": result.get("device_name", "Unknown"),
                    "mode": result.get("mode"),
                }
            )
        else:
            return create_error_response(
                result.get("error_code", ERROR_COMMAND_FAILED),
                result.get("error", "Climate mode command failed"),
            )
    except Exception as e:
        logger.error(f"Error setting climate mode {uuid}: {e}")
        return create_error_response(ERROR_COMMAND_FAILED, str(e))


@mcp.tool()
async def loxone_set_fan_speed(
    client_id: str = "default", uuid: str = "", speed: int = 0
) -> dict[str, Any]:
    """
    Set fan speed for ventilation controls.

    Args:
        client_id: Unique identifier for the client
        uuid: The UUID of the fan device
        speed: Fan speed (0-100)

    Returns:
        Standardized response with success status and speed information
    """
    logger.info(f"Setting fan speed {uuid} to {speed} for client {client_id}")

    if connection_manager is None:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, "Connection manager not initialized"
        )

    session = await get_or_create_session(client_id)
    if not session:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, f"Failed to get session for client {client_id}"
        )

    if not uuid:
        return create_error_response(ERROR_INVALID_PARAMETER, "UUID parameter is required")

    try:
        result = await session.control_fan_speed(uuid, speed)

        if result["success"]:
            return create_success_response(
                {
                    "device": uuid,
                    "device_name": result.get("device_name", "Unknown"),
                    "fan_speed": result.get("fan_speed"),
                }
            )
        else:
            return create_error_response(
                result.get("error_code", ERROR_COMMAND_FAILED),
                result.get("error", "Fan speed command failed"),
            )
    except Exception as e:
        logger.error(f"Error setting fan speed {uuid}: {e}")
        return create_error_response(ERROR_COMMAND_FAILED, str(e))


@mcp.tool()
async def loxone_media_play(client_id: str = "default", uuid: str = "") -> dict[str, Any]:
    """
    Start media playback.

    Args:
        client_id: Unique identifier for the client
        uuid: The UUID of the media player device

    Returns:
        Standardized response with success status
    """
    logger.info(f"Starting media playback {uuid} for client {client_id}")

    if connection_manager is None:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, "Connection manager not initialized"
        )

    session = await get_or_create_session(client_id)
    if not session:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, f"Failed to get session for client {client_id}"
        )

    if not uuid:
        return create_error_response(ERROR_INVALID_PARAMETER, "UUID parameter is required")

    try:
        result = await session.control_media_play(uuid)

        if result["success"]:
            return create_success_response(
                {
                    "device": uuid,
                    "device_name": result.get("device_name", "Unknown"),
                    "action": "play",
                }
            )
        else:
            return create_error_response(
                result.get("error_code", ERROR_COMMAND_FAILED),
                result.get("error", "Media play command failed"),
            )
    except Exception as e:
        logger.error(f"Error starting media playback {uuid}: {e}")
        return create_error_response(ERROR_COMMAND_FAILED, str(e))


@mcp.tool()
async def loxone_media_pause(client_id: str = "default", uuid: str = "") -> dict[str, Any]:
    """
    Pause media playback.

    Args:
        client_id: Unique identifier for the client
        uuid: The UUID of the media player device

    Returns:
        Standardized response with success status
    """
    logger.info(f"Pausing media playback {uuid} for client {client_id}")

    if connection_manager is None:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, "Connection manager not initialized"
        )

    session = await get_or_create_session(client_id)
    if not session:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, f"Failed to get session for client {client_id}"
        )

    if not uuid:
        return create_error_response(ERROR_INVALID_PARAMETER, "UUID parameter is required")

    try:
        result = await session.control_media_pause(uuid)

        if result["success"]:
            return create_success_response(
                {
                    "device": uuid,
                    "device_name": result.get("device_name", "Unknown"),
                    "action": "pause",
                }
            )
        else:
            return create_error_response(
                result.get("error_code", ERROR_COMMAND_FAILED),
                result.get("error", "Media pause command failed"),
            )
    except Exception as e:
        logger.error(f"Error pausing media playback {uuid}: {e}")
        return create_error_response(ERROR_COMMAND_FAILED, str(e))


@mcp.tool()
async def loxone_set_volume(
    client_id: str = "default", uuid: str = "", volume: int = 0
) -> dict[str, Any]:
    """
    Set media player volume.

    Args:
        client_id: Unique identifier for the client
        uuid: The UUID of the media player device
        volume: Volume level (0-100)

    Returns:
        Standardized response with success status and volume information
    """
    logger.info(f"Setting volume {uuid} to {volume} for client {client_id}")

    if connection_manager is None:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, "Connection manager not initialized"
        )

    session = await get_or_create_session(client_id)
    if not session:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, f"Failed to get session for client {client_id}"
        )

    if not uuid:
        return create_error_response(ERROR_INVALID_PARAMETER, "UUID parameter is required")

    try:
        result = await session.control_volume(uuid, volume)

        if result["success"]:
            return create_success_response(
                {
                    "device": uuid,
                    "device_name": result.get("device_name", "Unknown"),
                    "volume": result.get("volume"),
                }
            )
        else:
            return create_error_response(
                result.get("error_code", ERROR_COMMAND_FAILED),
                result.get("error", "Volume command failed"),
            )
    except Exception as e:
        logger.error(f"Error setting volume {uuid}: {e}")
        return create_error_response(ERROR_COMMAND_FAILED, str(e))


@mcp.tool()
async def loxone_arm_alarm(
    client_id: str = "default", uuid: str = "", code: str = ""
) -> dict[str, Any]:
    """
    Arm alarm system with PIN code.

    Args:
        client_id: Unique identifier for the client
        uuid: The UUID of the alarm device
        code: PIN code for authentication

    Returns:
        Standardized response with success status
    """
    logger.info(f"Arming alarm {uuid} for client {client_id}")

    if connection_manager is None:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, "Connection manager not initialized"
        )

    session = await get_or_create_session(client_id)
    if not session:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, f"Failed to get session for client {client_id}"
        )

    if not uuid or not code:
        return create_error_response(
            ERROR_INVALID_PARAMETER, "UUID and code parameters are required"
        )

    try:
        result = await session.control_alarm_arm(uuid, code)

        if result["success"]:
            return create_success_response(
                {
                    "device": uuid,
                    "device_name": result.get("device_name", "Unknown"),
                    "action": "arm",
                }
            )
        else:
            return create_error_response(
                result.get("error_code", ERROR_COMMAND_FAILED),
                result.get("error", "Alarm arm command failed"),
            )
    except Exception as e:
        logger.error(f"Error arming alarm {uuid}: {e}")
        return create_error_response(ERROR_COMMAND_FAILED, str(e))


@mcp.tool()
async def loxone_disarm_alarm(
    client_id: str = "default", uuid: str = "", code: str = ""
) -> dict[str, Any]:
    """
    Disarm alarm system with PIN code.

    Args:
        client_id: Unique identifier for the client
        uuid: The UUID of the alarm device
        code: PIN code for authentication

    Returns:
        Standardized response with success status
    """
    logger.info(f"Disarming alarm {uuid} for client {client_id}")

    if connection_manager is None:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, "Connection manager not initialized"
        )

    session = await get_or_create_session(client_id)
    if not session:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, f"Failed to get session for client {client_id}"
        )

    if not uuid or not code:
        return create_error_response(
            ERROR_INVALID_PARAMETER, "UUID and code parameters are required"
        )

    try:
        result = await session.control_alarm_disarm(uuid, code)

        if result["success"]:
            return create_success_response(
                {
                    "device": uuid,
                    "device_name": result.get("device_name", "Unknown"),
                    "action": "disarm",
                }
            )
        else:
            return create_error_response(
                result.get("error_code", ERROR_COMMAND_FAILED),
                result.get("error", "Alarm disarm command failed"),
            )
    except Exception as e:
        logger.error(f"Error disarming alarm {uuid}: {e}")
        return create_error_response(ERROR_COMMAND_FAILED, str(e))


@mcp.tool()
async def loxone_set_text_input(
    client_id: str = "default", uuid: str = "", text: str = ""
) -> dict[str, Any]:
    """
    Set text input value.

    Args:
        client_id: Unique identifier for the client
        uuid: The UUID of the text input device
        text: Text value to set

    Returns:
        Standardized response with success status and text information
    """
    logger.info(f"Setting text input {uuid} to '{text}' for client {client_id}")

    if connection_manager is None:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, "Connection manager not initialized"
        )

    session = await get_or_create_session(client_id)
    if not session:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, f"Failed to get session for client {client_id}"
        )

    if not uuid:
        return create_error_response(ERROR_INVALID_PARAMETER, "UUID parameter is required")

    try:
        result = await session.control_text_input(uuid, text)

        if result["success"]:
            return create_success_response(
                {
                    "device": uuid,
                    "device_name": result.get("device_name", "Unknown"),
                    "text": result.get("text"),
                }
            )
        else:
            return create_error_response(
                result.get("error_code", ERROR_COMMAND_FAILED),
                result.get("error", "Text input command failed"),
            )
    except Exception as e:
        logger.error(f"Error setting text input {uuid}: {e}")
        return create_error_response(ERROR_COMMAND_FAILED, str(e))


@mcp.tool()
async def loxone_set_number_input(
    client_id: str = "default", uuid: str = "", value: float = 0.0
) -> dict[str, Any]:
    """
    Set number input value (slider).

    Args:
        client_id: Unique identifier for the client
        uuid: The UUID of the number input device
        value: Numeric value to set

    Returns:
        Standardized response with success status and value information
    """
    logger.info(f"Setting number input {uuid} to {value} for client {client_id}")

    if connection_manager is None:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, "Connection manager not initialized"
        )

    session = await get_or_create_session(client_id)
    if not session:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, f"Failed to get session for client {client_id}"
        )

    if not uuid:
        return create_error_response(ERROR_INVALID_PARAMETER, "UUID parameter is required")

    try:
        result = await session.control_number_input(uuid, value)

        if result["success"]:
            return create_success_response(
                {
                    "device": uuid,
                    "device_name": result.get("device_name", "Unknown"),
                    "value": result.get("value"),
                }
            )
        else:
            return create_error_response(
                result.get("error_code", ERROR_COMMAND_FAILED),
                result.get("error", "Number input command failed"),
            )
    except Exception as e:
        logger.error(f"Error setting number input {uuid}: {e}")
        return create_error_response(ERROR_COMMAND_FAILED, str(e))


# ============================================================================
# Room Management Tools
# ============================================================================


@mcp.tool()
def loxone_list_rooms(client_id: str = "default") -> dict[str, Any]:
    """
    List all rooms with device counts.

    Args:
        client_id: Unique identifier for the client

    Returns:
        Standardized response with list of rooms and their device information
    """
    logger.info(f"Listing rooms for client {client_id}")

    session, device_mgr = get_session_or_fallback(client_id)

    if not session and not device_mgr:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, "Neither session nor global instances available"
        )

    active_device_manager = session.device_manager if session else device_mgr

    try:
        rooms = active_device_manager.list_rooms()

        return create_success_response({"rooms": rooms, "count": len(rooms)})
    except Exception as e:
        logger.error(f"Error listing rooms: {e}")
        return create_error_response(ERROR_COMMAND_FAILED, str(e))


@mcp.tool()
def loxone_get_room_devices(client_id: str = "default", room: str = "") -> dict[str, Any]:
    """
    Get all devices in a specific room with their current states.

    Args:
        client_id: Unique identifier for the client
        room: The room name to filter by

    Returns:
        Standardized response with devices in the room
    """
    logger.info(f"Getting devices in room '{room}' for client {client_id}")

    session, device_mgr = get_session_or_fallback(client_id)

    if not session and not device_mgr:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, "Neither session nor global instances available"
        )

    if not room:
        return create_error_response(ERROR_INVALID_PARAMETER, "Room parameter is required")

    active_device_manager = session.device_manager if session else device_mgr

    try:
        devices = active_device_manager.get_room_devices(room)

        return create_success_response({"room": room, "devices": devices, "count": len(devices)})
    except Exception as e:
        logger.error(f"Error getting room devices: {e}")
        return create_error_response(ERROR_COMMAND_FAILED, str(e))


@mcp.tool()
async def loxone_control_room(
    client_id: str = "default", room: str = "", action: str = ""
) -> dict[str, Any]:
    """
    Control all compatible devices in a room.

    Args:
        client_id: Unique identifier for the client
        room: The room name
        action: The action to perform (lights_off, lights_on, all_off, covers_open, covers_close)

    Returns:
        Standardized response with results of the room control operation
    """
    logger.info(f"Controlling room '{room}' with action '{action}' for client {client_id}")

    session, device_mgr = get_session_or_fallback(client_id)

    if not session and not device_mgr:
        return create_error_response(
            ERROR_INITIALIZATION_FAILED, "Neither session nor global instances available"
        )

    if not room or not action:
        return create_error_response(
            ERROR_INVALID_PARAMETER, "Room and action parameters are required"
        )

    active_device_manager = session.device_manager if session else device_mgr

    try:
        result = await active_device_manager.control_room(room, action)

        if result["success"]:
            return create_success_response(result)
        else:
            return create_error_response(
                ERROR_COMMAND_FAILED, result.get("error", "Room control failed"), details=result
            )
    except Exception as e:
        logger.error(f"Error controlling room: {e}")
        return create_error_response(ERROR_COMMAND_FAILED, str(e))


def main():
    """
    Main entry point for the Loxone MCP server.

    This function starts a stateless MCP server that does not require environment credentials.
    Each MCP client provides credentials when calling tools, and sessions are created dynamically.

    Environment variables:
    - MCP_TRANSPORT: Set to 'http' to enable HTTP transport (default: 'stdio')
    - MCP_HOST: Host to bind to for HTTP transport (default: '127.0.0.1')
    - MCP_PORT: Port to bind to for HTTP transport (default: 8000)
    """
    import os

    # Get transport configuration from environment
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8000"))

    logger.info("Starting Loxone MCP Server (stateless mode)...")
    logger.info(
        "Server does not require environment credentials - clients provide credentials via tool parameters"
    )

    if transport == "http":
        logger.info(f"Server will use HTTP transport on {host}:{port}")
        logger.info(f"MCP endpoint will be available at: http://{host}:{port}/mcp")
    else:
        logger.info("Server will use stdio transport for MCP client communication")

    try:
        if transport == "http":
            # Run with HTTP transport for web-based clients
            logger.debug(f"Initializing FastMCP server with HTTP transport on {host}:{port}")
            mcp.run(transport="http", host=host, port=port)
        else:
            # Run with stdio transport (default) for MCP clients like Claude Desktop
            logger.debug("Initializing FastMCP server with stdio transport")
            mcp.run()

    except KeyboardInterrupt:
        logger.info("Server stopped by user (Ctrl+C)")

    except ImportError as e:
        logger.error(f"Missing required dependency: {e}")
        logger.error("Please ensure all dependencies are installed: uv pip install -e .")
        raise

    except PermissionError as e:
        logger.error(f"Permission error starting server: {e}")
        logger.error("Check file permissions and user privileges")
        raise

    except OSError as e:
        logger.error(f"Operating system error: {e}")
        logger.error("This may indicate network or file system issues")
        raise

    except Exception as e:
        logger.error(f"Unexpected server error: {e}", exc_info=True)
        logger.error("Server failed to start - check configuration and dependencies")
        raise

    finally:
        logger.info("Loxone MCP Server main function completed")


def main_http():
    """
    Convenience function to start the server in HTTP mode.

    This is useful for creating separate entry points or when you want to
    explicitly start the server in HTTP mode without environment variables.
    """
    import os

    # Force HTTP transport
    os.environ["MCP_TRANSPORT"] = "http"

    # Use provided host/port or defaults
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8000"))

    logger.info(f"Starting Loxone MCP Server in HTTP mode on {host}:{port}")

    try:
        mcp.run(transport="http", host=host, port=port)
    except Exception as e:
        logger.error(f"Failed to start HTTP server: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()

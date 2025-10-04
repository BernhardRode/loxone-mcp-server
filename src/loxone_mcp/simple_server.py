#!/usr/bin/env python3
"""
Loxone MCP Server

FastMCP server for Loxone Miniserver integration.
Uses environment variables for configuration by default.

Environment Variables:
    LOXONE_HOST - Miniserver hostname or IP address
    LOXONE_USERNAME - Username for authentication
    LOXONE_PASSWORD - Password for authentication
    LOXONE_PORT - Port (optional, default: 80)

Usage:
    # Set environment variables or use .env file
    export LOXONE_HOST=10.0.3.5
    export LOXONE_USERNAME=Bernhard
    export LOXONE_PASSWORD=Entengasse13;

    # Run server
    uv run python src/loxone_mcp/simple_server.py
"""

import logging
import os
from pathlib import Path
from typing import Any

# Try to load .env file if it exists
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logging.info(f"Loaded environment from {env_path}")
except ImportError:
    # dotenv not available, try to load manually
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key] = value
        logging.info(f"Manually loaded environment from {env_path}")

from fastmcp import FastMCP

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastMCP server
mcp = FastMCP("loxone-mcp-server")


@mcp.tool()
async def loxone_list_devices(
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
    device_type: str | None = None,
    room: str | None = None,
) -> dict[str, Any]:
    """
    List all Loxone devices with optional filtering.

    Args:
        host: Loxone Miniserver host/IP address (uses LOXONE_HOST env var if not provided)
        username: Loxone username (uses LOXONE_USERNAME env var if not provided)
        password: Loxone password (uses LOXONE_PASSWORD env var if not provided)
        port: Loxone port (uses LOXONE_PORT env var or default: 80)
        client_id: Unique identifier for the client (default: "default")
        device_type: Filter by device type (e.g., "Switch", "Dimmer", "Jalousie")
        room: Filter by room name

    Returns:
        Standardized response with list of devices and their basic information
    """

    try:
        # Import here to avoid import issues when running as script
        import sys
        from pathlib import Path

        # Add the parent directory to path for imports
        parent_dir = Path(__file__).parent
        if str(parent_dir) not in sys.path:
            sys.path.insert(0, str(parent_dir))

        from .config import LoxoneConfig
        from .loxone_client import LoxoneClient
        from .device_manager import DeviceManager

        # Use environment variables as primary source, parameters as override
        try:
            if not all([host, username, password]):
                # Load from environment
                env_config = LoxoneConfig.from_env()
                host = host or env_config.host
                username = username or env_config.username
                password = password or env_config.password
                port = port if port != 80 else env_config.port
        except ValueError as e:
            return {
                "success": False,
                "error": f"Configuration error: {e}",
                "error_code": "MISSING_PARAMETERS",
            }

        logger.info(f"Listing devices for client {client_id} connecting to {host}:{port}")

        # Create configuration
        config = LoxoneConfig(host=host, username=username, password=password, port=port)

        # Create and connect client
        client = LoxoneClient(config)

        logger.info(f"Connecting to Loxone Miniserver at {host}:{port}...")
        connected = await client.connect()

        if not connected:
            return {
                "success": False,
                "error": f"Failed to connect to Loxone Miniserver at {host}:{port}",
                "error_code": "CONNECTION_FAILED",
            }

        try:
            # Get structure data
            logger.info("Fetching device structure...")
            structure = await client.get_structure()

            # Create device manager and load structure
            device_manager = DeviceManager()
            device_manager.load_devices(structure)

            # Get devices with filtering
            devices = device_manager.list_devices(device_type=device_type, room=room)

            # Format device information
            device_list = []
            for device in devices:
                device_info = {
                    "uuid": device.uuid,
                    "name": device.name,
                    "type": device.type,
                    "room": device.room,
                    "category": device.category,
                }
                device_list.append(device_info)

            logger.info(f"Successfully listed {len(device_list)} devices")

            return {
                "success": True,
                "devices": device_list,
                "count": len(device_list),
                "filters_applied": {"device_type": device_type, "room": room},
            }

        finally:
            # Always disconnect
            await client.disconnect()

    except Exception as e:
        logger.error(f"Error listing devices: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "error_code": "COMMAND_FAILED",
        }


@mcp.tool()
async def loxone_get_device_state(
    uuid: str,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """
    Get comprehensive state information for a specific Loxone device.

    Returns detailed device state including all available parameters, capabilities,
    metadata, and device-type specific state structures. This enhanced version
    provides complete state information with parameter descriptions, units, and
    validation rules.

    Args:
        uuid: The UUID of the device
        host: Loxone Miniserver host/IP address (uses LOXONE_HOST env var if not provided)
        username: Loxone username (uses LOXONE_USERNAME env var if not provided)
        password: Loxone password (uses LOXONE_PASSWORD env var if not provided)
        port: Loxone port (uses LOXONE_PORT env var or default: 80)
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

    if not uuid or not isinstance(uuid, str):
        return {
            "success": False,
            "error": "UUID parameter is required and must be a string",
            "error_code": "INVALID_PARAMETER",
        }

    try:
        # Import here to avoid import issues when running as script
        import sys
        from pathlib import Path

        # Add the parent directory to path for imports
        parent_dir = Path(__file__).parent
        if str(parent_dir) not in sys.path:
            sys.path.insert(0, str(parent_dir))

        from .config import LoxoneConfig
        from .loxone_client import LoxoneClient
        from .device_manager import DeviceManager

        # Use environment variables as primary source, parameters as override
        try:
            if not all([host, username, password]):
                # Load from environment
                env_config = LoxoneConfig.from_env()
                host = host or env_config.host
                username = username or env_config.username
                password = password or env_config.password
                port = port if port != 80 else env_config.port
        except ValueError as e:
            return {
                "success": False,
                "error": f"Configuration error: {e}",
                "error_code": "MISSING_PARAMETERS",
            }

        logger.info(f"Getting device state for {uuid} on {host}:{port}")

        # Create configuration
        config = LoxoneConfig(host=host, username=username, password=password, port=port)

        # Create and connect client
        client = LoxoneClient(config)

        logger.info(f"Connecting to Loxone Miniserver at {host}:{port}...")
        connected = await client.connect()

        if not connected:
            return {
                "success": False,
                "error": f"Failed to connect to Loxone Miniserver at {host}:{port}",
                "error_code": "CONNECTION_FAILED",
            }

        try:
            # Get structure data
            structure = await client.get_structure()

            # Create device manager and load structure
            device_manager = DeviceManager()
            device_manager.load_devices(structure)

            # Get specific device
            device = device_manager.get_device(uuid.strip())
            if not device:
                return {
                    "success": False,
                    "error": f"Device not found with UUID: {uuid}",
                    "error_code": "DEVICE_NOT_FOUND",
                }

            # Use enhanced device state information
            enhanced_state = device_manager.get_enhanced_device_state(uuid.strip())

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
            else:
                # Use enhanced state information
                device_state = enhanced_state

            logger.info(
                f"Successfully retrieved enhanced state for device '{device.name}' ({device.type})"
            )
            logger.debug(f"Enhanced state includes: {list(device_state.get('state', {}).keys())}")

            return {"success": True, **device_state}

        finally:
            # Always disconnect
            await client.disconnect()

    except Exception as e:
        logger.error(f"Error getting device state: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "error_code": "COMMAND_FAILED",
        }


@mcp.tool()
async def loxone_test_connection(
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
) -> dict[str, Any]:
    """
    Test connection to Loxone Miniserver.

    Args:
        host: Loxone Miniserver host/IP address (uses LOXONE_HOST env var if not provided)
        username: Loxone username (uses LOXONE_USERNAME env var if not provided)
        password: Loxone password (uses LOXONE_PASSWORD env var if not provided)
        port: Loxone port (uses LOXONE_PORT env var or default: 80)

    Returns:
        Connection test result
    """

    try:
        # Import here to avoid import issues when running as script
        import sys
        from pathlib import Path

        # Add the parent directory to path for imports
        parent_dir = Path(__file__).parent
        if str(parent_dir) not in sys.path:
            sys.path.insert(0, str(parent_dir))

        from .config import LoxoneConfig
        from .loxone_client import LoxoneClient

        # Use environment variables as primary source, parameters as override
        try:
            if not all([host, username, password]):
                # Load from environment
                env_config = LoxoneConfig.from_env()
                host = host or env_config.host
                username = username or env_config.username
                password = password or env_config.password
                port = port if port != 80 else env_config.port
        except ValueError as e:
            return {
                "success": False,
                "error": f"Configuration error: {e}",
                "error_code": "MISSING_PARAMETERS",
            }

        logger.info(f"Testing connection to {host}:{port}")

        # Create configuration
        config = LoxoneConfig(host=host, username=username, password=password, port=port)

        # Create and test client connection
        client = LoxoneClient(config)

        logger.info(f"Connecting to Loxone Miniserver at {host}:{port}...")
        connected = await client.connect()

        if not connected:
            return {
                "success": False,
                "error": f"Failed to connect to Loxone Miniserver at {host}:{port}",
                "error_code": "CONNECTION_FAILED",
                "host": host,
                "port": port,
            }

        try:
            # Test basic functionality
            logger.info("Testing structure retrieval...")
            structure = await client.get_structure()

            structure_info = {
                "rooms": len(structure.get("rooms", {})),
                "controls": len(structure.get("controls", {})),
                "categories": len(structure.get("categories", {})),
            }

            logger.info(f"Connection test successful: {structure_info}")

            return {
                "success": True,
                "message": "Connection successful",
                "host": host,
                "port": port,
                "structure_info": structure_info,
            }

        finally:
            # Always disconnect
            await client.disconnect()

    except Exception as e:
        logger.error(f"Connection test failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Connection test failed: {str(e)}",
            "error_code": "TEST_FAILED",
        }


def main():
    """Main entry point for the MCP server."""
    logger.info("Starting Loxone MCP Server...")
    logger.info(
        "Available tools: loxone_list_devices, loxone_get_device_state, loxone_test_connection"
    )
    mcp.run()


if __name__ == "__main__":
    main()

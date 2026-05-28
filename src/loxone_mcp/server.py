#!/usr/bin/env python3
"""Loxone MCP Server - all tools, stateless (credentials per call)."""

import logging
import os
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from .config import LoxoneConfig
from .client_session import ClientSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP("loxone-mcp-server")


async def _session(host, username, password, port=80) -> ClientSession:
    """Create, initialize and return a ClientSession. Caller must call cleanup()."""
    config = LoxoneConfig(host=host, username=username, password=password, port=port)
    session = ClientSession("mcp", config)
    await session.initialize()
    return session


def _creds(host, username, password, port):
    """Resolve credentials: tool args → env vars → XDG config file."""
    h = host or os.getenv("LOXONE_HOST")
    u = username or os.getenv("LOXONE_USERNAME")
    p = password or os.getenv("LOXONE_PASSWORD")
    po = port if port != 80 else int(os.getenv("LOXONE_PORT", "80"))
    if not all([h, u, p]):
        xdg = LoxoneConfig.from_xdg()
        if xdg:
            h = h or xdg.host
            u = u or xdg.username
            p = p or xdg.password
            po = po if po != 80 else xdg.port
    if not all([h, u, p]):
        raise ValueError(
            "host, username and password are required "
            "(via args, LOXONE_HOST/USERNAME/PASSWORD env vars, "
            f"or {LoxoneConfig.xdg_config_path()})"
        )
    return h, u, p, po


# ── Query tools ──────────────────────────────────────────────────────────────

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
    """List all Loxone devices with optional filtering.

    Args:
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
        device_type: Filter by device type (e.g. "Switch", "Dimmer", "Jalousie")
        room: Filter by room name
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        devices = session.device_manager.list_devices(device_type=device_type, room=room)
        return {
            "success": True,
            "devices": [
                {"uuid": d.uuid, "name": d.name, "type": d.type, "room": d.room, "category": d.category}
                for d in devices
            ],
            "count": len(devices),
            "filters_applied": {"device_type": device_type, "room": room},
        }
    finally:
        await session.cleanup()


@mcp.tool()
async def loxone_get_device_state(
    uuid: str,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Get comprehensive state information for a specific Loxone device.

    Args:
        uuid: The UUID of the device
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        state = session.device_manager.get_enhanced_device_state(uuid.strip())
        return {"success": True, **state}
    finally:
        await session.cleanup()


@mcp.tool()
async def loxone_test_connection(
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
) -> dict[str, Any]:
    """Test connection to Loxone Miniserver.

    Args:
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        dm = session.device_manager
        return {
            "success": True,
            "message": "Connection successful",
            "host": h,
            "port": po,
            "device_count": dm.get_device_count(),
        }
    finally:
        await session.cleanup()


# ── Control tools ─────────────────────────────────────────────────────────────

@mcp.tool()
async def loxone_send_command(
    uuid: str,
    value: str,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Send a raw command to a Loxone device.

    Args:
        uuid: The UUID of the device
        value: The command value (e.g. "On", "Off", "50")
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.send_command(uuid.strip(), value)
    finally:
        await session.cleanup()


@mcp.tool()
async def loxone_send_secured_command(
    uuid: str,
    value: str,
    code: str,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Send a PIN-protected command to a Loxone device (e.g. alarm systems).

    Args:
        uuid: The UUID of the device
        value: The command value
        code: PIN code for authentication
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.send_secured_command(uuid.strip(), value, code)
    finally:
        await session.cleanup()


@mcp.tool()
async def loxone_set_switch(
    uuid: str,
    state: bool,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Turn a Loxone switch on or off.

    Args:
        uuid: The UUID of the switch device
        state: True for on, False for off
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.control_switch(uuid.strip(), state)
    finally:
        await session.cleanup()


@mcp.tool()
async def loxone_set_dimmer(
    uuid: str,
    brightness: int,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Set the brightness of a Loxone dimmer (0-100).

    Args:
        uuid: The UUID of the dimmer device
        brightness: Brightness level 0-100
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.control_dimmer(uuid.strip(), brightness)
    finally:
        await session.cleanup()


@mcp.tool()
async def loxone_set_cover_position(
    uuid: str,
    position: int,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Set the position of a Loxone cover/blind (0=closed, 100=open).

    Args:
        uuid: The UUID of the cover device
        position: Position 0-100 (0=closed, 100=open)
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.control_cover_position(uuid.strip(), position)
    finally:
        await session.cleanup()


@mcp.tool()
async def loxone_set_temperature(
    uuid: str,
    temperature: float,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Set the target temperature for a Loxone climate control device.

    Args:
        uuid: The UUID of the climate control device
        temperature: Target temperature in Celsius
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.control_temperature(uuid.strip(), temperature)
    finally:
        await session.cleanup()


# ── Scene tools ───────────────────────────────────────────────────────────────

@mcp.tool()
async def loxone_list_scenes(
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """List all available Loxone scenes.

    Args:
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        scenes = session.device_manager.list_devices(device_type="Scene")
        return {
            "success": True,
            "scenes": [{"uuid": d.uuid, "name": d.name, "room": d.room} for d in scenes],
            "count": len(scenes),
        }
    finally:
        await session.cleanup()


@mcp.tool()
async def loxone_trigger_scene(
    uuid: str,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Activate a Loxone scene.

    Args:
        uuid: The UUID of the scene
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.trigger_scene(uuid.strip())
    finally:
        await session.cleanup()


# ── Cover open/close ──────────────────────────────────────────────────────────

@mcp.tool()
async def loxone_cover_open(
    uuid: str,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Fully open a Loxone cover/blind.

    Args:
        uuid: The UUID of the cover device
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.control_cover_open(uuid.strip())
    finally:
        await session.cleanup()


@mcp.tool()
async def loxone_cover_close(
    uuid: str,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Fully close a Loxone cover/blind.

    Args:
        uuid: The UUID of the cover device
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.control_cover_close(uuid.strip())
    finally:
        await session.cleanup()


# ── Climate & fan ─────────────────────────────────────────────────────────────

@mcp.tool()
async def loxone_set_climate_mode(
    uuid: str,
    mode: str,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Set the operating mode of a Loxone climate control device.

    Args:
        uuid: The UUID of the climate device
        mode: Operating mode (e.g. "auto", "heating", "cooling")
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.control_climate_mode(uuid.strip(), mode)
    finally:
        await session.cleanup()


@mcp.tool()
async def loxone_set_fan_speed(
    uuid: str,
    speed: int,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Set the fan speed of a Loxone ventilation device (0-100).

    Args:
        uuid: The UUID of the fan device
        speed: Fan speed 0-100
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.control_fan_speed(uuid.strip(), speed)
    finally:
        await session.cleanup()


# ── Light color ───────────────────────────────────────────────────────────────

@mcp.tool()
async def loxone_set_light_color(
    uuid: str,
    color: str,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Set the color of a Loxone RGB light.

    Args:
        uuid: The UUID of the light device
        color: Color value (e.g. hex "#FF0000" or "red")
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.control_light_color(uuid.strip(), color)
    finally:
        await session.cleanup()


# ── Media ─────────────────────────────────────────────────────────────────────

@mcp.tool()
async def loxone_media_play(
    uuid: str,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Start playback on a Loxone media device.

    Args:
        uuid: The UUID of the media device
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.control_media_play(uuid.strip())
    finally:
        await session.cleanup()


@mcp.tool()
async def loxone_media_pause(
    uuid: str,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Pause playback on a Loxone media device.

    Args:
        uuid: The UUID of the media device
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.control_media_pause(uuid.strip())
    finally:
        await session.cleanup()


@mcp.tool()
async def loxone_set_volume(
    uuid: str,
    volume: int,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Set the volume of a Loxone media device (0-100).

    Args:
        uuid: The UUID of the media device
        volume: Volume level 0-100
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.control_volume(uuid.strip(), volume)
    finally:
        await session.cleanup()


# ── Alarm ─────────────────────────────────────────────────────────────────────

@mcp.tool()
async def loxone_arm_alarm(
    uuid: str,
    code: str,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Arm a Loxone alarm system (requires PIN).

    Args:
        uuid: The UUID of the alarm device
        code: PIN code for authentication
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.control_alarm_arm(uuid.strip(), code)
    finally:
        await session.cleanup()


@mcp.tool()
async def loxone_disarm_alarm(
    uuid: str,
    code: str,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Disarm a Loxone alarm system (requires PIN).

    Args:
        uuid: The UUID of the alarm device
        code: PIN code for authentication
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.control_alarm_disarm(uuid.strip(), code)
    finally:
        await session.cleanup()


# ── Input controls ────────────────────────────────────────────────────────────

@mcp.tool()
async def loxone_set_text_input(
    uuid: str,
    text: str,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Set the value of a Loxone text input.

    Args:
        uuid: The UUID of the text input device
        text: Text value to set
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.control_text_input(uuid.strip(), text)
    finally:
        await session.cleanup()


@mcp.tool()
async def loxone_set_number_input(
    uuid: str,
    value: float,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int = 80,
    client_id: str = "default",
) -> dict[str, Any]:
    """Set the value of a Loxone numeric input.

    Args:
        uuid: The UUID of the numeric input device
        value: Numeric value to set
        host: Miniserver host/IP (uses LOXONE_HOST env var if omitted)
        username: Loxone username (uses LOXONE_USERNAME env var if omitted)
        password: Loxone password (uses LOXONE_PASSWORD env var if omitted)
        port: Loxone port (default: 80)
        client_id: Unique identifier for the client (default: "default")
    """
    try:
        h, u, p, po = _creds(host, username, password, port)
    except ValueError as e:
        return {"success": False, "error": str(e), "error_code": "MISSING_PARAMETERS"}

    session = await _session(h, u, p, po)
    try:
        return await session.control_number_input(uuid.strip(), value)
    finally:
        await session.cleanup()


# ── Auto-Discovery: generate per-room tools at startup ────────────────────────

import asyncio
import re
from fastmcp.tools import Tool


def _slugify(name: str) -> str:
    """Convert room name to valid Python identifier: 'Bad 2' -> 'bad_2'."""
    s = name.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def _register_room_tools():
    """Connect to Miniserver, discover rooms, and register per-room tools."""
    h = os.getenv("LOXONE_HOST")
    u = os.getenv("LOXONE_USERNAME")
    p = os.getenv("LOXONE_PASSWORD")
    po = int(os.getenv("LOXONE_PORT", "80"))

    if not all([h, u, p]):
        xdg = LoxoneConfig.from_xdg()
        if xdg:
            h = h or xdg.host
            u = u or xdg.username
            p = p or xdg.password
            po = po if po != 80 else xdg.port

    if not all([h, u, p]):
        logger.warning("No Loxone credentials found (env vars or XDG config) – skipping auto-discovery")
        return

    async def _discover():
        config = LoxoneConfig(host=h, username=u, password=p, port=po)
        session = ClientSession("discovery", config)
        await session.initialize()
        try:
            devices = session.device_manager.list_devices()
            # Group by room
            rooms_lights: dict[str, list] = {}
            rooms_blinds: dict[str, list] = {}
            for d in devices:
                if d.type == "LightControllerV2":
                    rooms_lights.setdefault(d.room, []).append(d.uuid)
                elif d.type == "Jalousie":
                    rooms_blinds.setdefault(d.room, []).append(d.uuid)
            return rooms_lights, rooms_blinds
        finally:
            await session.cleanup()

    try:
        rooms_lights, rooms_blinds = asyncio.run(_discover())
    except Exception as e:
        logger.error(f"Auto-discovery failed: {e}")
        return

    def _make_light_fn(room_name: str, uuids: list[str], on: bool):
        async def fn(
            host: str | None = None,
            username: str | None = None,
            password: str | None = None,
            port: int = 80,
        ) -> dict[str, Any]:
            _h, _u, _p, _po = _creds(host, username, password, port)
            s = await _session(_h, _u, _p, _po)
            try:
                results = []
                for uid in uuids:
                    r = await s.send_command(uid, "On" if on else "Off")
                    results.append(r.get("success", False))
                return {"success": all(results), "room": room_name, "lights": len(uuids), "state": "on" if on else "off"}
            finally:
                await s.cleanup()
        return fn

    def _make_blinds_fn(room_name: str, uuids: list[str], up: bool):
        async def fn(
            host: str | None = None,
            username: str | None = None,
            password: str | None = None,
            port: int = 80,
        ) -> dict[str, Any]:
            _h, _u, _p, _po = _creds(host, username, password, port)
            s = await _session(_h, _u, _p, _po)
            try:
                results = []
                for uid in uuids:
                    r = await s.send_command(uid, "FullUp" if up else "FullDown")
                    results.append(r.get("success", False))
                return {"success": all(results), "room": room_name, "blinds": len(uuids), "state": "up" if up else "down"}
            finally:
                await s.cleanup()
        return fn

    count = 0
    for room, uuids in rooms_lights.items():
        slug = _slugify(room)
        for on, suffix in [(True, "on"), (False, "off")]:
            name = f"{slug}_light_{suffix}"
            fn = _make_light_fn(room, uuids, on)
            fn.__doc__ = f"Turn {'on' if on else 'off'} all lights in {room} ({len(uuids)} device{'s' if len(uuids)>1 else ''})."
            mcp.add_tool(Tool.from_function(fn, name=name))
            count += 1

    for room, uuids in rooms_blinds.items():
        slug = _slugify(room)
        for up, suffix in [(True, "up"), (False, "down")]:
            name = f"{slug}_blinds_{suffix}"
            fn = _make_blinds_fn(room, uuids, up)
            fn.__doc__ = f"Move all blinds in {room} {'up (open)' if up else 'down (close)'} ({len(uuids)} device{'s' if len(uuids)>1 else ''})."
            mcp.add_tool(Tool.from_function(fn, name=name))
            count += 1

    logger.info(f"Auto-discovery: registered {count} room tools")


# Run auto-discovery on module load
_register_room_tools()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    """Main entry point for the MCP server."""
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport == "http":
        host = os.getenv("MCP_HOST", "127.0.0.1")
        port = int(os.getenv("MCP_PORT", "8000"))
        logger.info(f"Starting HTTP transport on http://{host}:{port}/mcp")
        mcp.run(transport="http", host=host, port=port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()

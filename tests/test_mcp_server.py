"""
Test the Loxone MCP server functionality.

Following TDD practices with pytest and async testing.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from fastmcp import Client
from pathlib import Path


@pytest.fixture
def server_script():
    """Path to the MCP server script."""
    return Path("src/loxone_mcp/simple_server.py")


@pytest.fixture
def mock_credentials():
    """Mock Loxone credentials for testing."""
    return {
        "host": "192.168.1.100",
        "username": "admin",
        "password": "test-password",
        "port": 80
    }


@pytest.mark.asyncio
async def test_mcp_server_tools_available(server_script):
    """Test that MCP server exposes the expected tools."""
    async with Client(str(server_script)) as client:
        tools = await client.list_tools()
        
        expected_tools = {
            "loxone_list_devices",
            "loxone_get_device_state", 
            "loxone_test_connection"
        }
        
        available_tools = {tool.name for tool in tools}
        assert expected_tools.issubset(available_tools)


@pytest.mark.asyncio
async def test_test_connection_missing_params(server_script):
    """Test connection test with missing parameters."""
    async with Client(str(server_script)) as client:
        result = await client.call_tool("loxone_test_connection", {})
        
        assert not result.data["success"]
        assert "MISSING_PARAMETERS" in result.data["error_code"]


@pytest.mark.asyncio
async def test_list_devices_missing_params(server_script):
    """Test device listing with missing parameters."""
    async with Client(str(server_script)) as client:
        result = await client.call_tool("loxone_list_devices", {})
        
        assert not result.data["success"]
        assert "MISSING_PARAMETERS" in result.data["error_code"]


@pytest.mark.asyncio
async def test_get_device_state_invalid_uuid(server_script, mock_credentials):
    """Test getting device state with invalid UUID."""
    async with Client(str(server_script)) as client:
        result = await client.call_tool("loxone_get_device_state", {
            **mock_credentials,
            "uuid": ""
        })
        
        assert not result.data["success"]
        assert "INVALID_PARAMETER" in result.data["error_code"]


@pytest.mark.asyncio
@patch('loxone_mcp.loxone_client.LoxoneClient.connect')
async def test_connection_failure_handling(mock_connect, server_script, mock_credentials):
    """Test handling of connection failures."""
    # Mock connection failure
    mock_connect.return_value = False
    
    async with Client(str(server_script)) as client:
        result = await client.call_tool("loxone_test_connection", mock_credentials)
        
        assert not result.data["success"]
        assert "CONNECTION_FAILED" in result.data["error_code"]


@pytest.mark.asyncio
async def test_successful_connection_mock(server_script, mock_credentials):
    """Test successful connection and structure retrieval with mocking."""
    with patch('src.loxone_mcp.simple_server.LoxoneClient') as mock_client_class:
        # Setup mock client instance
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        mock_client.connect.return_value = True
        mock_client.get_structure.return_value = {
            "rooms": {"room1": {}, "room2": {}},
            "controls": {"ctrl1": {}, "ctrl2": {}, "ctrl3": {}},
            "categories": {"cat1": {}}
        }
        mock_client.disconnect.return_value = None
        
        async with Client(str(server_script)) as client:
            result = await client.call_tool("loxone_test_connection", mock_credentials)
            
            assert result.data["success"]
            assert result.data["host"] == mock_credentials["host"]
            assert result.data["port"] == mock_credentials["port"]
            
            structure_info = result.data["structure_info"]
            assert structure_info["rooms"] == 2
            assert structure_info["controls"] == 3
            assert structure_info["categories"] == 1


@pytest.mark.asyncio
@patch('loxone_mcp.loxone_client.LoxoneClient.connect')
@patch('loxone_mcp.device_manager.DeviceManager.list_devices')
@patch('loxone_mcp.loxone_client.LoxoneClient.get_structure')
@patch('loxone_mcp.loxone_client.LoxoneClient.disconnect')
async def test_list_devices_success(mock_disconnect, mock_get_structure, 
                                   mock_list_devices, mock_connect,
                                   server_script, mock_credentials):
    """Test successful device listing."""
    # Mock successful connection and device listing
    mock_connect.return_value = True
    mock_get_structure.return_value = {}
    mock_disconnect.return_value = None
    
    # Mock device objects
    mock_device1 = AsyncMock()
    mock_device1.uuid = "device-1"
    mock_device1.name = "Living Room Light"
    mock_device1.type = "Switch"
    mock_device1.room = "Living Room"
    mock_device1.category = "Lighting"
    
    mock_device2 = AsyncMock()
    mock_device2.uuid = "device-2"
    mock_device2.name = "Kitchen Dimmer"
    mock_device2.type = "Dimmer"
    mock_device2.room = "Kitchen"
    mock_device2.category = "Lighting"
    
    mock_list_devices.return_value = [mock_device1, mock_device2]
    
    async with Client(str(server_script)) as client:
        result = await client.call_tool("loxone_list_devices", mock_credentials)
        
        assert result.data["success"]
        assert result.data["count"] == 2
        
        devices = result.data["devices"]
        assert len(devices) == 2
        assert devices[0]["name"] == "Living Room Light"
        assert devices[1]["name"] == "Kitchen Dimmer"


@pytest.mark.asyncio
async def test_parameter_validation():
    """Test that tool parameters are properly validated."""
    # This test ensures our tools validate input parameters correctly
    # without needing to actually connect to a Loxone server
    
    from loxone_mcp.config import LoxoneConfig
    
    # Test missing required environment variables
    with pytest.raises(ValueError, match="Missing required environment variables"):
        LoxoneConfig.from_env()
    
    # Test valid configuration
    config = LoxoneConfig(
        host="192.168.1.100",
        username="admin",
        password="password",
        port=80
    )
    
    assert config.host == "192.168.1.100"
    assert config.username == "admin"
    assert config.password == "password"
    assert config.port == 80
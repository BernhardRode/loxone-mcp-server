"""
Tests for command sending functionality.

Following TDD principles with async/await and pytest-asyncio.
Tests cover send_command, send_secured_command, and error handling.
"""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch

from src.loxone_mcp.loxone_client import (
    LoxoneClient,
    ConnectionState,
)
from src.loxone_mcp.config import LoxoneConfig


@pytest.fixture
def mock_config():
    """Create a mock LoxoneConfig for testing."""
    config = Mock(spec=LoxoneConfig)
    config.host = "192.168.1.100"
    config.port = 80
    config.username = "admin"
    config.password = "password"
    config.token_persist_path = "./test_token.json"
    config.load_token = Mock(return_value=None)
    config.save_token = Mock()
    return config


@pytest.fixture
def loxone_client(mock_config):
    """Create a LoxoneClient instance for testing."""
    return LoxoneClient(mock_config)


@pytest.fixture
def connected_client(loxone_client):
    """Create a connected LoxoneClient for testing."""
    loxone_client.state = ConnectionState.CONNECTED
    loxone_client._ws = AsyncMock()
    loxone_client._encryption_ready = True
    return loxone_client


class TestSendCommand:
    """Test send_command functionality."""
    
    @pytest.mark.asyncio
    async def test_send_command_success(self, connected_client):
        """Test successful command sending."""
        device_uuid = "12345678-1234-5678-1234-567812345678"
        value = "On"
        
        result = await connected_client.send_command(device_uuid, value)
        
        assert result is True
        connected_client._ws.send.assert_called_once()
        
        # Verify command was sent (may be encrypted)
        call_args = connected_client._ws.send.call_args[0][0]
        assert isinstance(call_args, str)
        assert len(call_args) > 0
    
    @pytest.mark.asyncio
    async def test_send_command_with_numeric_value(self, connected_client):
        """Test sending command with numeric value."""
        device_uuid = "12345678-1234-5678-1234-567812345678"
        value = "75"  # Dimmer value
        
        result = await connected_client.send_command(device_uuid, value)
        
        assert result is True
        connected_client._ws.send.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_command_when_not_connected(self, loxone_client):
        """Test sending command when not connected."""
        loxone_client.state = ConnectionState.DISCONNECTED
        
        result = await loxone_client.send_command("uuid", "On")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_command_without_websocket(self, loxone_client):
        """Test sending command without websocket connection."""
        loxone_client.state = ConnectionState.CONNECTED
        loxone_client._ws = None
        
        result = await loxone_client.send_command("uuid", "On")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_command_websocket_error(self, connected_client):
        """Test handling websocket error during command send."""
        connected_client._ws.send = AsyncMock(side_effect=Exception("Connection lost"))
        
        result = await connected_client.send_command("uuid", "On")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_command_encryption(self, connected_client):
        """Test that commands are encrypted when encryption is ready."""
        device_uuid = "12345678-1234-5678-1234-567812345678"
        value = "On"
        
        # Mock encryption
        with patch.object(connected_client, '_encrypt', new_callable=AsyncMock) as mock_encrypt:
            mock_encrypt.return_value = "encrypted_command"
            
            await connected_client.send_command(device_uuid, value)
            
            # Verify encryption was called
            mock_encrypt.assert_called_once()
            call_args = mock_encrypt.call_args[0][0]
            assert f"jdev/sps/io/{device_uuid}/{value}" == call_args


class TestSendSecuredCommand:
    """Test send_secured_command functionality."""
    
    @pytest.mark.asyncio
    async def test_send_secured_command_success(self, connected_client):
        """Test successful secured command sending."""
        device_uuid = "12345678-1234-5678-1234-567812345678"
        value = "On"
        code = "1234"
        
        # Mock visual hash retrieval
        visual_hash = {
            "key": "abcdef1234567890",
            "salt": "0987654321fedcba",
            "hash_alg": "SHA256"
        }
        
        with patch.object(connected_client, '_get_visual_hash', new_callable=AsyncMock) as mock_get_hash:
            mock_get_hash.return_value = visual_hash
            
            result = await connected_client.send_secured_command(device_uuid, value, code)
            
            assert result is True
            connected_client._ws.send.assert_called_once()
            
            # Verify command format includes hash
            call_args = connected_client._ws.send.call_args[0][0]
            assert "jdev/sps/ios" in call_args
            assert device_uuid in call_args
    
    @pytest.mark.asyncio
    async def test_send_secured_command_sha1(self, connected_client):
        """Test secured command with SHA1 hash algorithm."""
        device_uuid = "12345678-1234-5678-1234-567812345678"
        value = "On"
        code = "1234"
        
        visual_hash = {
            "key": "abcdef1234567890",
            "salt": "0987654321fedcba",
            "hash_alg": "SHA1"
        }
        
        with patch.object(connected_client, '_get_visual_hash', new_callable=AsyncMock) as mock_get_hash:
            mock_get_hash.return_value = visual_hash
            
            result = await connected_client.send_secured_command(device_uuid, value, code)
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_send_secured_command_when_not_connected(self, loxone_client):
        """Test sending secured command when not connected."""
        loxone_client.state = ConnectionState.DISCONNECTED
        
        result = await loxone_client.send_secured_command("uuid", "On", "1234")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_send_secured_command_visual_hash_failure(self, connected_client):
        """Test secured command when visual hash retrieval fails."""
        with patch.object(connected_client, '_get_visual_hash', new_callable=AsyncMock) as mock_get_hash:
            mock_get_hash.return_value = None
            
            result = await connected_client.send_secured_command("uuid", "On", "1234")
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_send_secured_command_invalid_hash_algorithm(self, connected_client):
        """Test secured command with invalid hash algorithm."""
        visual_hash = {
            "key": "abcdef1234567890",
            "salt": "0987654321fedcba",
            "hash_alg": "INVALID"
        }
        
        with patch.object(connected_client, '_get_visual_hash', new_callable=AsyncMock) as mock_get_hash:
            mock_get_hash.return_value = visual_hash
            
            result = await connected_client.send_secured_command("uuid", "On", "1234")
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_send_secured_command_websocket_error(self, connected_client):
        """Test handling websocket error during secured command send."""
        visual_hash = {
            "key": "abcdef1234567890",
            "salt": "0987654321fedcba",
            "hash_alg": "SHA256"
        }
        
        connected_client._ws.send = AsyncMock(side_effect=Exception("Connection lost"))
        
        with patch.object(connected_client, '_get_visual_hash', new_callable=AsyncMock) as mock_get_hash:
            mock_get_hash.return_value = visual_hash
            
            result = await connected_client.send_secured_command("uuid", "On", "1234")
            
            assert result is False


class TestGetVisualHash:
    """Test _get_visual_hash functionality."""
    
    @pytest.mark.asyncio
    async def test_get_visual_hash_success(self, connected_client):
        """Test successful visual hash retrieval."""
        # Mock responses
        response_json = json.dumps({
            "LL": {
                "value": {
                    "key": "abcdef1234567890",
                    "salt": "0987654321fedcba",
                    "hashAlg": "SHA256"
                }
            }
        })
        
        connected_client._ws.recv = AsyncMock(side_effect=[
            b'\x03\x00\x00\x00\x00\x00\x00\x00',  # Header
            response_json.encode()  # Response
        ])
        
        result = await connected_client._get_visual_hash()
        
        assert result is not None
        assert result["key"] == "abcdef1234567890"
        assert result["salt"] == "0987654321fedcba"
        assert result["hash_alg"] == "SHA256"
    
    @pytest.mark.asyncio
    async def test_get_visual_hash_default_algorithm(self, connected_client):
        """Test visual hash with default hash algorithm."""
        response_json = json.dumps({
            "LL": {
                "value": {
                    "key": "abcdef1234567890",
                    "salt": "0987654321fedcba"
                }
            }
        })
        
        connected_client._ws.recv = AsyncMock(side_effect=[
            b'\x03\x00\x00\x00\x00\x00\x00\x00',
            response_json.encode()
        ])
        
        result = await connected_client._get_visual_hash()
        
        assert result is not None
        assert result["hash_alg"] == "SHA1"  # Default
    
    @pytest.mark.asyncio
    async def test_get_visual_hash_missing_value(self, connected_client):
        """Test visual hash retrieval with missing value."""
        response_json = json.dumps({
            "LL": {
                "code": "200"
            }
        })
        
        connected_client._ws.recv = AsyncMock(side_effect=[
            b'\x03\x00\x00\x00\x00\x00\x00\x00',
            response_json.encode()
        ])
        
        result = await connected_client._get_visual_hash()
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_visual_hash_websocket_error(self, connected_client):
        """Test visual hash retrieval with websocket error."""
        connected_client._ws.recv = AsyncMock(side_effect=Exception("Connection lost"))
        
        result = await connected_client._get_visual_hash()
        
        assert result is None


class TestCommandIntegration:
    """Integration tests for command sending."""
    
    @pytest.mark.asyncio
    async def test_send_multiple_commands_sequentially(self, connected_client):
        """Test sending multiple commands in sequence."""
        commands = [
            ("uuid1", "On"),
            ("uuid2", "Off"),
            ("uuid3", "50")
        ]
        
        for device_uuid, value in commands:
            result = await connected_client.send_command(device_uuid, value)
            assert result is True
        
        assert connected_client._ws.send.call_count == 3
    
    @pytest.mark.asyncio
    async def test_send_command_and_secured_command(self, connected_client):
        """Test sending both regular and secured commands."""
        # Regular command
        result1 = await connected_client.send_command("uuid1", "On")
        assert result1 is True
        
        # Secured command
        visual_hash = {
            "key": "abcdef1234567890",
            "salt": "0987654321fedcba",
            "hash_alg": "SHA256"
        }
        
        with patch.object(connected_client, '_get_visual_hash', new_callable=AsyncMock) as mock_get_hash:
            mock_get_hash.return_value = visual_hash
            
            result2 = await connected_client.send_secured_command("uuid2", "On", "1234")
            assert result2 is True
        
        # Both commands should have been sent
        assert connected_client._ws.send.call_count >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

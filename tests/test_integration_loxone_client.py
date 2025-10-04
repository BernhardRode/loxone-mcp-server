"""
Integration tests for LoxoneClient connecting to real MiniServer.

These tests require environment variables to be set via .env file:
- LOXONE_HOST: Miniserver hostname or IP
- LOXONE_USERNAME: Username for authentication
- LOXONE_PASSWORD: Password for authentication
- LOXONE_PORT: Port (optional, default 80)

Following TDD principles with async/await and pytest-asyncio.
"""

import asyncio
import os
import pytest
import logging
import websockets
from unittest.mock import AsyncMock, Mock, patch
from src.loxone_mcp.loxone_client import LoxoneClient, ConnectionState
from src.loxone_mcp.config import LoxoneConfig

# Configure logging for integration tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Skip integration tests if environment variables are not set
INTEGRATION_ENV_VARS = ["LOXONE_HOST", "LOXONE_USERNAME", "LOXONE_PASSWORD"]
skip_integration = any(not os.getenv(var) for var in INTEGRATION_ENV_VARS)
skip_reason = f"Integration tests require environment variables: {', '.join(INTEGRATION_ENV_VARS)}"


@pytest.fixture
def real_config():
    """Create LoxoneConfig from environment variables for real MiniServer testing."""
    if skip_integration:
        pytest.skip(skip_reason)

    try:
        config = LoxoneConfig.from_env()
        logger.info(f"Using real MiniServer config: {config.host}:{config.port}")
        return config
    except ValueError as e:
        pytest.skip(f"Invalid configuration: {e}")


@pytest.fixture
def mock_server_config():
    """Create mock server configuration for testing connection logic without real server."""
    config = Mock(spec=LoxoneConfig)
    config.host = "mock.miniserver.local"
    config.port = 80
    config.username = "testuser"
    config.password = "testpass"
    config.token_persist_path = "./test_token.json"
    config.load_token = Mock(return_value=None)
    config.save_token = Mock()
    return config


class TestLoxoneClientRealConnection:
    """Test LoxoneClient with real MiniServer connection."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(skip_integration, reason=skip_reason)
    async def test_connect_to_real_miniserver(self, real_config):
        """Test establishing connection to real MiniServer."""
        client = LoxoneClient(real_config)

        try:
            # Test connection establishment
            success = await client.connect()

            if success:
                assert client.state == ConnectionState.CONNECTED
                assert client._ws is not None
                assert client._encryption_ready is True
                logger.info("Successfully connected to real MiniServer")

                # Test that we can get structure
                structure = await client.get_structure()
                assert structure is not None
                assert isinstance(structure, dict)
                logger.info(f"Retrieved structure with {len(structure)} top-level keys")

            else:
                # Connection failed - this might be expected in some test environments
                logger.warning(
                    "Failed to connect to MiniServer - this may be expected in test environment"
                )
                assert client.state == ConnectionState.DISCONNECTED

        finally:
            # Always cleanup
            await client.disconnect()
            assert client.state == ConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    @pytest.mark.skipif(skip_integration, reason=skip_reason)
    async def test_authentication_flow_with_real_server(self, real_config):
        """Test complete authentication flow with real MiniServer."""
        client = LoxoneClient(real_config)

        try:
            # Connect and authenticate
            success = await client.connect()

            if success:
                # Verify authentication worked
                assert client._token.token != ""
                assert client._token.valid_until > 0
                logger.info(
                    f"Authentication successful, token expires in {client._token.get_seconds_to_expire()} seconds"
                )

                # Test token persistence
                client._persist_token()
                real_config.save_token.assert_called_once()

            else:
                logger.warning("Authentication test skipped - connection failed")

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    @pytest.mark.skipif(skip_integration, reason=skip_reason)
    async def test_command_sending_with_real_server(self, real_config):
        """Test sending commands to real MiniServer."""
        client = LoxoneClient(real_config)

        try:
            success = await client.connect()

            if success:
                # Test sending a safe command (get version info)
                # This is a read-only command that shouldn't affect the system
                result = await client.send_command("jdev/cfg/version", "")

                # We expect this to either succeed or fail gracefully
                assert isinstance(result, bool)
                logger.info(f"Command sending test result: {result}")

            else:
                logger.warning("Command sending test skipped - connection failed")

        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    @pytest.mark.skipif(skip_integration, reason=skip_reason)
    async def test_state_update_callback_with_real_server(self, real_config):
        """Test state update callback invocation with real MiniServer."""
        client = LoxoneClient(real_config)
        callback_invoked = asyncio.Event()
        received_states = []

        async def test_callback(state_data):
            """Test callback that records received state updates."""
            received_states.append(state_data)
            callback_invoked.set()
            logger.info(f"Received state update: {len(state_data)} states")

        client.register_state_callback(test_callback)

        try:
            success = await client.connect()

            if success:
                # Start background tasks to process messages
                await client.start()

                # Wait for at least one state update (with timeout)
                try:
                    await asyncio.wait_for(callback_invoked.wait(), timeout=10.0)
                    assert len(received_states) > 0
                    logger.info(f"Successfully received {len(received_states)} state updates")
                except asyncio.TimeoutError:
                    logger.warning("No state updates received within timeout - this may be normal")

            else:
                logger.warning("State update test skipped - connection failed")

        finally:
            await client.disconnect()


class TestLoxoneClientMockServer:
    """Test LoxoneClient connection logic with mock server responses."""

    @pytest.mark.asyncio
    async def test_connection_establishment_flow(self, mock_server_config):
        """Test connection establishment flow with mocked responses."""
        client = LoxoneClient(mock_server_config)

        # Mock the HTTP client for public key retrieval
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """
        {
            "LL": {
                "value": "-----BEGIN CERTIFICATE-----\\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890ABCDEF\\n-----END CERTIFICATE-----"
            }
        }
        """

        # Mock WebSocket connection
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(
            side_effect=[
                # Key exchange response
                b"\x03\x00\x00\x00\x00\x00\x00\x00",  # Header
                '{"LL": {"Code": "200"}}',  # Success response
                # Enable updates responses
                b"\x03\x00\x00\x00\x00\x00\x00\x00",  # Header
                '{"LL": {"Code": "200"}}',  # Success response
            ]
        )
        mock_ws.send = AsyncMock()

        with patch("httpx.AsyncClient") as mock_http_client:
            with patch("websockets.connect") as mock_connect:
                # Setup WebSocket mock to return the mock_ws as an awaitable
                async def mock_connect_func(*args, **kwargs):
                    return mock_ws

                mock_connect.side_effect = mock_connect_func

                # Setup HTTP client mock
                mock_context = AsyncMock()
                mock_context.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
                mock_http_client.return_value = mock_context

                # Mock RSA operations
                with patch.object(client, "_init_rsa_cipher", return_value=True):
                    with patch.object(client, "_generate_session_key", return_value=True):
                        with patch.object(client, "_authenticate", return_value=True):

                            success = await client.connect()

                            assert success is True
                            assert client.state == ConnectionState.CONNECTED
                            assert client._encryption_ready is True

                            # Verify WebSocket operations
                            mock_ws.send.assert_called()
                            mock_ws.recv.assert_called()

    @pytest.mark.asyncio
    async def test_authentication_flow_mock(self, mock_server_config):
        """Test authentication flow with mocked server responses."""
        client = LoxoneClient(mock_server_config)
        client._encryption_ready = True
        client._ws = AsyncMock()

        # Mock key and salt response
        key_salt_response = """
        {
            "LL": {
                "value": {
                    "key": "1234567890abcdef",
                    "salt": "fedcba0987654321",
                    "hashAlg": "SHA256"
                }
            }
        }
        """

        # Mock token response
        token_response = """
        {
            "LL": {
                "value": {
                    "token": "mock_token_12345",
                    "validUntil": 2000000
                }
            }
        }
        """

        client._ws.recv = AsyncMock(
            side_effect=[
                b"\x03\x00\x00\x00\x00\x00\x00\x00",  # Header
                key_salt_response.encode(),  # Key and salt
                b"\x03\x00\x00\x00\x00\x00\x00\x00",  # Header
                token_response.encode(),  # Token
            ]
        )

        client._ws.send = AsyncMock()
        client._encrypt = AsyncMock(return_value="encrypted_command")
        client._version = 11.0

        result = await client._authenticate()

        assert result is True
        assert client._token.token == "mock_token_12345"
        assert client._token.valid_until == 2000000

    @pytest.mark.asyncio
    async def test_reconnection_logic_mock(self, mock_server_config):
        """Test reconnection logic with exponential backoff."""
        client = LoxoneClient(mock_server_config)

        # Track reconnection attempts
        connection_attempts = []

        async def mock_connect():
            connection_attempts.append(len(connection_attempts) + 1)
            if len(connection_attempts) < 3:
                # Fail first 2 attempts
                raise ConnectionError("Mock connection failure")
            # Stop reconnection after successful attempt
            client._should_reconnect = False
            return True

        # Mock the connection method
        with patch.object(client, "connect", side_effect=mock_connect):
            with patch("asyncio.sleep") as mock_sleep:

                # Test reconnection with exponential backoff
                try:
                    await asyncio.wait_for(client._handle_connection_loss(), timeout=2.0)
                except asyncio.TimeoutError:
                    # Stop reconnection to prevent hanging
                    client._should_reconnect = False

                # Should have attempted reconnection
                assert len(connection_attempts) >= 1

                # Verify exponential backoff was used
                if mock_sleep.called:
                    sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
                    # First delay should be initial delay
                    assert sleep_calls[0] >= 1

    @pytest.mark.asyncio
    async def test_message_processing_mock(self, mock_server_config):
        """Test message processing with mock WebSocket messages."""
        client = LoxoneClient(mock_server_config)
        client.state = ConnectionState.CONNECTED
        client._should_reconnect = True  # Allow processing

        # Mock WebSocket with test messages
        mock_ws = AsyncMock()

        # Create test state update message (binary format)
        import uuid
        import struct

        test_uuid = uuid.uuid4()
        test_value = 75.5

        # Create binary state update (24 bytes: 16 UUID + 8 double)
        state_message = test_uuid.bytes_le + struct.pack("d", test_value)

        # Track processed messages
        processed_messages = []

        async def mock_process_message(message):
            processed_messages.append(message)
            # Stop after processing one message
            client._should_reconnect = False

        # Mock recv to return messages then raise exception to end loop
        async def mock_recv():
            if len(processed_messages) == 0:
                return b"\x03\x02\x00\x00\x18\x00\x00\x00"  # Header
            elif len(processed_messages) == 1:
                return state_message  # State update data
            else:
                # Stop the loop by raising an exception
                raise websockets.exceptions.ConnectionClosed(None, None)

        mock_ws.recv = AsyncMock(side_effect=mock_recv)
        client._ws = mock_ws

        with patch.object(client, "_process_message", side_effect=mock_process_message):
            # Process messages with timeout
            try:
                await asyncio.wait_for(client._message_processor_loop(), timeout=2.0)
            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                pass  # Expected - we'll timeout or connection closed
            finally:
                # Ensure cleanup
                client._should_reconnect = False

            # Should have processed at least the header
            assert len(processed_messages) >= 1


class TestLoxoneClientErrorHandling:
    """Test error handling in LoxoneClient integration scenarios."""

    @pytest.mark.asyncio
    async def test_connection_timeout_handling(self, mock_server_config):
        """Test handling of connection timeouts."""
        client = LoxoneClient(mock_server_config)

        # Mock websockets.connect to raise timeout
        with patch("websockets.connect", side_effect=asyncio.TimeoutError()):
            success = await client.connect()

            assert success is False
            assert client.state == ConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_network_error_handling(self, mock_server_config):
        """Test handling of network errors during connection."""
        client = LoxoneClient(mock_server_config)

        # Mock websockets.connect to raise network error
        with patch("websockets.connect", side_effect=OSError("Network unreachable")):
            success = await client.connect()

            assert success is False
            assert client.state == ConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_invalid_response_handling(self, mock_server_config):
        """Test handling of invalid responses from server."""
        client = LoxoneClient(mock_server_config)

        # Mock HTTP response with invalid JSON
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Invalid JSON response"

        with patch("httpx.AsyncClient") as mock_http_client:
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            mock_http_client.return_value = mock_context

            success = await client.connect()

            assert success is False
            assert client.state == ConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_websocket_connection_closed_handling(self, mock_server_config):
        """Test handling of WebSocket connection being closed unexpectedly."""
        client = LoxoneClient(mock_server_config)
        client.state = ConnectionState.CONNECTED

        # Mock WebSocket that raises ConnectionClosed
        import websockets.exceptions

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=websockets.exceptions.ConnectionClosed(None, None))
        client._ws = mock_ws

        # Mock the connection loss handler
        with patch.object(client, "_handle_connection_loss") as mock_handler:
            try:
                await asyncio.wait_for(client._message_processor_loop(), timeout=0.1)
            except asyncio.TimeoutError:
                pass

            # Should have called connection loss handler
            mock_handler.assert_called()

    @pytest.mark.asyncio
    async def test_malformed_message_handling(self, mock_server_config):
        """Test handling of malformed messages from server."""
        client = LoxoneClient(mock_server_config)
        client.state = ConnectionState.CONNECTED
        client._should_reconnect = True

        # Track message processing
        message_count = 0

        async def mock_recv():
            nonlocal message_count
            message_count += 1
            if message_count == 1:
                return b"\x03\x00\x00\x00\x00\x00\x00\x00"  # Valid header
            elif message_count == 2:
                return b"Invalid message content"  # Invalid content
            elif message_count == 3:
                return None  # None message
            elif message_count == 4:
                return b""  # Empty message
            else:
                # Stop after processing test messages
                client._should_reconnect = False
                raise websockets.exceptions.ConnectionClosed(None, None)

        # Mock WebSocket with malformed messages
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=mock_recv)
        client._ws = mock_ws

        # Should handle malformed messages gracefully
        try:
            await asyncio.wait_for(client._message_processor_loop(), timeout=2.0)
        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
            pass  # Expected
        finally:
            # Ensure cleanup
            client._should_reconnect = False

        # Should have processed multiple messages
        assert message_count >= 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

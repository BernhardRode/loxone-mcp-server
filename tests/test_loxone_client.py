"""
Tests for LoxoneClient core functionality.

Following TDD principles with async/await and pytest-asyncio.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from src.loxone_mcp.loxone_client import (
    LoxoneClient,
    ConnectionState,
    MessageType,
    LxToken,
    LxJsonKeySalt,
    gen_init_vec,
    gen_key,
    check_and_decode_if_needed,
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


class TestLoxoneClientInitialization:
    """Test LoxoneClient initialization."""
    
    def test_client_initialization(self, loxone_client, mock_config):
        """Test that client initializes with correct configuration."""
        assert loxone_client.config == mock_config
        assert loxone_client._username == "admin"
        assert loxone_client._password == "password"
        assert loxone_client._host == "192.168.1.100"
        assert loxone_client._port == 80
        assert loxone_client.state == ConnectionState.DISCONNECTED
    
    def test_base_url_http_default_port(self, mock_config):
        """Test base URL construction for HTTP on port 80."""
        mock_config.port = 80
        client = LoxoneClient(mock_config)
        assert client._base_url == "http://192.168.1.100"
    
    def test_base_url_https_port(self, mock_config):
        """Test base URL construction for HTTPS on port 443."""
        mock_config.port = 443
        client = LoxoneClient(mock_config)
        assert client._base_url == "https://192.168.1.100"
    
    def test_base_url_custom_port(self, mock_config):
        """Test base URL construction for custom port."""
        mock_config.port = 8080
        client = LoxoneClient(mock_config)
        assert client._base_url == "http://192.168.1.100:8080"
    
    def test_encryption_keys_generated(self, loxone_client):
        """Test that encryption keys are generated on initialization."""
        assert loxone_client._iv is not None
        assert len(loxone_client._iv) == 16
        assert loxone_client._key is not None
        assert len(loxone_client._key) == 32


class TestTokenManagement:
    """Test token management functionality."""
    
    def test_token_initialization(self):
        """Test LxToken initialization."""
        token = LxToken("test_token", 1000000, "SHA256")
        assert token.token == "test_token"
        assert token.valid_until == 1000000
        assert token.hash_alg == "SHA256"
    
    def test_load_persisted_token(self, mock_config):
        """Test loading persisted token on initialization."""
        token_data = {
            "token": "persisted_token",
            "valid_until": 2000000,
            "hash_alg": "SHA256"
        }
        mock_config.load_token = Mock(return_value=token_data)
        
        client = LoxoneClient(mock_config)
        
        assert client._token.token == "persisted_token"
        assert client._token.valid_until == 2000000
        assert client._token.hash_alg == "SHA256"
    
    def test_persist_token(self, loxone_client, mock_config):
        """Test persisting token to disk."""
        loxone_client._token = LxToken("new_token", 3000000, "SHA1")
        loxone_client._persist_token()
        
        mock_config.save_token.assert_called_once()
        saved_data = mock_config.save_token.call_args[0][0]
        assert saved_data["token"] == "new_token"
        assert saved_data["valid_until"] == 3000000
        assert saved_data["hash_alg"] == "SHA1"


class TestStateCallbacks:
    """Test state callback registration."""
    
    def test_register_state_callback(self, loxone_client):
        """Test registering a state update callback."""
        callback = AsyncMock()
        loxone_client.register_state_callback(callback)
        
        assert callback in loxone_client._state_callbacks
    
    def test_multiple_callbacks(self, loxone_client):
        """Test registering multiple callbacks."""
        callback1 = AsyncMock()
        callback2 = AsyncMock()
        
        loxone_client.register_state_callback(callback1)
        loxone_client.register_state_callback(callback2)
        
        assert len(loxone_client._state_callbacks) == 2
        assert callback1 in loxone_client._state_callbacks
        assert callback2 in loxone_client._state_callbacks


class TestHelperFunctions:
    """Test helper functions."""
    
    def test_gen_init_vec(self):
        """Test initialization vector generation."""
        iv = gen_init_vec()
        assert len(iv) == 16
        assert isinstance(iv, bytes)
    
    def test_gen_key(self):
        """Test AES key generation."""
        key = gen_key()
        assert len(key) == 32
        assert isinstance(key, bytes)
    
    def test_check_and_decode_utf8(self):
        """Test decoding UTF-8 bytes."""
        message = b"Hello, World!"
        decoded = check_and_decode_if_needed(message)
        assert decoded == "Hello, World!"
    
    def test_check_and_decode_string(self):
        """Test that strings pass through unchanged."""
        message = "Already a string"
        decoded = check_and_decode_if_needed(message)
        assert decoded == "Already a string"


class TestMessageParsing:
    """Test message parsing functionality."""
    
    @pytest.mark.asyncio
    async def test_parse_keepalive_message(self, loxone_client):
        """Test parsing keepalive message."""
        # Keepalive message: 8 bytes with message type 6
        message = b'\x03\x06\x00\x00\x00\x00\x00\x00'
        await loxone_client._parse_loxone_message(message)
        
        assert loxone_client._current_message_type == MessageType.Keepalive
    
    @pytest.mark.asyncio
    async def test_parse_text_message(self, loxone_client):
        """Test parsing text message header."""
        # Text message: 8 bytes with message type 0
        message = b'\x03\x00\x00\x00\x00\x00\x00\x00'
        await loxone_client._parse_loxone_message(message)
        
        assert loxone_client._current_message_type == MessageType.TextMessage


class TestConnectionManagement:
    """Test connection management."""
    
    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self, loxone_client):
        """Test disconnect when not connected."""
        await loxone_client.disconnect()
        assert loxone_client.state == ConnectionState.DISCONNECTED
    
    def test_check_response_code_with_Code(self, loxone_client):
        """Test checking response code with 'Code' key."""
        resp_json = {"LL": {"Code": "200"}}
        assert loxone_client._check_response_code(resp_json, "200") is True
        assert loxone_client._check_response_code(resp_json, "400") is False
    
    def test_check_response_code_with_code(self, loxone_client):
        """Test checking response code with 'code' key."""
        resp_json = {"LL": {"code": "200"}}
        assert loxone_client._check_response_code(resp_json, "200") is True
        assert loxone_client._check_response_code(resp_json, "400") is False


class TestEncryption:
    """Test encryption functionality."""
    
    def test_generate_salt(self, loxone_client):
        """Test salt generation."""
        salt = loxone_client._generate_salt()
        
        assert salt is not None
        assert len(salt) > 0
        assert loxone_client._salt_used_count == 0
        assert loxone_client._salt_time_stamp > 0
    
    def test_new_salt_needed_by_count(self, loxone_client):
        """Test that new salt is needed after max use count."""
        import time
        loxone_client._salt = "test_salt"
        loxone_client._salt_used_count = 0
        loxone_client._salt_time_stamp = int(time.time())  # Use current time
        
        # Use salt up to max count
        for _ in range(30):
            assert loxone_client._new_salt_needed() is False
        
        # Next call should require new salt
        assert loxone_client._new_salt_needed() is True
    
    def test_get_new_aes_cipher(self, loxone_client):
        """Test AES cipher creation."""
        cipher = loxone_client._get_new_aes_cipher()
        assert cipher is not None


class TestKeySaltParsing:
    """Test LxJsonKeySalt parsing."""
    
    def test_read_user_salt_response(self):
        """Test parsing key and salt from response."""
        response = '''
        {
            "LL": {
                "value": {
                    "key": "ABCDEF1234567890",
                    "salt": "0987654321FEDCBA",
                    "hashAlg": "SHA256"
                }
            }
        }
        '''
        
        key_salt = LxJsonKeySalt()
        key_salt.read_user_salt_response(response)
        
        assert key_salt.key == "ABCDEF1234567890"
        assert key_salt.salt == "0987654321FEDCBA"
        assert key_salt.hash_alg == "SHA256"
    
    def test_read_user_salt_response_default_hash(self):
        """Test parsing with default hash algorithm."""
        response = '''
        {
            "LL": {
                "value": {
                    "key": "ABCDEF1234567890",
                    "salt": "0987654321FEDCBA"
                }
            }
        }
        '''
        
        key_salt = LxJsonKeySalt()
        key_salt.read_user_salt_response(response)
        
        assert key_salt.hash_alg == "SHA1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestRSAEncryption:
    """Test RSA encryption and key exchange."""
    
    def test_init_rsa_cipher_success(self, loxone_client):
        """Test successful RSA cipher initialization."""
        loxone_client._public_key = """-----BEGIN CERTIFICATE-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890ABCDEF
-----END CERTIFICATE-----"""
        
        # Mock RSA import
        with patch('src.loxone_mcp.loxone_client.RSA.importKey') as mock_import:
            with patch('src.loxone_mcp.loxone_client.PKCS1_v1_5.new') as mock_cipher:
                mock_import.return_value = Mock()
                mock_cipher.return_value = Mock()
                
                result = loxone_client._init_rsa_cipher()
                
                assert result is True
                assert loxone_client._rsa_cipher is not None
    
    def test_init_rsa_cipher_failure(self, loxone_client):
        """Test RSA cipher initialization failure."""
        loxone_client._public_key = "invalid_key"
        
        result = loxone_client._init_rsa_cipher()
        
        assert result is False
    
    def test_generate_session_key_success(self, loxone_client):
        """Test successful session key generation."""
        mock_cipher = Mock()
        mock_cipher.encrypt = Mock(return_value=b'encrypted_session_key')
        loxone_client._rsa_cipher = mock_cipher
        
        result = loxone_client._generate_session_key()
        
        assert result is True
        assert loxone_client._session_key is not None
        mock_cipher.encrypt.assert_called_once()
    
    def test_generate_session_key_failure(self, loxone_client):
        """Test session key generation failure."""
        loxone_client._rsa_cipher = None
        
        result = loxone_client._generate_session_key()
        
        assert result is False


class TestAuthentication:
    """Test authentication flows."""
    
    @pytest.mark.asyncio
    async def test_get_public_key_success(self, loxone_client):
        """Test successful public key retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"LL": {"value": "-----BEGIN CERTIFICATE-----\\nKEY\\n-----END CERTIFICATE-----"}}'
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_context
            
            result = await loxone_client._get_public_key()
            
            assert result is True
            assert loxone_client._public_key is not None
    
    @pytest.mark.asyncio
    async def test_get_public_key_http_error(self, loxone_client):
        """Test public key retrieval with HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 404
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_context = AsyncMock()
            mock_context.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_context
            
            result = await loxone_client._get_public_key()
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_hash_credentials_sha1(self, loxone_client):
        """Test credential hashing with SHA1."""
        key_salt = LxJsonKeySalt()
        key_salt.key = "1234567890abcdef"
        key_salt.salt = "fedcba0987654321"
        key_salt.hash_alg = "SHA1"
        
        result = loxone_client._hash_credentials(key_salt)
        
        assert result is not None
        assert len(result) > 0
        assert isinstance(result, str)
    
    @pytest.mark.asyncio
    async def test_hash_credentials_sha256(self, loxone_client):
        """Test credential hashing with SHA256."""
        key_salt = LxJsonKeySalt()
        key_salt.key = "1234567890abcdef"
        key_salt.salt = "fedcba0987654321"
        key_salt.hash_alg = "SHA256"
        
        result = loxone_client._hash_credentials(key_salt)
        
        assert result is not None
        assert len(result) > 0
        assert isinstance(result, str)


class TestTokenAcquisition:
    """Test token acquisition and usage."""
    
    @pytest.mark.asyncio
    async def test_acquire_token_success(self, loxone_client):
        """Test successful token acquisition."""
        # Setup
        loxone_client._encryption_ready = True
        loxone_client._ws = AsyncMock()
        loxone_client._version = 11.0
        
        # Mock responses
        key_salt_response = '''
        {
            "LL": {
                "value": {
                    "key": "1234567890abcdef",
                    "salt": "fedcba0987654321",
                    "hashAlg": "SHA256"
                }
            }
        }
        '''
        
        token_response = '''
        {
            "LL": {
                "value": {
                    "token": "new_token_12345",
                    "validUntil": 2000000
                }
            }
        }
        '''
        
        # Mock websocket recv to return appropriate responses
        loxone_client._ws.recv = AsyncMock(side_effect=[
            b'\x03\x00\x00\x00\x00\x00\x00\x00',  # Header
            key_salt_response.encode(),  # Key and salt
            b'\x03\x00\x00\x00\x00\x00\x00\x00',  # Header
            token_response.encode()  # Token
        ])
        
        loxone_client._ws.send = AsyncMock()
        
        # Mock encryption
        loxone_client._encrypt = AsyncMock(return_value="encrypted_command")
        
        result = await loxone_client._acquire_token()
        
        assert result is True
        assert loxone_client._token.token == "new_token_12345"
        assert loxone_client._token.valid_until == 2000000
    
    @pytest.mark.asyncio
    async def test_use_token_success(self, loxone_client):
        """Test successful token authentication."""
        # Setup
        loxone_client._encryption_ready = True
        loxone_client._ws = AsyncMock()
        loxone_client._token = LxToken("existing_token", 2000000, "SHA256")
        
        # Mock hash_token
        loxone_client._hash_token = AsyncMock(return_value="hashed_token")
        
        # Mock responses
        auth_response = '''
        {
            "LL": {
                "code": "200",
                "value": {
                    "validUntil": 2500000
                }
            }
        }
        '''
        
        loxone_client._ws.recv = AsyncMock(side_effect=[
            b'\x03\x00\x00\x00\x00\x00\x00\x00',  # Header
            auth_response.encode()  # Auth response
        ])
        
        loxone_client._ws.send = AsyncMock()
        loxone_client._encrypt = AsyncMock(return_value="encrypted_command")
        
        result = await loxone_client._use_token()
        
        assert result is True
        assert loxone_client._token.valid_until == 2500000
    
    @pytest.mark.asyncio
    async def test_hash_token_success(self, loxone_client):
        """Test successful token hashing."""
        # Setup
        loxone_client._encryption_ready = True
        loxone_client._ws = AsyncMock()
        loxone_client._token = LxToken("test_token", 2000000, "SHA256")
        
        # Mock responses
        key_response = '''
        {
            "LL": {
                "value": "1234567890abcdef"
            }
        }
        '''
        
        loxone_client._ws.recv = AsyncMock(side_effect=[
            b'\x03\x00\x00\x00\x00\x00\x00\x00',  # Header
            key_response.encode()  # Key response
        ])
        
        loxone_client._ws.send = AsyncMock()
        loxone_client._encrypt = AsyncMock(return_value="encrypted_command")
        
        result = await loxone_client._hash_token()
        
        assert result != -1
        assert isinstance(result, str)
        assert len(result) > 0


class TestTokenRefresh:
    """Test token refresh functionality."""
    
    @pytest.mark.asyncio
    async def test_refresh_token_success(self, loxone_client):
        """Test successful token refresh."""
        # Setup
        loxone_client._encryption_ready = True
        loxone_client._ws = AsyncMock()
        loxone_client._token = LxToken("existing_token", 1500000, "SHA256")
        loxone_client._version = 11.0
        
        # Mock responses
        key_response = '''
        {
            "LL": {
                "value": "1234567890abcdef"
            }
        }
        '''
        
        refresh_response = '''
        {
            "LL": {
                "value": {
                    "validUntil": 2500000
                }
            }
        }
        '''
        
        loxone_client._ws.recv = AsyncMock(side_effect=[
            b'\x03\x00\x00\x00\x00\x00\x00\x00',  # Header for key
            key_response.encode(),  # Key response
            b'\x03\x00\x00\x00\x00\x00\x00\x00',  # Header for refresh
            refresh_response.encode()  # Refresh response
        ])
        
        loxone_client._ws.send = AsyncMock()
        loxone_client._encrypt = AsyncMock(return_value="encrypted_command")
        
        result = await loxone_client._refresh_token()
        
        assert result is True
        assert loxone_client._token.valid_until == 2500000
    
    @pytest.mark.asyncio
    async def test_refresh_token_failure(self, loxone_client):
        """Test token refresh failure."""
        # Setup
        loxone_client._encryption_ready = True
        loxone_client._ws = AsyncMock()
        loxone_client._token = LxToken("existing_token", 1500000, "SHA256")
        
        # Mock responses with error
        key_response = '''
        {
            "LL": {
                "value": ""
            }
        }
        '''
        
        loxone_client._ws.recv = AsyncMock(side_effect=[
            b'\x03\x00\x00\x00\x00\x00\x00\x00',  # Header
            key_response.encode()  # Empty key response
        ])
        
        loxone_client._ws.send = AsyncMock()
        loxone_client._encrypt = AsyncMock(return_value="encrypted_command")
        
        result = await loxone_client._refresh_token()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_refresh_token_old_version(self, loxone_client):
        """Test token refresh with old Miniserver version."""
        # Setup
        loxone_client._encryption_ready = True
        loxone_client._ws = AsyncMock()
        loxone_client._token = LxToken("existing_token", 1500000, "SHA1")
        loxone_client._version = 9.0  # Old version
        
        # Mock responses
        key_response = '''
        {
            "LL": {
                "value": "1234567890abcdef"
            }
        }
        '''
        
        refresh_response = '''
        {
            "LL": {
                "value": {
                    "validUntil": 2500000
                }
            }
        }
        '''
        
        loxone_client._ws.recv = AsyncMock(side_effect=[
            b'\x03\x00\x00\x00\x00\x00\x00\x00',
            key_response.encode(),
            b'\x03\x00\x00\x00\x00\x00\x00\x00',
            refresh_response.encode()
        ])
        
        loxone_client._ws.send = AsyncMock()
        loxone_client._encrypt = AsyncMock(return_value="encrypted_command")
        
        result = await loxone_client._refresh_token()
        
        assert result is True


class TestAESEncryption:
    """Test AES encryption for commands."""
    
    @pytest.mark.asyncio
    async def test_encrypt_command_not_ready(self, loxone_client):
        """Test encryption when not ready returns plain command."""
        loxone_client._encryption_ready = False
        command = "test_command"
        
        result = await loxone_client._encrypt(command)
        
        assert result == command
    
    @pytest.mark.asyncio
    async def test_encrypt_command_with_new_salt(self, loxone_client):
        """Test encryption with new salt generation."""
        loxone_client._encryption_ready = True
        loxone_client._salt = ""
        command = "jdev/sps/io/uuid/value"
        
        result = await loxone_client._encrypt(command)
        
        assert result.startswith("jdev/sys/enc/")
        assert loxone_client._salt != ""
    
    @pytest.mark.asyncio
    async def test_encrypt_command_with_salt_rotation(self, loxone_client):
        """Test encryption with salt rotation."""
        loxone_client._encryption_ready = True
        loxone_client._salt = "old_salt"
        loxone_client._salt_used_count = 31  # Over max
        command = "jdev/sps/io/uuid/value"
        
        result = await loxone_client._encrypt(command)
        
        assert result.startswith("jdev/sys/enc/")
        # Salt should have been rotated
        assert loxone_client._salt != "old_salt"


class TestAuthenticationFlow:
    """Test complete authentication flow."""
    
    @pytest.mark.asyncio
    async def test_authenticate_with_valid_token(self, loxone_client):
        """Test authentication with valid existing token."""
        import time
        from datetime import datetime
        
        # Calculate a valid_until value that will be valid for > 300 seconds
        # Loxone uses seconds since 1.1.2009
        dt = datetime.strptime("1.1.2009", "%d.%m.%Y")
        try:
            start_date = int(dt.strftime("%s"))
        except Exception:
            start_date = int(dt.timestamp())
        
        # Set valid_until to be 1 hour from now
        current_time = int(round(time.time()))
        valid_until = current_time - start_date + 3600
        
        # Setup valid token
        loxone_client._token = LxToken("valid_token", valid_until, "SHA256")
        
        # Mock the methods
        with patch.object(loxone_client, '_use_token', new_callable=AsyncMock, return_value=True) as mock_use:
            with patch.object(loxone_client, '_acquire_token', new_callable=AsyncMock) as mock_acquire:
                result = await loxone_client._authenticate()
                
                assert result is True
                mock_use.assert_called_once()
                mock_acquire.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_authenticate_with_expired_token(self, loxone_client):
        """Test authentication with expired token."""
        # Setup expired token
        loxone_client._token = LxToken("expired_token", 100, "SHA256")
        
        with patch.object(loxone_client, '_use_token', new_callable=AsyncMock) as mock_use:
            with patch.object(loxone_client, '_acquire_token', new_callable=AsyncMock, return_value=True) as mock_acquire:
                result = await loxone_client._authenticate()
                
                assert result is True
                mock_use.assert_not_called()
                mock_acquire.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_authenticate_without_token(self, loxone_client):
        """Test authentication without existing token."""
        # No token
        loxone_client._token = LxToken()
        
        with patch.object(loxone_client, '_use_token', new_callable=AsyncMock) as mock_use:
            with patch.object(loxone_client, '_acquire_token', new_callable=AsyncMock, return_value=True) as mock_acquire:
                result = await loxone_client._authenticate()
                
                assert result is True
                mock_use.assert_not_called()
                mock_acquire.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestConnectionManagementAndReconnection:
    """Test connection management, keepalive, and reconnection with exponential backoff."""
    
    @pytest.mark.asyncio
    async def test_start_background_tasks(self, loxone_client):
        """Test that start() creates background tasks."""
        # Mock the loop methods
        with patch.object(loxone_client, '_keepalive_loop', new_callable=AsyncMock):
            with patch.object(loxone_client, '_message_processor_loop', new_callable=AsyncMock):
                await loxone_client.start()
                
                assert loxone_client._keepalive_task is not None
                assert loxone_client._message_processor_task is not None
                assert len(loxone_client.background_tasks) >= 2
                
                # Cleanup
                await loxone_client._cancel_background_tasks()
    
    @pytest.mark.asyncio
    async def test_cancel_background_tasks(self, loxone_client):
        """Test cancelling all background tasks."""
        # Create mock tasks
        task1 = asyncio.create_task(asyncio.sleep(100))
        task2 = asyncio.create_task(asyncio.sleep(100))
        
        loxone_client._keepalive_task = task1
        loxone_client._message_processor_task = task2
        loxone_client.background_tasks.add(task1)
        loxone_client.background_tasks.add(task2)
        
        await loxone_client._cancel_background_tasks()
        
        assert task1.cancelled()
        assert task2.cancelled()
        assert len(loxone_client.background_tasks) == 0
    
    @pytest.mark.asyncio
    async def test_disconnect_cancels_tasks(self, loxone_client):
        """Test that disconnect cancels background tasks."""
        # Setup mock tasks
        loxone_client._keepalive_task = asyncio.create_task(asyncio.sleep(100))
        loxone_client.background_tasks.add(loxone_client._keepalive_task)
        
        await loxone_client.disconnect()
        
        assert loxone_client.state == ConnectionState.DISCONNECTED
        assert loxone_client._manual_disconnect is True
        assert loxone_client._should_reconnect is False
        assert loxone_client._keepalive_task.cancelled()
    
    @pytest.mark.asyncio
    async def test_keepalive_sends_ping(self, loxone_client):
        """Test that keepalive loop sends ping messages."""
        loxone_client.state = ConnectionState.CONNECTED
        loxone_client._ws = AsyncMock()
        loxone_client._ws.ping = AsyncMock()
        loxone_client._token = LxToken("test_token", 999999999, "SHA256")
        loxone_client._should_reconnect = True
        
        # Mock asyncio.sleep to make test fast
        sleep_count = 0
        orig_sleep = asyncio.sleep
        async def mock_sleep(duration):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:  # Stop after second sleep
                loxone_client._should_reconnect = False
            await orig_sleep(0.01)  # Very short actual sleep
        
        with patch('asyncio.sleep', side_effect=mock_sleep):
            try:
                await asyncio.wait_for(loxone_client._keepalive_loop(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
        
        # Should have attempted at least one ping
        assert loxone_client._ws.ping.called
    
    @pytest.mark.asyncio
    async def test_keepalive_refreshes_expiring_token(self, loxone_client):
        """Test that keepalive refreshes token when expiring soon."""
        loxone_client.state = ConnectionState.CONNECTED
        loxone_client._ws = AsyncMock()
        loxone_client._ws.ping = AsyncMock()
        loxone_client._should_reconnect = True
        
        # Token expiring in 200 seconds (< 300 threshold)
        import time
        from datetime import datetime
        dt = datetime.strptime("1.1.2009", "%d.%m.%Y")
        try:
            start_date = int(dt.strftime("%s"))
        except Exception:
            start_date = int(dt.timestamp())
        current_time = int(round(time.time()))
        valid_until = current_time - start_date + 200
        
        loxone_client._token = LxToken("expiring_token", valid_until, "SHA256")
        
        # Mock asyncio.sleep to make test fast
        sleep_count = 0
        async def mock_sleep(duration):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                loxone_client._should_reconnect = False
            await asyncio.sleep(0.01)
        
        with patch.object(loxone_client, '_refresh_token', new_callable=AsyncMock, return_value=True) as mock_refresh:
            with patch('asyncio.sleep', side_effect=mock_sleep):
                try:
                    await asyncio.wait_for(loxone_client._keepalive_loop(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
            
            # Should have attempted token refresh
            assert mock_refresh.called
    
    @pytest.mark.asyncio
    async def test_keepalive_handles_timeout(self, loxone_client):
        """Test that keepalive handles ping timeout."""
        loxone_client.state = ConnectionState.CONNECTED
        loxone_client._ws = AsyncMock()
        loxone_client._ws.ping = AsyncMock(side_effect=asyncio.TimeoutError())
        loxone_client._token = LxToken("test_token", 999999999, "SHA256")
        loxone_client._should_reconnect = True
        
        # Mock asyncio.sleep to make test fast
        sleep_count = 0
        async def mock_sleep(duration):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                loxone_client._should_reconnect = False
            await asyncio.sleep(0.01)
        
        with patch.object(loxone_client, '_handle_connection_loss', new_callable=AsyncMock) as mock_handle:
            with patch('asyncio.sleep', side_effect=mock_sleep):
                try:
                    await asyncio.wait_for(loxone_client._keepalive_loop(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
            
            # Should have handled connection loss
            assert mock_handle.called
    
    @pytest.mark.asyncio
    async def test_message_processor_receives_messages(self, loxone_client):
        """Test that message processor receives and processes messages."""
        loxone_client.state = ConnectionState.CONNECTED
        loxone_client._ws = AsyncMock()
        
        test_message = '{"LL": {"value": "test"}}'
        async def recv_once():
            loxone_client._should_reconnect = False
            return test_message
        loxone_client._ws.recv = AsyncMock(side_effect=recv_once)
        
        with patch.object(loxone_client, '_process_message', new_callable=AsyncMock) as mock_process:
            loxone_client._should_reconnect = True
            await loxone_client._message_processor_loop()
            assert mock_process.called
    
    @pytest.mark.asyncio
    async def test_message_processor_handles_connection_closed(self, loxone_client):
        """Test that message processor handles connection closed."""
        import websockets
        
        loxone_client.state = ConnectionState.CONNECTED
        loxone_client._ws = AsyncMock()
        loxone_client._ws.recv = AsyncMock(side_effect=websockets.exceptions.ConnectionClosed(None, None))
        
        with patch.object(loxone_client, '_handle_connection_loss', new_callable=AsyncMock) as mock_handle:
            # Run message processor briefly
            async def run_processor_briefly():
                try:
                    await asyncio.wait_for(loxone_client._message_processor_loop(), timeout=0.1)
                except asyncio.TimeoutError:
                    pass
            
            loxone_client._should_reconnect = True
            await run_processor_briefly()
            
            # Should have handled connection loss
            assert mock_handle.called
    
    @pytest.mark.asyncio
    async def test_process_message_binary_header(self, loxone_client):
        """Test processing binary message header."""
        message = b'\x03\x06\x00\x00\x00\x00\x00\x00'  # Keepalive message
        
        await loxone_client._process_message(message)
        
        assert loxone_client._current_message_type == MessageType.Keepalive
    
    @pytest.mark.asyncio
    async def test_process_message_json(self, loxone_client):
        """Test processing JSON text message."""
        message = '{"LL": {"value": "test_data"}}'
        
        # Should not raise exception
        await loxone_client._process_message(message)
    
    @pytest.mark.asyncio
    async def test_process_message_non_json(self, loxone_client):
        """Test processing non-JSON text message."""
        message = "plain text message"
        
        # Should not raise exception
        await loxone_client._process_message(message)
    
    @pytest.mark.asyncio
    async def test_process_message_handles_errors(self, loxone_client):
        """Test that message processing handles errors gracefully."""
        # Invalid message that will cause processing error
        message = None
        
        # Should not raise exception
        await loxone_client._process_message(message)
    
    @pytest.mark.asyncio
    async def test_handle_connection_loss_manual_disconnect(self, loxone_client):
        """Test that connection loss is ignored on manual disconnect."""
        loxone_client._manual_disconnect = True
        loxone_client._ws = AsyncMock()
        
        await loxone_client._handle_connection_loss()
        
        # Should not start reconnection
        assert loxone_client._reconnect_task is None
    
    @pytest.mark.asyncio
    async def test_handle_connection_loss_starts_reconnection(self, loxone_client):
        """Test that connection loss starts reconnection."""
        loxone_client._manual_disconnect = False
        loxone_client._should_reconnect = True
        loxone_client._ws = AsyncMock()
        loxone_client.state = ConnectionState.CONNECTED
        
        with patch.object(loxone_client, '_reconnect_loop', new_callable=AsyncMock):
            await loxone_client._handle_connection_loss()
            
            assert loxone_client.state == ConnectionState.DISCONNECTED
            assert loxone_client._reconnect_task is not None
            
            # Cleanup
            if loxone_client._reconnect_task:
                loxone_client._reconnect_task.cancel()
                try:
                    await loxone_client._reconnect_task
                except asyncio.CancelledError:
                    pass
    
    @pytest.mark.asyncio
    async def test_reconnect_loop_exponential_backoff(self, loxone_client):
        """Test that reconnection uses exponential backoff."""
        loxone_client._should_reconnect = True
        loxone_client.state = ConnectionState.DISCONNECTED
        loxone_client._reconnect_delay = 1
        
        # Mock connect to fail multiple times
        connect_attempts = []
        
        async def mock_connect():
            connect_attempts.append(loxone_client._reconnect_delay)
            return False
        
        # Mock asyncio.sleep to make test fast and stop after a few attempts
        sleep_count = 0
        original_sleep = asyncio.sleep
        
        async def mock_sleep(duration):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 3:  # Stop after 3 attempts
                loxone_client._should_reconnect = False
            # Use original sleep with very short duration
            await original_sleep(0.001)
        
        with patch.object(loxone_client, 'connect', new_callable=AsyncMock, side_effect=mock_connect):
            with patch('asyncio.sleep', side_effect=mock_sleep):
                try:
                    await asyncio.wait_for(loxone_client._reconnect_loop(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
            
            # Should have attempted reconnection
            assert len(connect_attempts) > 0
            
            # Delay should have increased (exponential backoff)
            if len(connect_attempts) > 1:
                assert loxone_client._reconnect_delay > 1
    
    @pytest.mark.asyncio
    async def test_reconnect_loop_success(self, loxone_client):
        """Test successful reconnection."""
        loxone_client._should_reconnect = True
        loxone_client.state = ConnectionState.DISCONNECTED
        loxone_client._reconnect_delay = 1
        
        with patch.object(loxone_client, 'connect', new_callable=AsyncMock, return_value=True):
            await loxone_client._reconnect_loop()
            
            # Delay should be reset after successful connection
            assert loxone_client._reconnect_delay == 1
            assert loxone_client._reconnect_task is None
    
    @pytest.mark.asyncio
    async def test_reconnect_loop_max_delay(self, loxone_client):
        """Test that reconnection delay doesn't exceed maximum."""
        from src.loxone_mcp.loxone_client import RECONNECT_MAX_DELAY
        
        loxone_client._should_reconnect = True
        loxone_client.state = ConnectionState.DISCONNECTED
        loxone_client._reconnect_delay = RECONNECT_MAX_DELAY - 10
        
        # Mock asyncio.sleep to make test fast
        sleep_count = 0
        async def mock_sleep(duration):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                loxone_client._should_reconnect = False
            await asyncio.sleep(0.01)
        
        with patch.object(loxone_client, 'connect', new_callable=AsyncMock, return_value=False):
            with patch('asyncio.sleep', side_effect=mock_sleep):
                try:
                    await asyncio.wait_for(loxone_client._reconnect_loop(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
            
            # Delay should not exceed maximum
            assert loxone_client._reconnect_delay <= RECONNECT_MAX_DELAY
    
    @pytest.mark.asyncio
    async def test_reconnect_loop_stops_when_connected(self, loxone_client):
        """Test that reconnection loop stops when already connected."""
        loxone_client._should_reconnect = True
        loxone_client.state = ConnectionState.CONNECTED
        
        with patch.object(loxone_client, 'connect', new_callable=AsyncMock) as mock_connect:
            await loxone_client._reconnect_loop()
            
            # Should not attempt to connect if already connected
            mock_connect.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_connection_state_tracking(self, loxone_client):
        """Test connection state transitions."""
        assert loxone_client.state == ConnectionState.DISCONNECTED
        
        # Simulate connection process
        loxone_client.state = ConnectionState.CONNECTING
        assert loxone_client.state == ConnectionState.CONNECTING
        
        loxone_client.state = ConnectionState.CONNECTED
        assert loxone_client.state == ConnectionState.CONNECTED
        
        loxone_client.state = ConnectionState.DISCONNECTED
        assert loxone_client.state == ConnectionState.DISCONNECTED
    
    @pytest.mark.asyncio
    async def test_keepalive_loop_cancellation(self, loxone_client):
        """Test that keepalive loop can be cancelled."""
        loxone_client._should_reconnect = True
        loxone_client.state = ConnectionState.CONNECTED
        loxone_client._ws = AsyncMock()
        loxone_client._ws.ping = AsyncMock()
        loxone_client._token = LxToken("test_token", 999999999, "SHA256")
        
        # Store original sleep function
        original_sleep = asyncio.sleep
        
        # Mock asyncio.sleep to prevent long waits
        async def mock_sleep(duration):
            await original_sleep(0.001)  # Very short sleep
        
        with patch('asyncio.sleep', side_effect=mock_sleep):
            task = asyncio.create_task(loxone_client._keepalive_loop())
            
            # Let it run briefly with original sleep
            await original_sleep(0.01)
            
            # Cancel the task
            task.cancel()
            
            with pytest.raises(asyncio.CancelledError):
                await task
    
    @pytest.mark.asyncio
    async def test_message_processor_loop_cancellation(self, loxone_client):
        """Test that message processor loop can be cancelled."""
        loxone_client._should_reconnect = True
        loxone_client.state = ConnectionState.CONNECTED
        loxone_client._ws = AsyncMock()
        loxone_client._ws.recv = AsyncMock(side_effect=asyncio.TimeoutError())
        
        task = asyncio.create_task(loxone_client._message_processor_loop())
        
        # Let it run briefly
        await asyncio.sleep(0.1)
        
        # Cancel the task
        task.cancel()
        
        with pytest.raises(asyncio.CancelledError):
            await task
    
    @pytest.mark.asyncio
    async def test_reconnect_loop_cancellation(self, loxone_client):
        """Test that reconnect loop can be cancelled."""
        loxone_client._should_reconnect = True
        loxone_client.state = ConnectionState.DISCONNECTED
        
        # Store original sleep function
        original_sleep = asyncio.sleep
        
        # Mock asyncio.sleep to prevent long waits
        async def mock_sleep(duration):
            await original_sleep(0.001)  # Very short sleep
        
        with patch.object(loxone_client, 'connect', new_callable=AsyncMock, return_value=False):
            with patch('asyncio.sleep', side_effect=mock_sleep):
                task = asyncio.create_task(loxone_client._reconnect_loop())
                
                # Let it run briefly with original sleep
                await original_sleep(0.01)
                
                # Cancel the task
                task.cancel()
                
                with pytest.raises(asyncio.CancelledError):
                    await task

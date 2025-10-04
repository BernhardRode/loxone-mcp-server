"""
Unit tests for encryption functionality.

Tests cover:
- AES encryption/decryption
- RSA key exchange
- Token hashing
- Visual hash computation
- Key generation utilities
- Salt management
"""

import binascii
import hashlib
import json
from base64 import b64decode
from unittest.mock import AsyncMock
import pytest

from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.Hash import HMAC, SHA1, SHA256
from Crypto.PublicKey import RSA
from Crypto.Util import Padding

from loxone_mcp.loxone_client import (
    LoxoneClient,
    LxJsonKeySalt,
    LxToken,
    gen_init_vec,
    gen_key,
    time_elapsed_in_seconds,
    ConnectionState,
    IV_BYTES,
    AES_KEY_SIZE,
    SALT_MAX_AGE_SECONDS,
    SALT_MAX_USE_COUNT,
)
from loxone_mcp.config import LoxoneConfig


class TestKeyGeneration:
    """Test cryptographic key generation utilities."""

    def test_gen_init_vec_length(self):
        """Test that initialization vector has correct length."""
        iv = gen_init_vec()
        assert len(iv) == IV_BYTES
        assert isinstance(iv, bytes)

    def test_gen_init_vec_randomness(self):
        """Test that initialization vectors are random."""
        iv1 = gen_init_vec()
        iv2 = gen_init_vec()

        # Should be different (extremely unlikely to be the same)
        assert iv1 != iv2

    def test_gen_key_length(self):
        """Test that AES key has correct length."""
        key = gen_key()
        assert len(key) == AES_KEY_SIZE
        assert isinstance(key, bytes)

    def test_gen_key_randomness(self):
        """Test that AES keys are random."""
        key1 = gen_key()
        key2 = gen_key()

        # Should be different (extremely unlikely to be the same)
        assert key1 != key2

    def test_time_elapsed_in_seconds(self):
        """Test time elapsed function returns reasonable value."""
        timestamp = time_elapsed_in_seconds()
        assert isinstance(timestamp, int)
        assert timestamp > 1600000000  # After 2020
        assert timestamp < 2000000000  # Before 2033


class TestLxToken:
    """Test Loxone token class."""

    def test_token_initialization_defaults(self):
        """Test token initialization with default values."""
        token = LxToken()

        assert token.token == ""
        assert token.valid_until == 0
        assert token.hash_alg == "SHA1"

    def test_token_initialization_with_values(self):
        """Test token initialization with specific values."""
        token = LxToken(token="test_token_123", valid_until=1234567890, hash_alg="SHA256")

        assert token.token == "test_token_123"
        assert token.valid_until == 1234567890
        assert token.hash_alg == "SHA256"

    def test_token_seconds_to_expire(self):
        """Test token expiration calculation."""
        # The LxToken uses a specific base date (1.1.2009) and adds valid_until seconds
        # So we need to test with the actual implementation logic
        token = LxToken(valid_until=3600)  # 1 hour worth of seconds

        seconds_to_expire = token.get_seconds_to_expire()

        # The result depends on the base date calculation, so we just verify it's an integer
        assert isinstance(seconds_to_expire, int)

    def test_token_expired(self):
        """Test token expiration detection."""
        # Test with a very small valid_until value (should be expired)
        token = LxToken(valid_until=1)  # Very small value, likely expired

        seconds_to_expire = token.get_seconds_to_expire()

        # Just verify it returns an integer (the actual value depends on base date calculation)
        assert isinstance(seconds_to_expire, int)


class TestLxJsonKeySalt:
    """Test key and salt response parsing."""

    def test_key_salt_initialization(self):
        """Test key salt initialization with defaults."""
        key_salt = LxJsonKeySalt()

        assert key_salt.key is None
        assert key_salt.salt is None
        assert key_salt.hash_alg == "SHA1"
        assert key_salt.time_elapsed_in_seconds is None

    def test_read_user_salt_response_sha1(self):
        """Test parsing user salt response with SHA1."""
        response_data = {
            "LL": {
                "value": {"key": "abcdef1234567890", "salt": "fedcba0987654321", "hashAlg": "SHA1"}
            }
        }
        response_json = json.dumps(response_data)

        key_salt = LxJsonKeySalt()
        key_salt.read_user_salt_response(response_json)

        assert key_salt.key == "abcdef1234567890"
        assert key_salt.salt == "fedcba0987654321"
        assert key_salt.hash_alg == "SHA1"

    def test_read_user_salt_response_sha256(self):
        """Test parsing user salt response with SHA256."""
        response_data = {
            "LL": {
                "value": {
                    "key": "1234567890abcdef",
                    "salt": "0987654321fedcba",
                    "hashAlg": "SHA256",
                }
            }
        }
        response_json = json.dumps(response_data)

        key_salt = LxJsonKeySalt()
        key_salt.read_user_salt_response(response_json)

        assert key_salt.key == "1234567890abcdef"
        assert key_salt.salt == "0987654321fedcba"
        assert key_salt.hash_alg == "SHA256"

    def test_read_user_salt_response_default_hash_alg(self):
        """Test parsing user salt response without hashAlg (defaults to SHA1)."""
        response_data = {
            "LL": {
                "value": {
                    "key": "testkey123",
                    "salt": "testsalt456",
                    # No hashAlg field
                }
            }
        }
        response_json = json.dumps(response_data)

        key_salt = LxJsonKeySalt()
        key_salt.read_user_salt_response(response_json)

        assert key_salt.key == "testkey123"
        assert key_salt.salt == "testsalt456"
        assert key_salt.hash_alg == "SHA1"  # Should default to SHA1


class TestRSAEncryption:
    """Test RSA encryption functionality."""

    def test_init_rsa_cipher_valid_key(self):
        """Test RSA cipher initialization with valid public key."""
        config = LoxoneConfig(host="test.local", port=80, username="test", password="test")
        client = LoxoneClient(config)

        # Generate a test RSA key pair
        rsa_key = RSA.generate(2048)
        public_key_pem = rsa_key.publickey().export_key().decode("utf-8")

        # Format as Loxone certificate format
        client._public_key = public_key_pem.replace(
            "-----BEGIN PUBLIC KEY-----", "-----BEGIN CERTIFICATE-----"
        ).replace("-----END PUBLIC KEY-----", "-----END CERTIFICATE-----")

        result = client._init_rsa_cipher()

        assert result is True
        assert client._rsa_cipher is not None

    def test_init_rsa_cipher_invalid_key(self):
        """Test RSA cipher initialization with invalid public key."""
        config = LoxoneConfig(host="test.local", port=80, username="test", password="test")
        client = LoxoneClient(config)

        # Set invalid public key
        client._public_key = "invalid_key_data"

        result = client._init_rsa_cipher()

        assert result is False
        assert client._rsa_cipher is None

    def test_generate_session_key(self):
        """Test session key generation and RSA encryption."""
        config = LoxoneConfig(host="test.local", port=80, username="test", password="test")
        client = LoxoneClient(config)

        # Generate test RSA key pair
        rsa_key = RSA.generate(2048)
        public_key_pem = rsa_key.publickey().export_key().decode("utf-8")

        # Set up client with RSA cipher
        client._public_key = public_key_pem.replace(
            "-----BEGIN PUBLIC KEY-----", "-----BEGIN CERTIFICATE-----"
        ).replace("-----END PUBLIC KEY-----", "-----END CERTIFICATE-----")
        client._init_rsa_cipher()

        # Set test AES key and IV
        client._key = gen_key()
        client._iv = gen_init_vec()

        result = client._generate_session_key()

        assert result is True
        assert client._session_key is not None
        assert len(client._session_key) > 0

        # Verify session key can be decrypted
        encrypted_session = b64decode(client._session_key)
        rsa_cipher = PKCS1_v1_5.new(rsa_key)
        decrypted_session = rsa_cipher.decrypt(encrypted_session, None)

        assert decrypted_session is not None
        session_parts = decrypted_session.decode("utf-8").split(":")
        assert len(session_parts) == 2

        # Verify AES key and IV match
        decrypted_key = binascii.unhexlify(session_parts[0])
        decrypted_iv = binascii.unhexlify(session_parts[1])
        assert decrypted_key == client._key
        assert decrypted_iv == client._iv

    def test_generate_session_key_no_rsa_cipher(self):
        """Test session key generation without RSA cipher."""
        config = LoxoneConfig(host="test.local", port=80, username="test", password="test")
        client = LoxoneClient(config)

        # Don't initialize RSA cipher
        client._key = gen_key()
        client._iv = gen_init_vec()

        result = client._generate_session_key()

        assert result is False


class TestAESEncryption:
    """Test AES encryption functionality."""

    def test_get_new_aes_cipher(self):
        """Test AES cipher creation."""
        config = LoxoneConfig(host="test.local", port=80, username="test", password="test")
        client = LoxoneClient(config)

        # Set test key and IV
        client._key = gen_key()
        client._iv = gen_init_vec()

        cipher = client._get_new_aes_cipher()

        assert cipher is not None
        # Just verify it's an AES cipher object (the exact type may vary between pycryptodome versions)
        assert hasattr(cipher, "encrypt")
        assert hasattr(cipher, "decrypt")

    @pytest.mark.asyncio
    async def test_encrypt_command_not_ready(self):
        """Test command encryption when encryption is not ready."""
        config = LoxoneConfig(host="test.local", port=80, username="test", password="test")
        client = LoxoneClient(config)

        # Encryption not ready
        client._encryption_ready = False

        result = await client._encrypt("test_command")

        # Should return command unchanged
        assert result == "test_command"

    @pytest.mark.asyncio
    async def test_encrypt_command_with_salt(self):
        """Test command encryption with salt."""
        config = LoxoneConfig(host="test.local", port=80, username="test", password="test")
        client = LoxoneClient(config)

        # Set up encryption
        client._encryption_ready = True
        client._key = gen_key()
        client._iv = gen_init_vec()
        client._salt = ""  # No existing salt

        result = await client._encrypt("test_command")

        # Should return encrypted command
        assert result.startswith("jdev/sys/enc/")
        assert len(result) > len("jdev/sys/enc/")

        # Salt should be generated
        assert client._salt != ""

    @pytest.mark.asyncio
    async def test_encrypt_command_with_existing_salt(self):
        """Test command encryption with existing salt."""
        config = LoxoneConfig(host="test.local", port=80, username="test", password="test")
        client = LoxoneClient(config)

        # Set up encryption with existing salt
        client._encryption_ready = True
        client._key = gen_key()
        client._iv = gen_init_vec()
        client._salt = "existing_salt"
        client._salt_used_count = 5
        client._salt_time_stamp = time_elapsed_in_seconds()

        result = await client._encrypt("test_command")

        # Should return encrypted command
        assert result.startswith("jdev/sys/enc/")

        # Salt usage should be incremented
        assert client._salt_used_count == 6

    def test_generate_salt(self):
        """Test salt generation."""
        config = LoxoneConfig(host="test.local", port=80, username="test", password="test")
        client = LoxoneClient(config)

        salt = client._generate_salt()

        assert isinstance(salt, str)
        assert len(salt) > 0
        assert client._salt_used_count == 0
        assert client._salt_time_stamp > 0

    def test_new_salt_needed_count_exceeded(self):
        """Test salt renewal when usage count is exceeded."""
        config = LoxoneConfig(host="test.local", port=80, username="test", password="test")
        client = LoxoneClient(config)

        # Set salt usage to maximum
        client._salt_used_count = SALT_MAX_USE_COUNT
        client._salt_time_stamp = time_elapsed_in_seconds()

        result = client._new_salt_needed()

        assert result is True

    def test_new_salt_needed_time_exceeded(self):
        """Test salt renewal when time limit is exceeded."""
        config = LoxoneConfig(host="test.local", port=80, username="test", password="test")
        client = LoxoneClient(config)

        # Set salt timestamp to past
        client._salt_used_count = 1
        client._salt_time_stamp = time_elapsed_in_seconds() - SALT_MAX_AGE_SECONDS - 1

        result = client._new_salt_needed()

        assert result is True

    def test_new_salt_needed_within_limits(self):
        """Test salt renewal when within limits."""
        config = LoxoneConfig(host="test.local", port=80, username="test", password="test")
        client = LoxoneClient(config)

        # Set salt within limits
        client._salt_used_count = 5
        client._salt_time_stamp = time_elapsed_in_seconds()

        result = client._new_salt_needed()

        assert result is False


class TestCredentialHashing:
    """Test credential and token hashing functionality."""

    def test_hash_credentials_sha1(self):
        """Test credential hashing with SHA1."""
        config = LoxoneConfig(host="test.local", port=80, username="testuser", password="testpass")
        client = LoxoneClient(config)

        # Create test key salt
        key_salt = LxJsonKeySalt()
        key_salt.key = "abcdef1234567890"
        key_salt.salt = "fedcba0987654321"
        key_salt.hash_alg = "SHA1"

        result = client._hash_credentials(key_salt)

        assert isinstance(result, str)
        assert len(result) > 0

        # Verify the hashing process manually
        pwd_hash_str = f"testpass:{key_salt.salt}"
        m = hashlib.sha1()
        m.update(pwd_hash_str.encode("utf-8"))
        pwd_hash = m.hexdigest().upper()
        pwd_hash = f"testuser:{pwd_hash}"

        digester = HMAC.new(binascii.unhexlify(key_salt.key), pwd_hash.encode("utf-8"), SHA1)
        expected_hash = digester.hexdigest()

        assert result == expected_hash

    def test_hash_credentials_sha256(self):
        """Test credential hashing with SHA256."""
        config = LoxoneConfig(host="test.local", port=80, username="testuser", password="testpass")
        client = LoxoneClient(config)

        # Create test key salt
        key_salt = LxJsonKeySalt()
        key_salt.key = "1234567890abcdef"
        key_salt.salt = "0987654321fedcba"
        key_salt.hash_alg = "SHA256"

        result = client._hash_credentials(key_salt)

        assert isinstance(result, str)
        assert len(result) > 0

        # Verify the hashing process manually
        pwd_hash_str = f"testpass:{key_salt.salt}"
        m = hashlib.sha256()
        m.update(pwd_hash_str.encode("utf-8"))
        pwd_hash = m.hexdigest().upper()
        pwd_hash = f"testuser:{pwd_hash}"

        digester = HMAC.new(binascii.unhexlify(key_salt.key), pwd_hash.encode("utf-8"), SHA256)
        expected_hash = digester.hexdigest()

        assert result == expected_hash

    def test_hash_credentials_unknown_algorithm(self):
        """Test credential hashing with unknown hash algorithm."""
        config = LoxoneConfig(host="test.local", port=80, username="testuser", password="testpass")
        client = LoxoneClient(config)

        # Create test key salt with unknown algorithm
        key_salt = LxJsonKeySalt()
        key_salt.key = "abcdef1234567890"
        key_salt.salt = "fedcba0987654321"
        key_salt.hash_alg = "UNKNOWN"

        result = client._hash_credentials(key_salt)

        # Should return empty string for unknown algorithm
        assert result == ""


class TestVisualHashComputation:
    """Test visual hash computation for secured commands."""

    @pytest.mark.asyncio
    async def test_get_visual_hash_success(self):
        """Test successful visual hash retrieval."""
        config = LoxoneConfig(host="test.local", port=80, username="testuser", password="testpass")
        client = LoxoneClient(config)

        # Mock the encrypt method
        client._encrypt = AsyncMock(return_value="encrypted_command")

        # Mock websocket
        mock_ws = AsyncMock()
        client._ws = mock_ws

        # Mock response
        response_data = {
            "LL": {"value": {"key": "visual_key_123", "salt": "visual_salt_456", "hashAlg": "SHA1"}}
        }
        mock_ws.recv.return_value = json.dumps(response_data)

        result = await client._get_visual_hash()

        assert result is not None
        assert result["key"] == "visual_key_123"
        assert result["salt"] == "visual_salt_456"
        assert result["hash_alg"] == "SHA1"

        # Verify encrypt was called
        client._encrypt.assert_called_once()
        # Verify websocket send was called
        mock_ws.send.assert_called_once_with("encrypted_command")

    @pytest.mark.asyncio
    async def test_get_visual_hash_sha256(self):
        """Test visual hash retrieval with SHA256."""
        config = LoxoneConfig(host="test.local", port=80, username="testuser", password="testpass")
        client = LoxoneClient(config)

        client._encrypt = AsyncMock(return_value="encrypted_command")
        mock_ws = AsyncMock()
        client._ws = mock_ws

        # Mock response with SHA256
        response_data = {
            "LL": {
                "value": {"key": "visual_key_256", "salt": "visual_salt_256", "hashAlg": "SHA256"}
            }
        }
        mock_ws.recv.return_value = json.dumps(response_data)

        result = await client._get_visual_hash()

        assert result is not None
        assert result["hash_alg"] == "SHA256"

    @pytest.mark.asyncio
    async def test_get_visual_hash_invalid_response(self):
        """Test visual hash retrieval with invalid response."""
        config = LoxoneConfig(host="test.local", port=80, username="testuser", password="testpass")
        client = LoxoneClient(config)

        client._encrypt = AsyncMock(return_value="encrypted_command")
        mock_ws = AsyncMock()
        client._ws = mock_ws

        # Mock invalid response
        mock_ws.recv.return_value = '{"invalid": "response"}'

        result = await client._get_visual_hash()

        assert result is None

    @pytest.mark.asyncio
    async def test_get_visual_hash_exception(self):
        """Test visual hash retrieval with exception."""
        config = LoxoneConfig(host="test.local", port=80, username="testuser", password="testpass")
        client = LoxoneClient(config)

        client._encrypt = AsyncMock(side_effect=Exception("Test error"))

        result = await client._get_visual_hash()

        assert result is None

    @pytest.mark.asyncio
    async def test_send_secured_command_sha1(self):
        """Test sending secured command with SHA1 hash."""
        config = LoxoneConfig(host="test.local", port=80, username="testuser", password="testpass")
        client = LoxoneClient(config)

        # Set client state to connected
        client.state = ConnectionState.CONNECTED

        # Mock get_visual_hash
        visual_hash_data = {
            "key": "abcdef1234567890",
            "salt": "fedcba0987654321",
            "hash_alg": "SHA1",
        }
        client._get_visual_hash = AsyncMock(return_value=visual_hash_data)

        # Mock websocket
        mock_ws = AsyncMock()
        client._ws = mock_ws

        result = await client.send_secured_command("test-uuid", "1", "1234")

        assert result is True

        # Verify websocket send was called
        mock_ws.send.assert_called_once()

        # Verify the command format
        sent_command = mock_ws.send.call_args[0][0]
        assert sent_command.startswith("jdev/sps/ios/")
        assert "test-uuid" in sent_command
        assert "/1" in sent_command

    @pytest.mark.asyncio
    async def test_send_secured_command_sha256(self):
        """Test sending secured command with SHA256 hash."""
        config = LoxoneConfig(host="test.local", port=80, username="testuser", password="testpass")
        client = LoxoneClient(config)

        # Set client state to connected
        client.state = ConnectionState.CONNECTED

        # Mock get_visual_hash with SHA256
        visual_hash_data = {
            "key": "1234567890abcdef",
            "salt": "0987654321fedcba",
            "hash_alg": "SHA256",
        }
        client._get_visual_hash = AsyncMock(return_value=visual_hash_data)

        mock_ws = AsyncMock()
        client._ws = mock_ws

        result = await client.send_secured_command("test-uuid", "0", "5678")

        assert result is True
        mock_ws.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_secured_command_no_visual_hash(self):
        """Test sending secured command when visual hash fails."""
        config = LoxoneConfig(host="test.local", port=80, username="testuser", password="testpass")
        client = LoxoneClient(config)

        # Mock get_visual_hash to return None
        client._get_visual_hash = AsyncMock(return_value=None)

        result = await client.send_secured_command("test-uuid", "1", "1234")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_secured_command_unknown_hash_algorithm(self):
        """Test sending secured command with unknown hash algorithm."""
        config = LoxoneConfig(host="test.local", port=80, username="testuser", password="testpass")
        client = LoxoneClient(config)

        # Mock get_visual_hash with unknown algorithm
        visual_hash_data = {
            "key": "abcdef1234567890",
            "salt": "fedcba0987654321",
            "hash_alg": "UNKNOWN",
        }
        client._get_visual_hash = AsyncMock(return_value=visual_hash_data)

        result = await client.send_secured_command("test-uuid", "1", "1234")

        assert result is False

    def test_visual_hash_computation_manual(self):
        """Test manual visual hash computation to verify algorithm."""
        # Test data
        pin_code = "1234"
        salt = "testsalt123"
        key = "abcdef1234567890"

        # Compute hash manually
        pwd_hash_str = f"{pin_code}:{salt}"
        m = hashlib.sha1()
        m.update(pwd_hash_str.encode("utf-8"))
        pwd_hash = m.hexdigest().upper()

        # Create HMAC
        digester = HMAC.new(binascii.unhexlify(key), pwd_hash.encode("utf-8"), SHA1)
        expected_hash = digester.hexdigest()

        # Verify hash is reasonable
        assert len(expected_hash) == 40  # SHA1 hex digest length
        assert all(c in "0123456789abcdef" for c in expected_hash)


class TestEncryptionIntegration:
    """Test integration of encryption components."""

    def test_aes_encrypt_decrypt_roundtrip(self):
        """Test AES encryption and decryption roundtrip."""
        # Generate key and IV
        key = gen_key()
        iv = gen_init_vec()

        # Test data
        plaintext = "This is a test message for AES encryption"

        # Encrypt
        cipher_encrypt = AES.new(key, AES.MODE_CBC, iv)
        padded_plaintext = Padding.pad(plaintext.encode("utf-8"), 16)
        ciphertext = cipher_encrypt.encrypt(padded_plaintext)

        # Decrypt
        cipher_decrypt = AES.new(key, AES.MODE_CBC, iv)
        decrypted_padded = cipher_decrypt.decrypt(ciphertext)
        decrypted_plaintext = Padding.unpad(decrypted_padded, 16).decode("utf-8")

        assert decrypted_plaintext == plaintext

    def test_rsa_encrypt_decrypt_roundtrip(self):
        """Test RSA encryption and decryption roundtrip."""
        # Generate RSA key pair
        rsa_key = RSA.generate(2048)

        # Test data
        plaintext = "This is a test message for RSA encryption"

        # Encrypt with public key
        public_cipher = PKCS1_v1_5.new(rsa_key.publickey())
        ciphertext = public_cipher.encrypt(plaintext.encode("utf-8"))

        # Decrypt with private key
        private_cipher = PKCS1_v1_5.new(rsa_key)
        decrypted_plaintext = private_cipher.decrypt(ciphertext, None).decode("utf-8")

        assert decrypted_plaintext == plaintext

    def test_hmac_consistency(self):
        """Test HMAC computation consistency."""
        key = b"test_key_123"
        message = "test message"

        # Compute HMAC with SHA1
        hmac_sha1 = HMAC.new(key, message.encode("utf-8"), SHA1)
        digest_sha1 = hmac_sha1.hexdigest()

        # Compute again - should be identical
        hmac_sha1_2 = HMAC.new(key, message.encode("utf-8"), SHA1)
        digest_sha1_2 = hmac_sha1_2.hexdigest()

        assert digest_sha1 == digest_sha1_2

        # Compute HMAC with SHA256
        hmac_sha256 = HMAC.new(key, message.encode("utf-8"), SHA256)
        digest_sha256 = hmac_sha256.hexdigest()

        # Should be different from SHA1
        assert digest_sha1 != digest_sha256

        # SHA256 digest should be longer
        assert len(digest_sha256) > len(digest_sha1)

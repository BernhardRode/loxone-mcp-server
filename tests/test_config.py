"""
Unit tests for configuration management module.

Tests cover:
- Loading configuration from environment variables
- Loading configuration from JSON files
- Token persistence (save/load)
- Error handling for missing/invalid configuration
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest

from loxone_mcp.config import LoxoneConfig


class TestLoxoneConfigFromEnv:
    """Test LoxoneConfig.from_env() method with various environment variable scenarios."""

    def test_from_env_with_all_required_vars(self):
        """Test loading configuration with all required environment variables."""
        env_vars = {
            "LOXONE_HOST": "192.168.1.100",
            "LOXONE_PORT": "8080",
            "LOXONE_USERNAME": "admin",
            "LOXONE_PASSWORD": "secret123",
            "LOXONE_TOKEN_PATH": "/custom/token.json",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            config = LoxoneConfig.from_env()

            assert config.host == "192.168.1.100"
            assert config.port == 8080
            assert config.username == "admin"
            assert config.password == "secret123"
            assert config.token_persist_path == "/custom/token.json"

    def test_from_env_with_default_port(self):
        """Test loading configuration with default port when LOXONE_PORT is not set."""
        env_vars = {
            "LOXONE_HOST": "miniserver.local",
            "LOXONE_USERNAME": "user",
            "LOXONE_PASSWORD": "pass",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            config = LoxoneConfig.from_env()

            assert config.host == "miniserver.local"
            assert config.port == 80  # Default port
            assert config.username == "user"
            assert config.password == "pass"
            assert config.token_persist_path == "./loxone_token.json"  # Default path

    def test_from_env_with_default_token_path(self):
        """Test loading configuration with default token path when LOXONE_TOKEN_PATH is not set."""
        env_vars = {
            "LOXONE_HOST": "192.168.1.50",
            "LOXONE_PORT": "443",
            "LOXONE_USERNAME": "admin",
            "LOXONE_PASSWORD": "password",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            config = LoxoneConfig.from_env()

            assert config.token_persist_path == "./loxone_token.json"

    def test_from_env_missing_host(self):
        """Test error handling when LOXONE_HOST is missing."""
        env_vars = {"LOXONE_PORT": "80", "LOXONE_USERNAME": "admin", "LOXONE_PASSWORD": "password"}

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError) as exc_info:
                LoxoneConfig.from_env()

            assert "Missing required environment variables: LOXONE_HOST" in str(exc_info.value)

    def test_from_env_missing_username(self):
        """Test error handling when LOXONE_USERNAME is missing."""
        env_vars = {
            "LOXONE_HOST": "192.168.1.100",
            "LOXONE_PORT": "80",
            "LOXONE_PASSWORD": "password",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError) as exc_info:
                LoxoneConfig.from_env()

            assert "Missing required environment variables: LOXONE_USERNAME" in str(exc_info.value)

    def test_from_env_missing_password(self):
        """Test error handling when LOXONE_PASSWORD is missing."""
        env_vars = {"LOXONE_HOST": "192.168.1.100", "LOXONE_PORT": "80", "LOXONE_USERNAME": "admin"}

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError) as exc_info:
                LoxoneConfig.from_env()

            assert "Missing required environment variables: LOXONE_PASSWORD" in str(exc_info.value)

    def test_from_env_missing_multiple_vars(self):
        """Test error handling when multiple required environment variables are missing."""
        env_vars = {"LOXONE_PORT": "80"}

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError) as exc_info:
                LoxoneConfig.from_env()

            error_msg = str(exc_info.value)
            assert "Missing required environment variables:" in error_msg
            assert "LOXONE_HOST" in error_msg
            assert "LOXONE_USERNAME" in error_msg
            assert "LOXONE_PASSWORD" in error_msg

    def test_from_env_invalid_port_non_numeric(self):
        """Test error handling when LOXONE_PORT is not a valid number."""
        env_vars = {
            "LOXONE_HOST": "192.168.1.100",
            "LOXONE_PORT": "not_a_number",
            "LOXONE_USERNAME": "admin",
            "LOXONE_PASSWORD": "password",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError) as exc_info:
                LoxoneConfig.from_env()

            assert "Invalid LOXONE_PORT value 'not_a_number'" in str(exc_info.value)

    def test_from_env_invalid_port_out_of_range_low(self):
        """Test error handling when LOXONE_PORT is below valid range."""
        env_vars = {
            "LOXONE_HOST": "192.168.1.100",
            "LOXONE_PORT": "0",
            "LOXONE_USERNAME": "admin",
            "LOXONE_PASSWORD": "password",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError) as exc_info:
                LoxoneConfig.from_env()

            assert "Port must be between 1 and 65535, got 0" in str(exc_info.value)

    def test_from_env_invalid_port_out_of_range_high(self):
        """Test error handling when LOXONE_PORT is above valid range."""
        env_vars = {
            "LOXONE_HOST": "192.168.1.100",
            "LOXONE_PORT": "65536",
            "LOXONE_USERNAME": "admin",
            "LOXONE_PASSWORD": "password",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError) as exc_info:
                LoxoneConfig.from_env()

            assert "Port must be between 1 and 65535, got 65536" in str(exc_info.value)

    def test_from_env_empty_string_values(self):
        """Test error handling when required environment variables are empty strings."""
        env_vars = {
            "LOXONE_HOST": "",
            "LOXONE_PORT": "80",
            "LOXONE_USERNAME": "",
            "LOXONE_PASSWORD": "",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ValueError) as exc_info:
                LoxoneConfig.from_env()

            error_msg = str(exc_info.value)
            assert "Missing required environment variables:" in error_msg
            assert "LOXONE_HOST" in error_msg
            assert "LOXONE_USERNAME" in error_msg
            assert "LOXONE_PASSWORD" in error_msg


class TestLoxoneConfigFromFile:
    """Test LoxoneConfig.from_file() method with various JSON file scenarios."""

    def test_from_file_valid_complete_config(self):
        """Test loading configuration from a valid JSON file with all fields."""
        config_data = {
            "host": "192.168.1.200",
            "port": 9090,
            "username": "testuser",
            "password": "testpass",
            "token_persist_path": "/tmp/test_token.json",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            config = LoxoneConfig.from_file(config_file)

            assert config.host == "192.168.1.200"
            assert config.port == 9090
            assert config.username == "testuser"
            assert config.password == "testpass"
            assert config.token_persist_path == "/tmp/test_token.json"
        finally:
            os.unlink(config_file)

    def test_from_file_minimal_config_with_defaults(self):
        """Test loading configuration from JSON file with only required fields."""
        config_data = {"host": "miniserver.example.com", "username": "user", "password": "pass"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            config = LoxoneConfig.from_file(config_file)

            assert config.host == "miniserver.example.com"
            assert config.port == 80  # Default port
            assert config.username == "user"
            assert config.password == "pass"
            assert config.token_persist_path == "./loxone_token.json"  # Default path
        finally:
            os.unlink(config_file)

    def test_from_file_with_custom_port_and_token_path(self):
        """Test loading configuration with custom port and token path."""
        config_data = {
            "host": "192.168.1.150",
            "port": 443,
            "username": "admin",
            "password": "secure_password",
            "token_persist_path": "/var/lib/loxone/token.json",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            config = LoxoneConfig.from_file(config_file)

            assert config.port == 443
            assert config.token_persist_path == "/var/lib/loxone/token.json"
        finally:
            os.unlink(config_file)

    def test_from_file_nonexistent_file(self):
        """Test error handling when configuration file doesn't exist."""
        nonexistent_file = "/path/that/does/not/exist.json"

        with pytest.raises(FileNotFoundError) as exc_info:
            LoxoneConfig.from_file(nonexistent_file)

        assert f"Configuration file not found: {nonexistent_file}" in str(exc_info.value)

    def test_from_file_invalid_json(self):
        """Test error handling when configuration file contains invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"host": "192.168.1.100", "invalid": json}')  # Invalid JSON
            config_file = f.name

        try:
            with pytest.raises(json.JSONDecodeError) as exc_info:
                LoxoneConfig.from_file(config_file)

            assert "Invalid JSON in configuration file" in str(exc_info.value)
        finally:
            os.unlink(config_file)

    def test_from_file_missing_host(self):
        """Test error handling when host field is missing from JSON."""
        config_data = {"port": 80, "username": "admin", "password": "password"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            with pytest.raises(ValueError) as exc_info:
                LoxoneConfig.from_file(config_file)

            assert "Missing required fields in configuration file: host" in str(exc_info.value)
        finally:
            os.unlink(config_file)

    def test_from_file_missing_username(self):
        """Test error handling when username field is missing from JSON."""
        config_data = {"host": "192.168.1.100", "port": 80, "password": "password"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            with pytest.raises(ValueError) as exc_info:
                LoxoneConfig.from_file(config_file)

            assert "Missing required fields in configuration file: username" in str(exc_info.value)
        finally:
            os.unlink(config_file)

    def test_from_file_missing_password(self):
        """Test error handling when password field is missing from JSON."""
        config_data = {"host": "192.168.1.100", "port": 80, "username": "admin"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            with pytest.raises(ValueError) as exc_info:
                LoxoneConfig.from_file(config_file)

            assert "Missing required fields in configuration file: password" in str(exc_info.value)
        finally:
            os.unlink(config_file)

    def test_from_file_missing_multiple_fields(self):
        """Test error handling when multiple required fields are missing from JSON."""
        config_data = {"port": 80}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            with pytest.raises(ValueError) as exc_info:
                LoxoneConfig.from_file(config_file)

            error_msg = str(exc_info.value)
            assert "Missing required fields in configuration file:" in error_msg
            assert "host" in error_msg
            assert "username" in error_msg
            assert "password" in error_msg
        finally:
            os.unlink(config_file)

    def test_from_file_invalid_port_type(self):
        """Test error handling when port is not an integer."""
        config_data = {
            "host": "192.168.1.100",
            "port": "not_an_integer",
            "username": "admin",
            "password": "password",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            with pytest.raises(ValueError) as exc_info:
                LoxoneConfig.from_file(config_file)

            assert "Port must be an integer between 1 and 65535" in str(exc_info.value)
        finally:
            os.unlink(config_file)

    def test_from_file_invalid_port_range_low(self):
        """Test error handling when port is below valid range."""
        config_data = {
            "host": "192.168.1.100",
            "port": 0,
            "username": "admin",
            "password": "password",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            with pytest.raises(ValueError) as exc_info:
                LoxoneConfig.from_file(config_file)

            assert "Port must be an integer between 1 and 65535, got 0" in str(exc_info.value)
        finally:
            os.unlink(config_file)

    def test_from_file_invalid_port_range_high(self):
        """Test error handling when port is above valid range."""
        config_data = {
            "host": "192.168.1.100",
            "port": 70000,
            "username": "admin",
            "password": "password",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            config_file = f.name

        try:
            with pytest.raises(ValueError) as exc_info:
                LoxoneConfig.from_file(config_file)

            assert "Port must be an integer between 1 and 65535, got 70000" in str(exc_info.value)
        finally:
            os.unlink(config_file)


class TestLoxoneConfigTokenPersistence:
    """Test token save/load functionality."""

    def test_save_and_load_token_success(self):
        """Test successful token save and load cycle."""
        config = LoxoneConfig(host="192.168.1.100", port=80, username="admin", password="password")

        token_data = {
            "token": "abc123def456",
            "key": "encryption_key_here",
            "expires_at": 1234567890,
            "user": "admin",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            token_file = Path(temp_dir) / "test_token.json"
            config.token_persist_path = str(token_file)

            # Save token
            config.save_token(token_data)

            # Verify file was created
            assert token_file.exists()

            # Load token
            loaded_token = config.load_token()

            assert loaded_token == token_data

    def test_save_token_creates_parent_directories(self):
        """Test that save_token creates parent directories if they don't exist."""
        config = LoxoneConfig(host="192.168.1.100", port=80, username="admin", password="password")

        token_data = {"token": "test_token"}

        with tempfile.TemporaryDirectory() as temp_dir:
            nested_path = Path(temp_dir) / "nested" / "directories" / "token.json"
            config.token_persist_path = str(nested_path)

            # Save token (should create nested directories)
            config.save_token(token_data)

            # Verify file and directories were created
            assert nested_path.exists()
            assert nested_path.parent.exists()

            # Verify content
            loaded_token = config.load_token()
            assert loaded_token == token_data

    def test_load_token_nonexistent_file(self):
        """Test load_token returns None when token file doesn't exist."""
        config = LoxoneConfig(
            host="192.168.1.100",
            port=80,
            username="admin",
            password="password",
            token_persist_path="/path/that/does/not/exist.json",
        )

        result = config.load_token()
        assert result is None

    def test_load_token_invalid_json(self):
        """Test load_token returns None when token file contains invalid JSON."""
        config = LoxoneConfig(host="192.168.1.100", port=80, username="admin", password="password")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"invalid": json content}')  # Invalid JSON
            config.token_persist_path = f.name

        try:
            result = config.load_token()
            assert result is None
        finally:
            os.unlink(f.name)

    def test_save_token_permission_error(self):
        """Test save_token raises PermissionError when file cannot be written."""
        config = LoxoneConfig(
            host="192.168.1.100",
            port=80,
            username="admin",
            password="password",
            token_persist_path="/root/readonly_token.json",  # Typically not writable
        )

        token_data = {"token": "test_token"}

        # This test may not work on all systems, so we'll use a mock
        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            with pytest.raises(PermissionError):
                config.save_token(token_data)

    def test_load_token_permission_error(self):
        """Test load_token returns None when file cannot be read due to permissions."""
        config = LoxoneConfig(host="192.168.1.100", port=80, username="admin", password="password")

        # Create a file first
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"token": "test"}, f)
            config.token_persist_path = f.name

        try:
            # Mock permission error on read
            with patch("builtins.open", side_effect=PermissionError("Permission denied")):
                result = config.load_token()
                assert result is None
        finally:
            os.unlink(f.name)

    def test_save_token_os_error(self):
        """Test save_token raises OSError for other filesystem errors."""
        config = LoxoneConfig(host="192.168.1.100", port=80, username="admin", password="password")

        token_data = {"token": "test_token"}

        with patch("builtins.open", side_effect=OSError("Disk full")):
            with pytest.raises(OSError):
                config.save_token(token_data)

    def test_load_token_os_error(self):
        """Test load_token returns None for other filesystem errors."""
        config = LoxoneConfig(host="192.168.1.100", port=80, username="admin", password="password")

        # Create a file first
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"token": "test"}, f)
            config.token_persist_path = f.name

        try:
            # Mock OS error on read
            with patch("builtins.open", side_effect=OSError("I/O error")):
                result = config.load_token()
                assert result is None
        finally:
            os.unlink(f.name)

    def test_token_persistence_with_complex_data(self):
        """Test token persistence with complex nested data structures."""
        config = LoxoneConfig(host="192.168.1.100", port=80, username="admin", password="password")

        complex_token_data = {
            "token": "very_long_token_string_here",
            "key": "encryption_key_with_special_chars_!@#$%",
            "expires_at": 1234567890,
            "user_info": {
                "username": "admin",
                "permissions": ["read", "write", "admin"],
                "last_login": "2024-01-01T12:00:00Z",
            },
            "metadata": {
                "version": "1.0",
                "created_by": "loxone-mcp-server",
                "features": ["websocket", "encryption", "auto_refresh"],
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            token_file = Path(temp_dir) / "complex_token.json"
            config.token_persist_path = str(token_file)

            # Save complex token data
            config.save_token(complex_token_data)

            # Load and verify
            loaded_token = config.load_token()
            assert loaded_token == complex_token_data

            # Verify specific nested values
            assert loaded_token["user_info"]["username"] == "admin"
            assert loaded_token["metadata"]["features"] == [
                "websocket",
                "encryption",
                "auto_refresh",
            ]

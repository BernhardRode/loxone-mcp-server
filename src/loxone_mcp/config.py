"""
Configuration management for Loxone MCP Server.

Handles loading configuration from environment variables or JSON files,
and manages token persistence for authentication.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Configure enhanced logging for configuration management
logger.setLevel(logging.DEBUG)  # Allow debug messages for configuration troubleshooting


@dataclass
class LoxoneConfig:
    """Configuration for Loxone Miniserver connection."""

    host: str
    port: int
    username: str
    password: str
    token_persist_path: str = "./loxone_token.json"

    @classmethod
    def xdg_config_path(cls) -> Path:
        """Return the XDG config file path: $XDG_CONFIG_HOME/loxone-mcp/config.json."""
        xdg = os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        return Path(xdg) / "loxone-mcp" / "config.json"

    @classmethod
    def from_xdg(cls) -> Optional["LoxoneConfig"]:
        """Load configuration from XDG config directory. Returns None if not found."""
        path = cls.xdg_config_path()
        if not path.exists():
            return None
        try:
            return cls.from_file(str(path))
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning(f"Invalid XDG config at {path}: {e}")
            return None

    @classmethod
    def from_env(cls) -> "LoxoneConfig":
        """
        Load configuration from environment variables.

        Required environment variables:
        - LOXONE_HOST: Miniserver hostname or IP address
        - LOXONE_PORT: Miniserver port (default: 80)
        - LOXONE_USERNAME: Username for authentication
        - LOXONE_PASSWORD: Password for authentication

        Optional environment variables:
        - LOXONE_TOKEN_PATH: Path to persist token (default: ./loxone_token.json)

        Returns:
            LoxoneConfig instance

        Raises:
            ValueError: If required configuration is missing
        """
        host = os.getenv("LOXONE_HOST")
        port_str = os.getenv("LOXONE_PORT", "80")
        username = os.getenv("LOXONE_USERNAME")
        password = os.getenv("LOXONE_PASSWORD")
        token_persist_path = os.getenv("LOXONE_TOKEN_PATH", "./loxone_token.json")

        # Validate required fields with detailed error messages
        missing_fields = []
        if not host:
            missing_fields.append("LOXONE_HOST")
        if not username:
            missing_fields.append("LOXONE_USERNAME")
        if not password:
            missing_fields.append("LOXONE_PASSWORD")

        if missing_fields:
            error_msg = f"Missing required environment variables: {', '.join(missing_fields)}"
            logger.error(error_msg)
            logger.error("Required environment variables:")
            logger.error("  LOXONE_HOST - Miniserver hostname or IP address")
            logger.error("  LOXONE_USERNAME - Username for authentication")
            logger.error("  LOXONE_PASSWORD - Password for authentication")
            logger.error("Optional environment variables:")
            logger.error("  LOXONE_PORT - Miniserver port (default: 80)")
            logger.error(
                "  LOXONE_TOKEN_PATH - Token persistence path (default: ./loxone_token.json)"
            )
            raise ValueError(error_msg)

        # Validate and convert port
        try:
            port = int(port_str)
            if port < 1 or port > 65535:
                raise ValueError(f"Port must be between 1 and 65535, got {port}")
        except ValueError as e:
            raise ValueError(f"Invalid LOXONE_PORT value '{port_str}': {e}")

        logger.info(
            f"Loaded configuration from environment: host={host}, port={port}, username={username}"
        )

        return cls(
            host=host or "",
            port=port,
            username=username or "",
            password=password or "",
            token_persist_path=token_persist_path,
        )

    @classmethod
    def from_file(cls, path: str) -> "LoxoneConfig":
        """
        Load configuration from a JSON file.

        Expected JSON format:
        {
            "host": "192.168.1.100",
            "port": 80,
            "username": "admin",
            "password": "password",
            "token_persist_path": "./loxone_token.json"
        }

        Args:
            path: Path to the JSON configuration file

        Returns:
            LoxoneConfig instance

        Raises:
            FileNotFoundError: If the configuration file doesn't exist
            ValueError: If required configuration is missing or invalid
            json.JSONDecodeError: If the file contains invalid JSON
        """
        config_path = Path(path)

        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        try:
            with open(config_path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(f"Invalid JSON in configuration file: {e.msg}", e.doc, e.pos)

        # Validate required fields
        missing_fields = []
        if "host" not in data:
            missing_fields.append("host")
        if "username" not in data:
            missing_fields.append("username")
        if "password" not in data:
            missing_fields.append("password")

        if missing_fields:
            raise ValueError(
                f"Missing required fields in configuration file: {', '.join(missing_fields)}"
            )

        # Get port with default
        port = data.get("port", 80)

        # Validate port
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise ValueError(f"Port must be an integer between 1 and 65535, got {port}")

        # Get token persist path with default
        token_persist_path = data.get("token_persist_path", "./loxone_token.json")

        logger.info(f"Loaded configuration from file: {path}")

        return cls(
            host=data["host"],
            port=port,
            username=data["username"],
            password=data["password"],
            token_persist_path=token_persist_path,
        )

    def save_token(self, token_data: dict) -> None:
        """
        Persist token data to disk as JSON.

        Args:
            token_data: Dictionary containing token information to persist

        Raises:
            OSError: If the file cannot be written
        """
        token_path = Path(self.token_persist_path)

        try:
            # Create parent directories if they don't exist
            token_path.parent.mkdir(parents=True, exist_ok=True)

            # Write token data to file
            with open(token_path, "w") as f:
                json.dump(token_data, f, indent=2)

            logger.info(f"Token persisted to {self.token_persist_path}")

        except PermissionError as e:
            logger.error(f"Permission denied saving token to {self.token_persist_path}: {e}")
            logger.error("Check file/directory permissions for token persistence")
            raise
        except OSError as e:
            logger.error(f"OS error saving token to {self.token_persist_path}: {e}")
            logger.error("This may indicate disk space or filesystem issues")
            raise

    def load_token(self) -> Optional[dict]:
        """
        Load persisted token from disk.

        Returns:
            Dictionary containing token data if file exists and is valid,
            None if file doesn't exist or contains invalid JSON
        """
        token_path = Path(self.token_persist_path)

        if not token_path.exists():
            logger.debug(f"Token file not found: {self.token_persist_path}")
            return None

        try:
            with open(token_path, "r") as f:
                token_data = json.load(f)

            logger.info(f"Token loaded from {self.token_persist_path}")
            return token_data

        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in token file {self.token_persist_path}: {e}")
            logger.warning("Token file may be corrupted, will create new token on authentication")
            return None
        except PermissionError as e:
            logger.warning(f"Permission denied reading token file {self.token_persist_path}: {e}")
            logger.warning("Check file permissions for token persistence")
            return None
        except OSError as e:
            logger.warning(f"OS error reading token file {self.token_persist_path}: {e}")
            logger.warning("This may indicate filesystem issues")
            return None

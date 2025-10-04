"""
Connection management for multi-client Loxone MCP Server.

Manages multiple client sessions, each with their own Loxone connection
and device state. Handles session creation, cleanup, and lookup.
"""

import asyncio
import logging
from typing import Dict, Optional

from .config import LoxoneConfig
from .client_session import ClientSession

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages multiple client sessions for the Loxone MCP Server.

    Each client can connect with their own credentials to different
    Loxone Miniservers. The connection manager handles session lifecycle
    and provides thread-safe access to client sessions.
    """

    def __init__(self):
        """Initialize the connection manager."""
        self._sessions: Dict[str, ClientSession] = {}
        self._session_lock = asyncio.Lock()

        logger.info("ConnectionManager initialized")

    async def create_session(self, client_id: str, config: LoxoneConfig) -> ClientSession:
        """
        Create a new client session with the provided configuration.

        Args:
            client_id: Unique identifier for the client
            config: LoxoneConfig instance with connection details

        Returns:
            ClientSession instance for the client

        Raises:
            ValueError: If client_id is empty or session already exists
            ConnectionError: If unable to establish connection to Miniserver
        """
        if not client_id:
            raise ValueError("Client ID cannot be empty")

        async with self._session_lock:
            # Check if session already exists
            if client_id in self._sessions:
                logger.warning(
                    f"Session already exists for client {client_id}, removing old session"
                )
                await self._cleanup_session(client_id)

            logger.info(f"Creating new session for client {client_id}")

            try:
                # Create new client session
                session = ClientSession(client_id, config)

                # Initialize the session (connect to Miniserver)
                await session.initialize()

                # Store session
                self._sessions[client_id] = session

                logger.info(f"Successfully created session for client {client_id}")
                return session

            except Exception as e:
                logger.error(f"Failed to create session for client {client_id}: {e}")
                # Clean up any partial session
                if client_id in self._sessions:
                    await self._cleanup_session(client_id)
                raise ConnectionError(f"Unable to create session for client {client_id}: {e}")

    async def remove_session(self, client_id: str) -> None:
        """
        Remove and clean up a client session.

        Args:
            client_id: Unique identifier for the client
        """
        if not client_id:
            return

        async with self._session_lock:
            await self._cleanup_session(client_id)

    async def _cleanup_session(self, client_id: str) -> None:
        """
        Internal method to clean up a session.

        Args:
            client_id: Unique identifier for the client
        """
        session = self._sessions.get(client_id)
        if session:
            logger.info(f"Cleaning up session for client {client_id}")
            try:
                await session.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up session for client {client_id}: {e}")
            finally:
                del self._sessions[client_id]
                logger.info(f"Session removed for client {client_id}")

    def get_session(self, client_id: str) -> Optional[ClientSession]:
        """
        Get a client session by ID.

        Args:
            client_id: Unique identifier for the client

        Returns:
            ClientSession instance if found, None otherwise
        """
        if not client_id:
            return None

        session = self._sessions.get(client_id)
        if not session:
            logger.warning(f"No session found for client {client_id}")

        return session

    async def cleanup_all(self) -> None:
        """
        Clean up all client sessions.

        This method should be called during server shutdown to ensure
        all connections are properly closed and resources are released.
        """
        logger.info("Cleaning up all client sessions")

        async with self._session_lock:
            # Get list of client IDs to avoid modifying dict during iteration
            client_ids = list(self._sessions.keys())

            # Clean up each session
            cleanup_tasks = []
            for client_id in client_ids:
                task = asyncio.create_task(self._cleanup_session(client_id))
                cleanup_tasks.append(task)

            # Wait for all cleanup tasks to complete
            if cleanup_tasks:
                try:
                    await asyncio.gather(*cleanup_tasks, return_exceptions=True)
                except Exception as e:
                    logger.error(f"Error during session cleanup: {e}")

        logger.info("All client sessions cleaned up")

    def get_session_count(self) -> int:
        """
        Get the number of active sessions.

        Returns:
            Number of active client sessions
        """
        return len(self._sessions)

    def get_client_ids(self) -> list[str]:
        """
        Get list of active client IDs.

        Returns:
            List of client IDs with active sessions
        """
        return list(self._sessions.keys())

    def has_session(self, client_id: str) -> bool:
        """
        Check if a session exists for the given client ID.

        Args:
            client_id: Unique identifier for the client

        Returns:
            True if session exists, False otherwise
        """
        return client_id in self._sessions if client_id else False

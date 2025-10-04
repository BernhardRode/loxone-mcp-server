"""
Loxone WebSocket Client

Handles communication with Loxone Miniserver via WebSocket protocol.
Refactored from Home Assistant integration to be standalone.
"""

import asyncio
import binascii
import hashlib
import json
import logging
import time
import urllib.request as req
import uuid
from base64 import b64encode
from datetime import datetime
from enum import Enum
import struct
from struct import unpack
from typing import Callable, Optional, Dict, Any

import httpx
import websockets
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.Hash import HMAC, SHA1, SHA256
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes
from Crypto.Util import Padding
from websockets.protocol import State

try:
    from .config import LoxoneConfig
except ImportError:
    from config import LoxoneConfig

logger = logging.getLogger(__name__)

# Configure enhanced logging for this module
logger.setLevel(logging.DEBUG)  # Allow debug messages for detailed troubleshooting

# Constants
TIMEOUT = 30
KEEP_ALIVE_PERIOD = 120
RECONNECT_INITIAL_DELAY = 1  # Initial reconnection delay in seconds
RECONNECT_MAX_DELAY = 300  # Maximum reconnection delay (5 minutes)
RECONNECT_BACKOFF_FACTOR = 2  # Exponential backoff multiplier
IV_BYTES = 16
AES_KEY_SIZE = 32
SALT_BYTES = 16
SALT_MAX_AGE_SECONDS = 60 * 60
SALT_MAX_USE_COUNT = 30
TOKEN_PERMISSION = 4  # 2=web, 4=app
LOXAPPPATH = "/data/LoxAPP3.json"
ERROR_VALUE = -1

# Commands
CMD_GET_PUBLIC_KEY = "jdev/sys/getPublicKey"
CMD_KEY_EXCHANGE = "jdev/sys/keyexchange/"
CMD_GET_KEY_AND_SALT = "jdev/sys/getkey2/"
CMD_REQUEST_TOKEN = "jdev/sys/gettoken/"
CMD_REQUEST_TOKEN_JSON_WEB = "jdev/sys/getjwt/"
CMD_GET_KEY = "jdev/sys/getkey"
CMD_AUTH_WITH_TOKEN = "authwithtoken/"
CMD_REFRESH_TOKEN = "jdev/sys/refreshtoken/"
CMD_REFRESH_TOKEN_JSON_WEB = "jdev/sys/refreshjwt/"
CMD_ENCRYPT_CMD = "jdev/sys/enc/"
CMD_ENABLE_UPDATES = "jdev/sps/enablebinstatusupdate"
CMD_GET_VISUAL_PASSWD = "jdev/sys/getvisusalt/"


class MessageType(Enum):
    """Loxone message types."""

    TextMessage = 0
    BinaryFile = 1
    EventTableValueStates = 2
    EventTableTextStates = 3
    EventTableDaytimerStates = 4
    OutOfService = 5
    Keepalive = 6
    EventTableWeatherStates = 7


class ConnectionState(Enum):
    """Connection state tracking."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"


class LoxoneException(Exception):
    """Base class for all Loxone Exceptions."""

    pass


class LoxoneHTTPStatusError(LoxoneException):
    """An exception indicating an unusual http response from the miniserver."""

    pass


def gen_init_vec() -> bytes:
    """Generate initialization vector for AES encryption."""
    return get_random_bytes(IV_BYTES)


def gen_key() -> bytes:
    """Generate AES key."""
    return get_random_bytes(AES_KEY_SIZE)


def time_elapsed_in_seconds() -> int:
    """Get current time in seconds since epoch."""
    return int(round(time.time()))


def detect_encoding(byte_string: bytes) -> Optional[str]:
    """Detect encoding of byte string."""
    encodings = [
        "utf-8",
        "iso-8859-1",
        "ascii",
        "utf-16",
        "utf-32",
        "latin-1",
        "cp1252",
        "mac-roman",
        "big5",
        "shift_jis",
        "euc-jp",
        "gb2312",
    ]

    for encoding in encodings:
        try:
            byte_string.decode(encoding)
            return encoding
        except (UnicodeDecodeError, AttributeError):
            continue
    return None


def check_and_decode_if_needed(message):
    """Decode message if it's bytes, handling various encodings."""
    if isinstance(message, bytes):
        try:
            return message.decode("utf-8")
        except UnicodeDecodeError:
            logger.debug("Decoding problem for message, trying to detect encoding...")
            encoding = detect_encoding(message)
            if encoding:
                return message.decode(encoding)
            logger.warning("No valid encoding found, replacing invalid characters")
            return message.decode("utf-8", errors="replace")
    return message


class LxToken:
    """Loxone authentication token."""

    def __init__(self, token: str = "", valid_until: int = 0, hash_alg: str = "SHA1"):
        self._token = token
        self._valid_until = valid_until
        self._hash_alg = hash_alg

    def get_seconds_to_expire(self) -> int:
        """Get seconds until token expires."""
        dt = datetime.strptime("1.1.2009", "%d.%m.%Y")
        try:
            start_date = int(dt.strftime("%s"))
        except Exception:
            start_date = int(dt.timestamp())
        start_date = int(start_date) + self._valid_until
        return start_date - int(round(time.time()))

    @property
    def token(self) -> str:
        return self._token

    @property
    def valid_until(self) -> int:
        return self._valid_until

    def set_valid_until(self, value: int) -> None:
        self._valid_until = value

    @property
    def hash_alg(self) -> str:
        return self._hash_alg


class LxJsonKeySalt:
    """Key and salt response from Loxone."""

    def __init__(self):
        self.key: Optional[str] = None
        self.salt: Optional[str] = None
        self.hash_alg: str = "SHA1"
        self.time_elapsed_in_seconds: Optional[int] = None

    def read_user_salt_response(self, response: str) -> None:
        """Parse key and salt from Loxone response."""
        js = json.loads(response, strict=False)
        value = js["LL"]["value"]
        self.key = value["key"]
        self.salt = value["salt"]
        self.hash_alg = value.get("hashAlg", "SHA1")


class LoxoneClient:
    """
    Loxone WebSocket client for Miniserver communication.

    Handles connection, authentication, encryption, and message processing.
    """

    def __init__(self, config: LoxoneConfig):
        """
        Initialize Loxone client.

        Args:
            config: LoxoneConfig instance with connection details
        """
        self.config = config
        self._username = config.username
        self._password = config.password
        self._host = config.host
        self._port = config.port

        # Build base URL
        if self._port == 443:
            self._base_url = f"https://{self._host}"
        elif self._port == 80:
            self._base_url = f"http://{self._host}"
        else:
            self._base_url = f"http://{self._host}:{self._port}"

        # Encryption
        self._iv = gen_init_vec()
        self._key = gen_key()
        self._public_key: Optional[str] = None
        self._rsa_cipher = None
        self._session_key: Optional[str] = None
        self._encryption_ready = False

        # Salt management
        self._salt = ""
        self._salt_used_count = 0
        self._salt_time_stamp = 0

        # Token management
        self._token = LxToken()
        self._load_persisted_token()

        # WebSocket
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._current_message_type: Optional[MessageType] = None

        # Connection state
        self.state = ConnectionState.DISCONNECTED

        # Callbacks
        self._state_callbacks: list[Callable] = []

        # Background tasks
        self.background_tasks: set = set()
        self._keepalive_task: Optional[asyncio.Task] = None
        self._message_processor_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None

        # Reconnection management
        self._reconnect_delay = RECONNECT_INITIAL_DELAY
        self._should_reconnect = True
        self._manual_disconnect = False

        # Version info
        self._version = 0.0

        logger.info(f"LoxoneClient initialized for {self._base_url}")

    def _load_persisted_token(self) -> None:
        """Load persisted token from disk if available."""
        token_data = self.config.load_token()
        if token_data:
            try:
                self._token = LxToken(
                    token=token_data.get("token", ""),
                    valid_until=token_data.get("valid_until", 0),
                    hash_alg=token_data.get("hash_alg", "SHA1"),
                )
                logger.info("Loaded persisted token")
            except Exception as e:
                logger.warning(f"Failed to load persisted token: {e}")

    def _persist_token(self) -> None:
        """Persist current token to disk."""
        token_data = {
            "token": self._token.token,
            "valid_until": self._token.valid_until,
            "hash_alg": self._token.hash_alg,
        }
        try:
            self.config.save_token(token_data)
        except Exception as e:
            logger.error(f"Failed to persist token: {e}")

    def register_state_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Register a callback for state update notifications.

        Args:
            callback: Async function to call with state updates
        """
        self._state_callbacks.append(callback)
        logger.debug(f"Registered state callback: {callback.__name__}")

    async def connect(self) -> bool:
        """
        Establish connection to Loxone Miniserver.

        Returns:
            True if connection successful, False otherwise
        """
        logger.info(f"Connecting to Loxone Miniserver at {self._base_url}")
        self.state = ConnectionState.CONNECTING

        try:
            # Get public key
            if not await self._get_public_key():
                logger.error("Failed to get public key")
                self.state = ConnectionState.DISCONNECTED
                return False

            # Initialize RSA cipher
            if not self._init_rsa_cipher():
                logger.error("Failed to initialize RSA cipher")
                self.state = ConnectionState.DISCONNECTED
                return False

            # Generate session key
            if not self._generate_session_key():
                logger.error("Failed to generate session key")
                self.state = ConnectionState.DISCONNECTED
                return False

            # Connect WebSocket
            ws_url = self._base_url.replace("https", "wss").replace("http", "ws")
            ws_url = f"{ws_url}/ws/rfc6455"

            logger.debug(f"Connecting to WebSocket: {ws_url}")
            self._ws = await websockets.connect(ws_url, open_timeout=TIMEOUT)

            # Exchange keys
            await self._ws.send(f"{CMD_KEY_EXCHANGE}{self._session_key}")

            # Parse key exchange response
            message = await self._ws.recv()
            await self._parse_loxone_message(message)
            if self._current_message_type != MessageType.TextMessage:
                logger.error("Unexpected message type during key exchange")
                await self.disconnect()
                return False

            # Get JSON response
            message = await self._ws.recv()
            resp_json = json.loads(message)
            if not self._check_response_code(resp_json, "200"):
                logger.error("Key exchange failed")
                await self.disconnect()
                return False

            self._encryption_ready = True
            logger.info("Encryption established")

            # Authenticate
            if not await self._authenticate():
                logger.error("Authentication failed")
                await self.disconnect()
                return False

            # Enable status updates
            command = CMD_ENABLE_UPDATES
            enc_command = await self._encrypt(command)
            await self._ws.send(enc_command)
            await self._ws.recv()  # Acknowledge
            await self._ws.recv()  # Response

            self.state = ConnectionState.CONNECTED
            logger.info("Successfully connected to Loxone Miniserver")
            return True

        except websockets.exceptions.InvalidURI as e:
            logger.error(f"Invalid WebSocket URI: {e}")
            logger.error(f"Check the host and port configuration: {self._base_url}")
            self.state = ConnectionState.DISCONNECTED
            return False
        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"WebSocket connection closed during handshake: {e}")
            logger.error("This may indicate network issues or server unavailability")
            self.state = ConnectionState.DISCONNECTED
            return False
        except asyncio.TimeoutError:
            logger.error(f"Connection timeout after {TIMEOUT} seconds")
            logger.error(f"Check network connectivity to {self._base_url}")
            self.state = ConnectionState.DISCONNECTED
            return False
        except OSError as e:
            logger.error(f"Network error connecting to Miniserver: {e}")
            logger.error(f"Check if {self._host}:{self._port} is reachable")
            self.state = ConnectionState.DISCONNECTED
            return False
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from Miniserver: {e}")
            logger.error("This may indicate an incompatible Miniserver version or configuration")
            self.state = ConnectionState.DISCONNECTED
            return False
        except Exception as e:
            logger.error(f"Unexpected connection error: {e}", exc_info=True)
            logger.error(
                f"Connection context: host={self._host}, port={self._port}, base_url={self._base_url}"
            )
            self.state = ConnectionState.DISCONNECTED
            return False

    async def disconnect(self) -> None:
        """Gracefully close the WebSocket connection."""
        logger.info("Disconnecting from Loxone Miniserver")
        self._manual_disconnect = True
        self._should_reconnect = False
        self.state = ConnectionState.DISCONNECTED

        # Cancel background tasks
        await self._cancel_background_tasks()

        if self._ws and self._ws.state != State.CLOSED:
            try:
                await self._ws.close()
                logger.info("WebSocket connection closed")
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")

    async def start(self) -> None:
        """
        Start background tasks for connection management.

        This includes:
        - Keepalive mechanism to maintain connection
        - Message processing loop for state updates
        - Automatic reconnection on connection loss
        """
        logger.info("Starting background tasks")

        # Start keepalive task
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        self.background_tasks.add(self._keepalive_task)
        self._keepalive_task.add_done_callback(self.background_tasks.discard)

        # Start message processor task
        self._message_processor_task = asyncio.create_task(self._message_processor_loop())
        self.background_tasks.add(self._message_processor_task)
        self._message_processor_task.add_done_callback(self.background_tasks.discard)

        logger.info("Background tasks started")

    async def _cancel_background_tasks(self) -> None:
        """Cancel all background tasks."""
        logger.debug("Cancelling background tasks")

        tasks_to_cancel = [self._keepalive_task, self._message_processor_task, self._reconnect_task]

        for task in tasks_to_cancel:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Cancel any remaining tasks in the set
        for task in list(self.background_tasks):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self.background_tasks.clear()
        logger.debug("Background tasks cancelled")

    async def _keepalive_loop(self) -> None:
        """
        Periodic keepalive mechanism to maintain connection.

        Sends ping messages to prevent connection timeout.
        """
        logger.info("Keepalive loop started")

        try:
            while self._should_reconnect:
                if self.state == ConnectionState.CONNECTED and self._ws:
                    try:
                        # Send keepalive ping
                        await asyncio.wait_for(self._ws.ping(), timeout=TIMEOUT)
                        logger.debug("Keepalive ping sent")

                        # Check if token needs refresh (refresh 5 minutes before expiry)
                        if self._token.get_seconds_to_expire() < 300:
                            logger.info("Token expiring soon, refreshing...")
                            await self._refresh_token()

                    except asyncio.TimeoutError:
                        logger.warning("Keepalive ping timeout")
                        await self._handle_connection_loss()
                    except Exception as e:
                        logger.error(f"Keepalive error: {e}")
                        await self._handle_connection_loss()

                # Wait before next keepalive
                await asyncio.sleep(KEEP_ALIVE_PERIOD)

        except asyncio.CancelledError:
            logger.info("Keepalive loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Keepalive loop error: {e}", exc_info=True)

    async def _message_processor_loop(self) -> None:
        """
        Process incoming messages from WebSocket.

        Handles state updates and invokes registered callbacks.
        """
        logger.info("Message processor loop started")

        try:
            while self._should_reconnect:
                if self.state == ConnectionState.CONNECTED and self._ws:
                    try:
                        # Receive message with timeout
                        message = await asyncio.wait_for(
                            self._ws.recv(), timeout=TIMEOUT * 2  # Longer timeout for messages
                        )

                        # Process the message
                        await self._process_message(message)

                    except asyncio.TimeoutError:
                        # No message received, yield control and continue
                        await asyncio.sleep(0.01)
                        continue
                    except websockets.exceptions.ConnectionClosed as e:
                        logger.warning(f"WebSocket connection closed: {e}")
                        logger.info(
                            "Connection will be automatically restored if reconnection is enabled"
                        )
                        await self._handle_connection_loss()
                        break  # Exit loop on connection closed
                    except StopAsyncIteration:
                        # End of async iteration (typically from mocks in tests)
                        logger.debug("Received StopAsyncIteration - ending message processing")
                        break
                    except websockets.exceptions.WebSocketException as e:
                        logger.error(f"WebSocket protocol error: {e}")
                        logger.warning("WebSocket protocol issue detected, triggering reconnection")
                        await self._handle_connection_loss()
                        break
                    except json.JSONDecodeError as e:
                        logger.warning(f"Received malformed JSON message: {e}")
                        logger.debug(f"Malformed message content: {str(message)[:200]}...")
                        # Continue processing other messages
                        continue
                    except Exception as e:
                        logger.error(f"Unexpected message processing error: {e}", exc_info=True)
                        logger.warning("Continuing message processing despite error")
                        # Continue processing other messages
                else:
                    # Not connected, wait before checking again
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Message processor loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Message processor loop error: {e}", exc_info=True)

    async def _process_message(self, message) -> None:
        """
        Process a received message.

        Args:
            message: Raw message from WebSocket (bytes or str)
        """
        try:
            # Validate message
            if message is None:
                logger.warning("Received None message, skipping")
                return

            # Parse message header if it's a binary header
            if isinstance(message, bytes) and len(message) == 8:
                await self._parse_loxone_message(message)
                return

            # Skip empty messages
            if not message:
                logger.debug("Received empty message, skipping")
                return

            # Parse message content based on current message type
            parsed_data = await self._parse_message_content(message)

            # If we have state updates, notify callbacks
            if parsed_data and isinstance(parsed_data, dict):
                # Check if this is a state update (not a control response)
                if self._current_message_type in [
                    MessageType.EventTableValueStates,
                    MessageType.EventTableTextStates,
                    MessageType.EventTableDaytimerStates,
                    MessageType.EventTableWeatherStates,
                ]:
                    await self._notify_state_callbacks(parsed_data)

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            # Continue processing - don't let one bad message crash the processor

    async def _parse_message_content(self, message) -> Optional[Dict[str, Any]]:
        """
        Parse message content based on message type.

        Args:
            message: Raw message content (bytes or str)

        Returns:
            Parsed message data as dictionary, or None
        """
        try:
            if self._current_message_type == MessageType.TextMessage:
                # Text message - decode and parse JSON
                decoded = check_and_decode_if_needed(message)
                try:
                    return json.loads(decoded)
                except json.JSONDecodeError:
                    logger.debug(f"Non-JSON text message: {decoded[:100]}")
                    return {"text": decoded}

            elif self._current_message_type == MessageType.EventTableValueStates:
                # Binary state updates - parse UUID and value pairs
                return self._parse_value_states(message)

            elif self._current_message_type == MessageType.EventTableTextStates:
                # Text state updates - parse UUID and text pairs
                return self._parse_text_states(message)

            elif self._current_message_type == MessageType.BinaryFile:
                # Binary file data - typically LoxAPP3.json or other files
                logger.debug("Binary file message received")
                return {
                    "binary_file": True,
                    "size": len(message) if isinstance(message, bytes) else 0,
                }

            elif self._current_message_type == MessageType.EventTableDaytimerStates:
                # Daytimer state updates - similar to value states but for timers
                logger.debug("Daytimer state update received")
                return self._parse_daytimer_states(message)

            elif self._current_message_type == MessageType.Keepalive:
                logger.debug("Keepalive message received")
                return {"keepalive": True}

            elif self._current_message_type == MessageType.EventTableWeatherStates:
                logger.debug("Weather state update received")
                return self._parse_weather_states(message)

            elif self._current_message_type == MessageType.OutOfService:
                logger.warning("Out of service message received")
                return {"out_of_service": True}

            else:
                logger.debug(f"Unhandled message type: {self._current_message_type}")
                return {}

        except Exception as e:
            logger.error(f"Error parsing message content: {e}", exc_info=True)
            return None

    def _parse_value_states(self, message: bytes) -> Dict[str, float]:
        """
        Parse binary value state updates.

        Each state update is 24 bytes:
        - 16 bytes: UUID (little-endian)
        - 8 bytes: double value

        Args:
            message: Binary message containing state updates

        Returns:
            Dictionary mapping UUID strings to values
        """
        event_dict = {}

        try:
            length = len(message)
            num_updates = length // 24

            for i in range(num_updates):
                start = i * 24
                end = start + 24
                packet = message[start:end]

                # Parse UUID (little-endian)
                event_uuid = uuid.UUID(bytes_le=packet[0:16])
                fields = event_uuid.urn.replace("urn:uuid:", "").split("-")
                uuid_str = f"{fields[0]}-{fields[1]}-{fields[2]}-{fields[3]}{fields[4]}"

                # Parse value (double)
                value = unpack("d", packet[16:24])[0]

                event_dict[uuid_str] = value
                logger.debug(f"State update: {uuid_str} = {value}")

            return event_dict

        except Exception as e:
            logger.error(f"Error parsing value states: {e}", exc_info=True)
            return {}

    def _parse_text_states(self, message: bytes) -> Dict[str, str]:
        """
        Parse binary text state updates.

        Each state update contains:
        - 16 bytes: UUID (little-endian)
        - 16 bytes: Icon UUID (little-endian)
        - 4 bytes: text length (unsigned int)
        - N bytes: text content
        - Padding to 4-byte boundary

        Args:
            message: Binary message containing text state updates

        Returns:
            Dictionary mapping UUID strings to text values
        """
        event_dict = {}

        try:
            offset = 0

            while offset < len(message):
                # Parse UUID
                event_uuid = uuid.UUID(bytes_le=message[offset : offset + 16])
                fields = event_uuid.urn.replace("urn:uuid:", "").split("-")
                uuid_str = f"{fields[0]}-{fields[1]}-{fields[2]}-{fields[3]}{fields[4]}"
                offset += 16

                # Parse icon UUID (skip for now)
                offset += 16

                # Parse text length
                text_length = unpack("<I", message[offset : offset + 4])[0]
                offset += 4

                # Parse text content
                text_bytes = message[offset : offset + text_length]
                text = check_and_decode_if_needed(text_bytes)
                offset += text_length

                # Calculate padding to 4-byte boundary
                total_size = 16 + 16 + 4 + text_length
                padding = (4 - (total_size % 4)) % 4
                offset += padding

                event_dict[uuid_str] = text
                logger.debug(f"Text state update: {uuid_str} = {text}")

            return event_dict

        except Exception as e:
            logger.error(f"Error parsing text states: {e}", exc_info=True)
            return {}

    def _parse_daytimer_states(self, message: bytes) -> Dict[str, Any]:
        """
        Parse binary daytimer state updates.

        Daytimer states have a similar structure to value states but may contain
        additional timing information.

        Args:
            message: Binary message containing daytimer state updates

        Returns:
            Dictionary mapping UUID strings to daytimer values
        """

        try:
            # For now, treat daytimer states similar to value states
            # This may need refinement based on actual Loxone protocol documentation
            if len(message) % 24 == 0:
                # Standard 24-byte format like value states
                return self._parse_value_states(message)
            else:
                logger.debug(f"Daytimer message with non-standard length: {len(message)}")
                return {"daytimer_data": True, "length": len(message)}

        except Exception as e:
            logger.error(f"Error parsing daytimer states: {e}", exc_info=True)
            return {}

    def _parse_weather_states(self, message: bytes) -> Dict[str, Any]:
        """
        Parse binary weather state updates.

        Weather states contain meteorological data from weather stations.

        Args:
            message: Binary message containing weather state updates

        Returns:
            Dictionary mapping UUID strings to weather values
        """

        try:
            # Weather states may have variable structure
            # For now, attempt to parse as standard value states
            if len(message) % 24 == 0:
                return self._parse_value_states(message)
            else:
                logger.debug(f"Weather message with non-standard length: {len(message)}")
                return {"weather_data": True, "length": len(message)}

        except Exception as e:
            logger.error(f"Error parsing weather states: {e}", exc_info=True)
            return {}

    async def _notify_state_callbacks(self, state_updates: Dict[str, Any]) -> None:
        """
        Notify registered callbacks of state updates.

        Args:
            state_updates: Dictionary of UUID to value mappings
        """
        if not state_updates:
            return

        for callback in self._state_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(state_updates)
                else:
                    callback(state_updates)
            except Exception as e:
                logger.error(f"Error in state callback: {e}", exc_info=True)

    async def _handle_connection_loss(self) -> None:
        """
        Handle connection loss and trigger reconnection.
        """
        if self._manual_disconnect:
            logger.info("Manual disconnect, not reconnecting")
            return

        logger.warning("Connection lost, initiating reconnection")
        self.state = ConnectionState.DISCONNECTED

        # Close existing WebSocket if still open
        if self._ws and self._ws.state != State.CLOSED:
            try:
                await self._ws.close()
            except Exception:
                pass

        # Start reconnection process
        if self._should_reconnect and not self._reconnect_task:
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())
            self.background_tasks.add(self._reconnect_task)
            self._reconnect_task.add_done_callback(self.background_tasks.discard)

    async def _reconnect_loop(self) -> None:
        """
        Automatic reconnection with exponential backoff.

        Attempts to reconnect with increasing delays between attempts.
        """
        logger.info("Starting reconnection loop")

        try:
            while self._should_reconnect and self.state != ConnectionState.CONNECTED:
                logger.info(f"Attempting reconnection in {self._reconnect_delay} seconds...")
                await asyncio.sleep(self._reconnect_delay)

                try:
                    # Attempt to reconnect
                    success = await self.connect()

                    if success:
                        logger.info("Reconnection successful")
                        self._reconnect_delay = RECONNECT_INITIAL_DELAY  # Reset delay
                        self._reconnect_task = None
                        return
                    else:
                        logger.warning("Reconnection attempt failed")

                except Exception as e:
                    logger.error(f"Reconnection error: {e}", exc_info=True)

                # Exponential backoff
                self._reconnect_delay = min(
                    self._reconnect_delay * RECONNECT_BACKOFF_FACTOR, RECONNECT_MAX_DELAY
                )
                logger.info(f"Next reconnection attempt in {self._reconnect_delay} seconds")

        except asyncio.CancelledError:
            logger.info("Reconnection loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Reconnection loop error: {e}", exc_info=True)
        finally:
            self._reconnect_task = None

    async def get_structure(self) -> Dict[str, Any]:
        """
        Fetch and return LoxAPP3.json structure file.

        Returns:
            Dictionary containing Loxone structure data

        Raises:
            LoxoneHTTPStatusError: If HTTP request fails
        """
        logger.info("Fetching LoxAPP3.json structure")

        auth = (self._username, self._password)

        async with httpx.AsyncClient(
            auth=auth, base_url=self._base_url, verify=False, follow_redirects=True, timeout=TIMEOUT
        ) as client:
            # Get version info
            try:
                api_resp = await client.get("/jdev/cfg/apiKey")
                if api_resp.status_code == 200:
                    req_data = api_resp.json()
                    if "LL" in req_data and "value" in req_data["LL"]:
                        value = json.loads(req_data["LL"]["value"].replace("'", '"'))
                        version = value.get("version", "0.0")
                        self._version = float(".".join(version.split(".")[:2]))
                        logger.info(f"Miniserver version: {self._version}")
            except Exception as e:
                logger.warning(f"Failed to get version info: {e}")

            # Get structure
            response = await client.get(LOXAPPPATH)

            if response.status_code != 200:
                raise LoxoneHTTPStatusError(
                    f"Failed to fetch structure: HTTP {response.status_code}"
                )

            structure = response.json()
            if self._version:
                structure["softwareVersion"] = [int(x) for x in str(self._version).split(".")]

            logger.info("Successfully fetched LoxAPP3.json structure")
            return structure

    async def _get_public_key(self) -> bool:
        """Get RSA public key from Miniserver."""
        command = f"{self._base_url}/{CMD_GET_PUBLIC_KEY}"
        logger.debug(f"Getting public key from: {command}")

        try:
            async with httpx.AsyncClient(
                auth=(self._username, self._password),
                base_url=self._base_url,
                follow_redirects=True,
                verify=False,
                timeout=TIMEOUT,
            ) as client:
                response = await client.get(f"/{CMD_GET_PUBLIC_KEY}")

            if response.status_code != 200:
                logger.error(f"Failed to get public key: HTTP {response.status_code}")
                return False

            resp_json = json.loads(response.text)
            if "LL" in resp_json and "value" in resp_json["LL"]:
                self._public_key = resp_json["LL"]["value"]
                logger.debug("Public key retrieved successfully")
                return True
            else:
                logger.error("Public key not found in response")
                return False

        except Exception as e:
            logger.error(f"Error getting public key: {e}")
            return False

    def _init_rsa_cipher(self) -> bool:
        """Initialize RSA cipher with public key."""
        try:
            # Format public key
            public_key = self._public_key.replace(
                "-----BEGIN CERTIFICATE-----", "-----BEGIN PUBLIC KEY-----\n"
            )
            public_key = public_key.replace(
                "-----END CERTIFICATE-----", "\n-----END PUBLIC KEY-----\n"
            )

            # Create RSA cipher
            self._rsa_cipher = PKCS1_v1_5.new(RSA.importKey(public_key))
            logger.debug("RSA cipher initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Error initializing RSA cipher: {e}")
            return False

    def _generate_session_key(self) -> bool:
        """Generate and encrypt session key."""
        try:
            aes_key = binascii.hexlify(self._key).decode("utf-8")
            iv = binascii.hexlify(self._iv).decode("utf-8")
            sess = f"{aes_key}:{iv}"
            sess_encrypted = self._rsa_cipher.encrypt(bytes(sess, "utf-8"))
            self._session_key = b64encode(sess_encrypted).decode("utf-8")
            logger.debug("Session key generated successfully")
            return True

        except Exception as e:
            logger.error(f"Error generating session key: {e}")
            return False

    async def _authenticate(self) -> bool:
        """Authenticate with Miniserver using token or credentials."""
        # Check if we have a valid token
        if self._token.token and self._token.get_seconds_to_expire() > 300:
            logger.info("Using existing token for authentication")
            return await self._use_token()
        else:
            logger.info("Acquiring new token")
            return await self._acquire_token()

    async def _refresh_token(self) -> bool:
        """
        Refresh the authentication token before it expires.

        Returns:
            True if token refresh successful, False otherwise
        """
        logger.debug("Refreshing authentication token")

        try:
            # Get key for token hashing
            command = CMD_GET_KEY
            enc_command = await self._encrypt(command)
            await self._ws.send(enc_command)

            message = await self._ws.recv()
            await self._parse_loxone_message(message)

            message = await self._ws.recv()
            resp_json = json.loads(message)

            token_hash = None
            if "LL" in resp_json and "value" in resp_json["LL"]:
                key = resp_json["LL"]["value"]
                if key != "":
                    hash_alg = SHA1 if self._token.hash_alg == "SHA1" else SHA256
                    digester = HMAC.new(
                        binascii.unhexlify(key), self._token.token.encode("utf-8"), hash_alg
                    )
                    token_hash = digester.hexdigest()

            if not token_hash:
                logger.error("Failed to hash token for refresh")
                return False

            # Choose refresh command based on version
            if self._version < 10.2:
                command = f"{CMD_REFRESH_TOKEN}{token_hash}/{self._username}"
            else:
                command = f"{CMD_REFRESH_TOKEN_JSON_WEB}{token_hash}/{self._username}"

            enc_command = await self._encrypt(command)
            await self._ws.send(enc_command)

            message = await self._ws.recv()
            await self._parse_loxone_message(message)

            message = await self._ws.recv()
            resp_json = json.loads(message)

            # Update token validity
            if "LL" in resp_json and "value" in resp_json["LL"]:
                if "validUntil" in resp_json["LL"]["value"]:
                    self._token.set_valid_until(resp_json["LL"]["value"]["validUntil"])
                    self._persist_token()
                    logger.info(
                        f"Token refreshed successfully. Valid for {self._token.get_seconds_to_expire()} seconds"
                    )
                    return True

            logger.error("Failed to refresh token")
            return False

        except Exception as e:
            logger.error(f"Error refreshing token: {e}", exc_info=True)
            return False

    async def _use_token(self) -> bool:
        """Authenticate using existing token."""
        token_hash = await self._hash_token()
        if token_hash == ERROR_VALUE:
            return False

        command = f"{CMD_AUTH_WITH_TOKEN}{token_hash}/{self._username}"
        enc_command = await self._encrypt(command)
        await self._ws.send(enc_command)

        # Parse response
        message = await self._ws.recv()
        await self._parse_loxone_message(message)

        message = await self._ws.recv()
        resp_json = json.loads(message)

        if self._check_response_code(resp_json, "200"):
            if "value" in resp_json["LL"]:
                self._token.set_valid_until(resp_json["LL"]["value"]["validUntil"])
            logger.info("Token authentication successful")
            return True

        logger.warning("Token authentication failed")
        return False

    async def _acquire_token(self) -> bool:
        """Acquire new authentication token."""
        logger.debug("Acquiring new token")

        command = f"{CMD_GET_KEY_AND_SALT}{self._username}"
        enc_command = await self._encrypt(command)

        await self._ws.send(enc_command)
        message = await self._ws.recv()
        await self._parse_loxone_message(message)

        message = await self._ws.recv()

        key_and_salt = LxJsonKeySalt()
        key_and_salt.read_user_salt_response(message)

        new_hash = self._hash_credentials(key_and_salt)

        # Choose command based on version
        if self._version < 10.2:
            command = (
                f"{CMD_REQUEST_TOKEN}{new_hash}/{self._username}/"
                f"{TOKEN_PERMISSION}/edfc5f9a-df3f-4cad-9dddcdc42c732be2/homeassistant"
            )
        else:
            command = (
                f"{CMD_REQUEST_TOKEN_JSON_WEB}{new_hash}/{self._username}/"
                f"{TOKEN_PERMISSION}/edfc5f9a-df3f-4cad-9dddcdc42c732be2/homeassistant"
            )

        enc_command = await self._encrypt(command)
        await self._ws.send(enc_command)

        message = await self._ws.recv()
        await self._parse_loxone_message(message)

        message = await self._ws.recv()
        resp_json = json.loads(message)

        if "LL" in resp_json and "value" in resp_json["LL"]:
            value = resp_json["LL"]["value"]
            if "token" in value and "validUntil" in value:
                self._token = LxToken(value["token"], value["validUntil"], key_and_salt.hash_alg)
                self._persist_token()
                logger.info("Token acquired successfully")
                return True

        logger.error("Failed to acquire token")
        return False

    async def _hash_token(self) -> str:
        """Hash token for authentication."""
        try:
            command = CMD_GET_KEY
            enc_command = await self._encrypt(command)
            await self._ws.send(enc_command)

            message = await self._ws.recv()
            await self._parse_loxone_message(message)

            message = await self._ws.recv()
            resp_json = json.loads(message)

            if "LL" in resp_json and "value" in resp_json["LL"]:
                key = resp_json["LL"]["value"]
                if key != "":
                    hash_alg = SHA1 if self._token.hash_alg == "SHA1" else SHA256
                    digester = HMAC.new(
                        binascii.unhexlify(key), self._token.token.encode("utf-8"), hash_alg
                    )
                    return digester.hexdigest()

            return ERROR_VALUE

        except Exception as e:
            logger.error(f"Error hashing token: {e}")
            return ERROR_VALUE

    def _hash_credentials(self, key_salt: LxJsonKeySalt) -> str:
        """Hash credentials with salt."""
        pwd_hash_str = f"{self._password}:{key_salt.salt}"

        if key_salt.hash_alg == "SHA1":
            m = hashlib.sha1()
        elif key_salt.hash_alg == "SHA256":
            m = hashlib.sha256()
        else:
            logger.error(f"Unrecognized hash algorithm: {key_salt.hash_alg}")
            return ""

        m.update(pwd_hash_str.encode("utf-8"))
        pwd_hash = m.hexdigest().upper()
        pwd_hash = f"{self._username}:{pwd_hash}"

        hash_alg = SHA1 if key_salt.hash_alg == "SHA1" else SHA256
        digester = HMAC.new(binascii.unhexlify(key_salt.key), pwd_hash.encode("utf-8"), hash_alg)

        return digester.hexdigest()

    async def _encrypt(self, command: str) -> str:
        """Encrypt command for secure transmission."""
        if not self._encryption_ready:
            return command

        # Handle salt
        if self._salt != "" and self._new_salt_needed():
            prev_salt = self._salt
            self._salt = self._generate_salt()
            s = f"nextSalt/{prev_salt}/{self._salt}/{command}\0"
        else:
            if self._salt == "":
                self._salt = self._generate_salt()
            s = f"salt/{self._salt}/{command}\0"

        # Pad and encrypt
        s_padded = Padding.pad(bytes(s, "utf-8"), 16)
        aes_cipher = self._get_new_aes_cipher()
        encrypted = aes_cipher.encrypt(s_padded)
        encoded = b64encode(encrypted)
        encoded_url = req.pathname2url(encoded.decode("utf-8"))

        return f"{CMD_ENCRYPT_CMD}{encoded_url}"

    def _generate_salt(self) -> str:
        """Generate new salt for encryption."""
        salt = get_random_bytes(SALT_BYTES)
        salt = binascii.hexlify(salt).decode("utf-8")
        salt = req.pathname2url(salt)
        self._salt_time_stamp = time_elapsed_in_seconds()
        self._salt_used_count = 0
        return salt

    def _new_salt_needed(self) -> bool:
        """Check if new salt is needed."""
        self._salt_used_count += 1
        if (
            self._salt_used_count > SALT_MAX_USE_COUNT
            or time_elapsed_in_seconds() - self._salt_time_stamp > SALT_MAX_AGE_SECONDS
        ):
            return True
        return False

    def _get_new_aes_cipher(self):
        """Create new AES cipher instance."""
        return AES.new(self._key, AES.MODE_CBC, self._iv)

    async def _parse_loxone_message(self, message: bytes) -> None:
        """Parse Loxone message header."""
        if len(message) == 8:
            try:
                unpacked_data = unpack("ccccI", message)
                msg_type = int.from_bytes(unpacked_data[1], byteorder="big")

                # Validate message type
                try:
                    self._current_message_type = MessageType(msg_type)
                    logger.debug(f"Message type: {self._current_message_type.name}")
                except ValueError:
                    logger.warning(f"Unknown message type: {msg_type}, defaulting to TextMessage")
                    self._current_message_type = MessageType.TextMessage

            except (struct.error, IndexError) as e:
                logger.error(f"Error unpacking message header: {e}")
                self._current_message_type = MessageType.TextMessage
            except Exception as e:
                logger.error(f"Unexpected error parsing message header: {e}")
                self._current_message_type = MessageType.TextMessage
        else:
            logger.warning(f"Invalid message header length: {len(message)}, expected 8 bytes")
            self._current_message_type = MessageType.TextMessage

    def _check_response_code(self, resp_json: dict, expected_code: str) -> bool:
        """Check if response has expected code."""
        if "LL" in resp_json and "Code" in resp_json["LL"]:
            return str(resp_json["LL"]["Code"]) == expected_code
        if "LL" in resp_json and "code" in resp_json["LL"]:
            return str(resp_json["LL"]["code"]) == expected_code
        return False

    async def send_command(self, device_uuid: str, value: str) -> bool:
        """
        Send a command to a Loxone device.

        Args:
            device_uuid: UUID of the device to control
            value: Command value to send (e.g., "On", "Off", "50")

        Returns:
            True if command sent successfully, False otherwise
        """
        if self.state != ConnectionState.CONNECTED or not self._ws:
            logger.error("Cannot send command: not connected")
            return False

        try:
            command = f"jdev/sps/io/{device_uuid}/{value}"
            logger.debug(f"Sending command: {command}")

            # Send command (will be encrypted if encryption is ready)
            enc_command = await self._encrypt(command)
            await self._ws.send(enc_command)

            logger.info(f"Command sent to {device_uuid}: {value}")
            return True

        except Exception as e:
            logger.error(f"Error sending command: {e}", exc_info=True)
            return False

    async def send_secured_command(self, device_uuid: str, value: str, code: str) -> bool:
        """
        Send a secured command that requires PIN authentication.

        Args:
            device_uuid: UUID of the device to control
            value: Command value to send
            code: PIN code for authentication

        Returns:
            True if command sent successfully, False otherwise
        """
        if self.state != ConnectionState.CONNECTED or not self._ws:
            logger.error("Cannot send secured command: not connected")
            return False

        try:
            # Get visual salt for PIN authentication
            visual_hash = await self._get_visual_hash()
            if not visual_hash:
                logger.error("Failed to get visual hash for secured command")
                return False

            # Compute PIN hash
            pwd_hash_str = f"{code}:{visual_hash['salt']}"

            if visual_hash["hash_alg"] == "SHA1":
                m = hashlib.sha1()
            elif visual_hash["hash_alg"] == "SHA256":
                m = hashlib.sha256()
            else:
                logger.error(f"Unrecognized hash algorithm: {visual_hash['hash_alg']}")
                return False

            m.update(pwd_hash_str.encode("utf-8"))
            pwd_hash = m.hexdigest().upper()

            # Create HMAC with key
            hash_alg = SHA1 if visual_hash["hash_alg"] == "SHA1" else SHA256
            digester = HMAC.new(
                binascii.unhexlify(visual_hash["key"]), pwd_hash.encode("utf-8"), hash_alg
            )

            # Send secured command
            command = f"jdev/sps/ios/{digester.hexdigest()}/{device_uuid}/{value}"
            logger.debug(f"Sending secured command: {command}")

            await self._ws.send(command)

            logger.info(f"Secured command sent to {device_uuid}: {value}")
            return True

        except Exception as e:
            logger.error(f"Error sending secured command: {e}", exc_info=True)
            return False

    async def _get_visual_hash(self) -> Optional[Dict[str, str]]:
        """
        Get visual salt for PIN authentication.

        Returns:
            Dictionary with 'key', 'salt', and 'hash_alg', or None on failure
        """
        try:
            command = f"{CMD_GET_VISUAL_PASSWD}{self._username}"
            enc_command = await self._encrypt(command)
            await self._ws.send(enc_command)

            # Parse response header
            message = await self._ws.recv()
            await self._parse_loxone_message(message)

            # Parse response content
            message = await self._ws.recv()
            resp_json = json.loads(message)

            if "LL" in resp_json and "value" in resp_json["LL"]:
                value = resp_json["LL"]["value"]
                if "key" in value and "salt" in value:
                    return {
                        "key": value["key"],
                        "salt": value["salt"],
                        "hash_alg": value.get("hashAlg", "SHA1"),
                    }

            logger.error("Failed to get visual hash from response")
            return None

        except Exception as e:
            logger.error(f"Error getting visual hash: {e}", exc_info=True)
            return None

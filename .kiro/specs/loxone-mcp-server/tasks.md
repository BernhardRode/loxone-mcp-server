# Implementation Plan

- [x] 1. Set up project structure and dependencies
  - Create project directory structure with src/loxone_mcp/ layout
  - Create pyproject.toml with all required dependencies (mcp>=0.9.0, websockets>=14.0, pycryptodome>=3.20.0, httpx>=0.27.0)
  - Create .python-version file specifying Python 3.10+
  - Create README.md with installation and usage instructions
  - _Requirements: 1.1, 1.4_

- [x] 2. Implement configuration management module
  - [x] 2.1 Create config.py with LoxoneConfig dataclass
    - Implement LoxoneConfig dataclass with host, port, username, password, token_persist_path fields
    - Implement from_env() classmethod to load configuration from environment variables
    - Implement from_file() classmethod to load configuration from JSON file
    - Implement save_token() method to persist token data to disk as JSON
    - Implement load_token() method to load persisted token from disk
    - Add error handling for missing required configuration
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 3. Refactor Loxone communication layer
  - [x] 3.1 Create loxone_client.py with core websocket client
    - Extract and refactor LoxWs class from api.py to LoxoneClient class
    - Remove all Home Assistant dependencies (homeassistant.* imports)
    - Implement connect() method for establishing websocket connection
    - Implement disconnect() method for graceful connection closure
    - Implement get_structure() method to fetch and return LoxAPP3.json
    - Add register_state_callback() method for state update notifications
    - _Requirements: 2.1, 2.2, 2.3, 8.1_

  - [x] 3.2 Implement authentication and encryption
    - Refactor get_public_key() method for RSA public key retrieval
    - Refactor key exchange logic using pycryptodome RSA cipher
    - Implement token acquisition flow (acquire_token method)
    - Implement token refresh logic with automatic refresh before expiry
    - Implement AES encryption/decryption for commands using pycryptodome
    - Integrate token persistence using LoxoneConfig save/load methods
    - _Requirements: 2.3, 2.5, 7.3, 7.4_

  - [x] 3.3 Implement connection management and reconnection
    - Implement automatic reconnection with exponential backoff on connection loss
    - Implement keepalive mechanism using periodic ping messages
    - Add connection state tracking (CONNECTING, CONNECTED, DISCONNECTED)
    - Implement start() method to begin background tasks (keepalive, message processing)
    - Add error handling and logging for connection failures
    - _Requirements: 2.4, 2.6, 8.2, 8.5_

  - [x] 3.4 Implement message parsing and state updates
    - You crashed twice no... do not start stuipd stugg
    - you always run when doing - "uv run pytest tests/test_loxone_client.py::TestConnectionManagementAndReconnection::test_message_processor_receives_messages -v --tb=short"
    - Refactor message parser to handle binary and text messages
    - Implement state update message processing (MessageType.EventTableValueStates)
    - Add callback invocation for state updates to notify DeviceManager
    - Implement command sending methods (send_command, send_secured_command)
    - Add error handling for malformed messages
    - _Requirements: 9.1, 9.2, 8.3_

  - [x] 3.5 Implement secured command support
    - Implement get_visual_hash() method to request visual salt
    - Implement visual hash computation using PIN code and salt
    - Implement send_secured_command() with hash authentication
    - Add error handling for incorrect PIN codes
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 4. Implement device management module
  - [x] 4.1 Create device_manager.py with device data models
    - Create LoxoneDevice dataclass with uuid, name, type, room, category, states, details, controls fields
    - Implement DeviceManager class with device registry dictionary
    - Add device type constants for all supported types (Switch, Dimmer, Jalousie, etc.)
    - _Requirements: 3.1, 3.2_

  - [x] 4.2 Implement device discovery and registration
    - Implement load_devices() method to parse LoxAPP3.json structure
    - Add device type filtering to only register supported device types
    - Extract device metadata (name, room, category, capabilities) from structure
    - Create LoxoneDevice instances and store in registry
    - Add logging for discovered devices and unsupported types
    - _Requirements: 3.1, 3.2, 3.5_

  - [x] 4.3 Implement state management
    - Implement update_state() method to update device state cache
    - Implement get_device() method for UUID-based device lookup
    - Implement get_device_state() method to retrieve current device state
    - Add thread-safe state updates for concurrent access
    - _Requirements: 3.3, 3.4, 9.1, 9.2, 9.3_

  - [x] 4.4 Implement device query methods
    - Implement list_devices() method with optional device_type filter
    - Add room-based filtering to list_devices() method
    - Implement device information formatting for MCP tool responses
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 5. Implement MCP server and tool definitions
  - [x] 5.1 Create server.py with FastMCP server initialization
    - Import FastMCP from mcp.server.fastmcp
    - Create FastMCP instance with server name "loxone-mcp-server"
    - Implement server_lifespan() context manager for resource initialization
    - Initialize LoxoneClient and DeviceManager in lifespan
    - Connect to Miniserver and load device structure in lifespan
    - Add cleanup logic in lifespan finally block
    - Implement main() entry point to run FastMCP server
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 5.2 Implement device query tools
    - Implement loxone_list_devices tool with device_type and room filters
    - Implement loxone_get_device_state tool with uuid parameter
    - Implement loxone_get_device_info tool with uuid parameter
    - Add input validation and error responses for invalid UUIDs
    - Format tool responses with device information (uuid, name, type, room, state)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 5.3 Implement device control tools
    - Implement loxone_send_command tool with uuid and value parameters
    - Implement loxone_set_switch tool with uuid and state (bool) parameters
    - Implement loxone_set_dimmer tool with uuid and brightness (0-100) parameters
    - Implement loxone_set_cover_position tool with uuid and position parameters
    - Implement loxone_set_temperature tool with uuid and temperature parameters
    - Add device type validation before sending commands
    - Return success/error responses with updated state information
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 5.4 Implement secured command tool
    - Implement loxone_send_secured_command tool with uuid, value, and code parameters
    - Integrate with LoxoneClient.send_secured_command() method
    - Add error handling for authentication failures
    - Return success/error responses
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 5.5 Implement scene management tools
    - Implement loxone_list_scenes tool to return all available scenes
    - Implement loxone_trigger_scene tool with scene uuid parameter
    - Add scene discovery in DeviceManager.load_devices()
    - Add error handling for invalid scene UUIDs
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 6. Implement error handling and logging
  - Add comprehensive logging throughout all modules (debug, info, warning, error levels)
  - Implement consistent error response format for all MCP tools
  - Add context information to all error log messages
  - Implement graceful error handling for websocket failures
  - Add validation error messages for invalid tool parameters
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 7. Create unit tests
  - [x] 7.1 Create tests for configuration management
    - Write tests for LoxoneConfig.from_env() with various environment variables
    - Write tests for LoxoneConfig.from_file() with valid and invalid JSON
    - Write tests for token save/load functionality
    - Write tests for missing required configuration error handling
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 7.2 Create tests for device manager
    - Write tests for device registration from LoxAPP3.json structure
    - Write tests for state update functionality
    - Write tests for device query methods with filters
    - Write tests for unsupported device type handling
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 7.3 Create tests for message parsing
    - Write tests for binary message decoding
    - Write tests for text message parsing
    - Write tests for state update message processing
    - Write tests for malformed message error handling
    - _Requirements: 9.1, 9.2, 8.3_

  - [x] 7.4 Create tests for encryption
    - Write tests for AES encryption/decryption
    - Write tests for RSA key exchange
    - Write tests for token hashing
    - Write tests for visual hash computation
    - _Requirements: 2.3, 6.2, 6.3_

- [x] 8. Create documentation and deployment configuration
  - Update README.md with MCP server installation instructions
  - Add configuration examples for environment variables and config file
  - Add MCP client configuration examples (Claude Desktop, etc.)
  - Document all available MCP tools with parameters and examples
  - Add troubleshooting section for common issues
  - Create example .env file with all configuration options
  - _Requirements: 1.4, 7.1, 7.2_
  
- [x] 9. Create integration tests

  - [x] 9.1 Create tests for LoxoneClient to connect to real MiniServer
    - ENV Variables are set via .env
    - Write tests for connection establishment with mock server
    - Write tests for authentication flow
    - Write tests for command sending
    - Write tests for reconnection logic
    - Write tests for state update callback invocation
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6_

  - [x] 9.2 Create tests for MCP tools
    - Write tests for each tool with valid inputs
    - Write tests for error handling with invalid inputs
    - Write tests for tool response format validation
    - Write tests for device type validation in control tools
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 10. Implement multi-client connection management
  - [x] 10.1 Create connection_manager.py with ConnectionManager class
    - Implement ConnectionManager class to manage multiple client sessions
    - Add create_session() method to create new client sessions with credentials
    - Add remove_session() method to clean up disconnected clients
    - Add get_session() method for client session lookup
    - Implement cleanup_all() method for server shutdown
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 10.2 Create client_session.py with ClientSession class
    - Implement ClientSession class wrapping LoxoneClient and DeviceManager
    - Add high-level control methods for all device types (switches, lights, covers, climate, etc.)
    - Implement session-specific state management
    - Add error handling and logging for session operations
    - _Requirements: 11.1, 11.2, 11.3, 12.1, 12.2, 12.3_

  - [x] 10.3 Update server.py for multi-client support
    - Modify FastMCP server to handle client connections and disconnections
    - Implement client_connected() handler to create sessions with credentials
    - Implement client_disconnected() handler to clean up sessions
    - Update all MCP tools to accept client_id parameter
    - Add client session lookup in all tool implementations
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

- [x] 11. Implement complete Home Assistant component feature migration
  - [x] 11.1 Extend device_manager.py for all device types
    - Add support for all HA component device types (ColorPickerV2, MediaPlayer, Alarm, etc.)
    - Implement device capability detection and mapping
    - Add device type constants for all supported types
    - Extend LoxoneDevice dataclass with capabilities field
    - _Requirements: 12.1, 12.2, 12.3_

  - [x] 11.2 Implement comprehensive device control methods in ClientSession
    - Add control_light_color() for RGB color lighting
    - Add control_cover_open/close() methods for covers
    - Add control_climate_mode() for climate control modes
    - Add control_fan_speed() for ventilation controls
    - Add control_media_play/pause/volume() for media players
    - Add control_alarm_arm/disarm() for alarm systems with PIN
    - Add control_text_input() and control_number_input() for input controls
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9_

  - [x] 11.3 Add comprehensive MCP tools for all device types
    - Implement loxone_set_light_color tool for color lighting
    - Implement loxone_cover_open/close tools for cover controls
    - Implement loxone_set_climate_mode tool for climate controls
    - Implement loxone_set_fan_speed tool for fan controls
    - Implement loxone_media_play/pause/volume tools for media players
    - Implement loxone_arm/disarm_alarm tools for alarm systems
    - Implement loxone_set_text/number_input tools for input controls
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9_

- [x] 12. Implement enhanced device state information system
  - [x] 12.1 Enhance DeviceManager with comprehensive state management
    - Implement get_enhanced_device_state() method to return detailed device state information
    - Implement build_state_structure() method to create device-type specific state structures
    - Implement extract_device_capabilities() method to detect device capabilities from LoxAPP3.json
    - Add device-specific state builders (_build_light_state, _build_color_light_state, _build_cover_state, _build_climate_state)
    - Implement empty state cache handling with Miniserver state request fallback
    - _Requirements: 5A.1, 5A.2, 5A.3, 5A.4, 5A.5, 5A.6, 5A.7_

  - [x] 12.2 Update LoxoneDevice data model for enhanced state support
    - Add capabilities field to LoxoneDevice dataclass for storing device capability information
    - Add metadata field for state parameter descriptions and units
    - Implement state parameter validation and default value handling
    - Add last_updated and reachable status tracking to device states
    - _Requirements: 5A.2, 5A.4, 5A.5_

  - [x] 12.3 Update MCP tools to use enhanced state information
    - Modify loxone_get_device_state tool to use get_enhanced_device_state() method
    - Update tool responses to include comprehensive state information with capabilities and metadata
    - Add state parameter documentation to tool descriptions
    - Implement error handling for devices with unavailable state information
    - _Requirements: 5A.1, 5A.2, 5A.3, 5A.4_

- [ ] 13. Implement enhanced room-based device management
  - [ ] 13.1 Add room management methods to DeviceManager
    - Implement list_rooms() method to return all rooms with device counts
    - Implement get_room_devices() method to get all devices in a room with states
    - Implement control_room() method for room-wide actions (lights_off, all_off)
    - Add room-based device filtering and grouping
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [ ] 13.2 Implement room management MCP tools
    - Implement loxone_list_rooms tool to list all rooms
    - Implement loxone_get_room_devices tool to get room device details
    - Implement loxone_control_room tool for room-wide control actions
    - Add error handling for invalid room names
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

- [ ] 14. Update configuration management for multi-client support
  - [ ] 14.1 Extend LoxoneConfig for client-specific configurations
    - Add support for client-provided credentials in config
    - Implement per-client token persistence with client_id prefixes
    - Add validation for client credential formats
    - _Requirements: 11.1, 11.2, 11.6_

- [ ] 15. Create comprehensive tests for new features
  - [ ] 15.1 Create tests for enhanced device state information
    - Write tests for get_enhanced_device_state() method with different device types
    - Write tests for build_state_structure() method and device-specific builders
    - Write tests for capability detection and metadata generation
    - Write tests for empty state cache handling and fallback mechanisms
    - Write tests for enhanced MCP tool responses with comprehensive state information
    - _Requirements: 5A.1, 5A.2, 5A.3, 5A.4, 5A.5, 5A.6, 5A.7_

  - [ ] 15.2 Create tests for multi-client connection management
    - Write tests for ConnectionManager session creation and cleanup
    - Write tests for ClientSession device control methods
    - Write tests for client credential handling
    - Write tests for concurrent client connections
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ] 15.3 Create tests for complete device type support
    - Write tests for all new device control methods
    - Write tests for device capability detection
    - Write tests for room-based device management
    - Write tests for all new MCP tools
    - _Requirements: 12.1, 12.2, 12.3, 13.1, 13.2, 13.3_

- [ ] 16. Update documentation and deployment configuration
  - Update README.md with enhanced device state information features
  - Add documentation for comprehensive state structures and capabilities
  - Update MCP tool documentation with enhanced state response examples
  - Add troubleshooting section for empty device state issues
  - Document device capability detection and metadata features
  - Add configuration examples for enhanced state management
  - _Requirements: 1.4, 7.1, 7.2, 5A.1, 5A.2, 5A.5_
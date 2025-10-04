# Requirements Document

## Introduction

This document outlines the requirements for refactoring the existing Home Assistant Loxone integration into a standalone Model Context Protocol (MCP) server. The current implementation is a Home Assistant custom component that provides integration with Loxone Miniserver devices. The goal is to transform this into an MCP server that exposes Loxone functionality through standardized MCP tools, making it accessible to any MCP-compatible client (including AI assistants, IDEs, and other applications).

The MCP server will maintain the core Loxone communication capabilities (websocket connection, authentication, token management, encryption) while exposing device control and monitoring through MCP tools instead of Home Assistant entities.

## Requirements

### Requirement 1: MCP Server Foundation

**User Story:** As a developer, I want a standalone MCP server implementation, so that I can interact with Loxone devices from any MCP-compatible client without requiring Home Assistant.

#### Acceptance Criteria

1. WHEN the server is started THEN it SHALL initialize as a valid MCP server using the FastMCP or similar MCP framework
2. WHEN a client connects THEN the server SHALL expose its available tools through the MCP protocol
3. WHEN the server is running THEN it SHALL NOT depend on Home Assistant libraries or infrastructure
4. WHEN the server starts THEN it SHALL load configuration from a standard configuration file (JSON or environment variables)
5. IF the server encounters a fatal error THEN it SHALL log the error and shut down gracefully

### Requirement 2: Loxone Connection Management

**User Story:** As a user, I want the MCP server to establish and maintain a connection to my Loxone Miniserver, so that I can interact with my Loxone devices reliably.

#### Acceptance Criteria

1. WHEN the server starts THEN it SHALL connect to the Loxone Miniserver using the provided host, port, username, and password
2. WHEN connecting THEN it SHALL retrieve the LoxAPP3.json configuration file containing all device definitions
3. WHEN the websocket connection is established THEN it SHALL perform the complete authentication flow (key exchange, token acquisition/refresh, encryption setup)
4. WHEN the connection is lost THEN it SHALL attempt to reconnect automatically with exponential backoff
5. WHEN a token expires THEN it SHALL refresh the token automatically before expiration
6. WHEN the connection is active THEN it SHALL maintain a keepalive mechanism to prevent disconnection
7. IF authentication fails THEN it SHALL log the error and retry with appropriate delays

### Requirement 3: Device Discovery and State Management

**User Story:** As a user, I want the MCP server to discover and track all my Loxone devices and their states, so that I can query and control them through MCP tools.

#### Acceptance Criteria

1. WHEN the LoxAPP3.json is retrieved THEN it SHALL parse all supported device types (switches, lights, covers, sensors, climate controls, etc.)
2. WHEN devices are discovered THEN it SHALL store device metadata including UUID, name, type, room, and capabilities
3. WHEN state updates are received via websocket THEN it SHALL update the internal state cache for affected devices
4. WHEN a device state changes THEN it SHALL maintain the current state in memory for quick retrieval
5. IF an unsupported device type is encountered THEN it SHALL log a warning and skip that device

### Requirement 4: Device Control Tools

**User Story:** As a user, I want to control my Loxone devices through MCP tools, so that I can turn on lights, adjust thermostats, and operate other devices from any MCP client.

#### Acceptance Criteria

1. WHEN the "loxone_send_command" tool is called with a device UUID and value THEN it SHALL send the command to the Miniserver via websocket
2. WHEN the "loxone_set_switch" tool is called THEN it SHALL turn a switch on or off
3. WHEN the "loxone_set_dimmer" tool is called THEN it SHALL set a dimmer to the specified brightness level (0-100)
4. WHEN the "loxone_set_cover_position" tool is called THEN it SHALL move a cover (blinds/shades) to the specified position
5. WHEN the "loxone_set_temperature" tool is called THEN it SHALL set the target temperature for a climate control device
6. WHEN a control command succeeds THEN it SHALL return a success response with the updated state
7. IF a control command fails THEN it SHALL return an error response with details

### Requirement 5: Device Query Tools

**User Story:** As a user, I want to query the state and information of my Loxone devices through MCP tools, so that I can check device status and retrieve device details.

#### Acceptance Criteria

1. WHEN the "loxone_list_devices" tool is called THEN it SHALL return a list of all discovered devices with their basic information
2. WHEN the "loxone_list_devices" tool is called with a device type filter THEN it SHALL return only devices of that type
3. WHEN the "loxone_list_devices" tool is called with a room filter THEN it SHALL return only devices in that room
4. WHEN the "loxone_get_device_state" tool is called with a device UUID THEN it SHALL return the current state of that device
5. WHEN the "loxone_get_device_info" tool is called with a device UUID THEN it SHALL return detailed information about the device including all metadata
6. WHEN device information is returned THEN it SHALL include UUID, name, type, room, current state, and available controls

### Requirement 5A: Enhanced Device State Information

**User Story:** As a user, I want detailed state information for all device types, especially lighting controls, so that I can accurately determine the current status and operational parameters of my devices.

#### Acceptance Criteria

1. WHEN the "loxone_get_device_state" tool is called for a light control device THEN it SHALL return detailed state information including on/off status, brightness level, color values, and operational mode
2. WHEN the "loxone_get_device_state" tool is called for any device THEN it SHALL return all available state parameters specific to that device type, not just basic state values
3. WHEN a device has multiple state parameters (e.g., position and tilt for covers) THEN all parameters SHALL be included in the state response
4. WHEN a device state is unavailable or not yet initialized THEN it SHALL return appropriate default values or null indicators with clear status information
5. WHEN state information is retrieved THEN it SHALL include metadata about state parameter meanings, units, and valid ranges
6. IF a device type has specific state parameters (brightness, color, temperature, position, etc.) THEN those parameters SHALL be explicitly included in the response structure
7. WHEN the state cache is empty for a device THEN the system SHALL attempt to request current state from the Miniserver before returning the response

### Requirement 6: Secured Command Support

**User Story:** As a user, I want to execute secured commands that require a PIN code, so that I can control security-sensitive devices like alarm systems.

#### Acceptance Criteria

1. WHEN the "loxone_send_secured_command" tool is called with a device UUID, value, and PIN code THEN it SHALL perform the visual hash authentication
2. WHEN secured authentication is required THEN it SHALL request the visual salt from the Miniserver
3. WHEN the visual salt is received THEN it SHALL compute the proper hash using the PIN code and salt
4. WHEN the secured command is sent THEN it SHALL use the computed hash for authentication
5. IF the PIN code is incorrect THEN it SHALL return an error indicating authentication failure

### Requirement 7: Configuration Management

**User Story:** As a system administrator, I want to configure the MCP server through a configuration file or environment variables, so that I can deploy it in different environments easily.

#### Acceptance Criteria

1. WHEN the server starts THEN it SHALL read configuration from environment variables or a config file
2. WHEN configuration is loaded THEN it SHALL support the following parameters: host, port, username, password, token persistence path
3. WHEN a token is acquired THEN it SHALL persist it to disk for reuse across restarts
4. WHEN the server restarts THEN it SHALL load the persisted token if still valid
5. IF required configuration is missing THEN it SHALL log an error and refuse to start

### Requirement 8: Error Handling and Logging

**User Story:** As a system administrator, I want comprehensive error handling and logging, so that I can troubleshoot issues and monitor the server's operation.

#### Acceptance Criteria

1. WHEN any operation occurs THEN it SHALL log appropriate messages at the correct level (debug, info, warning, error)
2. WHEN an error occurs THEN it SHALL include context information in the log message
3. WHEN a websocket message cannot be parsed THEN it SHALL log the error and continue processing other messages
4. WHEN a tool is called with invalid parameters THEN it SHALL return a descriptive error message
5. WHEN the connection fails THEN it SHALL log the failure reason and retry count

### Requirement 9: Real-time State Updates

**User Story:** As a user, I want the MCP server to maintain up-to-date device states, so that queries return current information without delays.

#### Acceptance Criteria

1. WHEN a state update message is received via websocket THEN it SHALL update the internal state cache immediately
2. WHEN multiple state updates arrive in quick succession THEN it SHALL process them all without dropping updates
3. WHEN a device state is queried THEN it SHALL return the most recently received state
4. WHEN the websocket connection is re-established THEN it SHALL request a full state update from the Miniserver

### Requirement 10: Scene Execution Support

**User Story:** As a user, I want to trigger Loxone scenes through MCP tools, so that I can activate predefined automation scenarios.

#### Acceptance Criteria

1. WHEN the "loxone_list_scenes" tool is called THEN it SHALL return a list of all available scenes
2. WHEN the "loxone_trigger_scene" tool is called with a scene UUID THEN it SHALL activate that scene on the Miniserver
3. WHEN a scene is triggered THEN it SHALL return a success response
4. IF a scene UUID is invalid THEN it SHALL return an error response

### Requirement 11: Dynamic Client Connection with Credentials

**User Story:** As an MCP client, I want to provide Loxone credentials dynamically when connecting, so that I can connect to different Loxone servers without changing server configuration.

#### Acceptance Criteria

1. WHEN an MCP client connects THEN it SHALL be able to provide LOXONE_USERNAME, LOXONE_PASSWORD, and LOXONE_HOST as connection parameters
2. WHEN client credentials are provided THEN the server SHALL use those credentials instead of configuration file values
3. WHEN client credentials are provided THEN the server SHALL establish a new connection to the specified Loxone host
4. WHEN multiple clients connect with different credentials THEN the server SHALL maintain separate connections for each client
5. WHEN a client disconnects THEN the server SHALL clean up the associated Loxone connection
6. IF client credentials are invalid THEN the server SHALL return an error and not establish the connection
7. WHEN no client credentials are provided THEN the server SHALL fall back to configuration file or environment variable credentials

### Requirement 12: Complete Custom Component Feature Migration

**User Story:** As a user migrating from the Home Assistant custom component, I want all existing functionality available through MCP tools, so that I don't lose any capabilities.

#### Acceptance Criteria

1. WHEN migrating THEN the MCP server SHALL support all device types from the custom component (switches, lights, covers, sensors, climate, fans, media players, alarms, etc.)
2. WHEN migrating THEN the MCP server SHALL support all control operations available in the custom component
3. WHEN migrating THEN the MCP server SHALL support all sensor readings and state monitoring from the custom component
4. WHEN migrating THEN the MCP server SHALL support alarm control panel operations with PIN codes
5. WHEN migrating THEN the MCP server SHALL support media player controls (play, pause, volume, etc.)
6. WHEN migrating THEN the MCP server SHALL support fan speed controls and modes
7. WHEN migrating THEN the MCP server SHALL support text input controls for Loxone text inputs
8. WHEN migrating THEN the MCP server SHALL support number input controls for Loxone sliders
9. WHEN migrating THEN the MCP server SHALL support all climate control features (temperature, mode, fan speed)

### Requirement 13: Enhanced Room-Based Device Management

**User Story:** As a user, I want comprehensive room-based device management through MCP tools, so that I can easily organize and control devices by location.

#### Acceptance Criteria

1. WHEN the "loxone_list_rooms" tool is called THEN it SHALL return a list of all rooms with device counts
2. WHEN the "loxone_get_room_devices" tool is called with a room name THEN it SHALL return all devices in that room with their current states
3. WHEN the "loxone_control_room" tool is called with a room name and action THEN it SHALL perform the action on all compatible devices in that room (e.g., "lights_off", "all_off")
4. WHEN room-based control is executed THEN it SHALL return a summary of which devices were affected and their new states
5. WHEN a room name is invalid THEN it SHALL return an error with available room names

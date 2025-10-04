# Loxone MCP Control Enhancement - Design Document

## Overview

This design document outlines the architecture and implementation approach for enhancing the existing Loxone MCP server with comprehensive device control capabilities. The enhancement will extend the current read-only MCP interface to support bidirectional communication, enabling full home automation control through standardized MCP tools.

The design focuses on maintaining backward compatibility while adding robust control functionality that integrates seamlessly with the existing device discovery and state management systems.

## Architecture

### High-Level Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   MCP Client    │    │  Loxone MCP     │    │   Loxone        │
│   (AI Agent)    │◄──►│    Server       │◄──►│  Miniserver     │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │  Device State   │
                       │     Cache       │
                       └─────────────────┘
```

### Component Architecture

```
Loxone MCP Server
├── MCP Tools Layer (FastMCP)
│   ├── Device Query Tools (existing)
│   │   ├── loxone_list_devices
│   │   ├── loxone_get_device_state
│   │   └── loxone_test_connection
│   └── Device Control Tools (new)
│       ├── loxone_control_switch
│       ├── loxone_control_dimmer
│       ├── loxone_control_cover
│       ├── loxone_trigger_scene
│       ├── loxone_set_mood
│       ├── loxone_control_climate
│       ├── loxone_control_room
│       └── loxone_batch_control
├── Session Management Layer
│   ├── ConnectionManager (existing)
│   ├── ClientSession (enhanced)
│   └── CommandQueue (new)
├── Device Management Layer
│   ├── DeviceManager (enhanced)
│   ├── StateCache (enhanced)
│   └── CommandValidator (new)
├── Protocol Layer
│   ├── LoxoneClient (enhanced)
│   ├── WebSocketManager (enhanced)
│   └── EncryptionHandler (existing)
└── Configuration Layer
    ├── LoxoneConfig (existing)
    └── ControlConfig (new)
```

## Components and Interfaces

### 1. Enhanced MCP Tools Layer

#### New Control Tools

**loxone_control_switch**
```python
async def loxone_control_switch(
    host: str,
    username: str, 
    password: str,
    uuid: str,
    state: bool,  # True=On, False=Off
    port: int = 80,
    client_id: str = "default"
) -> dict[str, Any]
```

**loxone_control_dimmer**
```python
async def loxone_control_dimmer(
    host: str,
    username: str,
    password: str, 
    uuid: str,
    brightness: int,  # 0-100
    port: int = 80,
    client_id: str = "default"
) -> dict[str, Any]
```

**loxone_control_cover**
```python
async def loxone_control_cover(
    host: str,
    username: str,
    password: str,
    uuid: str,
    action: str,  # "open", "close", "stop", "position"
    position: int = None,  # 0-100, required if action="position"
    tilt: int = None,  # 0-100, optional for jalousies
    port: int = 80,
    client_id: str = "default"
) -> dict[str, Any]
```

**loxone_trigger_scene**
```python
async def loxone_trigger_scene(
    host: str,
    username: str,
    password: str,
    uuid: str,  # Scene or state switch UUID
    port: int = 80,
    client_id: str = "default"
) -> dict[str, Any]
```

**loxone_control_room**
```python
async def loxone_control_room(
    host: str,
    username: str,
    password: str,
    room: str,
    action: str,  # "lights_on", "lights_off", "blinds_open", "blinds_close"
    port: int = 80,
    client_id: str = "default"
) -> dict[str, Any]
```

### 2. Enhanced ClientSession

The `ClientSession` class will be extended with new control methods:

```python
class ClientSession:
    # Existing methods...
    
    # New control methods
    async def control_switch(self, uuid: str, state: bool) -> Dict[str, Any]
    async def control_dimmer(self, uuid: str, brightness: int) -> Dict[str, Any]
    async def control_cover(self, uuid: str, action: str, **kwargs) -> Dict[str, Any]
    async def trigger_scene(self, uuid: str) -> Dict[str, Any]
    async def set_mood(self, uuid: str) -> Dict[str, Any]
    async def control_climate(self, uuid: str, **kwargs) -> Dict[str, Any]
    async def control_room(self, room: str, action: str) -> Dict[str, Any]
    async def batch_control(self, commands: List[Dict]) -> Dict[str, Any]
    
    # Enhanced command sending
    async def send_command_with_validation(self, uuid: str, value: str) -> Dict[str, Any]
    async def send_secured_command_with_validation(self, uuid: str, value: str, code: str) -> Dict[str, Any]
```

### 3. Command Validation System

New `CommandValidator` class to ensure command safety and correctness:

```python
class CommandValidator:
    def validate_switch_command(self, device: LoxoneDevice, state: bool) -> ValidationResult
    def validate_dimmer_command(self, device: LoxoneDevice, brightness: int) -> ValidationResult
    def validate_cover_command(self, device: LoxoneDevice, action: str, **kwargs) -> ValidationResult
    def validate_climate_command(self, device: LoxoneDevice, **kwargs) -> ValidationResult
    def validate_device_compatibility(self, device: LoxoneDevice, command_type: str) -> bool
    def sanitize_command_value(self, value: Any, expected_type: str, range_limits: tuple) -> Any
```

### 4. Enhanced LoxoneClient

Extensions to support reliable command sending:

```python
class LoxoneClient:
    # Existing methods...
    
    # Enhanced command methods
    async def send_command_with_retry(self, uuid: str, value: str, max_retries: int = 3) -> bool
    async def send_batch_commands(self, commands: List[Tuple[str, str]]) -> Dict[str, bool]
    async def wait_for_command_confirmation(self, uuid: str, timeout: float = 5.0) -> bool
    
    # State synchronization
    async def force_state_refresh(self, uuid: str = None) -> None
    def register_command_callback(self, callback: Callable) -> None
```

### 5. Command Queue System

New `CommandQueue` class for handling command ordering and retry logic:

```python
class CommandQueue:
    def __init__(self, max_concurrent: int = 5)
    async def enqueue_command(self, command: Command) -> str  # Returns command_id
    async def execute_next(self) -> Optional[CommandResult]
    async def retry_failed_command(self, command_id: str) -> bool
    def get_queue_status(self) -> Dict[str, Any]
    def cancel_command(self, command_id: str) -> bool
```

## Data Models

### Enhanced Device Capabilities

Extend the existing `LoxoneDevice` class with control-specific metadata:

```python
@dataclass
class LoxoneDevice:
    # Existing fields...
    
    # Enhanced control metadata
    control_commands: Dict[str, Any] = field(default_factory=dict)
    command_validation: Dict[str, Any] = field(default_factory=dict)
    last_command_time: Optional[float] = None
    command_history: List[Dict[str, Any]] = field(default_factory=list)
    
    def get_supported_commands(self) -> List[str]
    def validate_command(self, command: str, value: Any) -> bool
    def add_command_to_history(self, command: str, value: Any, result: bool) -> None
```

### Command Models

```python
@dataclass
class Command:
    uuid: str
    command_type: str
    value: Any
    timestamp: float
    client_id: str
    retry_count: int = 0
    max_retries: int = 3
    timeout: float = 5.0
    
@dataclass 
class CommandResult:
    command: Command
    success: bool
    response: Dict[str, Any]
    execution_time: float
    error_message: Optional[str] = None
```

## Error Handling

### Error Classification

1. **Validation Errors**: Invalid parameters, unsupported device types
2. **Connection Errors**: WebSocket disconnection, timeout issues  
3. **Authentication Errors**: Invalid credentials, expired tokens
4. **Device Errors**: Device unreachable, command rejected by device
5. **System Errors**: Internal server errors, resource exhaustion

### Error Response Format

```python
{
    "success": false,
    "error_code": "DEVICE_VALIDATION_FAILED",
    "error_message": "Brightness value 150 is outside valid range 0-100",
    "details": {
        "parameter": "brightness",
        "provided_value": 150,
        "valid_range": [0, 100],
        "device_uuid": "15c2a003-024d-777c-ffff24b3ef2f8379"
    },
    "context": {
        "device_name": "Lichtsteuerung",
        "device_type": "LightControllerV2",
        "room": "Empore"
    },
    "retry_suggested": true,
    "retry_delay": 1.0
}
```

### Retry Strategy

- **Connection Errors**: Exponential backoff (1s, 2s, 4s, 8s)
- **Device Busy**: Linear retry (1s intervals, max 5 retries)
- **Validation Errors**: No retry (immediate failure)
- **Authentication Errors**: Token refresh attempt, then fail

## Testing Strategy

### Unit Testing

1. **Command Validation Tests**
   - Test all parameter validation rules
   - Test device type compatibility checks
   - Test edge cases and boundary conditions

2. **Protocol Communication Tests**
   - Mock WebSocket communication
   - Test command encoding/decoding
   - Test error response parsing

3. **State Management Tests**
   - Test state cache updates after commands
   - Test state synchronization scenarios
   - Test concurrent access patterns

### Integration Testing

1. **End-to-End Control Tests**
   - Test complete command flow from MCP tool to device
   - Test state consistency after commands
   - Test error propagation through all layers

2. **Multi-Device Scenarios**
   - Test room control operations
   - Test batch command execution
   - Test concurrent device control

3. **Resilience Testing**
   - Test behavior during connection loss
   - Test command queue behavior under load
   - Test recovery after Miniserver restart

### Performance Testing

1. **Command Throughput**
   - Measure commands per second capacity
   - Test queue performance under load
   - Identify bottlenecks in command processing

2. **State Synchronization Performance**
   - Measure state update latency
   - Test cache performance with large device counts
   - Test memory usage patterns

## Security Considerations

### Authentication and Authorization

1. **Credential Management**
   - Secure storage of Loxone credentials
   - Token refresh mechanisms
   - Session timeout handling

2. **Command Authorization**
   - Validate client permissions for device control
   - Implement rate limiting for command execution
   - Log all control operations for audit

### Input Validation

1. **Parameter Sanitization**
   - Validate all input parameters against expected ranges
   - Prevent injection attacks through command values
   - Sanitize device UUIDs and room names

2. **Device State Validation**
   - Verify device exists before sending commands
   - Check device capabilities before command execution
   - Validate command compatibility with device type

## Deployment Considerations

### Configuration Management

1. **Control Feature Flags**
   - Enable/disable control features per client
   - Configure command rate limits
   - Set retry policies and timeouts

2. **Device Access Control**
   - Configure which devices can be controlled
   - Set room-level access permissions
   - Define secured device PIN requirements

### Monitoring and Observability

1. **Command Metrics**
   - Track command success/failure rates
   - Monitor command execution times
   - Alert on high error rates

2. **System Health**
   - Monitor WebSocket connection stability
   - Track device state synchronization lag
   - Monitor memory and CPU usage patterns

### Backward Compatibility

1. **Existing API Preservation**
   - All existing MCP tools remain unchanged
   - Existing client sessions continue to work
   - No breaking changes to current interfaces

2. **Graceful Degradation**
   - Control features fail gracefully if unavailable
   - Read-only mode fallback for connection issues
   - Clear error messages for unsupported operations
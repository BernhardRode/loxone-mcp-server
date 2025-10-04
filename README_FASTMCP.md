# Loxone FastMCP Client & Server

This project provides a FastMCP (Model Context Protocol) server and client for Loxone Miniserver integration. It allows you to list rooms and devices from your Loxone smart home system using the modern FastMCP framework.

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- `uv` package manager (recommended) or `pip`
- Access to a Loxone Miniserver

### Installation

1. **Clone and setup the project:**
   ```bash
   git clone <repository-url>
   cd PyLoxone
   uv sync
   ```

2. **Configure your Loxone credentials:**
   ```bash
   cp .env.example .env
   # Edit .env with your Loxone Miniserver details
   ```

   Update `.env` with your actual values:
   ```bash
   LOXONE_HOST=192.168.1.100        # Your Miniserver IP
   LOXONE_USERNAME=admin            # Your username
   LOXONE_PASSWORD=your-password    # Your password
   LOXONE_PORT=80                   # Port (80 for HTTP, 443 for HTTPS)
   ```

### Usage

#### Running the MCP Server

```bash
# Start the MCP server (runs in STDIO mode for MCP clients)
uv run mcp-server
```

#### Running the Demo Client

```bash
# Set environment variables (or use .env file)
export LOXONE_HOST=192.168.1.100
export LOXONE_USERNAME=admin
export LOXONE_PASSWORD=your-password
export LOXONE_PORT=80

# Run the demo client
uv run mcp-client
```

Or use the standalone demo script:
```bash
uv run python scripts/demo_client.py
```

## 🏗️ Architecture

### FastMCP Server (`simple_server.py`)

The server provides two main MCP tools:

1. **`loxone_list_devices`** - List all devices with optional filtering
2. **`loxone_get_device_state`** - Get current state of a specific device

**Key Features:**
- ✅ Stateless design - credentials provided per request
- ✅ Proper error handling and validation
- ✅ FastMCP 2.0 compatible
- ✅ Automatic connection management
- ✅ Device filtering by type and room

### FastMCP Client (`client.py`)

The client demonstrates how to:
- Connect to the FastMCP server
- List all devices and group them by room
- Filter devices by type
- Get device states
- Handle errors gracefully

## 📋 Available Tools

### `loxone_list_devices`

Lists all Loxone devices with optional filtering.

**Parameters:**
- `host` (required): Miniserver IP/hostname
- `username` (required): Loxone username
- `password` (required): Loxone password
- `port` (optional): Port number (default: 80)
- `client_id` (optional): Client identifier (default: "default")
- `device_type` (optional): Filter by device type (e.g., "Dimmer", "Switch")
- `room` (optional): Filter by room name

**Example Response:**
```json
{
  "success": true,
  "devices": [
    {
      "uuid": "12345678-1234-1234-1234-123456789001",
      "name": "Living Room Main Light",
      "type": "Dimmer",
      "room": "Living Room",
      "category": "Lighting"
    }
  ],
  "count": 1,
  "filters_applied": {
    "device_type": null,
    "room": null
  }
}
```

### `loxone_get_device_state`

Gets the current state of a specific device.

**Parameters:**
- `host` (required): Miniserver IP/hostname
- `username` (required): Loxone username
- `password` (required): Loxone password
- `uuid` (required): Device UUID
- `port` (optional): Port number (default: 80)
- `client_id` (optional): Client identifier (default: "default")

**Example Response:**
```json
{
  "success": true,
  "uuid": "12345678-1234-1234-1234-123456789001",
  "name": "Living Room Main Light",
  "type": "Dimmer",
  "room": "Living Room",
  "category": "Lighting",
  "state": {
    "brightness": 75.5,
    "active": 1
  },
  "details": {
    "defaultRating": 0,
    "room": "0f1e7a66-0179-7f1e-ffff403fb0c34b9e"
  }
}
```

## 🔧 Development

### Project Structure

```
src/loxone_mcp/
├── simple_server.py      # FastMCP server implementation
├── client.py            # FastMCP client implementation
├── loxone_client.py     # Loxone WebSocket client
├── config.py            # Configuration management
├── device_manager.py    # Device data management
└── ...

scripts/
├── demo_client.py       # Standalone demo client
├── test_fastmcp.py     # FastMCP connection test
└── ...
```

### Testing

1. **Test FastMCP connection:**
   ```bash
   uv run python scripts/test_fastmcp.py
   ```

2. **Test with real Loxone server:**
   ```bash
   # Set your credentials
   export LOXONE_HOST=your-miniserver-ip
   export LOXONE_USERNAME=your-username
   export LOXONE_PASSWORD=your-password
   
   # Run demo
   uv run python scripts/demo_client.py
   ```

### Adding New Tools

To add new MCP tools, edit `simple_server.py`:

```python
@mcp.tool()
async def your_new_tool(
    host: str,
    username: str,
    password: str,
    # ... other parameters
) -> dict[str, Any]:
    """
    Your tool description.
    
    Args:
        host: Miniserver IP/hostname
        # ... parameter descriptions
    
    Returns:
        Standardized response dictionary
    """
    # Your implementation here
    pass
```

## 🐛 Troubleshooting

### Common Issues

1. **Connection Failed (HTTP 404)**
   - Check if the Miniserver IP is correct
   - Ensure the Miniserver is powered on and reachable
   - Verify network connectivity

2. **Authentication Failed**
   - Check username and password
   - Ensure the user has appropriate permissions
   - Try logging in via Loxone Config to verify credentials

3. **Import Errors**
   - Make sure you're using `uv run` or have activated the virtual environment
   - Check that all dependencies are installed: `uv sync`

4. **FastMCP Connection Issues**
   - Ensure you're using the correct server script path
   - Check that the server starts without errors
   - Verify FastMCP is properly installed: `uv add fastmcp`

### Debug Mode

Enable debug logging by setting:
```bash
export LOG_LEVEL=DEBUG
```

### Network Diagnostics

Test basic connectivity:
```bash
# Test HTTP connectivity
curl http://your-miniserver-ip/jdev/sys/getPublicKey

# Test with authentication
curl -u username:password http://your-miniserver-ip/data/LoxAPP3.json
```

## 📚 FastMCP Integration

This implementation follows FastMCP best practices:

- ✅ **Stateless Design**: No server-side credential storage
- ✅ **Proper Error Handling**: Standardized error responses
- ✅ **Type Safety**: Full type annotations
- ✅ **Documentation**: Comprehensive docstrings
- ✅ **Async/Await**: Modern async patterns
- ✅ **Connection Management**: Automatic cleanup

### Using with MCP Clients

The server can be used with any MCP-compatible client:

1. **Claude Desktop**: Add to MCP configuration
2. **Custom Clients**: Use FastMCP Client library
3. **Other MCP Tools**: Standard MCP protocol support

Example MCP configuration for Claude Desktop:
```json
{
  "mcpServers": {
    "loxone": {
      "command": "uv",
      "args": ["run", "mcp-server"],
      "cwd": "/path/to/PyLoxone"
    }
  }
}
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🔗 Related Projects

- [FastMCP](https://gofastmcp.com) - Modern MCP framework
- [Loxone](https://www.loxone.com) - Smart home automation
- [Model Context Protocol](https://modelcontextprotocol.io) - MCP specification
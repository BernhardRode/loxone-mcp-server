# Loxone MCP Server

A Model Context Protocol (MCP) server that connects AI assistants and IDEs to your Loxone smart home system. Control lights, blinds, climate, and scenes through natural language or code.

## What it does

- **Device Control**: Turn lights on/off, adjust dimmers, control blinds and climate
- **Scene Management**: Trigger Loxone scenes and automation scenarios  
- **Real-time Updates**: Live device state monitoring via WebSocket
- **Secure Access**: PIN-protected commands for security devices
- **Auto Discovery**: Finds all your Loxone devices automatically

## Requirements

- Python 3.10+
- Loxone Miniserver (Gen 1/2, firmware 10.0+)
- Network access to your Miniserver
- Valid Miniserver credentials

## Local Setup

### Install uv (Python package manager)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)  
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Install and run the server

```bash
# Clone and setup
git clone <repository-url>
cd loxone-mcp-server

# Install dependencies
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# Run the server (no configuration needed)
uv run loxone-mcp-server
```

## Configuration

The server is **stateless** and does not require environment credentials. Each MCP client provides credentials when calling tools.

Optional server configuration:

```bash
# Optional server settings
MCP_TRANSPORT=http    # Set to 'http' for HTTP mode (default: 'stdio')
MCP_HOST=127.0.0.1    # HTTP host (default: '127.0.0.1')
MCP_PORT=8000         # HTTP port (default: 8000)
LOG_LEVEL=INFO        # Logging level
```

## Running the MCP Server

The server supports two transport modes:

### 1. Stdio Mode (Default)
For MCP clients like Claude Desktop that connect via stdio:

```bash
# Run with stdio transport (default)
uv run loxone-mcp-server
```

### 2. HTTP Mode  
For web-based clients or Amazon Q CLI that connect via HTTP:

```bash
# Run with HTTP transport
MCP_TRANSPORT=http uv run loxone-mcp-server

# Or use the dedicated HTTP command
uv run loxone-mcp-server-http

# Server will be available at: http://127.0.0.1:8000/mcp
```

## Amazon Q CLI MCP Configuration

### Setup Amazon Q CLI Agent (Stdio Mode)

The project includes a pre-configured Amazon Q CLI agent:

```bash
# Activate the agent (no credentials needed - provided per tool call)
q use agent loxone-smart-home
```

The agent configuration is in `.amazonq/cli-agents/loxone-agent.json` and includes:
- MCP server setup with `uv` runner
- Allowed tools for safe operation
- Resource access to docs and config files

**Note:** Credentials are now provided per tool call, not stored in settings.

### Setup Amazon Q CLI with HTTP Transport

To use Amazon Q CLI with HTTP transport, run the server in one console and configure Q CLI to connect via HTTP:

**Console 1 - Start the HTTP server:**
```bash
# Start HTTP server (no credentials needed)
MCP_TRANSPORT=http uv run loxone-mcp-server

# Server will show: "MCP endpoint will be available at: http://127.0.0.1:8000/mcp"
```

**Console 2 - Configure Amazon Q CLI:**
```bash
# Create HTTP-based agent configuration
q agent create loxone-http --mcp-server http://127.0.0.1:8000/mcp

# Or modify existing agent to use HTTP endpoint
q settings set agent.loxone-smart-home.mcp_endpoint http://127.0.0.1:8000/mcp

# Use the agent
q use agent loxone-http
```

### Using with Other MCP Clients

#### Claude Desktop (Stdio Mode)

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "loxone": {
      "command": "uv",
      "args": ["--directory", "/path/to/loxone-mcp-server", "run", "loxone-mcp-server"]
    }
  }
}
```

#### Claude Desktop (HTTP Mode)

For HTTP mode, start the server separately and configure Claude Desktop to connect via HTTP:

1. **Start the server in HTTP mode:**
```bash
MCP_TRANSPORT=http uv run loxone-mcp-server
```

2. **Configure Claude Desktop for HTTP:**
```json
{
  "mcpServers": {
    "loxone": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

#### Other MCP Clients

- **Stdio mode**: Use the command-line pattern shown above
- **HTTP mode**: Connect to `http://127.0.0.1:8000/mcp` endpoint

## Available MCP Tools

The server provides these tools for AI assistants. **All tools require Miniserver credentials as parameters:**

- **`loxone_list_devices`** - List all devices (requires: host, username, password)
- **`loxone_get_device_state`** - Get current device state (requires: host, username, password, uuid)
- **`loxone_set_switch`** - Turn switches on/off (requires: host, username, password, uuid, state)
- **`loxone_set_dimmer`** - Control light brightness (requires: host, username, password, uuid, brightness)
- **`loxone_set_cover_position`** - Control blinds/covers (requires: host, username, password, uuid, position)
- **`loxone_set_temperature`** - Set climate target temperature (requires: host, username, password, uuid, temperature)
- **`loxone_list_scenes`** - List available scenes (requires: host, username, password)
- **`loxone_trigger_scene`** - Activate a scene (requires: host, username, password, uuid)
- **`loxone_send_command`** - Send raw commands (requires: host, username, password, uuid, value)
- **`loxone_send_secured_command`** - PIN-protected commands (requires: host, username, password, uuid, value, code)

**Example usage:** 
- "List devices on my Miniserver at 192.168.1.100 with username admin and password mypass"
- "Turn on device uuid abc123 on Miniserver 192.168.1.100 with credentials admin/mypass"

## Development

### Setup Development Environment

```bash
# Install dependencies
uv pip install -e ".[dev]"

# Setup pre-commit hooks (optional but recommended)
make setup-pre-commit
```

### Running Tests and Checks

```bash
# Run all CI checks locally
make ci-check

# Individual commands
make test          # Run tests with coverage
make lint          # Check code with ruff
make format        # Format code with black
make type-check    # Type check with mypy
```

### Testing with Real Miniserver

```bash
# Integration tests now use credentials passed to tools
uv run pytest tests/integration/
```

### Testing HTTP Transport

```bash
# Start server in HTTP mode (no credentials needed)
MCP_TRANSPORT=http uv run loxone-mcp-server

# In another terminal, test the endpoint
curl -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "ping"}'
```

## Troubleshooting

### Common Issues

**Connection Failed**
- Check Miniserver IP and credentials
- Verify network connectivity: `ping <miniserver-ip>`
- Ensure ports 80/443 are accessible

**Authentication Failed**  
- Verify username/password in Loxone Config
- Delete token file and restart: `rm loxone_token.json`
- Check user permissions in Loxone Config

**Device Not Found**
- Restart server to reload device structure
- Check device UUID in Loxone Config
- Ensure device is not hidden/disabled

**Debug Logging**
```bash
export LOG_LEVEL=DEBUG
uv run loxone-mcp-server
```

## License

MIT License - see LICENSE file for details.

## Related Projects

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Loxone Smart Home](https://www.loxone.com/)
- [Home Assistant Loxone Integration](https://www.home-assistant.io/integrations/loxone/)

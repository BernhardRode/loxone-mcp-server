# Amazon Q Developer CLI Integration Guide

This guide shows you how to configure Amazon Q Developer CLI to provide credentials for the Loxone MCP server, allowing you to run the server without hardcoding credentials.

## Prerequisites

1. **Amazon Q Developer CLI installed**
   ```bash
   # Install Q Developer CLI (if not already installed)
   # Follow instructions at: https://github.com/aws/amazon-q-developer-cli
   ```

2. **Loxone MCP Server project**
   ```bash
   # Ensure you're in the project directory
   cd /path/to/loxone-mcp-server
   
   # Install dependencies
   uv sync
   ```

## Configuration Methods

### Method 1: Q Developer CLI Settings (Recommended)

Configure Loxone credentials using Q Developer CLI settings:

```bash
# Set Loxone Miniserver details
q settings set loxone.host 192.168.1.100
q settings set loxone.username admin
q settings set loxone.password your-password
q settings set loxone.port 80  # Optional, defaults to 80

# Verify settings
q settings get loxone
```

### Method 2: Environment Variables with Q_ Prefix

Set environment variables that the integration script will detect:

```bash
export Q_LOXONE_HOST=192.168.1.100
export Q_LOXONE_USERNAME=admin
export Q_LOXONE_PASSWORD=your-password
export Q_LOXONE_PORT=80  # Optional
```

### Method 3: Q Developer Configuration File

Create or edit the Q Developer configuration file:

**Location**: `~/.amazonq/config.json`

```json
{
  "loxone": {
    "host": "192.168.1.100",
    "username": "admin", 
    "password": "your-password",
    "port": 80
  },
  "tools": {
    "loxone-mcp": {
      "enabled": true,
      "auto_start": false
    }
  }
}
```

## Running the Server

### Using the Integration Script

```bash
# Make the script executable
chmod +x scripts/q-developer-integration.py

# Test credential retrieval
./scripts/q-developer-integration.py --test-credentials

# Show configuration that would be used
./scripts/q-developer-integration.py --show-config

# Run the MCP server with Q Developer credentials
./scripts/q-developer-integration.py

# Run with additional server arguments
./scripts/q-developer-integration.py --help
./scripts/q-developer-integration.py --log-level DEBUG
```

### Direct uv Commands

Once credentials are configured, you can also run directly:

```bash
# The integration script sets environment variables, so you can also run:
source <(python scripts/q-developer-integration.py --export-env)
uv run loxone-mcp-server
```

## MCP Client Configuration

### Claude Desktop with Q Developer Integration

Add this to your Claude Desktop MCP configuration:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**Linux**: `~/.config/claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "loxone": {
      "command": "python",
      "args": [
        "/path/to/loxone-mcp-server/scripts/q-developer-integration.py"
      ],
      "cwd": "/path/to/loxone-mcp-server"
    }
  }
}
```

### Alternative: Using uv with Q Developer

```json
{
  "mcpServers": {
    "loxone": {
      "command": "uv",
      "args": [
        "run", 
        "python",
        "scripts/q-developer-integration.py"
      ],
      "cwd": "/path/to/loxone-mcp-server"
    }
  }
}
```

## Troubleshooting

### Credential Issues

```bash
# Check if Q Developer CLI is working
q --version

# Test credential retrieval
./scripts/q-developer-integration.py --test-credentials

# Show what configuration would be used
./scripts/q-developer-integration.py --show-config

# Check Q Developer settings
q settings list | grep loxone
```

### Connection Issues

```bash
# Test with debug logging
./scripts/q-developer-integration.py --log-level DEBUG

# Test connection to Miniserver
ping 192.168.1.100

# Check if Miniserver is accessible
curl http://192.168.1.100/jdev/cfg/api
```

### Environment Issues

```bash
# Check Python and uv installation
python --version
uv --version

# Verify project setup
uv run python -c "import loxone_mcp; print('OK')"

# Check virtual environment
uv run which python
```

## Security Best Practices

1. **Use Q Developer CLI settings** instead of environment variables when possible
2. **Protect configuration files** with appropriate permissions:
   ```bash
   chmod 600 ~/.amazonq/config.json
   ```
3. **Use read-only Miniserver users** for monitoring-only scenarios
4. **Regularly rotate passwords** and regenerate tokens
5. **Monitor access logs** on your Miniserver

## Advanced Configuration

### Custom Configuration Locations

You can specify custom configuration file locations:

```bash
# Set custom config path
export Q_CONFIG_PATH=/path/to/custom/config.json
./scripts/q-developer-integration.py
```

### Integration with CI/CD

For automated deployments, use environment variables:

```bash
# In your CI/CD pipeline
export Q_LOXONE_HOST=$LOXONE_HOST_SECRET
export Q_LOXONE_USERNAME=$LOXONE_USERNAME_SECRET  
export Q_LOXONE_PASSWORD=$LOXONE_PASSWORD_SECRET

# Run the server
python scripts/q-developer-integration.py
```

### Multiple Miniserver Support

Configure multiple Miniservers:

```json
{
  "loxone": {
    "default": {
      "host": "192.168.1.100",
      "username": "admin",
      "password": "password1"
    },
    "office": {
      "host": "192.168.1.101", 
      "username": "admin",
      "password": "password2"
    }
  }
}
```

Then specify which one to use:

```bash
export Q_LOXONE_PROFILE=office
./scripts/q-developer-integration.py
```

## Next Steps

1. **Configure your credentials** using one of the methods above
2. **Test the integration** with `--test-credentials`
3. **Run the MCP server** and verify it connects to your Miniserver
4. **Configure your MCP client** (Claude Desktop, etc.) to use the server
5. **Test device discovery** and control through your MCP client

For more information, see the main [README.md](../README.md) and [troubleshooting guide](troubleshooting.md).
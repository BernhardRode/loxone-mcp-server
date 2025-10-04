#!/bin/bash

# Loxone MCP Server & Client Example
# This script shows how to run the server and client as requested

echo "🏠 Loxone MCP Server & Client Example"
echo "====================================="
echo

# Check if environment variables are set
if [ -z "$LOXONE_HOST" ] || [ -z "$LOXONE_USERNAME" ] || [ -z "$LOXONE_PASSWORD" ]; then
    echo "⚠️  Please set your Loxone credentials first:"
    echo
    echo "export LOXONE_HOST=192.168.1.100"
    echo "export LOXONE_USERNAME=admin"
    echo "export LOXONE_PASSWORD=your-password"
    echo "export LOXONE_PORT=80  # optional"
    echo
    echo "Then run this script again."
    exit 1
fi

echo "✅ Environment variables detected:"
echo "   LOXONE_HOST: $LOXONE_HOST"
echo "   LOXONE_USERNAME: $LOXONE_USERNAME"
echo "   LOXONE_PORT: ${LOXONE_PORT:-80}"
echo

echo "📋 Available commands:"
echo
echo "1. Run MCP Server (STDIO mode for MCP clients):"
echo "   uv run mcp-server"
echo
echo "2. Run MCP Client (connects to server and lists rooms/devices):"
echo "   uv run mcp-client"
echo
echo "3. Run Demo Client (standalone demo with detailed output):"
echo "   uv run python scripts/demo_client.py"
echo

# Ask user what they want to run
echo "What would you like to run?"
echo "1) MCP Server"
echo "2) MCP Client" 
echo "3) Demo Client"
echo "4) Test FastMCP Connection"
read -p "Enter choice (1-4): " choice

case $choice in
    1)
        echo
        echo "🚀 Starting MCP Server..."
        echo "   (Press Ctrl+C to stop)"
        echo
        uv run mcp-server
        ;;
    2)
        echo
        echo "🚀 Starting MCP Client..."
        echo
        uv run mcp-client
        ;;
    3)
        echo
        echo "🚀 Starting Demo Client..."
        echo
        uv run python scripts/demo_client.py
        ;;
    4)
        echo
        echo "🧪 Testing FastMCP Connection..."
        echo
        uv run python scripts/test_fastmcp.py
        ;;
    *)
        echo "Invalid choice. Please run the script again and choose 1-4."
        exit 1
        ;;
esac
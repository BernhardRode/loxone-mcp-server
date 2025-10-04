#!/usr/bin/env python3
"""Smoke test to verify the package can be imported and basic functionality works."""


def test_import():
    """Test that the main module can be imported."""
    try:
        import loxone_mcp  # noqa: F401

        print("✓ Successfully imported loxone_mcp")
    except ImportError as e:
        print(f"✗ Failed to import loxone_mcp: {e}")
        exit(1)


def test_server_creation():
    """Test that the server module can be imported."""
    try:
        from loxone_mcp.simple_server import mcp

        assert mcp is not None
        print("✓ Successfully imported MCP server")
    except Exception as e:
        print(f"✗ Failed to import server: {e}")
        exit(1)


if __name__ == "__main__":
    print("Running smoke tests...")
    test_import()
    test_server_creation()
    print("✓ All smoke tests passed!")

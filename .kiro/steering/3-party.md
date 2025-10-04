---
inclusion: always
---

# Third-Party Dependencies & External Tools

## Context7 MCP Integration

When working with external dependencies and tools, always verify current information using Context7 MCP before making recommendations or implementing changes.

### Required MCP Lookups

Before working with these tools, fetch latest documentation:

- **UV** - uv is an extremely fast Python package and project manager, we use it for everything python related
- **Release Please** - Automated release management
- **Release Please Actions** - GitHub Actions integration
- **Python packaging tools** (uv, poetry, pip-tools)
- **Testing frameworks** (pytest, hypothesis, pytest-asyncio)
- **Linting/formatting tools** (ruff, black, mypy)

### Dependency Management Rules

1. **Always check latest versions** via Context7 MCP before suggesting updates
2. **Verify compatibility** with current Python version (3.10+)
3. **Use pyproject.toml** as single source of truth for dependencies
4. **Lock file management** - maintain uv.lock for reproducible builds
5. **Security scanning** - verify no known vulnerabilities in suggested packages

### Integration Patterns

- Use Context7 MCP to get current best practices for tool configuration
- Verify GitHub Actions workflow patterns are up-to-date
- Check for breaking changes in major version updates
- Ensure networking libraries (websockets, aiohttp, uvloop) are current

### Before Making Changes

1. Query Context7 MCP for latest tool documentation
2. Check release notes for breaking changes
3. Verify compatibility with existing codebase
4. Test changes in isolated environment first
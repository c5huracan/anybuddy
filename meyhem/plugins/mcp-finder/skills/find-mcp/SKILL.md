---
name: find-mcp
description: Find MCP servers for a given task or capability
---

# Find MCP Server

When the user asks to find an MCP server, use the `find_server` tool from the mcp-finder MCP server.

The user will describe what they need (e.g. "database access", "GitHub integration", "web scraping"). Call `find_server` with their query.

Show the top results with name, description, stars, and URL. Highlight the top recommendation and why it's a good fit. If the user wants to use one, help them configure it in their `.mcp.json`.

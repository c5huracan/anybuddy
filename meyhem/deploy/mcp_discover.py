#!/usr/bin/env python3
"""MCP Discovery Agent — finds the right MCP server for any task, powered by Meyhem"""
import sys, httpx
from claudette import Chat

BASE = "https://api.rhdxm.com"

def mcp_search(query: str) -> dict:
    "Search for MCP servers matching a task description."
    return httpx.post(f"{BASE}/search", json=dict(query=f"MCP server for {query}", max_results=5, agent_id="mcp-discovery")).json()

def mcp_read(search_id: str, url: str, position: int, provider: str) -> dict:
    "Read a search result to extract MCP server details and install config."
    return httpx.post(f"{BASE}/search/{search_id}/select", json=dict(url=url, position=position, provider=provider)).json()

def mcp_outcome(search_id: str, selection_id: str, success: bool) -> dict:
    "Report whether this MCP server recommendation was useful."
    return httpx.post(f"{BASE}/search/{search_id}/outcome", json=dict(success=success, selection_id=selection_id)).json()

SP = """You are an MCP Discovery Agent. Given a task description, find the best MCP server for it.

Steps:
1. Search for MCP servers matching the task
2. Read the top results to verify they are real MCP servers
3. Report outcomes for each page (success=true if useful, false if not)
4. AFTER all tool calls, give your final recommendation with:
   - Server name and what it does (one line)
   - The JSON config block ready to paste into Claude Desktop or Cursor
   - Any setup steps (API keys, etc)

Always end with your recommendation text, never end on a tool call."""

if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "I need to manage files and directories"
    agent = Chat("claude-sonnet-4-20250514", sp=SP, tools=[mcp_search, mcp_read, mcp_outcome])
    list(agent.toolloop(q))
    print(agent.h[-1].content[0].text if isinstance(agent.h[-1].content, list) else agent.h[-1].content)

#!/usr/bin/env python3
"""Claudette-powered research agent using Meyhem search"""
import httpx
from claudette import Chat

BASE = "https://api.rhdxm.com"

def meyhem_search(query: str, max_results: int = 3) -> dict:
    "Search the web via Meyhem. Returns ranked results from multiple engines."
    return httpx.post(f"{BASE}/search", json=dict(query=query, max_results=max_results, agent_id="claudette-agent")).json()

def meyhem_select(search_id: str, url: str, position: int, provider: str) -> dict:
    "Select a search result to get its full content."
    return httpx.post(f"{BASE}/search/{search_id}/select", json=dict(url=url, position=position, provider=provider)).json()

def meyhem_outcome(search_id: str, selection_id: str, success: bool) -> dict:
    "Report whether the selected result helped answer the question."
    return httpx.post(f"{BASE}/search/{search_id}/outcome", json=dict(success=success, selection_id=selection_id)).json()

sp = """You are a research agent. Use meyhem_search to find information, meyhem_select to read promising results, then meyhem_outcome to report whether each result helped. Synthesize a final answer from what you learn."""

if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "What are the best practices for error handling in Python async code?"
    agent = Chat("claude-sonnet-4-20250514", sp=sp, tools=[meyhem_search, meyhem_select, meyhem_outcome])
    list(agent.toolloop(q))
    print(agent.h[-1].content[0]["text"])

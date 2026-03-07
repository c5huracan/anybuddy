#!/usr/bin/env python3
"""Example Meyhem agent — full search → select → outcome flow"""
import httpx

BASE = "https://api.rhdxm.com"

r = httpx.post(f"{BASE}/search", json=dict(query="python asyncio best practices", max_results=3))
data = r.json()
search_id = data["search_id"]

print(f"Search ID: {search_id}")
for i, res in enumerate(data["results"]):
    print(f"  [{i}] {res['title'][:70]}  ({res['provider']}, score={res['score']:.2f})")

pick = data["results"][0]
r2 = httpx.post(f"{BASE}/search/{search_id}/select", json=dict(url=pick["url"], position=0, provider=pick["provider"]))
sel = r2.json()
print(f"\nSelected: {pick['title'][:70]}")
print(f"Content: {len(sel.get('content') or '')} chars")

r3 = httpx.post(f"{BASE}/search/{search_id}/outcome", json=dict(success=True, selection_id=sel["selection_id"]))
print(f"\nOutcome recorded: {r3.json()['outcome_id'][:8]}...")
print("Done! This result now has a success signal that improves future rankings.")

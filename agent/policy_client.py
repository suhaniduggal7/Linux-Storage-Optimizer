"""
policy_client.py - the agent's only way of reading policy. It never
reads a local copy of policy.json and never hardcodes rules - it
always asks the central server's /policy endpoint, so there is
exactly ONE source of truth shared by every local scan AND every
remote agent, with no second, driftable copy of "what's protected"
living on this machine.

Caches the last successful fetch for a short window so
local_executor doesn't make a network round-trip for every single
file in a batch - but execute_actions always forces a fresh fetch
right before running, so a policy change on the central server takes
effect on the very next cleanup, not up to CACHE_SECONDS later.
"""

import time
import requests

_cache = {"policy": None, "fetched_at": 0.0}
CACHE_SECONDS = 30


def get_policy(central_server: str, force_refresh: bool = False) -> dict:
    now = time.time()
    if not force_refresh and _cache["policy"] and (now - _cache["fetched_at"]) < CACHE_SECONDS:
        return _cache["policy"]

    response = requests.get(f"{central_server}/policy", timeout=10)
    response.raise_for_status()
    policy = response.json()

    _cache["policy"] = policy
    _cache["fetched_at"] = now
    return policy

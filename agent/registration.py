"""
registration.py - tells the central server this agent exists and how
to call it back. Registering doesn't trigger a scan by itself - it
just makes this machine show up in the dashboard's "Live Agents"
panel. Retries a few times on startup since, in a real deployment,
the central server and an agent can come up in either order.
"""

import time
import requests


def register_with_central(
    central_server: str,
    hostname: str,
    callback_host: str,
    agent_port: int,
    disk_threshold: float,
    retries: int = 5,
    delay: float = 3.0,
) -> bool:
    url = f"{central_server}/register"
    payload = {
        "hostname": hostname,
        "callback_host": callback_host,
        "agent_port": agent_port,
        "disk_threshold": disk_threshold,
    }

    for attempt in range(1, retries + 1):
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            print(f"[registration] Registered '{hostname}' with {central_server}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"[registration] Attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(delay)

    print(
        f"[registration] Could not register with {central_server} after {retries} attempts - "
        f"the agent will keep running and this won't block monitoring, but it won't appear "
        f"on the dashboard until registration succeeds."
    )
    return False

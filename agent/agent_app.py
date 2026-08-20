"""
agent_app.py - runs ON a monitored Linux machine, as a separate
process from the central server (server.py). This is the piece
matching the original blueprint's "Central AI Server + Linux Agent
nodes" design: instead of the central server reaching out and
pulling data (like it does for servers.json folders), each agent
PUSHES a report in on its own schedule, with zero clicks needed.

Two jobs:
  1. A background loop that checks THIS machine's own disk usage on
     an interval (check_interval_seconds in config.yaml). Once usage
     crosses disk_threshold, it collects flagged files
     (metadata.py) and POSTs a report to the central server's
     /agent-report.
  2. A small FastAPI app exposing /execute, which the central server
     calls (via /agents/{hostname}/execute) once a human has
     reviewed and approved a cleanup plan on the dashboard - see
     local_executor.py for what actually happens to a file.

Run with:
    uvicorn agent_app:app --host 0.0.0.0 --port <agent_port>
(agent_port must match config.yaml, since that's what the central
server was told to call back on at registration time.)
"""

import shutil
import threading
import time
from typing import List, Optional

import requests
import yaml
from fastapi import FastAPI
from pydantic import BaseModel

from metadata import collect_files
from registration import register_with_central
from local_executor import execute_actions

with open("config.yaml", "r") as f:
    CONFIG = yaml.safe_load(f)

CENTRAL_SERVER = CONFIG["central_server"].rstrip("/")
HOSTNAME = CONFIG["hostname"]
CALLBACK_HOST = CONFIG["callback_host"]
AGENT_PORT = CONFIG["agent_port"]
DISK_THRESHOLD = CONFIG["disk_threshold"]
CHECK_INTERVAL = CONFIG.get("check_interval_seconds", 300)
SCAN_PATHS = CONFIG.get("scan_paths", ["/"])
MIN_FILE_SIZE_MB = CONFIG.get("min_file_size_mb", 1.0)
MIN_UID = CONFIG.get("protected_uids_below", 1000)

app = FastAPI(title=f"Node Sanity Agent - {HOSTNAME}")


def get_disk_usage_percent(path: str = "/") -> float:
    try:
        total, used, free = shutil.disk_usage(path)
        return round((used / total) * 100, 1) if total else 0.0
    except OSError:
        return 0.0


def monitor_loop():
    """Runs forever in a background thread. Never raises out of the
    loop - a single bad iteration (e.g. central server briefly down)
    just gets logged and retried on the next interval."""
    while True:
        try:
            check_path = SCAN_PATHS[0] if SCAN_PATHS else "/"
            usage = get_disk_usage_percent(check_path)
            print(f"[monitor] {HOSTNAME} disk usage: {usage}% (threshold {DISK_THRESHOLD}%)")

            if usage >= DISK_THRESHOLD:
                files = collect_files(SCAN_PATHS, MIN_FILE_SIZE_MB, MIN_UID)
                print(f"[monitor] Threshold crossed - flagging {len(files)} file(s), reporting to central server")

                payload = {
                    "hostname": HOSTNAME,
                    "disk_usage_percent": usage,
                    "target_usage": DISK_THRESHOLD,
                    "files": files,
                }
                try:
                    response = requests.post(f"{CENTRAL_SERVER}/agent-report", json=payload, timeout=30)
                    response.raise_for_status()
                    print(f"[monitor] Report sent: {response.json()}")
                except requests.exceptions.RequestException as e:
                    print(f"[monitor] Could not reach central server: {e}")

        except Exception as e:
            print(f"[monitor] Unexpected error in monitor loop: {e}")

        time.sleep(CHECK_INTERVAL)


@app.on_event("startup")
def on_startup():
    register_with_central(CENTRAL_SERVER, HOSTNAME, CALLBACK_HOST, AGENT_PORT, DISK_THRESHOLD)
    thread = threading.Thread(target=monitor_loop, daemon=True)
    thread.start()


@app.get("/")
def home():
    return {"status": f"Agent '{HOSTNAME}' is running", "scan_paths": SCAN_PATHS}


@app.get("/health")
def health():
    check_path = SCAN_PATHS[0] if SCAN_PATHS else "/"
    return {
        "hostname": HOSTNAME,
        "disk_usage_percent": get_disk_usage_percent(check_path),
        "disk_threshold": DISK_THRESHOLD,
        "scan_paths": SCAN_PATHS,
    }


@app.post("/scan-now")
def scan_now():
    """Manual trigger for testing/demos, so you don't have to wait
    for the disk to actually fill up or the interval to elapse to
    see the pipeline work end-to-end."""
    files = collect_files(SCAN_PATHS, MIN_FILE_SIZE_MB, MIN_UID)
    return {"hostname": HOSTNAME, "flagged_count": len(files), "files": files[:50]}


class ExecuteAction(BaseModel):
    action: str
    path: str
    size_mb: float
    age_days: float
    type: str
    owner: str = "unknown"
    uid: Optional[int] = None
    reason: str = ""


class ExecuteRequest(BaseModel):
    actions: List[ExecuteAction]


@app.post("/execute")
def execute(payload: ExecuteRequest):
    """
    Called by the central server after a human approves a cleanup
    plan for this agent. Re-validates everything against the CURRENT
    policy (fetched fresh from central) before touching anything -
    central approval is a proposal, not a guarantee. See
    local_executor.py for the actual safety gate.
    """
    actions = [a.model_dump() for a in payload.actions]
    result = execute_actions(actions, CENTRAL_SERVER, SCAN_PATHS)
    return result

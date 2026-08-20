"""
local_executor.py - the ONLY module in the agent/ folder allowed to
actually touch a file on THIS machine. Mirrors the central
executor.py's safety model exactly:
  - Re-validates every action against a freshly-fetched policy
    (via policy_client.get_policy(force_refresh=True)) right before
    running it - never trusts a plan just because it was already
    approved centrally.
  - Never permanently deletes - "delete" goes to this machine's own
    Recycle Bin / Trash via send2trash.
  - "Compress" gzips the file next to the original, then trashes the
    original (never deletes it directly).
  - Every action is attempted independently, wrapped in try/except,
    so one failure doesn't stop the rest of the batch.

The central server's /agents/{hostname}/execute relays actions here
over HTTP after a human approves them on the dashboard - central
approval is treated as a proposal only. This is where the real,
final check happens, on the machine that actually owns the file.
"""

import gzip
import shutil
from typing import Dict, List

from send2trash import send2trash

from policy_validator import validate_action
from policy_client import get_policy


def _compress_file(path: str) -> str:
    gz_path = path + ".gz"
    with open(path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    return gz_path


def execute_actions(actions: List[Dict], central_server: str, scan_paths: List[str]) -> Dict[str, List[Dict]]:
    """
    actions: already meant to be human-approved, relayed from the
    central server. scan_paths: this agent's own configured scope,
    from config.yaml - an action outside these paths is rejected
    regardless of what the central server sent.
    """
    policy = get_policy(central_server, force_refresh=True)
    executed, failed = [], []

    for action in actions:
        ok, reason = validate_action(action, policy, scan_paths, check_exists=True)
        if not ok:
            failed.append({**action, "error": f"Rejected at execution time: {reason}"})
            continue

        path = action["path"]
        try:
            if action["action"] == "compress":
                gz_path = _compress_file(path)
                send2trash(path)
                executed.append({**action, "result": f"Compressed to {gz_path}, original sent to trash"})

            elif action["action"] == "delete":
                send2trash(path)
                executed.append({**action, "result": "Sent to Recycle Bin / Trash"})

            else:
                failed.append({**action, "error": f"Unknown action type '{action['action']}'"})

        except Exception as e:
            failed.append({**action, "error": str(e)})

    return {"executed": executed, "failed": failed}

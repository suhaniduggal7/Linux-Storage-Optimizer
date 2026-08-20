"""
metadata.py - walks this agent's configured scan_paths and builds the
file list sent inside an AgentReport to the central server's
/agent-report endpoint.

Mirrors the central scanner.py's type-guessing logic (kept in sync
manually - both are small enough that a shared import would add more
coupling than it's worth between two separately-deployable pieces),
but adds UID / protected-user info the central server has no way to
determine on its own, since it can never see this machine's
filesystem directly - only what this file chooses to report.
"""

import os
import time
from datetime import datetime, timezone
from typing import List, Dict

from user_mapper import get_username, is_protected_user


def guess_file_type(path: str) -> str:
    lower = path.lower()
    if "/log" in lower or lower.endswith(".log"):
        return "log"
    elif "/cache" in lower:
        return "cache"
    elif "backup" in lower:
        return "backup"
    elif lower.endswith(".iso"):
        return "iso"
    elif "/tmp" in lower or "/temp" in lower:
        return "tmp"
    return "other"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def collect_files(scan_paths: List[str], min_size_mb: float = 1.0, min_uid: int = 1000) -> List[Dict]:
    """
    Returns a list of file-metadata dicts for every file under
    scan_paths at or above min_size_mb - keeping the report focused
    on files actually worth a human's attention, rather than
    listing every tiny file on the box.
    """
    results = []

    for base in scan_paths:
        if not os.path.isdir(base):
            print(f"[metadata] scan path '{base}' does not exist or is not a directory - skipping")
            continue

        for root, dirs, files in os.walk(base):
            for name in files:
                full_path = os.path.join(root, name)
                try:
                    stat = os.stat(full_path)
                    size_mb = round(stat.st_size / (1024 * 1024), 2)
                    if size_mb < min_size_mb:
                        continue

                    age_days = round((time.time() - stat.st_mtime) / 86400, 1)
                    uid = getattr(stat, "st_uid", None)

                    results.append({
                        "path": full_path,
                        "size_mb": size_mb,
                        "age_days": age_days,
                        "owner": get_username(uid),
                        "uid": uid,
                        "protected_user": is_protected_user(uid, min_uid),
                        "modified": _iso(stat.st_mtime),
                        "accessed": _iso(stat.st_atime),
                        "type": guess_file_type(full_path),
                    })

                except (OSError, FileNotFoundError):
                    continue

    return results

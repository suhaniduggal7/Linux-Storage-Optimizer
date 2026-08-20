"""
user_mapper.py - maps a file's numeric UID to a username, and flags
whether that UID belongs to a protected system account.

Linux-only (uses the pwd module) - this whole agent/ folder is meant
to run on the actual Linux machine being monitored, unlike the
central server, which just serves a dashboard and can run anywhere,
including Windows.
"""

import os

try:
    import pwd
    HAS_PWD = True
except ImportError:
    HAS_PWD = False


def get_uid(path: str):
    try:
        return os.stat(path).st_uid
    except OSError:
        return None


def get_username(uid) -> str:
    if not HAS_PWD or uid is None:
        return "unknown"
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return f"uid:{uid}"


def is_protected_user(uid, min_uid: int = 1000) -> bool:
    """
    System accounts (root, daemon, www-data, ...) sit below min_uid
    on every mainstream distro - real human accounts start at
    min_uid (1000 on Debian/Ubuntu and most others). A uid that
    couldn't be read (None) is treated as protected, i.e. NOT safe
    to touch - erring toward caution rather than guessing.
    """
    if uid is None:
        return True
    return uid < min_uid

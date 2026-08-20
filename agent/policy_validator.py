"""
policy_validator.py (agent-local copy) - the same safety gate as the
central server's policy_validator.py, deployed here because this
agent is a separately-runnable process that may live on a different
machine entirely, with no access to the central codebase at runtime.

This is intentionally the same validation LOGIC, not a different or
looser one - it's kept identical to the central copy on purpose. The
policy DATA it checks against always comes from policy_client.py,
which fetches it from the central server's /policy endpoint, so
there is still only one source of truth for the actual rules - only
the validation code itself is duplicated, not the policy content.
"""

import os
from typing import Dict, List, Tuple, Union

ScopeType = Union[str, List[str]]


def _normalize(path: str) -> str:
    return os.path.normpath(path).replace("\\", "/").lower()


def is_within(path: str, parent: str) -> bool:
    """True if `path` is inside `parent` (or equal to it)."""
    p = _normalize(path)
    parent_n = _normalize(parent)
    return p == parent_n or p.startswith(parent_n + "/")


def is_within_any(path: str, parents: List[str]) -> bool:
    return any(is_within(path, parent) for parent in parents)


def validate_action(
    action: Dict,
    policy: Dict,
    allowed_scope: ScopeType,
    check_exists: bool = True,
) -> Tuple[bool, str]:
    """
    Returns (is_allowed, reason). reason explains the rejection when
    is_allowed is False, or is a short confirmation when True.

    allowed_scope: either a single scanned folder (str) or a list of
    allowed path prefixes (a remote agent's configured scan_paths).

    check_exists: set False when validating on the central server for
    a file that lives on a remote agent's disk - existence can only
    be confirmed on that agent's own machine, which re-validates with
    check_exists=True right before actually running the action.
    """
    path = action.get("path", "")
    if not path:
        return False, "Missing path"

    # 1. Must actually still exist on disk (nothing stale/fabricated) -
    #    only meaningful when checking on the machine that owns the file.
    if check_exists and not os.path.exists(path):
        return False, "File no longer exists"

    # 2. Must be inside the folder(s) that were actually in scope - a
    #    proposal can never reach outside where it was found.
    in_scope = (
        is_within(path, allowed_scope)
        if isinstance(allowed_scope, str)
        else is_within_any(path, allowed_scope)
    )
    if not in_scope:
        return False, f"Path is outside the allowed scan scope ({allowed_scope})"

    # 3. Must not be inside any never-touch system path.
    for blocked in policy.get("never_touch_paths", []):
        if is_within(path, blocked):
            return False, f"Path is inside a protected system location ({blocked})"

    # 4. Must not have a protected extension (executables, system files).
    _, ext = os.path.splitext(path)
    if ext.lower() in {e.lower() for e in policy.get("never_touch_extensions", [])}:
        return False, f"Protected file extension ({ext})"

    # 5. Must meet the age threshold.
    min_age = policy.get("min_age_days", 30)
    if action.get("age_days", 0) < min_age:
        return False, f"File is newer than the {min_age}-day policy threshold"

    # 6. Type must be one policy actually allows cleaning up.
    if action.get("type") not in policy.get("cleanup_types", []):
        return False, f"File type '{action.get('type')}' is not in the cleanup allow-list"

    # 7. Must not belong to a protected system user (uid below min_uid).
    #    Only checked when a uid is present - locally-scanned files on
    #    Windows won't have one, so this only bites for Linux agent
    #    reports, where it matters most.
    uid = action.get("uid")
    min_uid = policy.get("min_uid")
    if uid is not None and min_uid is not None and uid < min_uid:
        return False, f"File belongs to a protected system user (uid {uid} < {min_uid})"

    return True, "Passes policy"


def validate_plan(
    actions: List[Dict],
    policy: Dict,
    allowed_scope: ScopeType,
    check_exists: bool = True,
) -> Dict[str, List[Dict]]:
    """
    Runs every action through validate_action(). Returns
    {"approved": [...], "rejected": [...]} - rejected entries keep
    the original action plus a 'rejection_reason' field, so the UI
    can show the user WHY something was filtered out rather than
    just silently dropping it.
    """
    approved, rejected = [], []

    for action in actions:
        ok, reason = validate_action(action, policy, allowed_scope, check_exists)
        if ok:
            approved.append(action)
        else:
            rejected.append({**action, "rejection_reason": reason})

    return {"approved": approved, "rejected": rejected}

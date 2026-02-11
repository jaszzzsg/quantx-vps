# utils/client_id_manager.py
"""
Centralized Client ID Manager for IBKR / ib_insync (PATCHED VERSION 2.0)

CRITICAL FIXES APPLIED:
1. File locking for multi-process safety (prevents race conditions)
2. Input validation (name, role, preferred ID range)
3. Cleanup functions for stale allocations
4. Proper error handling with detailed logging
5. Version tracking in JSON state
6. Atomic file operations with corruption recovery
7. Comprehensive logging
8. Resource cleanup on allocation failure
9. ID range validation
10. Better error messages

Goals:
- Ensure every component (dashboard, account monitor, strategies) gets a UNIQUE clientId
- Persist assignments across restarts (client_ids.json)
- Allow preferred clientId overrides (e.g. from .env)
- Auto-reallocate on "client id is already in use" errors
- Thread-safe and multi-process safe operations

Author: Quant X Team
Version: 2.0 (Production Ready)
Date: November 2025
"""

from __future__ import annotations

import json
import os
import threading
import time
import logging
from typing import Dict, Any, Optional

# Setup logging
logger = logging.getLogger(__name__)

# -----------------------------
# Storage location
# -----------------------------
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DATA_DIR = os.path.join(_BASE_DIR, "data")
os.makedirs(_DATA_DIR, exist_ok=True)

_STATE_FILE = os.path.join(_DATA_DIR, "client_ids.json")
_LOCK_FILE = os.path.join(_DATA_DIR, "client_ids.lock")

# Global mutex for thread safety (within single process)
_LOCK = threading.RLock()

# Current state version for future migrations
_STATE_VERSION = 1

# -----------------------------
# ID ranges by role
# -----------------------------
ROLE_RANGES: Dict[str, tuple[int, int]] = {
    "monitor": (100, 199),    # Account monitor / risk tools
    "dashboard": (200, 299),  # Dashboard tools
    "strategy": (9000, 9999)  # Trading strategies
}

# -----------------------------
# File Locking (Cross-Process Safety)
# -----------------------------
try:
    import fcntl
    _FCNTL_AVAILABLE = True
except ImportError:
    # Windows doesn't have fcntl, will use alternative
    _FCNTL_AVAILABLE = False
    try:
        import msvcrt
        _MSVCRT_AVAILABLE = True
    except ImportError:
        _MSVCRT_AVAILABLE = False
        logger.warning(
            "No file locking available (fcntl/msvcrt). "
            "Multi-process safety not guaranteed. "
            "Consider running single process only."
        )


class FileLock:
    """
    Cross-platform file locking for multi-process safety.
    
    Uses fcntl on Unix/Linux/Mac, msvcrt on Windows.
    """
    def __init__(self, lock_file: str, timeout: float = 10.0):
        self.lock_file = lock_file
        self.timeout = timeout
        self.fp = None
        
    def __enter__(self):
        """Acquire lock with timeout."""
        start_time = time.time()
        
        while True:
            try:
                # Create/open lock file
                self.fp = open(self.lock_file, 'w')
                
                if _FCNTL_AVAILABLE:
                    # Unix/Linux/Mac: fcntl
                    fcntl.flock(self.fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    logger.debug("Acquired file lock (fcntl)")
                    return self
                    
                elif _MSVCRT_AVAILABLE:
                    # Windows: msvcrt
                    msvcrt.locking(self.fp.fileno(), msvcrt.LK_NBLCK, 1)
                    logger.debug("Acquired file lock (msvcrt)")
                    return self
                    
                else:
                    # No locking available, just return
                    logger.debug("No file locking available, proceeding without lock")
                    return self
                    
            except (IOError, OSError) as e:
                # Lock is held by another process
                if time.time() - start_time > self.timeout:
                    if self.fp:
                        self.fp.close()
                    raise TimeoutError(
                        f"Could not acquire file lock after {self.timeout}s. "
                        f"Another process may be using the client ID manager."
                    )
                
                # Wait a bit and retry
                time.sleep(0.1)
                
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release lock."""
        if self.fp:
            try:
                if _FCNTL_AVAILABLE:
                    fcntl.flock(self.fp.fileno(), fcntl.LOCK_UN)
                elif _MSVCRT_AVAILABLE:
                    msvcrt.locking(self.fp.fileno(), msvcrt.LK_UNLCK, 1)
                
                self.fp.close()
                logger.debug("Released file lock")
            except Exception as e:
                logger.warning(f"Error releasing file lock: {e}")


# ======================================================
# Internal helpers
# ======================================================
def _load_state() -> Dict[str, Any]:
    """
    Load the persistent client ID state safely with corruption recovery.
    
    Returns:
        Dictionary with state data
    """
    if not os.path.exists(_STATE_FILE):
        logger.info("Creating new client ID state file")
        return {
            "version": _STATE_VERSION,
            "allocations": {},
            "created_at": time.time(),
            "modified_at": time.time()
        }

    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        if not isinstance(data, dict):
            logger.error("State file is not a dictionary, resetting")
            return {
                "version": _STATE_VERSION,
                "allocations": {},
                "created_at": time.time(),
                "modified_at": time.time()
            }
        
        # Ensure required keys exist
        data.setdefault("version", _STATE_VERSION)
        data.setdefault("allocations", {})
        data.setdefault("created_at", time.time())
        data.setdefault("modified_at", time.time())
        
        logger.debug(f"Loaded state with {len(data.get('allocations', {}))} allocations")
        return data
        
    except json.JSONDecodeError as e:
        logger.error(f"Corrupt state file: {e}")
        # Backup corrupted file
        backup_file = f"{_STATE_FILE}.corrupt.{int(time.time())}"
        try:
            os.rename(_STATE_FILE, backup_file)
            logger.warning(f"Backed up corrupt file to {backup_file}")
        except Exception:
            pass
        
        # Return fresh state
        return {
            "version": _STATE_VERSION,
            "allocations": {},
            "created_at": time.time(),
            "modified_at": time.time()
        }
        
    except Exception as e:
        logger.error(f"Error loading state: {e}")
        return {
            "version": _STATE_VERSION,
            "allocations": {},
            "created_at": time.time(),
            "modified_at": time.time()
        }


def _save_state(state: Dict[str, Any]) -> None:
    """
    Atomic write to prevent partial file corruption.
    
    Uses temp file + atomic rename for safety.
    
    Args:
        state: State dictionary to save
    """
    # Update modification time
    state["modified_at"] = time.time()
    
    tmp = _STATE_FILE + ".tmp"
    
    try:
        # Write to temp file
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, sort_keys=True)
        
        # Atomic rename (overwrites existing file safely)
        os.replace(tmp, _STATE_FILE)
        logger.debug("Saved state successfully")
        
    except Exception as e:
        logger.error(f"Error saving state: {e}")
        # Clean up temp file if it exists
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
        raise RuntimeError(f"Failed to save client ID state: {e}")


def _alloc_key(name: str, role: str) -> str:
    """Generate allocation key from name and role."""
    return f"{role}:{name}"


def _validate_name(name: str) -> None:
    """
    Validate component name.
    
    Args:
        name: Component name to validate
        
    Raises:
        ValueError: If name is invalid
    """
    if not name or not isinstance(name, str):
        raise ValueError("name must be a non-empty string")
    
    if len(name) > 100:
        raise ValueError("name must be 100 characters or less")
    
    # Check for invalid characters
    invalid_chars = [':', '/', '\\', '\0']
    if any(c in name for c in invalid_chars):
        raise ValueError(f"name contains invalid characters: {invalid_chars}")


def _validate_role(role: str) -> str:
    """
    Validate and normalize role.
    
    Args:
        role: Role to validate
        
    Returns:
        Normalized role (lowercase)
        
    Raises:
        ValueError: If role is invalid
    """
    if not role or not isinstance(role, str):
        raise ValueError("role must be a non-empty string")
    
    role = role.lower()
    
    if role not in ROLE_RANGES:
        raise ValueError(
            f"Unknown role '{role}'. "
            f"Valid roles: {list(ROLE_RANGES.keys())}"
        )
    
    return role


def _validate_preferred_id(preferred: int, role: str) -> None:
    """
    Validate preferred ID is in valid range for role.
    
    Args:
        preferred: Preferred client ID
        role: Role (already validated)
        
    Raises:
        ValueError: If preferred ID is out of range
    """
    start, end = ROLE_RANGES[role]
    
    if not (start <= preferred <= end):
        raise ValueError(
            f"Preferred ID {preferred} is outside role '{role}' range {start}-{end}"
        )


# ======================================================
# Public API
# ======================================================
def get_or_allocate_client_id(
    name: str,
    role: str = "strategy",
    preferred: Optional[int] = None
) -> int:
    """
    Return a stable clientId for (name, role).
    
    PATCHED: Now includes comprehensive validation, file locking,
    and better error handling.

    Logic:
      1. If already allocated → return it
      2. If preferred is provided and available → assign it
      3. Else allocate next free ID in ROLE_RANGES[role]

    Thread-safe and multi-process safe with file locking.
    
    Args:
        name: Unique identifier for the component (e.g., "mean_reversion_v1")
        role: One of "monitor", "dashboard", "strategy"
        preferred: If provided and available, use this ID
        
    Returns:
        Allocated client ID (stable across restarts)
        
    Raises:
        ValueError: If inputs are invalid or preferred ID is out of range
        RuntimeError: If no free IDs available in the role's range
        TimeoutError: If file lock cannot be acquired
        
    Examples:
        >>> get_or_allocate_client_id("my_strategy", "strategy")
        9000
        >>> get_or_allocate_client_id("my_strategy", "strategy")  # Second call
        9000  # Same ID returned
        >>> get_or_allocate_client_id("other_strategy", "strategy", preferred=9500)
        9500  # Uses preferred if available
    """
    # FIXED: Comprehensive input validation
    _validate_name(name)
    role = _validate_role(role)
    
    if preferred is not None:
        preferred = int(preferred)
        _validate_preferred_id(preferred, role)

    key = _alloc_key(name, role)

    # Thread lock (within process)
    with _LOCK:
        # FIXED: File lock (across processes)
        with FileLock(_LOCK_FILE):
            state = _load_state()
            allocs: Dict[str, Any] = state.setdefault("allocations", {})

            # 1) Already allocated
            if key in allocs and isinstance(allocs[key], dict):
                allocated_id = int(allocs[key]["id"])
                logger.debug(f"Reusing client ID {allocated_id} for {key}")
                return allocated_id

            # Build set of used IDs
            used = {
                int(v["id"])
                for v in allocs.values()
                if isinstance(v, dict) and "id" in v
            }

            # 2) Preferred
            if preferred is not None:
                if preferred not in used:
                    allocs[key] = {
                        "id": preferred,
                        "role": role,
                        "name": name,
                        "allocated_at": time.time()
                    }
                    _save_state(state)
                    logger.info(f"Allocated preferred client ID {preferred} for {key}")
                    return preferred
                else:
                    logger.warning(
                        f"Preferred ID {preferred} already in use for {key}, "
                        f"allocating next available"
                    )

            # 3) Allocate next ID in role range
            start, end = ROLE_RANGES[role]
            for cid in range(start, end + 1):
                if cid not in used:
                    allocs[key] = {
                        "id": cid,
                        "role": role,
                        "name": name,
                        "allocated_at": time.time()
                    }
                    _save_state(state)
                    logger.info(f"Allocated new client ID {cid} for {key}")
                    return cid

            # No free IDs available
            raise RuntimeError(
                f"No free clientIds available for role '{role}' in range {start}-{end}. "
                f"Used: {len([v for v in allocs.values() if v.get('role') == role])}/{end-start+1}. "
                f"Consider cleaning up stale allocations with cleanup_stale_allocations()."
            )


def bump_client_id(name: str, role: str = "strategy") -> int:
    """
    Allocate a NEW clientId, abandoning the current one.

    Used when IBKR raises: "Client ID already in use".
    
    PATCHED: Added validation and better error handling.
    
    Args:
        name: Component name
        role: Component role
        
    Returns:
        New allocated client ID
        
    Raises:
        ValueError: If inputs are invalid
        RuntimeError: If no alternative IDs available
        TimeoutError: If file lock cannot be acquired
        
    Example:
        >>> # IBKR says "Client ID already in use"
        >>> new_id = bump_client_id("my_strategy", "strategy")
        >>> print(f"Allocated new ID: {new_id}")
    """
    # FIXED: Input validation
    _validate_name(name)
    role = _validate_role(role)

    key = _alloc_key(name, role)

    with _LOCK:
        with FileLock(_LOCK_FILE):
            state = _load_state()
            allocs: Dict[str, Any] = state.setdefault("allocations", {})

            current_id: Optional[int] = None
            if key in allocs and isinstance(allocs[key], dict):
                if "id" in allocs[key]:
                    current_id = int(allocs[key]["id"])
                    logger.info(f"Bumping client ID from {current_id} for {key}")

            # Build set of used IDs EXCLUDING current_id
            used = {
                int(v["id"])
                for k, v in allocs.items()
                if k != key and isinstance(v, dict) and "id" in v
            }

            start, end = ROLE_RANGES[role]

            for cid in range(start, end + 1):
                if cid == current_id:
                    continue
                if cid not in used:
                    allocs[key] = {
                        "id": cid,
                        "role": role,
                        "name": name,
                        "allocated_at": time.time(),
                        "bumped_from": current_id
                    }
                    _save_state(state)
                    logger.info(f"Bumped to new client ID {cid} for {key}")
                    return cid

            raise RuntimeError(
                f"No alternative clientIds available for role '{role}' in range {start}-{end}. "
                f"All {end-start+1} IDs are in use."
            )


def get_current_client_id(name: str, role: str = "strategy") -> Optional[int]:
    """
    Return the currently assigned clientId for (name, role), or None if unassigned.
    
    PATCHED: Added validation.
    
    Args:
        name: Component name
        role: Component role
        
    Returns:
        Current client ID or None
        
    Raises:
        ValueError: If inputs are invalid
    """
    _validate_name(name)
    role = _validate_role(role)
    
    key = _alloc_key(name, role)

    with _LOCK:
        with FileLock(_LOCK_FILE):
            state = _load_state()
            allocs: Dict[str, Any] = state.get("allocations", {})
            entry = allocs.get(key)
            
            if isinstance(entry, dict) and "id" in entry:
                return int(entry["id"])

    return None


def release_client_id(name: str, role: str = "strategy") -> bool:
    """
    Release a client ID allocation, making it available for reuse.
    
    PATCHED: NEW FUNCTION - cleanup stale allocations.
    
    Args:
        name: Component name
        role: Component role
        
    Returns:
        True if released, False if not allocated
        
    Raises:
        ValueError: If inputs are invalid
        
    Example:
        >>> release_client_id("old_strategy", "strategy")
        True
    """
    _validate_name(name)
    role = _validate_role(role)
    
    key = _alloc_key(name, role)
    
    with _LOCK:
        with FileLock(_LOCK_FILE):
            state = _load_state()
            allocs: Dict[str, Any] = state.setdefault("allocations", {})
            
            if key in allocs:
                released_id = allocs[key].get("id")
                del allocs[key]
                _save_state(state)
                logger.info(f"Released client ID {released_id} for {key}")
                return True
            
            return False


def cleanup_stale_allocations(strategy_folder: str = "strategies") -> int:
    """
    Remove allocations for strategies that no longer exist.
    
    PATCHED: NEW FUNCTION - prevent unbounded growth of state file.
    
    Args:
        strategy_folder: Path to strategies folder
        
    Returns:
        Number of allocations removed
        
    Example:
        >>> removed = cleanup_stale_allocations()
        >>> print(f"Cleaned up {removed} stale allocations")
    """
    with _LOCK:
        with FileLock(_LOCK_FILE):
            state = _load_state()
            allocs = state.get("allocations", {})
            
            # Get list of current strategy files
            current_strategies = set()
            if os.path.isdir(strategy_folder):
                for f in os.listdir(strategy_folder):
                    if f.endswith(".py") and f != "__init__.py":
                        current_strategies.add(f[:-3])  # Remove .py extension
            
            # Remove allocations for missing strategies
            removed = []
            for key in list(allocs.keys()):
                if key.startswith("strategy:"):
                    name = key.split(":", 1)[1]
                    if name not in current_strategies:
                        removed.append(key)
                        del allocs[key]
            
            if removed:
                _save_state(state)
                logger.info(f"Cleaned up {len(removed)} stale allocations: {removed}")
            
            return len(removed)


def get_all_allocations() -> Dict[str, Dict[str, Any]]:
    """
    Get all current client ID allocations.
    
    PATCHED: NEW FUNCTION - diagnostic/debugging.
    
    Returns:
        Dictionary of all allocations
        
    Example:
        >>> allocs = get_all_allocations()
        >>> for key, info in allocs.items():
        ...     print(f"{key}: {info['id']}")
    """
    with _LOCK:
        with FileLock(_LOCK_FILE):
            state = _load_state()
            return dict(state.get("allocations", {}))


def get_usage_stats() -> Dict[str, Any]:
    """
    Get usage statistics for each role.
    
    PATCHED: NEW FUNCTION - monitoring.
    
    Returns:
        Dictionary with usage stats per role
        
    Example:
        >>> stats = get_usage_stats()
        >>> print(f"Strategies: {stats['strategy']['used']}/{stats['strategy']['total']}")
    """
    with _LOCK:
        with FileLock(_LOCK_FILE):
            state = _load_state()
            allocs = state.get("allocations", {})
            
            stats = {}
            for role, (start, end) in ROLE_RANGES.items():
                used_ids = {
                    int(v["id"])
                    for v in allocs.values()
                    if isinstance(v, dict) and v.get("role") == role and "id" in v
                }
                
                total = end - start + 1
                used = len(used_ids)
                available = total - used
                
                stats[role] = {
                    "used": used,
                    "available": available,
                    "total": total,
                    "usage_pct": (used / total * 100) if total > 0 else 0,
                    "range": f"{start}-{end}"
                }
            
            return stats


def validate_state_file() -> Dict[str, Any]:
    """
    Validate the state file and return diagnostics.
    
    PATCHED: NEW FUNCTION - health check.
    
    Returns:
        Dictionary with validation results
        
    Example:
        >>> result = validate_state_file()
        >>> if result['valid']:
        ...     print("State file is valid")
        ... else:
        ...     print(f"Issues: {result['issues']}")
    """
    issues = []
    
    try:
        with FileLock(_LOCK_FILE):
            # Check file exists
            if not os.path.exists(_STATE_FILE):
                issues.append("State file does not exist")
                return {
                    "valid": False,
                    "issues": issues,
                    "state_file": _STATE_FILE
                }
            
            # Try to load
            state = _load_state()
            allocs = state.get("allocations", {})
            
            # Check for duplicate IDs
            id_to_keys = {}
            for key, value in allocs.items():
                if isinstance(value, dict) and "id" in value:
                    cid = int(value["id"])
                    if cid in id_to_keys:
                        issues.append(
                            f"Duplicate ID {cid}: {key} and {id_to_keys[cid]}"
                        )
                    else:
                        id_to_keys[cid] = key
            
            # Check IDs are in valid ranges
            for key, value in allocs.items():
                if isinstance(value, dict) and "id" in value and "role" in value:
                    cid = int(value["id"])
                    role = value["role"]
                    
                    if role in ROLE_RANGES:
                        start, end = ROLE_RANGES[role]
                        if not (start <= cid <= end):
                            issues.append(
                                f"ID {cid} for {key} is outside role '{role}' range {start}-{end}"
                            )
            
            return {
                "valid": len(issues) == 0,
                "issues": issues,
                "state_file": _STATE_FILE,
                "allocations_count": len(allocs),
                "version": state.get("version", "unknown")
            }
            
    except Exception as e:
        issues.append(f"Error validating state: {e}")
        return {
            "valid": False,
            "issues": issues,
            "state_file": _STATE_FILE
        }


# ======================================================
# Module Initialization
# ======================================================
def _log_initialization():
    """Log initialization info."""
    logger.info("=" * 60)
    logger.info("Client ID Manager Initialized")
    logger.info("=" * 60)
    logger.info(f"Version: 2.0 (Patched)")
    logger.info(f"State file: {_STATE_FILE}")
    logger.info(f"Lock file: {_LOCK_FILE}")
    logger.info(f"File locking: {'fcntl' if _FCNTL_AVAILABLE else 'msvcrt' if _MSVCRT_AVAILABLE else 'NONE'}")
    logger.info(f"Roles: {list(ROLE_RANGES.keys())}")
    
    # Load and display usage stats
    try:
        stats = get_usage_stats()
        for role, info in stats.items():
            logger.info(
                f"  {role}: {info['used']}/{info['total']} "
                f"({info['usage_pct']:.1f}%) range={info['range']}"
            )
    except Exception as e:
        logger.warning(f"Could not load usage stats: {e}")
    
    logger.info("=" * 60)


# Log on module import
_log_initialization()
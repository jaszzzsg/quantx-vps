"""
CENTRALIZED IBKR Client ID Manager with Excel Logging
Prevents conflicts, auto-detects used IDs, logs to Excel.
"""
import json
import fcntl
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

# CENTRALIZED paths (accessible to all projects)
LOCK_FILE = Path("/root/shared/ibkr/client_ids.json")
LOG_FILE = Path("/root/shared/ibkr/client_id_log.xlsx")

# Port-based ID ranges (prevents conflicts)
PORT_RANGES = {
    4001: (100, 199),  # LIVE account
    4002: (200, 299),  # Paper account
    7497: (300, 399),  # TWS (if used)
}

# Reserved IDs (hardcoded in existing scripts - DO NOT AUTO-ASSIGN)
RESERVED_IDS = {
    # Port 4002 (Paper) - quantx_dix
    20: {"port": 4002, "purpose": "dix_history_smoke", "project": "quantx_dix"},
    21: {"port": 4002, "purpose": "dix_history_6y_run", "project": "quantx_dix"},
    22: {"port": 4002, "purpose": "dix_daily_one_day_ACTIVE", "project": "quantx_dix"},
    23: {"port": 4002, "purpose": "ibkr_symbol_profile_cache", "project": "quantx_dix"},
    24: {"port": 4002, "purpose": "dix_history_6y", "project": "quantx_dix"},
    26: {"port": 4002, "purpose": "fetch_6y_chunked", "project": "quantx_dix"},
    80: {"port": 4002, "purpose": "chunk_2020_RUNNING", "project": "quantx_dix"},
    
    # Port 4002 (Paper) - quantx_arm VIX fetch
    991: {"port": 4002, "purpose": "arm_vix_fetch_ACTIVE", "project": "quantx_arm"},
    
    # Port 4001 (LIVE) - To be documented
    # Add ARM regime LIVE IDs here when identified
}


def _ensure_files():
    """Ensure lock file and log directory exist."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    if not LOCK_FILE.exists():
        LOCK_FILE.write_text(json.dumps({"used": [], "registry": {}}))


def get_client_id(host: str, port: int, purpose: str, project: str = "unknown") -> int:
    """
    Get next available client ID for IBKR connection.
    
    Args:
        host: IBKR host (usually 127.0.0.1)
        port: IBKR port (4001=LIVE, 4002=Paper)
        purpose: Description (e.g., "chunk_2020", "daily_dix", "arm_regime")
        project: Project name (e.g., "quantx_dix", "QuantX_Dashboard_Monitor")
    
    Returns:
        int: Assigned client ID
    """
    _ensure_files()
    
    # Determine ID range based on port
    if port not in PORT_RANGES:
        raise ValueError(f"Unknown port {port}. Expected: {list(PORT_RANGES.keys())}")
    
    range_start, range_end = PORT_RANGES[port]
    
    with open(LOCK_FILE, "r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        
        try:
            data = json.loads(f.read())
        except:
            data = {"used": [], "registry": {}}
        
        # Get currently used IDs
        used = set(data.get("used", []))
        
        # Add ALL reserved IDs (regardless of port) to prevent conflicts
        used.update(RESERVED_IDS.keys())
        
        # Find next available ID in port's range
        next_id = range_start
        while next_id <= range_end and next_id in used:
            next_id += 1
        
        if next_id > range_end:
            raise RuntimeError(f"No available client IDs for port {port} (range {range_start}-{range_end} exhausted)")
        
        # Mark as used
        used.add(next_id)
        data["used"] = sorted(list(used))
        
        # Record in registry
        if "registry" not in data:
            data["registry"] = {}
        
        timestamp = datetime.now(timezone.utc).isoformat()
        data["registry"][str(next_id)] = {
            "purpose": purpose,
            "project": project,
            "host": host,
            "port": port,
            "timestamp": timestamp,
            "status": "active",
        }
        
        # Save JSON
        f.seek(0)
        f.truncate()
        f.write(json.dumps(data, indent=2))
        
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    # Log to Excel
    _log_to_excel(next_id, purpose, project, host, port, "assigned", timestamp)
    
    port_type = "LIVE" if port == 4001 else "Paper" if port == 4002 else "TWS"
    print(f"[ClientID] ID {next_id} assigned → '{purpose}' ({project}) on {host}:{port} ({port_type})")
    return next_id


def release_client_id(client_id: int):
    """Release a client ID when connection closes."""
    _ensure_files()
    
    timestamp = datetime.now(timezone.utc).isoformat()
    
    with open(LOCK_FILE, "r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        
        data = json.loads(f.read())
        used = set(data.get("used", []))
        used.discard(client_id)
        data["used"] = sorted(list(used))
        
        # Update registry
        if "registry" in data and str(client_id) in data["registry"]:
            info = data["registry"][str(client_id)]
            del data["registry"][str(client_id)]
            
            # Log release
            _log_to_excel(
                client_id,
                info.get("purpose", "unknown"),
                info.get("project", "unknown"),
                info.get("host", "unknown"),
                info.get("port", 0),
                "released",
                timestamp
            )
        
        f.seek(0)
        f.truncate()
        f.write(json.dumps(data, indent=2))
        
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    print(f"[ClientID] Released ID {client_id}")


def list_active_ids() -> dict:
    """List all currently active client IDs."""
    _ensure_files()
    data = json.loads(LOCK_FILE.read_text())
    return data.get("registry", {})


def list_by_port(port: int) -> dict:
    """List active IDs for specific port."""
    _ensure_files()
    data = json.loads(LOCK_FILE.read_text())
    registry = data.get("registry", {})
    return {k: v for k, v in registry.items() if v.get("port") == port}


def list_reserved_ids() -> dict:
    """List all reserved (hardcoded) IDs."""
    return RESERVED_IDS


def cleanup_all():
    """Clear all locked IDs (call when IBKR Gateway restarts)."""
    _ensure_files()
    
    data = json.loads(LOCK_FILE.read_text())
    registry = data.get("registry", {})
    
    # Log cleanup for each active ID
    timestamp = datetime.now(timezone.utc).isoformat()
    for cid, info in registry.items():
        _log_to_excel(
            int(cid),
            info.get("purpose", "unknown"),
            info.get("project", "unknown"),
            info.get("host", "unknown"),
            info.get("port", 0),
            "cleanup",
            timestamp
        )
    
    LOCK_FILE.write_text(json.dumps({"used": [], "registry": {}}))
    print("[ClientID] Cleared all locks")


def _log_to_excel(client_id: int, purpose: str, project: str, host: str, port: int, action: str, timestamp: str):
    """Internal: Log client ID event to Excel."""
    try:
        # Load existing log or create new
        if LOG_FILE.exists():
            df = pd.read_excel(LOG_FILE)
        else:
            df = pd.DataFrame(columns=["Timestamp", "ClientID", "Port", "PortType", "Action", "Purpose", "Project", "Host", "Notes"])
        
        port_type = "LIVE" if port == 4001 else "Paper" if port == 4002 else "TWS" if port == 7497 else "Unknown"
        
        # Add new row
        new_row = pd.DataFrame([{
            "Timestamp": timestamp,
            "ClientID": client_id,
            "Port": port,
            "PortType": port_type,
            "Action": action,
            "Purpose": purpose,
            "Project": project,
            "Host": host,
            "Notes": f"{action.capitalize()} for {purpose} ({project})",
        }])
        
        df = pd.concat([df, new_row], ignore_index=True)
        
        # Save to Excel
        df.to_excel(LOG_FILE, index=False, engine='openpyxl')
    except Exception as e:
        print(f"[ClientID] Warning: Excel logging failed: {e}")


def view_log() -> pd.DataFrame:
    """View the complete client ID log."""
    _ensure_files()
    if not LOG_FILE.exists():
        return pd.DataFrame(columns=["Timestamp", "ClientID", "Port", "PortType", "Action", "Purpose", "Project", "Host", "Notes"])
    return pd.read_excel(LOG_FILE)

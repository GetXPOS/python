import os
import re
from datetime import datetime, timezone


def resolve_token(token):
    """Resolve token from explicit value or XPOS_TOKEN env var.
    Auto-prepends 'tk_' if missing."""
    t = token or os.environ.get("XPOS_TOKEN") or None
    if not t:
        return None
    return t if t.startswith("tk_") else "tk_" + t


def build_ssh_user(token, mode):
    """Build SSH username from token and mode."""
    if not token:
        return "x"
    return token + "+tcp" if mode == "tcp" else token


def build_remote_forward(port, host="localhost", subdomain=None, domain=None):
    """Build the -R remote forward string for SSH."""
    if domain:
        return "{}:80:{}:{}".format(domain, host, port)
    if subdomain:
        return "{}:80:{}:{}".format(subdomain, host, port)
    return "0:{}:{}".format(host, port)


def parse_url(buffer):
    """Parse HTTPS URL from SSH server output. Falls back to HTTP."""
    match = re.search(r"HTTPS:\s+(https://\S+)", buffer, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"HTTP:\s+(https?://\S+)", buffer, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def parse_port_url(buffer):
    """Parse port-based tunnel URL (ip:port) from SSH server output."""
    match = re.search(r"tunnel created!\r?\n\s+(\S+:\d+)", buffer, re.IGNORECASE)
    return match.group(1) if match else None


def parse_expiry(buffer):
    """Parse RFC3339 expiry timestamp from output."""
    match = re.search(r"Expires:\s+(\S+)", buffer)
    return match.group(1) if match else None


def parse_error(line):
    """Parse error message from output line."""
    match = re.match(r"^Error:\s*(.+)", line)
    return match.group(1).strip() if match else None


def format_expiry(rfc3339):
    """Format RFC3339 expiry to human-readable string."""
    try:
        # Python 3.8 compat: fromisoformat can't parse Z suffix
        ts = rfc3339.replace("Z", "+00:00")
        expiry = datetime.fromisoformat(ts)
        now = datetime.now(timezone.utc)
        diff = expiry - now
        total_seconds = int(diff.total_seconds())
        if total_seconds <= 0:
            return "Expired"

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60

        hh = "{:02d}".format(expiry.hour)
        mm = "{:02d}".format(expiry.minute)

        if hours > 0:
            return "Expires in {}h {}m ({}:{} UTC)".format(hours, minutes, hh, mm)
        return "Expires in {}m ({}:{} UTC)".format(minutes, hh, mm)
    except Exception:
        return "Expires: " + rfc3339


def should_filter_line(line):
    """Check if an output line should be filtered from pass-through display."""
    trimmed = line.strip()
    if not trimmed:
        return True
    if re.match(r"^Tunnel created!", trimmed, re.IGNORECASE):
        return True
    if re.match(r"^TCP tunnel created!", trimmed, re.IGNORECASE):
        return True
    if re.match(r"^HTTP:", trimmed, re.IGNORECASE):
        return True
    if re.match(r"^HTTPS:", trimmed, re.IGNORECASE):
        return True
    if re.match(r"^Expires:", trimmed, re.IGNORECASE):
        return True
    if re.match(r"^Press Ctrl\+C", trimmed, re.IGNORECASE):
        return True
    if re.match(r"^Tunnel closed", trimmed, re.IGNORECASE):
        return True
    if re.match(r"^\d+\.\d+\.\d+\.\d+:\d+$", trimmed):
        return True
    return False

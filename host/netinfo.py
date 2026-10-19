"""Find the machine's real LAN IPv4 address (no packets are sent)."""

import socket

# Private-range addresses used only to ask the OS "which interface would you
# use to reach this?". UDP connect() just selects a route; it transmits nothing,
# so no traffic leaves the machine and nothing outside the LAN is contacted.
_PROBE_TARGETS = ("10.255.255.255", "192.168.255.255", "172.31.255.255")


def _usable(ip: str) -> bool:
    return not (ip.startswith(("127.", "0.", "169.254.")) or ip == "")


def _via_route(target: str) -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((target, 1))
        ip = sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()
    return ip if _usable(ip) else None


def _via_hostname() -> str | None:
    try:
        _, _, addresses = socket.gethostbyname_ex(socket.gethostname())
    except OSError:
        return None
    for ip in addresses:
        if _usable(ip):
            return ip
    return None


def find_lan_ip() -> tuple[str, bool]:
    """Return ``(ip, found)``. ``found`` is False if only loopback was available."""
    for target in _PROBE_TARGETS:
        ip = _via_route(target)
        if ip:
            return ip, True
    ip = _via_hostname()
    if ip:
        return ip, True
    return "127.0.0.1", False

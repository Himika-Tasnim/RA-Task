"""
Working out which address a phone can actually reach this machine on.

Shared by the ACA-Py launcher (agent/run_agent.py) and the Django portal
(portal/portal/settings.py) so the QR codes and the agent's DIDComm endpoint
always agree on the host.

Why this is its own module: a stale IP is the single most common way this demo
breaks. Everything starts up cleanly, the pages render, the QR codes look
right, and the wallet just times out with no useful error. DHCP hands out a new
address whenever you rejoin a network, so hard-coding one address is fragile.

AGENT_HOST_IP in .env accepts:

    auto                      detect the LAN address at startup (recommended)
    192.168.1.20              use exactly this address
    192.168.1.20,10.0.0.5     several, the first is used in invitations
    auto,10.0.0.5             mix: detected address first, then extras
"""

from __future__ import annotations

import socket
from typing import List, Set

AUTO = "auto"


def detect_lan_ip() -> str:
    """
    Best guess at this machine's address on the LAN.

    Opening a UDP socket toward a public address makes the OS pick the
    interface it would really route through. No packets are sent. This is what
    lets us skip loopback, VMware adapters and 169.254.x link-local addresses
    without having to enumerate and rank every interface.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return ""
    finally:
        sock.close()


def local_addresses() -> Set[str]:
    """Every IPv4 address this host answers on, for sanity-checking config."""
    found = {detect_lan_ip()}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except socket.gaierror:
        pass
    found.discard("")
    return found


def resolve_host_ips(configured: str) -> List[str]:
    """
    Turn the AGENT_HOST_IP setting into an ordered list of addresses.

    The first entry is the one that goes into invitations, so it must be the
    address the phone will use. Duplicates are dropped but order is kept.
    """
    raw = (configured or AUTO).strip()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        parts = [AUTO]

    resolved: List[str] = []
    for part in parts:
        value = detect_lan_ip() if part.lower() == AUTO else part
        if value and value not in resolved:
            resolved.append(value)

    # Never hand back an empty list -- loopback at least keeps the portal usable
    # from this machine, and the caller's warning explains why a phone can't
    # reach it.
    return resolved or ["127.0.0.1"]


def primary_host_ip(configured: str) -> str:
    """The address that goes into QR codes and DIDComm invitations."""
    return resolve_host_ips(configured)[0]


def describe_unreachable(ip: str) -> str:
    """
    Explain why `ip` won't work for a phone, or return "" if it looks fine.

    Kept as a message rather than a hard failure because there are legitimate
    reasons to point this at an address we can't verify -- a port-forward, a
    tunnel, or a hostname that resolves differently from the phone's side.
    """
    if ip.startswith("127.") or ip == "localhost":
        return (
            "loopback -- reachable only from this machine, so a phone wallet "
            "will time out"
        )
    if ip.startswith("169.254."):
        return (
            "a link-local address -- this machine did not get a DHCP lease, so "
            "check the WiFi connection"
        )
    if ip not in local_addresses():
        return (
            f"not an address on this machine (detected {detect_lan_ip() or 'none'}) "
            "-- your IP has probably changed"
        )
    return ""

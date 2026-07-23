"""
A DIDComm mediator, run as a third ACA-Py instance.

Why this exists: a phone has no public address, so it cannot receive DIDComm
messages directly. Wallets solve this with a mediator -- a always-reachable
agent that holds messages and forwards them. Bifold refuses to finish starting
up without one.

Bifold's README points at Indicio's public mediator, but its WebSocket host
(ws.us-east.public.mediator.indiciotech.io) no longer resolves in DNS --
verified against three independent resolvers. Credo prefers that WebSocket
transport for mediation, so setup fails with "error 1045 ... initialize Context
module in didcomm".

Running our own fixes that and is strictly better for this demo:
  - no dependency on a third-party service staying up
  - no internet needed at all; phone and mediator are on the same WiFi
  - one less thing to explain if it breaks during a recording

    python agent/run_mediator.py

Then generate the invitation the wallet needs:

    python agent/mediator_invitation.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from run_agent import patch_windows_signal_handlers  # noqa: E402
from lanip import resolve_host_ips  # noqa: E402

load_dotenv(ROOT / ".env")


def env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def build_args(host_ips: list) -> list:
    endpoint_port = env("MEDIATOR_ENDPOINT_PORT", "8040")
    admin_port = env("MEDIATOR_ADMIN_PORT", "8041")
    ws_port = env("MEDIATOR_WS_PORT", "8042")

    (Path(__file__).resolve().parent / "wallet").mkdir(exist_ok=True)

    # Advertise HTTP first; Credo will use it when the WebSocket isn't offered.
    endpoints = [f"http://{ip}:{endpoint_port}" for ip in host_ips]
    endpoints += [f"ws://{ip}:{ws_port}" for ip in host_ips]

    return [
        "aca-py",
        "start",
        "--label", "University Portal Mediator",

        # Both an HTTP and a WebSocket inbound transport. Credo prefers the
        # WebSocket for mediation because it lets the mediator push messages to
        # the phone without the phone polling.
        "--inbound-transport", "http", "0.0.0.0", endpoint_port,
        "--inbound-transport", "ws", "0.0.0.0", ws_port,
        "--outbound-transport", "http",
        "--outbound-transport", "ws",
        "--endpoint", *endpoints,

        "--admin", "0.0.0.0", admin_port,
        "--admin-api-key", env("ACAPY_ADMIN_API_KEY", "demo-admin-api-key"),

        "--wallet-type", "askar",
        "--wallet-name", env("MEDIATOR_WALLET_NAME", "portal_mediator"),
        "--wallet-key", env("WALLET_KEY", "demo-wallet-key-change-me"),
        "--auto-provision",

        # A mediator only relays encrypted envelopes -- it never reads
        # credentials, resolves a schema or writes anything. So it needs no
        # ledger at all, and skipping it removes a startup dependency.
        "--no-ledger",

        # This is what makes it a mediator: grant mediation to anyone who asks.
        # Fine for a demo; a real deployment would gate this.
        "--open-mediation",

        "--auto-accept-invites",
        "--auto-accept-requests",
        "--auto-ping-connection",

        "--log-level", "info",
    ]


def main() -> None:
    host_ips = resolve_host_ips(env("AGENT_HOST_IP", "auto"))
    patch_windows_signal_handlers()

    ep = env("MEDIATOR_ENDPOINT_PORT", "8040")
    ws = env("MEDIATOR_WS_PORT", "8042")
    print("")
    print("  DIDComm mediator for the mobile wallet")
    print(f"  HTTP      : http://{host_ips[0]}:{ep}")
    print(f"  WebSocket : ws://{host_ips[0]}:{ws}")
    print(f"  Admin API : http://127.0.0.1:{env('MEDIATOR_ADMIN_PORT', '8041')}")
    print("")
    print("  Next: python agent/mediator_invitation.py")
    print("")

    from aries_cloudagent.__main__ import main as acapy_main

    acapy_main(build_args(host_ips) + sys.argv[1:])


if __name__ == "__main__":
    main()

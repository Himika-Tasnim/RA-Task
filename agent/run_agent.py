

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from lanip import describe_unreachable, resolve_host_ips  # noqa: E402


def warn_if_unreachable(host_ips: list) -> None:
    """
    Point out an endpoint a phone won't be able to reach.

    This is a warning rather than a hard stop: there are legitimate setups we
    can't verify from here (a tunnel, a port-forward). But a stale address
    fails so quietly -- agent starts, QR renders, wallet just times out -- that
    it is worth saying loudly up front.
    """
    problem = describe_unreachable(host_ips[0])
    if not problem:
        return

    print("=" * 72, file=sys.stderr)
    print(f" WARNING: the endpoint address {host_ips[0]} is {problem}.", file=sys.stderr)
    print("", file=sys.stderr)
    print(" Set AGENT_HOST_IP=auto in .env to detect it automatically.", file=sys.stderr)
    print("=" * 72, file=sys.stderr)


def patch_windows_signal_handlers() -> None:
    """Make add/remove_signal_handler no-ops on Windows (see module docstring)."""
    if sys.platform != "win32":
        return

    def _add_signal_handler(self, sig, callback, *args):
        return None

    def _remove_signal_handler(self, sig):
        return True

    # Patch the abstract base (which is what actually raises) plus the Proactor
    # loop, so the no-op wins regardless of which loop policy is in effect.
    for loop_cls in (
        asyncio.AbstractEventLoop,
        asyncio.proactor_events.BaseProactorEventLoop,
        asyncio.selector_events.BaseSelectorEventLoop,
    ):
        loop_cls.add_signal_handler = _add_signal_handler
        loop_cls.remove_signal_handler = _remove_signal_handler


def env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def build_args(host_ips: list) -> list:
    endpoint_port = env("AGENT_ENDPOINT_PORT", "8020")
    admin_port = env("AGENT_ADMIN_PORT", "8021")
    portal_port = env("PORTAL_PORT", "8000")

    wallet_dir = Path(__file__).resolve().parent / "wallet"
    wallet_dir.mkdir(exist_ok=True)

    # --endpoint takes several values; ACA-Py puts them all in the DIDDoc and
    # uses the FIRST one in invitations. So the primary address must lead.
    endpoints = [f"http://{ip}:{endpoint_port}" for ip in host_ips]

    return [
        "aca-py",
        "start",
        "--label", "Demo University",

        # Inbound DIDComm: listen on every interface, but ADVERTISE the LAN IP,
        # because that is the address the phone's wallet has to dial back.
        "--inbound-transport", "http", "0.0.0.0", endpoint_port,
        "--outbound-transport", "http",
        "--endpoint", *endpoints,

        # Admin API on loopback only. It is the most powerful interface here
        # -- it can issue credentials, create DIDs and read the wallet -- and
        # only the portal (same machine) calls it. Binding 0.0.0.0 exposed it
        # to every device on the WiFi behind nothing but a shared key that
        # ships as a demo default. The DIDComm transports below stay on
        # 0.0.0.0 because the phone genuinely must reach those.
        "--admin", "127.0.0.1", admin_port,
        "--admin-api-key", env("ACAPY_ADMIN_API_KEY", "demo-admin-api-key"),

        # Askar wallet (SQLite), provisioned automatically on first run.
        "--wallet-type", "askar",
        "--wallet-name", env("WALLET_NAME", "university_portal"),
        "--wallet-key", env("WALLET_KEY", "demo-wallet-key-change-me"),
        "--auto-provision",

        # Public DID on the BCovrin test ledger, derived from AGENT_SEED.
        "--genesis-url", env("LEDGER_GENESIS_URL", "http://test.bcovrin.vonx.io/genesis"),
        "--seed", env("AGENT_SEED"),
        "--public-invites",

        # Push protocol state changes to the portal. The part after '#' is sent
        # as an x-api-key header on every webhook; the portal rejects requests
        # without it, so the endpoint cannot be used to forge a login.
        "--webhook-url",
        f"http://127.0.0.1:{portal_port}/webhooks#{env('WEBHOOK_API_KEY', 'demo-webhook-api-key')}",

        # Automation, so the demo is one tap in the wallet at each step.
        "--auto-accept-invites",
        "--auto-accept-requests",
        "--auto-ping-connection",
        "--auto-respond-messages",
        "--auto-respond-credential-proposal",
        "--auto-respond-credential-request",
        "--auto-verify-presentation",

        # Keep completed exchange records instead of deleting them. Without
        # this the portal's polling fallback 404s the moment a presentation
        # succeeds, and the audit trail on /profile/ has nothing to point at.
        "--preserve-exchange-records",

        "--log-level", "info",
    ]


def main() -> None:
    seed = env("AGENT_SEED")
    if len(seed) != 32:
        sys.exit(
            f"AGENT_SEED must be exactly 32 characters (got {len(seed)}). "
            "Check your .env file."
        )

    host_ips = resolve_host_ips(env("AGENT_HOST_IP", "auto"))
    warn_if_unreachable(host_ips)

    patch_windows_signal_handlers()

    args = build_args(host_ips) + sys.argv[1:]

    endpoint_port = env("AGENT_ENDPOINT_PORT", "8020")
    print("")
    print(f"  DIDComm endpoint : http://{host_ips[0]}:{endpoint_port}"
          "   <- your phone must be able to reach this")
    for extra in host_ips[1:]:
        print(f"    also advertised: http://{extra}:{endpoint_port}")
    print(f"  Admin API        : http://127.0.0.1:{env('AGENT_ADMIN_PORT', '8021')}")
    print(f"  Webhooks         -> http://127.0.0.1:{env('PORTAL_PORT', '8000')}/webhooks")
    print("")

    from aries_cloudagent.__main__ import main as acapy_main

    acapy_main(args)


if __name__ == "__main__":
    main()

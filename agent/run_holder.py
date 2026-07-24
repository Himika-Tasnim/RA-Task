

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_agent import patch_windows_signal_handlers  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def build_args() -> list:
    endpoint_port = env("HOLDER_ENDPOINT_PORT", "8030")
    admin_port = env("HOLDER_ADMIN_PORT", "8031")

    (Path(__file__).resolve().parent / "wallet").mkdir(exist_ok=True)

    return [
        "aca-py",
        "start",
        "--label", "Student Wallet",

        # Both agents run on this machine, so loopback is enough for the holder.
        "--inbound-transport", "http", "0.0.0.0", endpoint_port,
        "--outbound-transport", "http",
        "--endpoint", f"http://127.0.0.1:{endpoint_port}",

        # Admin API on loopback only. It is the most powerful interface here
        # -- it can issue credentials, create DIDs and read the wallet -- and
        # only the portal (same machine) calls it. Binding 0.0.0.0 exposed it
        # to every device on the WiFi behind nothing but a shared key that
        # ships as a demo default. The DIDComm transports below stay on
        # 0.0.0.0 because the phone genuinely must reach those.
        "--admin", "127.0.0.1", admin_port,
        "--admin-api-key", env("ACAPY_ADMIN_API_KEY", "demo-admin-api-key"),

        # Its own wallet, separate from the issuer's.
        "--wallet-type", "askar",
        "--wallet-name", env("HOLDER_WALLET_NAME", "student_wallet"),
        "--wallet-key", env("WALLET_KEY", "demo-wallet-key-change-me"),
        "--auto-provision",

        # Read-only ledger access: needed to resolve the schema and cred-def
        # when validating an offer and building a presentation. No seed, because
        # a holder has no reason to own a public DID.
        "--genesis-url", env("LEDGER_GENESIS_URL", "http://test.bcovrin.vonx.io/genesis"),

        # Holder-side automation: behave like a wallet whose user taps Accept.
        "--auto-accept-invites",
        "--auto-accept-requests",
        "--auto-respond-credential-offer",
        "--auto-store-credential",
        "--auto-respond-presentation-request",
        "--auto-ping-connection",

        "--log-level", "warning",
    ]


def main() -> None:
    patch_windows_signal_handlers()

    print("")
    print(f"  Student wallet (holder) agent")
    print(f"  DIDComm  : http://127.0.0.1:{env('HOLDER_ENDPOINT_PORT', '8030')}")
    print(f"  Admin API: http://127.0.0.1:{env('HOLDER_ADMIN_PORT', '8031')}")
    print("")

    from aries_cloudagent.__main__ import main as acapy_main

    acapy_main(build_args() + sys.argv[1:])


if __name__ == "__main__":
    main()

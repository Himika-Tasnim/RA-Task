"""
A second ACA-Py instance that plays the STUDENT'S WALLET (the holder).

This exists for two reasons:

  1. Testing. It lets `scripts/demo_end_to_end.py` drive the entire flow --
     connect, receive a credential, present a proof, log in -- with no phone
     involved, so the SSI plumbing can be verified on its own.
  2. Fallback. If a mobile wallet can't be installed, this still demonstrates a
     genuine holder: a separate agent, with its own wallet and its own keys,
     that receives a real credential and produces a real presentation.

It is NOT a replacement for the mobile wallet in the final demo -- the task
asks for a phone scanning a QR code. Use this to prove the backend is correct,
then point the phone at the same QR codes.

    python agent/run_holder.py
"""

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

        "--admin", "0.0.0.0", admin_port,
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

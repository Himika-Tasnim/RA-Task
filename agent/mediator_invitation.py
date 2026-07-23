"""
Create the mediator invitation that Bifold needs, and write it into the app's
.env as MEDIATOR_URL.

Bifold will only accept an invitation as a mediator if it carries the goal code
`aries.vc.mediate` -- that is how it distinguishes "connect to me as your
mediator" from an ordinary connection invitation.

Run this AFTER agent/run_mediator.py is up:

    python agent/mediator_invitation.py
    python agent/mediator_invitation.py --write-env    # also update Bifold's .env
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MEDIATION_GOAL_CODE = "aries.vc.mediate"
BIFOLD_ENV = Path(os.getenv("BIFOLD_APP_DIR", r"E:\bifold-wallet\samples\app")) / ".env"


def main() -> int:
    admin = f"http://127.0.0.1:{os.getenv('MEDIATOR_ADMIN_PORT', '8041')}"
    headers = {"X-API-KEY": os.getenv("ACAPY_ADMIN_API_KEY", "demo-admin-api-key")}

    try:
        requests.get(f"{admin}/status", headers=headers, timeout=10).raise_for_status()
    except requests.RequestException as exc:
        print(
            f"ERROR: mediator not reachable at {admin}.\n"
            f"Start it first:  python agent/run_mediator.py\n\n{exc}",
            file=sys.stderr,
        )
        return 1

    payload = {
        "handshake_protocols": ["https://didcomm.org/didexchange/1.0"],
        "use_public_did": False,
        "my_label": "University Portal Mediator",
        # Without this goal code Bifold treats it as a normal connection.
        "goal_code": MEDIATION_GOAL_CODE,
        "goal": "Provide mediation for the University Portal demo wallet",
    }

    resp = requests.post(
        f"{admin}/out-of-band/create-invitation",
        headers=headers,
        params={"auto_accept": "true", "multi_use": "true"},
        json=payload,
        timeout=30,
    )
    if not resp.ok:
        print(f"ERROR: {resp.status_code}: {resp.text[:400]}", file=sys.stderr)
        return 1

    url = resp.json()["invitation_url"]

    print("Mediator invitation created.\n")
    print(f"  goal_code : {MEDIATION_GOAL_CODE}")
    print(f"  length    : {len(url)} chars\n")
    print(url)
    print()

    if "--write-env" in sys.argv:
        if not BIFOLD_ENV.parent.exists():
            print(f"ERROR: {BIFOLD_ENV.parent} does not exist.", file=sys.stderr)
            return 1
        # Path.write_text() gained `newline` only in 3.10; open() keeps this
        # working on the 3.9 runtime the portal uses.
        with open(BIFOLD_ENV, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f"MEDIATOR_URL={url}\n")
        print(f"Wrote {BIFOLD_ENV}")
        print("Rebuild the app for this to take effect:")
        print("  cd samples\\app\\android && .\\gradlew.bat assembleRelease")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

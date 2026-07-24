

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SEED = os.getenv("AGENT_SEED", "")
REGISTER_URL = os.getenv("LEDGER_REGISTER_URL", "http://test.bcovrin.vonx.io/register")
ALIAS = "Demo University Portal"


def main() -> int:
    if len(SEED) != 32:
        print(
            f"ERROR: AGENT_SEED must be exactly 32 characters, got {len(SEED)}.\n"
            "Edit .env and try again.",
            file=sys.stderr,
        )
        return 1

    payload = {"seed": SEED, "role": "ENDORSER", "alias": ALIAS}
    print(f"Registering DID on {REGISTER_URL} ...")

    try:
        resp = requests.post(REGISTER_URL, json=payload, timeout=30)
    except requests.RequestException as exc:
        print(f"ERROR: could not reach the ledger: {exc}", file=sys.stderr)
        return 1

    if resp.status_code != 200:
        print(f"ERROR: ledger returned {resp.status_code}: {resp.text}", file=sys.stderr)
        return 1

    data = resp.json()
    print("\nDID registered successfully:\n")
    print(json.dumps(data, indent=2))
    print(
        "\nThe agent derives this same DID from AGENT_SEED at startup, so there is "
        "nothing to copy anywhere. You can now run:  python agent/run_agent.py"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

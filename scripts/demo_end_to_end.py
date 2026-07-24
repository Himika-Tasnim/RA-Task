
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PORTAL = f"http://127.0.0.1:{os.getenv('PORTAL_PORT', '8000')}"
HOLDER = f"http://127.0.0.1:{os.getenv('HOLDER_ADMIN_PORT', '8031')}"
ISSUER = f"http://127.0.0.1:{os.getenv('AGENT_ADMIN_PORT', '8021')}"
HEADERS = {"X-API-KEY": os.getenv("ACAPY_ADMIN_API_KEY", "demo-admin-api-key")}

STUDENT = {
    "full_name": "Ayesha Rahman",
    "id_number": "STU-2024-0142",
    "department": "Computer Science",
    "email": "ayesha@demo-university.edu",
    "role": "student",
}

PASS, FAIL = "  [OK]  ", "  [FAIL]"


def step(n: int, text: str) -> None:
    print(f"\n{n}. {text}")


def die(msg: str) -> "NoReturn":  # type: ignore[valid-type]
    print(f"{FAIL} {msg}")
    sys.exit(1)


def wait_for(fn, what: str, timeout: int = 60, interval: float = 1.5):
    """Poll `fn` until it returns something truthy."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = fn()
        if result:
            return result
        time.sleep(interval)
    die(f"timed out waiting for {what}")


def preflight() -> None:
    step(0, "Checking the three processes are up")
    for name, url in (
        ("portal", f"{PORTAL}/"),
        ("issuer agent", f"{ISSUER}/status"),
        ("holder agent", f"{HOLDER}/status"),
    ):
        try:
            headers = HEADERS if "status" in url else {}
            resp = requests.get(url, headers=headers, timeout=10)
            if not resp.ok:
                die(f"{name} at {url} returned {resp.status_code}")
        except requests.RequestException as exc:
            die(f"{name} is not reachable at {url} ({exc})")
        print(f"{PASS} {name}")


def held_referents() -> set:
    """Ids of the credentials currently in the holder's wallet."""
    creds = requests.get(f"{HOLDER}/credentials", headers=HEADERS, timeout=15).json()
    return {c["referent"] for c in creds.get("results", [])}


def issue_credential(session: requests.Session) -> None:
    step(1, "Registrar issues a Student ID credential")

    # Snapshot first, so a credential left over from an earlier run can't make
    # this step look like it passed.
    before = held_referents()

    page = session.get(f"{PORTAL}/issue/", timeout=15)
    if "/login" in page.url:
        die(
            "Issuance is gated: a faculty credential already exists, so /issue/ "
            "now requires a faculty login.\n"
            "  Reset the demo data first:  python portal/manage.py reset_demo"
        )
    csrf = session.cookies.get("csrftoken", "")
    resp = session.post(
        f"{PORTAL}/issue/start/",
        data={**STUDENT, "csrfmiddlewaretoken": csrf},
        headers={"Referer": f"{PORTAL}/issue/"},
        timeout=20,
    )
    if not resp.ok:
        die(f"issue/start returned {resp.status_code}")

    match = re.search(r"/issue/(\d+)/", resp.url)
    if not match:
        die(f"did not land on the issuance wait page (got {resp.url})")
    issue_pk = match.group(1)
    print(f"{PASS} invitation created (issuance #{issue_pk})")

    token = re.search(r"/i/([a-f0-9]{12})/", resp.text)
    if not token:
        die("no short invitation URL found on the page")
    invitation = requests.get(
        f"{PORTAL}/i/{token.group(1)}/",
        headers={"Accept": "application/json"},
        timeout=15,
    ).json()
    print(f"{PASS} invitation resolves: {invitation.get('@type', '?').split('/')[-2:]}")

    step(2, "Student's wallet scans the QR and accepts the credential")
    received = requests.post(
        f"{HOLDER}/out-of-band/receive-invitation",
        headers=HEADERS,
        params={"auto_accept": "true"},
        json=invitation,
        timeout=30,
    )
    if not received.ok:
        die(f"holder could not receive the invitation: {received.text[:300]}")
    print(f"{PASS} holder accepted the connection invitation")

    def new_credential_stored():
        # Check the wallet's stored credentials rather than the exchange
        # records: a holder with --auto-store-credential deletes the exchange
        # record once the credential is safely in the wallet, so that record
        # list is empty exactly when issuance succeeded.
        creds = requests.get(
            f"{HOLDER}/credentials", headers=HEADERS, timeout=15
        ).json()
        for cred in creds.get("results", []):
            if cred["referent"] not in before:
                return cred
        return None

    cred = wait_for(new_credential_stored, "the credential to reach the wallet", timeout=120)
    print(f"{PASS} credential stored in the holder's wallet")
    print(f"         cred_def: {cred.get('cred_def_id')}")
    for key in ("full_name", "id_number", "department", "email"):
        print(f"         {key:13}= {cred['attrs'][key]}")

    def portal_says_issued():
        data = requests.get(f"{PORTAL}/issue/{issue_pk}/status/", timeout=15).json()
        return data.get("done")

    wait_for(portal_says_issued, "the portal to report issuance complete", timeout=60)
    print(f"{PASS} portal reports: issued")


def login_with_proof(session: requests.Session) -> None:
    step(3, "Student logs in by presenting the credential")

    page = session.get(f"{PORTAL}/login/", timeout=20)
    pres_ex_id = re.search(r"/login/status/([0-9a-f-]{36})/", page.text)
    token = re.search(r"/i/([a-f0-9]{12})/", page.text)
    if not pres_ex_id or not token:
        die("login page did not contain a proof request")
    pres_ex_id = pres_ex_id.group(1)
    print(f"{PASS} proof request created ({pres_ex_id[:8]}...)")

    invitation = requests.get(
        f"{PORTAL}/i/{token.group(1)}/",
        headers={"Accept": "application/json"},
        timeout=15,
    ).json()

    resp = requests.post(
        f"{HOLDER}/out-of-band/receive-invitation",
        headers=HEADERS,
        params={"auto_accept": "true"},
        json=invitation,
        timeout=30,
    )
    if not resp.ok:
        die(f"holder could not receive the proof request: {resp.text[:300]}")
    print(f"{PASS} holder received the proof request and is presenting")

    def verified():
        data = requests.get(
            f"{PORTAL}/login/status/{pres_ex_id}/", timeout=15
        ).json()
        if data.get("state") == "failed":
            die(f"presentation rejected: {data.get('detail')}")
        return data.get("verified")

    wait_for(verified, "the presentation to verify", timeout=120)
    print(f"{PASS} presentation VERIFIED by ACA-Py")

    resp = session.get(f"{PORTAL}/login/complete/{pres_ex_id}/", timeout=20)
    if not resp.ok or "/dashboard" not in resp.url:
        die(f"login did not create a session (landed on {resp.url})")
    print(f"{PASS} session created -> redirected to {resp.url}")


def browse_protected(session: requests.Session) -> None:
    step(4, "Navigating the protected pages on that one session")

    for name, path, must_contain in (
        ("Dashboard", "/dashboard/", "Enrolled courses"),
        ("Profile", "/profile/", STUDENT["id_number"]),
        ("Dashboard again", "/dashboard/", "Enrolled courses"),
    ):
        resp = session.get(f"{PORTAL}{path}", timeout=15)
        if resp.status_code != 200 or "/login" in resp.url:
            die(f"{name} redirected to login -- session not holding")
        if must_contain not in resp.text:
            die(f"{name} did not contain expected content {must_contain!r}")
        print(f"{PASS} {name} served without re-authenticating")

    resp = session.get(f"{PORTAL}/profile/", timeout=15)
    for key, value in STUDENT.items():
        if value not in resp.text:
            die(f"profile is missing the disclosed attribute {key}={value!r}")
    print(f"{PASS} profile shows all 4 attributes disclosed by the wallet")


def logout(session: requests.Session) -> None:
    step(5, "Logging out")
    session.get(f"{PORTAL}/logout/", timeout=15)

    resp = session.get(f"{PORTAL}/dashboard/", timeout=15, allow_redirects=True)
    if "/login" not in resp.url:
        die("dashboard still reachable after logout")
    print(f"{PASS} session destroyed -- dashboard now redirects to login")


def main() -> None:
    print("=" * 66)
    print("  SSI University Portal -- end-to-end verification")
    print("=" * 66)

    preflight()
    session = requests.Session()
    issue_credential(session)
    login_with_proof(session)
    browse_protected(session)
    logout(session)

    print("\n" + "=" * 66)
    print("  ALL STEPS PASSED")
    print("=" * 66)
    print(
        "\nThe backend is verified. For the recorded demo, run the same flow with\n"
        "a phone wallet scanning the QR codes at /issue/ and /login/.\n"
    )


if __name__ == "__main__":
    main()

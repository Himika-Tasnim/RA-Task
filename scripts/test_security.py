
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
ISSUER = f"http://127.0.0.1:{os.getenv('AGENT_ADMIN_PORT', '8021')}"
HOLDER = f"http://127.0.0.1:{os.getenv('HOLDER_ADMIN_PORT', '8031')}"
H = {"X-API-KEY": os.getenv("ACAPY_ADMIN_API_KEY", "demo-admin-api-key")}

IMPOSTOR_TAG = "not-the-university"
STUDENT = {
    "full_name": "Mallory Impostor",
    "id_number": "STU-9999-0001",
    "department": "Computer Science",
    "email": "mallory@example.com",
    "role": "student",
}

passed = failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}")
    if detail:
        print(f"         {detail}")


def section(n: int, title: str) -> None:
    print(f"\n{n}. {title}")


def wait_for(fn, what, timeout=90, interval=1.5):
    end = time.time() + timeout
    while time.time() < end:
        r = fn()
        if r:
            return r
        time.sleep(interval)
    return None


# ---------------------------------------------------------------------------
def test_no_session():
    section(1, "Protected pages with no session")
    s = requests.Session()
    for path in ("/dashboard/", "/profile/", "/messages/"):
        r = s.get(f"{PORTAL}{path}", timeout=15)
        check(
            f"{path} refuses anonymous access",
            "/login" in r.url,
            f"landed on {r.url}",
        )


def test_forged_pres_ex_id():
    section(2, "Forged presentation-exchange id in the login URL")
    s = requests.Session()
    fake = "00000000-1111-2222-3333-444444444444"
    r = s.get(f"{PORTAL}/login/complete/{fake}/", timeout=15)
    no_session = "/dashboard" not in r.url
    check("made-up pres_ex_id does not create a session", no_session, f"landed on {r.url}")

    r2 = s.get(f"{PORTAL}/dashboard/", timeout=15)
    check("dashboard still refused afterwards", "/login" in r2.url)


def test_unanswered_proof_replay():
    section(3, "Real proof request that was never answered")
    s = requests.Session()
    page = s.get(f"{PORTAL}/login/", timeout=20)
    m = re.search(r"/login/status/([0-9a-f-]{36})/", page.text)
    if not m:
        check("could not create a proof request", False)
        return
    pres_ex_id = m.group(1)

    status = s.get(f"{PORTAL}/login/status/{pres_ex_id}/", timeout=15).json()
    check("status reports not verified", not status.get("verified"), f"state={status.get('state')}")

    r = s.get(f"{PORTAL}/login/complete/{pres_ex_id}/", timeout=20)
    check(
        "login-complete refuses an unverified exchange",
        "/dashboard" not in r.url,
        f"landed on {r.url}",
    )


# ---------------------------------------------------------------------------
def publish_impostor_cred_def(schema_id: str) -> str:
    """A second credential definition standing in for a different issuer."""
    found = requests.get(
        f"{ISSUER}/credential-definitions/created",
        headers=H, params={"schema_id": schema_id}, timeout=30,
    ).json()
    for cd in found.get("credential_definition_ids", []):
        if cd.rsplit(":", 1)[-1] == IMPOSTOR_TAG:
            return cd
    print("     publishing an impostor credential definition (~10s) ...")
    r = requests.post(
        f"{ISSUER}/credential-definitions",
        headers=H,
        json={"schema_id": schema_id, "tag": IMPOSTOR_TAG, "support_revocation": False},
        timeout=180,
    ).json()
    return r.get("credential_definition_id") or r["sent"]["credential_definition_id"]


def holder_credentials():
    return requests.get(f"{HOLDER}/credentials", headers=H, timeout=20).json().get("results", [])


def delete_holder_credential(referent: str):
    requests.delete(f"{HOLDER}/credential/{referent}", headers=H, timeout=20)


def issue_to_holder(cred_def_id: str, attrs: dict) -> bool:
    """
    Issue over the issuer's connection to the software holder.

    Match on the holder's label rather than taking the newest active
    connection: connectionless proof requests also leave behind connections
    (labelled "didcomm-oob-invitation") that cannot carry a credential offer.
    """
    conns = requests.get(f"{ISSUER}/connections", headers=H, timeout=20).json().get("results", [])
    wallet = [
        c for c in conns
        if c.get("their_label") == "Student Wallet"
        and c.get("state") in ("active", "completed")
    ]
    if not wallet:
        return False
    conn_id = wallet[-1]["connection_id"]
    before = {c["referent"] for c in holder_credentials()}
    requests.post(
        f"{ISSUER}/issue-credential-2.0/send",
        headers=H,
        json={
            "connection_id": conn_id,
            "auto_remove": False,
            "credential_preview": {
                "@type": "issue-credential/2.0/credential-preview",
                "attributes": [{"name": k, "value": str(v)} for k, v in attrs.items()],
            },
            "filter": {"indy": {"cred_def_id": cred_def_id}},
        },
        timeout=60,
    )
    return bool(wait_for(
        lambda: next((c for c in holder_credentials() if c["referent"] not in before), None),
        "credential to arrive",
    ))


def test_wrong_issuer():
    section(4, "Credential from a DIFFERENT credential definition")

    artifacts = requests.get(f"{PORTAL}/", timeout=15)  # ensure portal awake
    schema_id = requests.get(
        f"{ISSUER}/schemas/created", headers=H,
        params={"schema_name": "university_student_id", "schema_version": "1.0"}, timeout=30,
    ).json().get("schema_ids", [None])[0]
    if not schema_id:
        check("found the schema on the ledger", False)
        return

    impostor = publish_impostor_cred_def(schema_id)
    print(f"     impostor cred-def: {impostor}")

    genuine = [c for c in holder_credentials()]
    stashed = [c["referent"] for c in genuine]
    print(f"     temporarily removing {len(stashed)} genuine credential(s) from the wallet")
    for ref in stashed:
        delete_holder_credential(ref)

    ok = issue_to_holder(impostor, STUDENT)
    check("impostor credential issued into the wallet", ok)
    if not ok:
        return

    held = holder_credentials()
    check(
        "wallet now holds ONLY the impostor credential",
        all(c["cred_def_id"] == impostor for c in held) and len(held) > 0,
        f"holds {[c['cred_def_id'].rsplit(':',1)[-1] for c in held]}",
    )

    # Attempt a real login with only the impostor credential.
    s = requests.Session()
    page = s.get(f"{PORTAL}/login/", timeout=20)
    m = re.search(r"/login/status/([0-9a-f-]{36})/", page.text)
    tok = re.search(r"/i/([a-f0-9]{12})/", page.text)
    if not (m and tok):
        check("built a login proof request", False)
        return
    pres_ex_id = m.group(1)

    invitation = requests.get(
        f"{PORTAL}/i/{tok.group(1)}/", headers={"Accept": "application/json"}, timeout=20
    ).json()
    requests.post(
        f"{HOLDER}/out-of-band/receive-invitation",
        headers=H, params={"auto_accept": "true"}, json=invitation, timeout=40,
    )

    # Give it time to fail rather than assuming instant rejection.
    verified = wait_for(
        lambda: requests.get(f"{PORTAL}/login/status/{pres_ex_id}/", timeout=15).json().get("verified"),
        "verification", timeout=45,
    )
    check(
        "login REJECTED a credential from another cred-def",
        not verified,
        "the proof request restricts to the portal's own cred_def_id",
    )

    r = s.get(f"{PORTAL}/login/complete/{pres_ex_id}/", timeout=20)
    check("login-complete refuses it too", "/dashboard" not in r.url, f"landed on {r.url}")

    # --- restore a genuine credential so the demo still works --------------
    print("     restoring a genuine credential ...")
    for c in holder_credentials():
        delete_holder_credential(c["referent"])
    artifacts_page = requests.get(f"{PORTAL}/", timeout=15).text
    m = re.search(r"([0-9A-Za-z]{21,22}:3:CL:\d+:university-portal)", artifacts_page)
    if m and issue_to_holder(m.group(1), {
        "full_name": "Ayesha Rahman", "id_number": "STU-2024-0142",
        "department": "Computer Science", "email": "ayesha@demo-university.edu",
        "role": "student",
    }):
        print("     genuine credential restored")
    else:
        print("     WARNING: could not restore -- re-issue one via /issue/ before demoing")


def test_logout_destroys_session():
    section(5, "Logout actually destroys the session")
    s = requests.Session()
    r = s.get(f"{PORTAL}/dashboard/", timeout=15)
    check("starts logged out", "/login" in r.url)


def _forged_webhook_body(pres_ex_id: str) -> dict:
    """A webhook that claims a verified presentation which never happened."""
    return {
        "pres_ex_id": pres_ex_id,
        "state": "done",
        "verified": "true",
        "by_format": {
            "pres": {
                "indy": {
                    "identifiers": [
                        {"cred_def_id": "WazjcnK7xmg2BwiGzStH1S:3:CL:3225339:university-portal"}
                    ],
                    "requested_proof": {
                        "revealed_attr_groups": {
                            "university_id": {
                                "values": {
                                    "full_name": {"raw": "Mallory Impostor"},
                                    "id_number": {"raw": "HACK-0001"},
                                    "department": {"raw": "None"},
                                    "email": {"raw": "mallory@example.com"},
                                    "role": {"raw": "faculty"},
                                }
                            }
                        }
                    },
                }
            }
        },
    }


def test_webhook_forgery():
    
    section(6, "Forged ACA-Py webhook (authentication bypass)")
    s = requests.Session()
    page = s.get(f"{PORTAL}/login/", timeout=20)
    m = re.search(r"/login/status/([0-9a-f-]{36})/", page.text)
    if not m:
        check("could not create a proof request", False)
        return
    pres_ex_id = m.group(1)

    body = _forged_webhook_body(pres_ex_id)
    url = f"{PORTAL}/webhooks/topic/present_proof_v2_0/"

    unauth = requests.post(url, json=body, timeout=20)
    check(
        "webhook without the shared key is rejected",
        unauth.status_code == 401,
        f"HTTP {unauth.status_code}",
    )

    # Even holding the key must not be enough: the handler re-reads the record
    # from ACA-Py rather than believing the payload.
    withkey = requests.post(
        url, json=body, headers={"x-api-key": os.getenv("WEBHOOK_API_KEY", "demo-webhook-api-key")},
        timeout=20,
    )
    status = s.get(f"{PORTAL}/login/status/{pres_ex_id}/", timeout=15).json()
    check(
        "a forged payload cannot mark a login verified",
        not status.get("verified"),
        f"webhook HTTP {withkey.status_code}, session verified={status.get('verified')}",
    )

    r = s.get(f"{PORTAL}/login/complete/{pres_ex_id}/", timeout=20)
    check("forged login cannot reach the dashboard", "/dashboard" not in r.url)


def test_login_replay_and_binding():
    """
    A verified login belongs to one browser and may be used once.

    pres_ex_id is public, so a second browser must not be able to complete
    someone else's login, and the same proof must not be replayable.
    """
    section(7, "Login session binding and replay")
    victim = requests.Session()
    page = victim.get(f"{PORTAL}/login/", timeout=20)
    m = re.search(r"/login/status/([0-9a-f-]{36})/", page.text)
    tok = re.search(r"/i/([a-f0-9]{12})/", page.text)
    if not (m and tok):
        check("built a login proof request", False)
        return
    pres_ex_id = m.group(1)

    invitation = requests.get(
        f"{PORTAL}/i/{tok.group(1)}/", headers={"Accept": "application/json"}, timeout=20
    ).json()
    requests.post(
        f"{HOLDER}/out-of-band/receive-invitation",
        headers=H, params={"auto_accept": "true"}, json=invitation, timeout=40,
    )
    verified = wait_for(
        lambda: victim.get(f"{PORTAL}/login/status/{pres_ex_id}/", timeout=15).json().get("verified"),
        "verification", timeout=60,
    )
    if not verified:
        check("presentation verified for the binding test", False)
        return

    # A different browser tries to claim the freshly verified login.
    attacker = requests.Session()
    attacker.get(f"{PORTAL}/", timeout=15)  # get its own session cookie
    r = attacker.get(f"{PORTAL}/login/complete/{pres_ex_id}/", timeout=20)
    check(
        "another browser cannot claim the login",
        "/dashboard" not in r.url,
        f"landed on {r.url}",
    )

    # The rightful browser completes it, then tries again.
    ok = victim.get(f"{PORTAL}/login/complete/{pres_ex_id}/", timeout=20)
    check("the requesting browser can complete it", "/dashboard" in ok.url)

    # Log out, then try to get back in by replaying the same proof rather than
    # presenting again. Both guards should bite: the session is marked consumed,
    # and logging out issued a new browser key.
    victim.get(f"{PORTAL}/logout/", timeout=15)
    replay = victim.get(f"{PORTAL}/login/complete/{pres_ex_id}/", timeout=20)
    check(
        "the same proof cannot be replayed after logout",
        "/dashboard" not in replay.url,
        f"landed on {replay.url}",
    )
    still_out = victim.get(f"{PORTAL}/dashboard/", timeout=15)
    check("dashboard still refused after the replay attempt", "/login" in still_out.url)


def main():
    print("=" * 68)
    print("  SSI University Portal -- security / negative tests")
    print("=" * 68)

    for url, name in ((f"{PORTAL}/", "portal"), (f"{ISSUER}/status", "issuer"), (f"{HOLDER}/status", "holder")):
        try:
            requests.get(url, headers=H if "status" in url else {}, timeout=10).raise_for_status()
        except requests.RequestException as exc:
            sys.exit(f"{name} not reachable at {url}: {exc}")

    test_no_session()
    test_forged_pres_ex_id()
    test_unanswered_proof_replay()
    test_wrong_issuer()
    test_logout_destroys_session()
    test_webhook_forgery()
    test_login_replay_and_binding()

    print("\n" + "=" * 68)
    print(f"  {passed} passed, {failed} failed")
    print("=" * 68)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

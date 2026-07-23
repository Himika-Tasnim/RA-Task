# SSI University Portal

A university portal where students log in with a **Verifiable Credential instead of a
password**. The student holds a "Student ID" credential in a mobile wallet, scans a QR
proof-request on the login page, and the portal grants a session only after the
presentation is cryptographically verified.

Built with **ACA-Py** (Aries Cloud Agent Python) for all SSI operations and **Django**
for the portal.

> **Runs natively on Windows — no Docker, no WSL.** See
> [Why no Docker](#why-no-docker-and-what-that-cost) for how, and what had to be worked
> around.

- **[SETUP.md](SETUP.md)** — recreate this project from scratch, step by step
- **[USER_MANUAL.md](USER_MANUAL.md)** — how to run and demo it day to day

---

## What it does

| Requirement | Where it lives |
|---|---|
| Issue a Student ID / Faculty ID VC (`full_name`, `id_number`, `department`, `email`, `role`) | [issue_start](portal/ssi/views.py) → [`_on_connection`](portal/ssi/views.py) |
| Student holds the credential in a wallet | Mobile wallet (or [run_holder.py](agent/run_holder.py) for testing) |
| Login by scanning a QR proof-request | [login_page](portal/ssi/views.py) |
| Backend verifies proof, then creates a session | [login_complete](portal/ssi/views.py) |
| Two protected pages, no re-auth | [dashboard](portal/ssi/views.py), [profile](portal/ssi/views.py) |
| Working logout | [logout_view](portal/ssi/views.py) |
| **Bonus:** 1-to-1 DIDComm messaging (faculty ↔ student) | [messages_page](portal/ssi/views.py) |

---

## Architecture

```
   ┌──────────────┐   scans QR    ┌───────────────────┐
   │ Mobile wallet│◄──────────────│  Django portal    │
   │  (holder)    │               │  :8000            │
   │              │               │                   │
   │  holds the   │               │  login page,      │
   │  Student ID  │               │  dashboard,       │
   │  credential  │               │  profile, logout  │
   └──────┬───────┘               └─────────┬─────────┘
          │                                 │
          │ DIDComm                   Admin API (REST)
          │ :8020                     :8021  + webhooks
          │                                 │
          └────────────►┌───────────────────▼─────┐
                        │   ACA-Py agent          │
                        │   issuer + verifier     │
                        └───────────┬─────────────┘
                                    │ writes/reads
                                    ▼
                        ┌─────────────────────────┐
                        │ BCovrin test ledger      │
                        │ DID, schema, cred-def    │
                        └─────────────────────────┘
```

The portal never handles keys, DIDs or the ledger. Every SSI operation goes through
ACA-Py's Admin API via a thin client in [portal/ssi/acapy.py](portal/ssi/acapy.py).

**Published to the ledger** (BCovrin test net):

| | |
|---|---|
| Issuer DID | `WazjcnK7xmg2BwiGzStH1S` |
| Student schema | `WazjcnK7xmg2BwiGzStH1S:2:university_student_id:1.0` |
| Student cred-def | `WazjcnK7xmg2BwiGzStH1S:3:CL:3225339:university-portal` |
| Faculty schema | `WazjcnK7xmg2BwiGzStH1S:2:university_faculty_id:1.0` |
| Faculty cred-def | `WazjcnK7xmg2BwiGzStH1S:3:CL:3225341:university-portal` |

---

## How the login actually works

This is the part worth understanding, because it's what makes the login *authentication*
rather than a form the student fills in themselves.

1. **The portal builds a proof request** restricted to its own `cred_def_id`
   ([`create_proof_request`](portal/ssi/acapy.py)). Only a credential this university
   actually issued and signed can satisfy it.

2. **All attributes are requested as one group**, not one referent each:

   ```python
   {"university_id": {"names": [...], "restrictions": [{"issuer_did": ...}]}}
   ```

   A group forces every attribute to come from the **same** credential. With separate
   referents a holder could legitimately satisfy each one from a different credential —
   mixing a real name with someone else's ID number.

   The restriction is on `issuer_did` rather than `cred_def_id` because the login must
   accept *either* the Student ID or the Faculty ID. Listing one restriction per
   cred-def is the obvious way to express that, and AnonCreds does treat a restriction
   list as OR — but ACA-Py's holder-side auto-presentation cannot build a presentation
   from it. Verified by experiment: one `cred_def_id` restriction verifies, two produce
   *"referent did not produce any credentials"*.

   `issuer_did` alone would also admit any other cred-def published under the same DID,
   so [`from_allowed_cred_def`](portal/ssi/acapy.py) checks the presented credential
   against the published list **after** verification. `scripts/test_security.py`
   exercises exactly this: its impostor cred-def is issued under our own DID, so only
   that server-side check rejects it.

3. **The request is wrapped in a connectionless out-of-band invitation**, so scanning
   one QR is the whole interaction — no connection has to be set up first.

4. **ACA-Py verifies the presentation** (`--auto-verify-presentation`) and reports
   `verified: "true"`.

5. **Only then** does [`login_complete`](portal/ssi/views.py) create the Django session.
   It re-checks verification server-side rather than trusting the browser's poll, so
   hitting that URL directly cannot fake a login.

The disclosed attributes come back under `revealed_attr_groups` and are pulled out by
[`revealed_attributes`](portal/ssi/acapy.py). The portal had never seen those values
before the presentation — that's why `/profile/` can display them.

---

## Project layout

```
.
├── lanip.py                  Shared LAN-address detection (agent + portal agree on the host)
├── .env.example              All configuration; copy to .env
│
├── agent/
│   ├── run_agent.py          Issuer/verifier ACA-Py launcher (+ the Windows fix)
│   ├── run_holder.py         Software "wallet" used only for automated testing
│   ├── register_did.py       Writes the issuer DID to the BCovrin ledger
│   └── start_agent.ps1       Thin PowerShell wrapper
│
├── portal/
│   ├── manage.py
│   ├── portal/settings.py
│   └── ssi/
│       ├── acapy.py          Admin API client — every SSI call goes through here
│       ├── views.py          Issuance, proof login, protected pages, webhooks
│       ├── models.py         LedgerArtifacts, IssuanceRequest, LoginSession, BasicMessage
│       ├── management/commands/ssi_setup.py   Publishes schema + cred-def
│       └── templates/ssi/
│
└── scripts/
    └── demo_end_to_end.py    Automated verification of the whole flow
```

---

## Verification

[scripts/demo_end_to_end.py](scripts/demo_end_to_end.py) drives the entire journey with a
software holder standing in for the phone, and asserts each step:

```
1. Registrar issues a Student ID credential          [OK]
2. Wallet scans the QR and accepts the credential    [OK]
     cred_def: WazjcnK7xmg2BwiGzStH1S:3:CL:3225245:university-portal
     student_name = Ayesha Rahman
     student_id   = STU-2024-0142
     department   = Computer Science
     email        = ayesha@demo-university.edu
3. Student logs in by presenting the credential      [OK]  presentation VERIFIED
4. Dashboard / Profile / Dashboard again             [OK]  no re-authentication
5. Logout                                            [OK]  dashboard redirects to login
```

The holder agent is a **test harness, not part of the demo** — it exists so the backend
can be proven correct without a phone in the loop. The recorded demo uses a real mobile
wallet scanning the same QR codes at the same endpoints.

---

## Why no Docker, and what that cost

ACA-Py is normally deployed as a container alongside an Indy ledger. Neither Docker nor
WSL was available here, so the agent runs directly from `pip` on Python 3.9. Three things
had to be solved:

**1. Version.** The current `acapy-agent` 1.x needs Python 3.12+. `aries-cloudagent`
0.12.8 is the last line supporting 3.9, and its Rust native libraries (`aries_askar`,
`indy_vdr`, `anoncreds`) all ship working Windows wheels.

**2. Windows has no SIGTERM.** ACA-Py's `run_loop()` calls
`loop.add_signal_handler(signal.SIGTERM, ...)`, which asyncio only implements on Unix —
on Windows it raises `NotImplementedError` and the agent dies during startup.
[agent/run_agent.py](agent/run_agent.py) makes that registration a no-op. Nothing is
lost: SIGTERM isn't a Windows signal, and Ctrl-C still shuts down cleanly through the
`KeyboardInterrupt` path ACA-Py already handles. The fix lives in this repo rather than
as a patch to the installed package, so a fresh clone works.

**3. No local ledger.** Instead of running one, the agent uses the hosted **BCovrin test
network**, and [agent/register_did.py](agent/register_did.py) registers the issuer DID
there.

## Two other things worth knowing

**QR codes were too big to scan.** A proof-request invitation is ~1.8 KB, which
overflowed the QR library outright at default error correction and produced a
version-31 (141×141) grid that phone cameras struggle with. Two fixes: grouping the
requested attributes cut it from 2386 to 1786 bytes, and the pages now show a **compact
QR** holding a short URL the wallet fetches (`/i/<token>/`) with the full-data QR one
click away for wallets that don't implement out-of-band URL shortening.

**A stale IP address breaks everything silently.** DHCP reassigned this machine's address
mid-development; the agent kept advertising the old one, and connections simply timed out
with no useful error. `AGENT_HOST_IP=auto` in `.env` now detects the LAN address at
startup, several addresses can be listed, and the agent warns loudly if the configured
address isn't reachable. See [lanip.py](lanip.py).

---

## Mobile wallet

The wallet must support **AnonCreds** credentials on the **BCovrin Test** network.

| Option | Notes |
|---|---|
| **BC Wallet** | Built on Aries Bifold, on both app stores, documented against BCovrin Test. Easiest path to a Bifold-based wallet with no build toolchain. |
| **Orbit Edge Wallet** | Northern Block; also recommended in the ACA-Py workshop for BCovrin Test. |
| **Build Bifold from source** | [openwallet-foundation/bifold-wallet](https://github.com/openwallet-foundation/bifold-wallet) — most faithful to the task, but needs the React Native toolchain and Android Studio/Xcode. |

Whichever you use, the phone must be on **the same WiFi network** as this machine, and
the wallet's ledger must be set to **BCovrin Test**. See
[USER_MANUAL.md](USER_MANUAL.md) for the walkthrough and troubleshooting.

---

## Quick start

Full instructions in [SETUP.md](SETUP.md). Once set up, three terminals:

```powershell
# 1. ACA-Py agent
.\.venv\Scripts\python.exe agent\run_agent.py

# 2. Django portal
.\.venv\Scripts\python.exe portal\manage.py runserver 0.0.0.0:8000

# 3. (optional) verify the whole flow without a phone
.\.venv\Scripts\python.exe agent\run_holder.py      # in its own terminal
.\.venv\Scripts\python.exe scripts\demo_end_to_end.py
```

Then open the portal, issue a credential at `/issue/`, and log in at `/login/`.

---

## References

- [ACA-Py](https://github.com/openwallet-foundation/acapy) · [docs](https://aca-py.org/latest/features/DevReadMe/)
- [Aries Bifold](https://github.com/openwallet-foundation/bifold-wallet)
- [SSI tutorial](https://github.com/CrypticConsultancyLimited/ssi-tutorial)

# SSI University Portal

A university portal where students and faculty **log in by presenting a
verifiable credential from a phone wallet** — no passwords, and no user
table. The portal issues Student ID / Faculty ID credentials to a mobile
wallet, verifies them at login, and includes a bonus 1-to-1 encrypted
messaging feature between faculty and students over DIDComm.

Built with **ACA-Py** (Hyperledger Aries) for every SSI operation and
**Django** for the web portal. Runs natively on Windows — no Docker, no WSL.

```
   ┌───────────────┐   1. scan QR    ┌────────────────────┐
   │ Phone wallet  │◄────────────────│  Django portal     │
   │  (Bifold)     │                 │  :8000             │
   │               │  2. present     │                    │
   │  holds the    │─────proof──────►│  login, dashboard, │
   │  credential   │                 │  profile, messages │
   └───────┬───────┘                 └─────────┬──────────┘
           │                                   │
           │ DIDComm :8020            Admin API :8021
           │                          + signed webhooks
           ▼                                   ▼
   ┌───────────────┐               ┌────────────────────┐
   │  Mediator     │               │  ACA-Py agent      │
   │  :8040/:8042  │               │  issuer + verifier │
   └───────────────┘               └─────────┬──────────┘
                                             │ publishes / reads
                                             ▼
                                   ┌────────────────────┐
                                   │ BCovrin test ledger│
                                   │ DID, schemas,      │
                                   │ credential defs    │
                                   └────────────────────┘
```

The `role` (student/faculty) lives **inside the credential**, signed by the
university — not in a database column. Presenting the other credential from
the same wallet changes the entire portal, with no server-side account
switch.

## Further reading

This README is the single entry point, but the project has deeper
documentation for specific topics:

| Doc | Covers |
|---|---|
| [LEARN_SSI.md](LEARN_SSI.md) | SSI concepts from zero — DIDs, credentials, ledgers, wallets |
| [SETUP_GUIDE.md](SETUP_GUIDE.md) | The exhaustive build log — every trap hit while building this on Windows |
| [HOW_IT_WORKS.md](HOW_IT_WORKS.md) | Engineering detail: security design, demo script, troubleshooting |
| [MESSAGING_PROTOCOL.md](MESSAGING_PROTOCOL.md) | The messaging feature in depth: DIDComm/Aries RFCs, handshake, state machine |

---

## 1. Technologies used

### Backend / SSI core

| Technology | Version | Role |
|---|---|---|
| [**ACA-Py**](https://github.com/openwallet-foundation/acapy) (`aries-cloudagent`) | `0.12.8` | Hyperledger Aries cloud agent — issues credentials, verifies proofs, manages DIDComm connections. Runs as the **issuer + verifier** agent and as a local **mediator** instance. The portal never touches keys or the ledger directly; everything goes through ACA-Py's admin HTTP API and its webhook callbacks. |
| **Aries Askar** (`aries_askar`) | via ACA-Py `[askar]` extra | Secure wallet storage (native library) — holds the agent's DIDs and keys. |
| **Indy VDR** (`indy_vdr`) | via ACA-Py `[indy]` extra | Reads/writes the Indy ledger (DIDs, schemas, credential definitions). |
| **AnonCreds** (`anoncreds`) | via ACA-Py | The credential format used — supports zero-knowledge selective disclosure. |
| **Python** | 3.9 – 3.12 (pinned to 3.9 in this build) | ACA-Py `0.12.8` is the last release supporting 3.9; the 1.x rename (`acapy-agent`) needs 3.12+. |
| [**Django**](https://www.djangoproject.com/) | `4.2.16` | The web portal — routing, sessions, templates, ORM. No `django.contrib.auth` and no admin app: there is deliberately no username/password login path. |
| **SQLite** | (Django default) | Local database. Stores only portal-side bookkeeping — issuance records, login sessions, chat/connection state — never credential contents or private keys. |
| `python-dotenv` | ≥1.0 | Loads shared config from a single root `.env` used by both the Django settings and the agent launchers. |
| `requests` | ≥2.31 | HTTP client the portal uses to call ACA-Py's admin API. |
| `qrcode[pil]` | ≥7.4 | Renders out-of-band invitations and proof requests as scannable QR codes. |

### Identity protocols (Hyperledger Aries RFCs)

All standard, unmodified Aries protocols — nothing here is a custom message
type:

| Protocol | RFC | Used for |
|---|---|---|
| **Out-of-Band** | [0434](https://github.com/decentralized-identity/aries-rfcs/tree/main/features/0434-outofband) | Wraps every QR invitation (issuance, login, messaging) |
| **DID Exchange 1.0** | [0023](https://github.com/decentralized-identity/aries-rfcs/tree/main/features/0023-did-exchange) | The connection handshake: request → response → complete |
| **Issue Credential** | Aries credential-issuance protocol | Offering and issuing Student/Faculty ID credentials |
| **Present Proof** | Aries proof-presentation protocol | The login proof request/response |
| **Basic Message 1.0** | [0095](https://github.com/decentralized-identity/aries-rfcs/tree/main/features/0095-basic-message) | Plain encrypted chat messages over an established connection |
| **Mediator Coordination** | [0211](https://github.com/decentralized-identity/aries-rfcs/tree/main/features/0211-route-coordination) | Lets a phone with no public address receive DIDComm via a mediator |
| **Connections Protocol** | [0160](https://github.com/decentralized-identity/aries-rfcs/tree/main/features/0160-connection-protocol) | Superseded by 0023; ACA-Py's state naming (`active`) still reflects it |

### Ledger

- [**BCovrin Test Network**](http://test.bcovrin.vonx.io) — a public, hosted
  Hyperledger Indy test ledger. Stores the issuer's public DID, the two
  credential schemas (Student ID / Faculty ID), and their credential
  definitions. Nothing to run locally.

### Mobile wallet

- [**Aries Bifold**](https://github.com/openwallet-foundation/bifold-wallet)
  — the open-source reference Aries mobile wallet (React Native), used as
  the **holder** app on the phone. A prebuilt release APK is served from
  the portal itself; see [§3.5](#35-installing-the-mobile-wallet-apk).
- Build toolchain: **Node 20.19.2**, **Yarn 4.9.2** (via Corepack), **JDK
  17**, **Android SDK** (platform 36, build-tools 36.0.0), **Android NDK**
  27.1.12297006, **Gradle**.

### Everything else

- **PowerShell / Windows** as the primary target platform — the project
  runs with no Docker and no WSL. `agent/run_agent.py` and
  `agent/run_mediator.py` work around a Windows-specific ACA-Py crash
  (`SIGTERM` is unimplemented under asyncio on Windows).
- Plain Python scripts for orchestration and testing: `run.py` (starts
  agent + mediator + portal together), `scripts/demo_end_to_end.py`
  (automated happy-path test using a software wallet), and
  `scripts/test_security.py` (19 automated attack/regression tests).

---

## 2. How it works — the three workflows

The portal never handles keys, DIDs, or the ledger directly. Every SSI
operation goes through ACA-Py's admin API via
[`portal/ssi/acapy.py`](portal/ssi/acapy.py), and ACA-Py reports back
asynchronously via signed webhooks handled in
[`portal/ssi/views.py`](portal/ssi/views.py).

### 2.1 Issuance — getting a credential onto a phone

```
Faculty          Django portal            ACA-Py agent            Holder wallet
   │  fill form        │                        │                        │
   ├───────────────────►  create invitation      │                        │
   │                   ├────────────────────────►│                        │
   │   QR code          │◄────────── invitation ─┤                        │
   │◄───────────────────┤                        │◄─────────── scan ──────┤
   │                   │◄──── webhook: connected ─┤                        │
   │                   ├────────────────────────► send credential offer   │
   │                   │                        ├───────────────────────►│
   │                   │                        │◄──────── accept ───────┤
   │   "issued"         │◄──── webhook: issued ───┤                        │
   │◄───────────────────┤                        │                        │
```

1. A **faculty member** opens `/issue/`, picks **Student** or **Faculty**,
   and fills in the person's details.
2. The portal asks ACA-Py for an out-of-band invitation and renders it as a
   QR code.
3. The holder (phone wallet) scans it; a DIDComm connection forms.
4. ACA-Py fires a `connections` webhook. The portal matches it to the
   pending form submission and **immediately pushes the credential offer**
   — this is why nobody has to click anything between the scan and the
   offer appearing.
5. The holder reviews and accepts the offer in their wallet. The credential
   (`full_name`, `id_number`, `department`, `email`, `role`) now lives in
   their wallet, cryptographically signed by the university's DID. The
   portal keeps only a record that it was issued — never the credential
   contents.

The `/issue/` page tracks this live: `waiting for scan → wallet connected →
credential offered → credential issued`.

`/issue/` requires a faculty session — **except** on a fresh database with
no faculty credential yet, where it opens itself for exactly one bootstrap
issuance (since nobody could otherwise log in to authorize the first one).

### 2.2 Login — proving who you are without a password

```
Anyone            Django portal            ACA-Py agent            Holder wallet
   │  open /login/     │                        │                        │
   ├───────────────────► create proof request    │                        │
   │                   ├────────────────────────►│                        │
   │   QR code          │◄────── proof request ──┤                        │
   │◄───────────────────┤                        │◄─────────── scan ──────┤
   │                   │                        │◄──── present + share ──┤
   │                   │◄──── webhook: verified ─┤ (verified cryptographically)
   │                   │  re-checks with ACA-Py  │                        │
   │                   ├────────────────────────►│                        │
   │  session created   │◄──────── confirmed ─────┤                        │
   │◄───────────────────┤                        │                        │
```

1. `/login/` asks ACA-Py for a proof request restricted to this
   university's credentials (`issuer_did` restriction) and wraps it in a
   **connectionless** out-of-band invitation, so a single scan is the whole
   interaction.
2. The holder scans, reviews exactly which attributes are being requested,
   and taps **Share**.
3. ACA-Py verifies the presentation cryptographically — signature validity,
   the issuer DID, and that all requested attributes came from **one**
   credential (requested as a single referent group, not one-per-attribute,
   so a holder cannot mix attributes from two different credentials).
4. Only after ACA-Py itself confirms verification does
   [`login_complete`](portal/ssi/views.py) create a Django session — the
   browser's status poll is never trusted on its own; the server re-checks
   with ACA-Py directly.
5. The session is bound to the browser that requested the proof, and the
   proof exchange is single-use (marked consumed on first completion), so
   it can't be replayed or hijacked from another browser.

From there, `/dashboard/` and `/profile/` render role-specific content off
that one session — no credential is presented again until `/logout/`.

### 2.3 Messaging (bonus feature) — 1-to-1 encrypted chat

`/messages/` is a **directory of people**, not a QR generator — faculty see
students, students see faculty. There is exactly **one ACA-Py agent** in
the system ("Demo University"); every wallet connects *to that agent*,
never to each other directly, so messaging is deliberately relayed through
the portal's own UI.

The connect handshake, when Karim (faculty) presses **Connect** on Tanvir
(student)'s row:

```
Karim (faculty)      Django portal        ACA-Py agent       Tanvir (student)
   │  click Connect       │                     │                     │
   ├──────────────────────► create invitation    │                     │
   │                      ├────────────────────►│                     │
   │  "waiting on them"    │◄──── invitation ────┤                     │
   │◄──────────────────────┤                     │                     │
   │                      │                     │◄─ Tanvir opens his ─┤
   │                      │                     │   own Messages page,│
   │                      │                     │   scans with HIS    │
   │                      │                     │   own wallet        │
   │                      │◄─ webhook: request ──┤◄────────────────────┤
   │                      │                     │  auto-accept →      │
   │                      │                     ├─── response ───────►│
   │                      │◄─ webhook: complete ─┤◄──── complete ──────┤
   │  "connected"          │                     │      "connected"     │
   │◄──────────────────────┤─────────────────────┼─────────────────────►│
   │  type + send            both sides send/receive Basic Messages     │
   │  ◄───────────────────────────────────────────────────────────────► │
```

1. The portal asks ACA-Py for a new out-of-band invitation
   (`didexchange/1.0`, `auto_accept=true`) and stores a `ChatInvitation`
   row as `AWAITING_SCAN`. Karim sees "waiting for them to scan."
2. **Tanvir**, not Karim, opens *his own* Messages page, sees the pending
   invitation, and scans it with *his own* wallet. His wallet shows its own
   native "connect to Demo University?" prompt — **that prompt is the real
   consent step**, happening on his device, before anything is sent.
3. Once Tanvir's wallet sends the DID Exchange request, ACA-Py auto-accepts
   and completes the handshake (request → response → complete). Both sides'
   `/messages/` pages poll and flip to **CONNECTED** without a refresh.
4. From then on, either side can send text — the portal calls
   `POST /connections/{id}/send-message` (Basic Message, RFC 0095); the
   other side's message arrives via a `basicmessages` webhook. The same
   connection carries traffic both ways.
5. Either party can **Resend** a stuck invitation or **Disconnect** an
   active one at any time; disconnecting deletes the local connection
   record (DID Exchange has no protocol-level "goodbye").

Full state machine, sequence diagram, and design rationale (why consent
lives in the wallet's own scan prompt rather than a website Accept button):
[MESSAGING_PROTOCOL.md](MESSAGING_PROTOCOL.md).

### 2.4 What's on the ledger vs. what's in the database

| Stored on the **ledger** (BCovrin) | Stored in the **portal database** (SQLite) |
|---|---|
| Issuer DID | Issuance records (who/when, not the credential itself) |
| Student ID schema + credential definition | Login session records |
| Faculty ID schema + credential definition | `ChatInvitation` connection state + message history |

Credential contents (`full_name`, `id_number`, `department`, `email`,
`role`) and private keys live **only in the holder's wallet** and the
agent's Askar store — never in the Django database.

---

## 3. How to set up

Full step-by-step build log (with every trap hit while developing this on
Windows) is in [SETUP_GUIDE.md](SETUP_GUIDE.md). This section covers the
condensed path.

### 3.1 Prerequisites

```powershell
python --version    # 3.9 - 3.12 required
git --version
```

**Python version matters**: this project pins `aries-cloudagent==0.12.8`,
the last ACA-Py release that supports Python 3.9. No Docker, no WSL, and no
local ledger are needed for the backend.

### 3.2 Install and configure

```powershell
git clone https://github.com/Himika-Tasnim/RA-demo.git "RA Project"
cd "RA Project"

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Verify the native crypto libraries loaded correctly (the step most likely
to fail on an unusual platform):

```powershell
.\.venv\Scripts\python.exe -c "import aries_askar, indy_vdr, anoncreds; print('native libs OK')"
.\.venv\Scripts\aca-py.exe --version    # expect 0.12.8
```

Copy the environment template:

```powershell
Copy-Item .env.example .env
```

The defaults work for a local demo as-is. `AGENT_HOST_IP=auto` matters
most — it is the address your **phone** uses to reach this PC, and
auto-detecting it avoids a stale hard-coded IP silently breaking the demo
after you change networks. Before anything beyond a local demo, change
`WALLET_KEY`, `ACAPY_ADMIN_API_KEY`, `WEBHOOK_API_KEY` and
`DJANGO_SECRET_KEY` — Django refuses to start with `DEBUG=0` while any of
them still hold their demo defaults.

### 3.3 Provision the ledger and database (one-time)

```powershell
# Register the issuer DID on the BCovrin test ledger (idempotent)
.\.venv\Scripts\python.exe agent\register_did.py

# Django database
cd portal
..\.venv\Scripts\python.exe manage.py migrate
cd ..
```

Then, **with the agent running** (next step), publish the two credential
schemas and their credential definitions:

```powershell
cd portal
..\.venv\Scripts\python.exe manage.py ssi_setup
cd ..
```

### 3.4 Run the project

The simplest option — one command starts and health-checks the agent,
mediator, and portal in order, and streams all three logs together:

```powershell
.\.venv\Scripts\python.exe run.py
```

Equivalently, by hand in three separate terminals (useful if you want to
watch one process in isolation):

```powershell
.\.venv\Scripts\python.exe agent\run_agent.py                             # 1. issuer + verifier
.\.venv\Scripts\python.exe agent\run_mediator.py                          # 2. so the phone can receive
cd portal; ..\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000   # 3. the portal
```

Then open <http://127.0.0.1:8000>. Both status rows on the home page should
be green.

`0.0.0.0` on the portal's bind address is required — the Django default
binds to localhost only, which the phone cannot reach.

**Verify without a phone** (a fourth, optional terminal) before involving
real hardware:

```powershell
.\.venv\Scripts\python.exe agent\run_holder.py             # software wallet, testing only
.\.venv\Scripts\python.exe scripts\demo_end_to_end.py       # scripted happy-path (5 steps)
.\.venv\Scripts\python.exe scripts\test_security.py         # 19 automated attack/regression tests
```

Both scripts must pass before you involve a phone — if they do, any later
failure is wallet or network related, not the backend.

### 3.5 Installing the mobile wallet (APK)

You need the **Aries Bifold** wallet app on an Android phone on the **same
WiFi** as this PC.

**Fastest path — install the prebuilt APK:**

A prebuilt `bifold-wallet.apk` already ships in this checkout at
[`portal/ssi/static/bifold-wallet.apk`](portal/ssi/static/bifold-wallet.apk)
(it isn't committed to git — ~180 MB and gitignored — but it's on disk once
you have the project). With the portal running (`run.py` or step 3.4), grab
it one of two ways:

- **On the phone itself** (same WiFi, no cable): open this link directly in
  the phone's browser —

  ```
  http://<this-PC's-LAN-IP>:8000/static/bifold-wallet.apk
  ```

  e.g. `http://192.168.0.121:8000/static/bifold-wallet.apk` — swap in the
  IP the agent prints at startup. It downloads and Android prompts to
  install it (allow "install from unknown sources" if asked).
- **Over USB**, with `adb`:
  ```powershell
  adb install -r "portal\ssi\static\bifold-wallet.apk"
  ```

If that file isn't present (fresh clone, nothing copied in yet), build one
from source — see below — and drop it at that exact path to make the link
above work.

Then point the wallet at your local mediator (writes `MEDIATOR_URL` into
the Bifold app's env):

   ```powershell
   .\.venv\Scripts\python.exe agent\mediator_invitation.py --write-env
   ```

> **BC Wallet does not work as a substitute.** It's Bifold-based and on the
> app stores, but it allowlists BC Government services and will reject this
> project's QR codes.

**Building Bifold from source**, if you don't already have an APK: install
Node 20.19.2, Yarn 4.9.2 (via `corepack`), JDK 17, and the Android SDK
(platform 36 / build-tools 36.0.0 / NDK 27.1.12297006); clone
`openwallet-foundation/bifold-wallet`; pre-fetch the native `askar` /
`anoncreds` / `indy-vdr` binaries with `curl` (Yarn's own fetch has no
retry and reliably fails on these); apply two small patches (allow
cleartext HTTP for the LAN agent, fix a wrong module namespace in
credential deletion); then `gradlew assembleRelease`. This is long enough
that it has its own fully worked section, with every failure mode hit
while doing it on Windows: [SETUP_GUIDE.md, Part 4](SETUP_GUIDE.md#part-4--the-mobile-wallet-aries-bifold).

### 3.6 Network access for the phone

Windows blocks inbound connections by default. In an **Administrator**
PowerShell:

```powershell
New-NetFirewallRule -DisplayName "SSI Portal"   -Direction Inbound -LocalPort 8000      -Protocol TCP -Action Allow -Profile Public,Private
New-NetFirewallRule -DisplayName "SSI Agent"    -Direction Inbound -LocalPort 8020      -Protocol TCP -Action Allow -Profile Public,Private
New-NetFirewallRule -DisplayName "SSI Mediator" -Direction Inbound -LocalPort 8040,8042 -Protocol TCP -Action Allow -Profile Public,Private
```

Before touching the wallet, prove reachability from the phone's own
browser: `http://<this-PC's-LAN-IP>:8000` should load the portal. If it
doesn't, no wallet will connect either — fix that first.

### 3.7 First run

1. Open Bifold, choose a language, set a PIN, allow camera access. It
   registers with your mediator here.
2. On the PC, open `/issue/` — on a fresh database this is in **bootstrap
   mode** (open to anyone, since no faculty exists yet to authorize it).
3. Issue a **Faculty** credential, scan it with the wallet, accept.
4. From then on, `/issue/` requires a faculty login — log in with that
   credential at `/login/` to issue more.

### 3.8 Resetting

| Goal | Command |
|---|---|
| Clear credentials, logins, chats | `python portal/manage.py reset_demo` |
| Also forget the ledger records | `python portal/manage.py reset_demo --ledger` then `ssi_setup` |
| Wipe the agent wallet | stop the agent, delete `agent/wallet/`, restart |
| Wipe the phone wallet | `python scripts/reset_phone_wallet.py` |
| Start completely fresh | delete `portal/db.sqlite3`, `migrate`, `ssi_setup` |

---

## Project layout

```
agent/     ACA-Py launchers: issuer/verifier, mediator, test holder, DID registration
portal/    Django project -- the ssi app holds all portal logic
scripts/   End-to-end and security tests, plus wallet helpers
lanip.py   Shared LAN-address detection, so agent and portal agree on the host
run.py     Starts the agent, mediator, and portal together from one terminal
```

## Security notes

Two real vulnerabilities were found and fixed during development — an
**authentication bypass** through an unauthenticated webhook endpoint, and
**unauthenticated credential issuance** that let anyone mint a faculty
credential for themselves. Both, plus the full hardening list (session
binding, single-use proofs, CSRF/clickjacking headers, refusal to start
with demo secrets in production mode) and the project's known limitations
(plain HTTP on the LAN, no revocation registry, test ledger only), are
documented in [HOW_IT_WORKS.md § Security](HOW_IT_WORKS.md#security). All
of it is regression-tested by [`scripts/test_security.py`](scripts/test_security.py)
(19 tests).

## References

- [ACA-Py](https://github.com/openwallet-foundation/acapy) · [docs](https://aca-py.org/latest/)
- [Aries Bifold](https://github.com/openwallet-foundation/bifold-wallet)
- [Aries RFCs](https://github.com/decentralized-identity/aries-rfcs)
- [BCovrin Test Ledger](http://test.bcovrin.vonx.io)

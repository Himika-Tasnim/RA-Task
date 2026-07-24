# SSI University Portal

A university portal where students and faculty log in by presenting a
verifiable credential from a phone wallet. No passwords, no classic user
table: the portal issues Student ID and Faculty ID credentials, verifies
login by proof presentation, and supports 1-to-1 encrypted messaging over
DIDComm.

This repository runs the portal and all SSI infrastructure natively on
Windows using ACA-Py and Django. No Docker or WSL is required.

## What this repo contains

- `run.py` — start the agent, mediator, and portal together with one command
- `agent/run_agent.py` — start the issuer/verifier ACA-Py agent
- `agent/run_mediator.py` — start the DIDComm mediator ACA-Py instance
- `agent/register_did.py` — register the issuer DID on the BCovrin ledger
- `agent/mediator_invitation.py` — create the mediator invitation URL for the wallet app
- `agent/run_holder.py` — optional software holder agent for backend testing
- `portal/manage.py ssi_setup` — publish the Student and Faculty schemas and credential definitions
- `portal/manage.py runserver 0.0.0.0:8000` — start the web portal

## Verified setup steps

### 1. Install dependencies

```powershell
cd "E:\RA Project"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Create the environment file

```powershell
Copy-Item .env.example .env
```

Leave `AGENT_HOST_IP=auto` in `.env` for local demo use. It detects the
LAN address your phone needs to reach. Replace demo secrets before any
real deployment.

### 3. Register the issuer DID (one-time)

```powershell
.\.venv\Scripts\python.exe agent\register_did.py
```

This writes the public DID derived from `AGENT_SEED` to the BCovrin test
ledger. Re-running with the same seed is safe.

### 4. Prepare the Django database (one-time)

```powershell
cd portal
..\.venv\Scripts\python.exe manage.py migrate
cd ..
```

### 5. Start everything

```powershell
.\.venv\Scripts\python.exe run.py
```

`run.py` starts the agent, mediator, and portal together, health-checks
each one, and streams all their logs in one terminal. Leave it running —
the next two steps use a second terminal while it's up.

On Windows, running the agent/mediator this way (instead of calling
`aca-py` directly) is required: they patch Windows signal handling so
ACA-Py does not fail with `NotImplementedError`.

### 6. Publish schemas and credential definitions (one-time)

With `run.py` still running, in a second terminal:

```powershell
cd portal
..\.venv\Scripts\python.exe manage.py ssi_setup
cd ..
```

This creates the Student and Faculty schema and their credential
definitions on the ledger, then stores the artifact IDs in the portal DB.
It's idempotent — safe to re-run.

### 7. Install the wallet app on your phone

This project targets the [Bifold](https://github.com/openwallet-foundation/bifold-wallet)
mobile wallet (Android package `com.ariesbifold`). Bifold doesn't publish
a signed APK for download, so build it from that repo (`cd samples\app\android
&& .\gradlew.bat assembleRelease`), or use an existing `app-release.apk` if
you already built one.

Install it on your phone with adb (phone connected over USB, or over
Wi-Fi with wireless debugging enabled in Developer options):

```powershell
adb install -r path\to\app-release.apk
```

Without adb, copy the APK to the phone (e.g. via a cloud drive or cable)
and open it from a file manager — Android will prompt to allow installs
from that app the first time.

### 8. Create the mediator invitation

With `run.py` still running:

```powershell
.\.venv\Scripts\python.exe agent\mediator_invitation.py
```

Paste the resulting invitation URL into the wallet app to connect it to
the mediator. If `BIFOLD_APP_DIR` is set in `.env`, add `--write-env`
instead to save the mediator URL straight into the wallet app's `.env`
file (rebuild the app for it to take effect).

### 9. Optional: software wallet test (no phone required)

```powershell
.\.venv\Scripts\python.exe agent\run_holder.py
.\.venv\Scripts\python.exe scripts\demo_end_to_end.py
.\.venv\Scripts\python.exe scripts\test_security.py
```

`agent/run_holder.py` is a software holder agent used only for backend
testing. The real demo uses the mobile wallet from step 7.

## Running the demo

1. Open `http://127.0.0.1:8000/`
2. Open `/issue/` and issue the first credential
   - On a fresh database, `/issue/` runs in bootstrap mode and is open.
   - Issue a **Faculty** credential first.
3. Scan the QR code in the mobile wallet and accept the credential.
4. Open `/login/` and scan the login proof request.
5. After login, use `/dashboard/`, `/profile/`, and `/messages/`.

## Running processes individually

`run.py` is the recommended way to start the backend — the commands
below are only useful if you need to run or restart one process on its
own (e.g. while debugging).

| Command | Purpose |
|---|---|
| `python agent\run_agent.py` | Start the issuer/verifier ACA-Py agent |
| `python agent\run_mediator.py` | Start the local mediator agent |
| `cd portal && ..\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000` | Run the portal UI (`0.0.0.0` so the phone can reach it over the LAN) |

## Command reference

| Command | Purpose |
|---|---|
| `python agent\register_did.py` | Register the issuer DID on BCovrin |
| `cd portal && ..\.venv\Scripts\python.exe manage.py migrate` | Prepare the portal database |
| `python run.py` | Start agent, mediator, and portal together |
| `cd portal && ..\.venv\Scripts\python.exe manage.py ssi_setup` | Publish schemas and cred-defs |
| `python agent\mediator_invitation.py` | Create the mediator invitation URL |
| `python agent\run_holder.py` | Start a software wallet holder for tests |
| `python scripts\demo_end_to_end.py` | Validate the happy-path flow |
| `python scripts\test_security.py` | Run security regression tests |

## Reset and cleanup

| Action | Command |
|---|---|
| Clear portal state | `python portal\manage.py reset_demo` |
| Clear ledger artifacts too | `python portal\manage.py reset_demo --ledger` then `cd portal && ..\.venv\Scripts\python.exe manage.py ssi_setup` |
| Reset the phone wallet | `python scripts\reset_phone_wallet.py` |
| Start fresh | delete `portal\db.sqlite3`, then `cd portal && ..\.venv\Scripts\python.exe manage.py migrate && ..\.venv\Scripts\python.exe manage.py ssi_setup` |

## Project layout

- `agent/` — ACA-Py launchers and helpers
- `portal/` — Django portal code and SSI logic
- `scripts/` — end-to-end and security test scripts
- `lanip.py` — LAN address detection shared by agent and portal
- `run.py` — combined startup script

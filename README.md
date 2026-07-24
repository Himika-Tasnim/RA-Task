# SSI University Portal

A university portal where students and faculty log in by presenting a
verifiable credential from a phone wallet. No passwords, no classic user
table: the portal issues Student ID and Faculty ID credentials, verifies
login by proof presentation, and supports 1-to-1 encrypted messaging over
DIDComm.

This repository runs the portal and all SSI infrastructure natively on
Windows using ACA-Py and Django. No Docker or WSL is required.

## What this repo contains

- `agent/run_agent.py` — start the issuer/verifier ACA-Py agent
- `agent/run_mediator.py` — start the DIDComm mediator ACA-Py instance
- `agent/register_did.py` — register the issuer DID on the BCovrin ledger
- `portal/manage.py ssi_setup` — publish the Student and Faculty schemas and credential definitions
- `portal/manage.py runserver 0.0.0.0:8000` — start the web portal
- `agent/run_holder.py` — optional software holder agent for backend testing
- `agent/mediator_invitation.py` — create the mediator invitation URL for the wallet app
- `run.py` — start agent, mediator, and portal together from one terminal

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

### 3. Register the issuer DID

```powershell
.\.venv\Scripts\python.exe agent\register_did.py
```

This writes the public DID derived from `AGENT_SEED` to the BCovrin test
ledger. Re-running with the same seed is safe.

### 4. Prepare the Django database

```powershell
cd portal
..\.venv\Scripts\python.exe manage.py migrate
cd ..
```

### 5. Start the ACA-Py issuer/verifier agent

```powershell
.\.venv\Scripts\python.exe agent\run_agent.py
```

On Windows, `agent/run_agent.py` is the supported entrypoint. It patches
Windows signal handling so ACA-Py does not fail with `NotImplementedError`.

### 6. Publish schemas and credential definitions

With the agent running:

```powershell
cd portal
..\.venv\Scripts\python.exe manage.py ssi_setup
cd ..
```

This creates the Student and Faculty schema and their credential
definitions on the ledger, then stores the artifact IDs in the portal DB.

### 7. Start the mediator

```powershell
.\.venv\Scripts\python.exe agent\run_mediator.py
```

The wallet needs a mediator because it has no public address. This script
starts an ACA-Py mediator with HTTP and WebSocket transports.

### 8. Start the portal

```powershell
cd portal
..\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

`0.0.0.0` is required so the phone can reach the portal over the LAN.

### 9. Alternative: start all processes together

```powershell
.\.venv\Scripts\python.exe run.py
```

`run.py` starts the agent, mediator, and portal sequentially, health-checks
each one, and streams all logs together.

### 10. Optional software wallet test

```powershell
.\.venv\Scripts\python.exe agent\run_holder.py
.\.venv\Scripts\python.exe scripts\demo_end_to_end.py
.\.venv\Scripts\python.exe scripts\test_security.py
```

`agent/run_holder.py` is a software holder agent used only for backend
testing. The real demo uses a mobile wallet.

### 11. Create the mediator invitation

After `agent/run_mediator.py` is running:

```powershell
.\.venv\Scripts\python.exe agent\mediator_invitation.py
```

If `BIFOLD_APP_DIR` is set in `.env`, add `--write-env` to save the mediator
URL into the wallet app's `.env` file.

## Running the demo

1. Open `http://127.0.0.1:8000/`
2. Open `/issue/` and issue the first credential
   - On a fresh database, `/issue/` runs in bootstrap mode and is open.
   - Issue a **Faculty** credential first.
3. Scan the QR code in the mobile wallet and accept the credential.
4. Open `/login/` and scan the login proof request.
5. After login, use `/dashboard/`, `/profile/`, and `/messages/`.

## Command reference

| Command | Purpose |
|---|---|
| `python agent\register_did.py` | Register the issuer DID on BCovrin |
| `cd portal && ..\.venv\Scripts\python.exe manage.py migrate` | Prepare the portal database |
| `cd portal && ..\.venv\Scripts\python.exe manage.py ssi_setup` | Publish schemas and cred-defs |
| `python agent\run_agent.py` | Start the issuer/verifier ACA-Py agent |
| `python agent\run_mediator.py` | Start the local mediator agent |
| `cd portal && ..\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000` | Run the portal UI |
| `python .\venv\Scripts\python.exe run.py` | Start agent, mediator, and portal together |
| `python agent\run_holder.py` | Start a software wallet holder for tests |
| `python agent\mediator_invitation.py` | Create the mediator invitation URL |
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

## More documentation

- [SETUP_GUIDE.md](SETUP_GUIDE.md) — complete Windows build and trap log
- [HOW_IT_WORKS.md](HOW_IT_WORKS.md) — design, security, and behavior details
- [LEARN_SSI.md](LEARN_SSI.md) — SSI concepts and architecture
- [MESSAGING_PROTOCOL.md](MESSAGING_PROTOCOL.md) — chat protocol and DIDComm details

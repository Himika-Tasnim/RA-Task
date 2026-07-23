# Setup

How to recreate this project from nothing. Written for Windows, since that's the
awkward case; notes for macOS/Linux are inline where the two differ.

Budget about 20 minutes, most of it waiting on the install.

---

## 0. What you need

| | |
|---|---|
| **Python 3.9 – 3.12** | 3.9 works and is what this was built on. See the note below before using 3.13. |
| **Git** | To clone / publish |
| **A phone on the same WiFi** | For the real demo. Optional if you only run the automated test. |

You do **not** need Docker, WSL, or a local Indy ledger.

> **On the Python version.** This project pins `aries-cloudagent==0.12.8`, the last ACA-Py
> line that supports Python 3.9. If you're on **3.12+** you can instead use the current
> `acapy-agent` 1.x — the admin API calls in this project are unchanged, but you'd update
> `requirements.txt` and the import in [agent/run_agent.py](agent/run_agent.py). On
> **3.13** neither is reliable yet; use 3.12.

Check what you have:

```powershell
python --version
git --version
```

---

## 1. Get the code

```powershell
git clone <your-repo-url> "RA Project"
cd "RA Project"
```

Starting from scratch instead? The layout you need is in the
[Project layout](README.md#project-layout) section of the README.

---

## 2. Create the virtualenv and install

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

macOS/Linux: `.venv/bin/python` throughout instead of `.venv\Scripts\python.exe`.

This pulls ACA-Py plus three Rust native libraries (`aries-askar`, `indy-vdr`,
`anoncreds`). It takes a few minutes. Confirm they actually load — this is the step most
likely to fail on an unusual platform:

```powershell
.\.venv\Scripts\python.exe -c "import aries_askar, indy_vdr, anoncreds; print('native libs OK')"
.\.venv\Scripts\aca-py.exe --version
```

Expected:

```
native libs OK
0.12.8
```

<details>
<summary>If the native libraries fail to import</summary>

There's no prebuilt wheel for your Python version or platform. Either switch to a
supported Python (3.9–3.12 on x86-64), or run ACA-Py in Docker and point
`ACAPY_ADMIN_URL` at it — the portal only ever talks to the agent over HTTP, so it does
not care where the agent runs.
</details>

---

## 3. Configure

```powershell
Copy-Item .env.example .env
```

The defaults work as-is for a local demo. The one setting worth understanding:

```ini
AGENT_HOST_IP=auto
```

This is the address your **phone** will use to reach this machine. `auto` detects your
LAN address at startup, which is what you want — DHCP hands out a new address whenever
you rejoin a network, and a stale one fails silently: the agent starts, the QR code
renders, and the wallet just times out. You can also pin it (`192.168.1.20`) or list
several (`auto,10.0.0.5`); the first is the one used in QR invitations.

Before anything real, change `WALLET_KEY`, `ACAPY_ADMIN_API_KEY` and `DJANGO_SECRET_KEY`.
`.env` is git-ignored.

---

## 4. Register the issuer DID on the ledger

```powershell
.\.venv\Scripts\python.exe agent\register_did.py
```

This asks the public **BCovrin test ledger** to write a DID for your `AGENT_SEED`, with
an ENDORSER role — that role is what later lets the agent publish a schema and credential
definition.

```
DID registered successfully:
{
  "did": "WazjcnK7xmg2BwiGzStH1S",
  "verkey": "H8GzuRbD4VpwSCxPoURjFVkEQhYdw6fhLjy4vphvrYdC"
}
```

The DID is derived from the seed, so re-running this is harmless and there is nothing to
copy anywhere. Keep `AGENT_SEED` stable or you'll get a different DID and have to
republish the schema.

---

## 5. Set up the database

```powershell
cd portal
..\.venv\Scripts\python.exe manage.py migrate
cd ..
```

---

## 6. Start the agent

Leave this running in its own terminal:

```powershell
.\.venv\Scripts\python.exe agent\run_agent.py
```

You should see, before the ACA-Py banner:

```
  DIDComm endpoint : http://192.168.0.121:8020   <- your phone must be able to reach this
  Admin API        : http://127.0.0.1:8021
  Webhooks         -> http://127.0.0.1:8000/webhooks
```

Check that the address on the first line is your real WiFi address. If it warns that the
address is unreachable, fix `AGENT_HOST_IP` before continuing.

Confirm it's alive from another terminal:

```powershell
curl.exe -H "X-API-KEY: demo-admin-api-key" http://127.0.0.1:8021/status
```

---

## 7. Publish the schema and credential definition

With the agent running:

```powershell
cd portal
..\.venv\Scripts\python.exe manage.py ssi_setup
cd ..
```

```
Issuer public DID: WazjcnK7xmg2BwiGzStH1S
Schema published: WazjcnK7xmg2BwiGzStH1S:2:student_id_card:1.0
Publishing credential definition (this can take ~10s) ...
Cred-def published: WazjcnK7xmg2BwiGzStH1S:3:CL:3225245:university-portal
SSI setup complete.
```

This is a **one-time** step — it writes to the ledger. It's idempotent, so running it
again reuses what's already there rather than publishing duplicates.

---

## 8. Start the portal

Another terminal, left running:

```powershell
cd portal
..\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

`0.0.0.0` matters: it lets the phone load pages and fetch short-form invitations.

Open <http://127.0.0.1:8000>. The home page should show **agent: running** and
**credential definition: published**. If either is red, that page tells you which step to
go back to.

---

## 9. Verify it works, without a phone

Strongly recommended before you involve a wallet — it isolates backend problems from
wallet problems.

Start the software holder in a **third** terminal:

```powershell
.\.venv\Scripts\python.exe agent\run_holder.py
```

Then run the test:

```powershell
.\.venv\Scripts\python.exe scripts\demo_end_to_end.py
```

Expected ending:

```
5. Logging out
  [OK]   session destroyed -- dashboard now redirects to login

==================================================================
  ALL STEPS PASSED
==================================================================
```

If this passes, the SSI plumbing is correct and anything that goes wrong from here is
wallet or network related.

---

## 10. Set up the phone wallet

Install a wallet that supports **AnonCreds** on the **BCovrin Test** network:

- **BC Wallet** — built on Aries Bifold, on both app stores, documented against BCovrin Test
- **Orbit Edge Wallet** — Northern Block, also recommended in the ACA-Py workshop
- **Bifold from source** — [openwallet-foundation/bifold-wallet](https://github.com/openwallet-foundation/bifold-wallet), needs React Native + Android Studio/Xcode

Then:

1. Put the phone on **the same WiFi** as this machine.
2. In wallet settings, select the **BCovrin Test** ledger.
3. Sanity-check reachability by opening `http://<your-ip>:8000` in the phone's browser.
   If that page doesn't load, the wallet won't connect either — see
   [USER_MANUAL.md](USER_MANUAL.md#the-phone-cant-reach-the-portal).

---

## Summary

Once set up, a normal session is three terminals:

```powershell
.\.venv\Scripts\python.exe agent\run_agent.py                        # 1
cd portal; ..\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000   # 2
.\.venv\Scripts\python.exe agent\run_holder.py                       # 3, testing only
```

Steps 4, 5 and 7 (DID, migrate, ssi_setup) are one-time. Day-to-day use is in
[USER_MANUAL.md](USER_MANUAL.md).

---

## Starting over

| Goal | Do this |
|---|---|
| Clear portal data, keep the ledger | Delete `portal/db.sqlite3`, run `manage.py migrate` and `manage.py ssi_setup` |
| Reset the agent's wallet | Stop the agent, delete `agent/wallet/`, restart (it re-provisions from the seed) |
| New issuer identity | Change `AGENT_SEED`, re-run `register_did.py`, then `ssi_setup` |

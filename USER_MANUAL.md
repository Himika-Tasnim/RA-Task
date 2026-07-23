# User Manual

Day-to-day operation of the SSI University Portal: starting it, issuing a credential,
logging in with a phone, and what to do when something doesn't work.

First-time installation is in [SETUP.md](SETUP.md).

---

## Starting up

Two terminals, both left running. Order matters — the agent should be up before the
portal, so the portal's status page reads correctly.

**Terminal 1 — ACA-Py agent**

```powershell
.\.venv\Scripts\python.exe agent\run_agent.py
```

Note the DIDComm address it prints. That's what your phone needs to reach:

```
  DIDComm endpoint : http://192.168.0.121:8020   <- your phone must be able to reach this
```

**Terminal 2 — Django portal**

```powershell
cd portal
..\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

Then open <http://127.0.0.1:8000>. Both status rows on the home page should be green:

| Row | Green means | If red |
|---|---|---|
| ACA-Py agent | `running` | Terminal 1 isn't up, or crashed |
| Credential definition | `published` | Run `manage.py ssi_setup` ([SETUP.md](SETUP.md) step 7) |

**Shutting down:** Ctrl-C in each terminal. Nothing is lost — the wallet, ledger entries
and issued credentials all persist.

---

## The pages

| Page | Who it's for | Protected |
|---|---|---|
| `/` | Everyone — system status and an overview | No |
| `/issue/` | Registrar — issue a Student ID credential | No¹ |
| `/login/` | Student — scan to log in | No |
| `/dashboard/` | Student — courses and notices | **Yes** |
| `/profile/` | Student — the attributes their wallet disclosed | **Yes** |
| `/messages/` | Student — DIDComm chat (bonus) | **Yes** |
| `/logout/` | Ends the session | — |

¹ The issuance page is deliberately left open so the demo can be recorded in one pass.
In anything real it would sit behind staff authentication.

---

## Issuing a Student ID credential

1. Go to **Issue Credential** (`/issue/`).
2. Fill in name, student ID, department and email, then **Generate invitation QR**.
3. Scan the QR with the wallet and accept the connection with *Demo University*.
4. A credential offer arrives on its own — tap **Accept**.

The page tracks progress live, with no need to refresh:

```
waiting for scan…  →  wallet connected  →  credential offered  →  credential issued
```

Once it reaches **credential issued**, the credential is in the wallet and the student can
log in.

**What's happening underneath:** the QR is an out-of-band invitation. When the wallet
completes the connection, ACA-Py fires a `connections` webhook at the portal, which
matches it to your form submission and immediately pushes the credential offer — that's
why no one has to click anything between the scan and the offer.

---

## Logging in with a credential

1. Go to **Login** (`/login/`).
2. Scan the QR with the wallet holding the Student ID.
3. The wallet shows what's being requested — tap **Share**.
4. The page switches to *verified — signing you in…* and lands on the Dashboard.

Then navigate **Dashboard → Profile → Dashboard** freely. No credential is presented
again; that's the session doing its job. **Logout** ends it, and Dashboard immediately
bounces back to Login.

`/profile/` shows the four attributes the wallet disclosed, plus the issuer DID and
credential definition the proof was checked against. The portal had never stored those
values — they arrived in the presentation.

---

## The two QR codes

Each QR page offers two encodings, with a **switch** link underneath:

- **Compact QR** (default) — holds a short URL (`/i/<token>/`) that the wallet fetches to
  retrieve the invitation. Small, dense-free, scans almost instantly.
- **Full QR** — the entire invitation inline. A much denser grid, but works with wallets
  that don't implement out-of-band URL shortening.

Start with compact. If the wallet doesn't recognise it, click **switch** and scan again.
Both produce an identical result.

Under *Can't scan?* you can also copy either URL and paste it into the wallet, which is
handy when screen-sharing.

---

## Bonus: secure messaging

`/messages/` exchanges text over DIDComm with any wallet that has an active connection —
a connection created during issuance is reused, so issue a credential first.

Pick a connection, type, and send. Incoming messages arrive via the `basicmessages`
webhook and appear after a refresh. Both directions are end-to-end encrypted over
DIDComm; the portal only ever sees plaintext because it is one of the two parties.

---

## Recording the demo

The required sequence is: **issue credential → login via proof → both protected pages →
logout.**

A run that records cleanly:

1. Start both terminals. Open `/` and let the green status rows show on camera — it
   establishes that the agent is live and the credential definition is on a real ledger.
2. `/issue/` — fill the form, scan, accept in the wallet, wait for **credential issued**.
3. `/login/` — scan, tap Share in the wallet, get signed in automatically.
4. `/dashboard/`, then `/profile/`. Pause on Profile: those attributes came out of the
   credential, and the panel below names the issuer DID they were verified against.
5. `/logout/`, then click Dashboard to show it redirects to Login.

Worth doing beforehand:

- Run `scripts\demo_end_to_end.py` once, so you know the backend is good.
- Delete previous credentials from the wallet, so the login screen doesn't offer a
  choice mid-recording.
- Check the agent's printed IP still matches your network.

---

## Troubleshooting

### The phone can't reach the portal

The most common problem by far, and it usually isn't the wallet.

**Test it directly:** open `http://<the-ip-the-agent-printed>:8000` in the phone's
browser. If that page doesn't load, no wallet will connect either.

Work through:

1. **Same network?** Phone and PC on the same WiFi. Guest networks and "client isolation"
   on the router block device-to-device traffic entirely.
2. **Right address?** Compare the agent's printed IP against `ipconfig`. If they differ,
   your IP changed — set `AGENT_HOST_IP=auto` in `.env` and restart the agent.
3. **Server bound publicly?** The portal must run with `0.0.0.0:8000`, not the default
   `127.0.0.1:8000`.
4. **Firewall.** Windows Firewall blocks inbound ports on first use. Allow Python on
   private networks, or open ports 8000 and 8020:

   ```powershell
   New-NetFirewallRule -DisplayName "SSI Portal" -Direction Inbound -LocalPort 8000,8020 -Protocol TCP -Action Allow -Profile Private
   ```

### "Agent unreachable" on the home page

Terminal 1 isn't running or exited. Check it for a traceback and restart. Verify with:

```powershell
curl.exe -H "X-API-KEY: demo-admin-api-key" http://127.0.0.1:8021/status
```

### "No credential definition found"

`ssi_setup` hasn't run against this database. With the agent up:

```powershell
cd portal; ..\.venv\Scripts\python.exe manage.py ssi_setup
```

### The wallet scans, then nothing happens

The wallet decoded the QR but can't reach the DIDComm endpoint — same causes as
[the phone can't reach the portal](#the-phone-cant-reach-the-portal), for port 8020.
Confirm from the phone's browser: `http://<ip>:8020` should return a response rather than
hanging.

### The wallet won't accept the credential

Its ledger is probably wrong. The credential definition lives on **BCovrin Test**; a
wallet pointed at Sovrin, IDunion or a BC production ledger cannot resolve it. Change the
network in wallet settings and retry.

### Login says "not verified", or the wallet has nothing to present

The proof request is restricted to this portal's `cred_def_id`, so the wallet must hold a
credential issued by *this* agent. If you re-ran `register_did.py` with a new seed, or
republished the credential definition, previously issued credentials no longer satisfy
it — issue a fresh one.

### The QR code won't scan

Click **switch** to try the other encoding. Otherwise: increase screen brightness, zoom
the browser, and hold the phone steady — the full QR is a dense grid and cameras need a
moment to lock on.

### Port already in use

Something is still bound from an earlier run:

```powershell
netstat -ano | Select-String ":8000|:8020|:8021"
Stop-Process -Id <pid>
```

Or change the ports in `.env`.

---

## Resetting

| Goal | Do this |
|---|---|
| Clear issued credentials and login history | Delete `portal/db.sqlite3`, then `manage.py migrate` and `manage.py ssi_setup` |
| Reset the agent's wallet and connections | Stop the agent, delete `agent/wallet/`, restart |
| Start completely fresh, including a new DID | Change `AGENT_SEED` in `.env`, re-run `register_did.py`, then both of the above |

Deleting `portal/db.sqlite3` does **not** remove anything from the ledger — the schema
and credential definition stay published, which is why `ssi_setup` finds and reuses them.

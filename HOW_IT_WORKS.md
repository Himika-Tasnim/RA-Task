# How It Works — and how to use it

A university portal where people log in by **presenting a verifiable credential
from a phone wallet** instead of typing a password.

Setup instructions are in [SETUP_GUIDE.md](SETUP_GUIDE.md). This document covers
what the system does, why it is built this way, and how to drive it.

---

# Part 1 — How it works

## The idea

There is no password, and no user table. The portal stores nothing about you
until you prove who you are, and what it learns comes from a credential the
university signed and your wallet chose to disclose.

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

The portal never handles keys, DIDs or the ledger. Every SSI operation goes
through ACA-Py's admin API via [portal/ssi/acapy.py](portal/ssi/acapy.py).

## The three flows

### Issuance

1. A faculty member opens `/issue/`, picks **Student** or **Faculty**, fills in
   the details.
2. The portal asks ACA-Py for an out-of-band invitation and renders it as a QR.
3. The holder scans it; a DIDComm connection forms.
4. ACA-Py fires a `connections` webhook; the portal matches it to the form
   submission and **immediately pushes the credential offer** — which is why
   nobody clicks anything between the scan and the offer.
5. The holder accepts. The credential now lives in their wallet, signed by the
   university, and the portal keeps only a record that it was issued.

### Login

1. `/login/` asks ACA-Py for a proof request and wraps it in a *connectionless*
   invitation, so one scan is the whole interaction.
2. The holder scans, reviews what is being asked, and shares.
3. ACA-Py verifies the presentation cryptographically.
4. Only then does [`login_complete`](portal/ssi/views.py) create a Django
   session.

### Messaging (the bonus)

`/messages/` is a directory of people, not a QR generator. Faculty see students,
students see faculty. Picking someone produces a QR **for that person**; once
they scan it there is a direct DIDComm connection carrying Basic Messages both
ways — unrelated to credential issuance.

## What is on the ledger

| | |
|---|---|
| Issuer DID | `WazjcnK7xmg2BwiGzStH1S` |
| Student schema | `...:2:university_student_id:1.0` |
| Student cred-def | `...:3:CL:3225339:university-portal` |
| Faculty schema | `...:2:university_faculty_id:1.0` |
| Faculty cred-def | `...:3:CL:3225341:university-portal` |

Attributes are `full_name`, `id_number`, `department`, `email`, `role`.

**Two schemas, one per role.** Wallets name a credential card after its schema.
Sharing one schema would give a holder two identical-looking cards with no way
to choose correctly at login.

**`role` lives inside the credential**, signed by the university — not in a
database column. That is what makes it trustworthy: presenting the other
credential from the same wallet changes the entire portal, with no server-side
account switch.

---

## Why the login is authentication, not a form

Four things have to hold, and each is deliberate.

**1. The proof request is restricted to this university's credentials.**

```python
{"university_id": {"names": [...], "restrictions": [{"issuer_did": ...}]}}
```

**2. All attributes come from one credential.** They are requested as a single
*group* (`names`), not one referent each. With separate referents a holder could
satisfy each from a *different* credential — a real name with someone else's ID
number.

**3. The presented credential is checked against an allowlist.** The restriction
can only pin `issuer_did`, which would also admit any other cred-def published
under the same DID. [`from_allowed_cred_def`](portal/ssi/acapy.py) closes that
gap after verification.

> Why not restrict on `cred_def_id` directly, listing both? AnonCreds treats a
> restriction list as OR, so it *should* work — but ACA-Py's holder-side
> auto-presentation cannot build a presentation from it. Verified by experiment:
> one `cred_def_id` restriction verifies, two produce *"referent did not produce
> any credentials"*. Hence `issuer_did` plus the server-side check.

**4. Verification is re-checked server-side.** The browser polls for status, but
`login_complete` never trusts that poll — it asks ACA-Py directly.

---

## Security

The interesting parts, including two real vulnerabilities found and fixed during
development. All of these are regression-tested by
[scripts/test_security.py](scripts/test_security.py) — **19 tests**.

### Fixed: authentication bypass via the webhook endpoint

The webhook endpoint was unauthenticated and CSRF-exempt, and the handler
believed whatever the payload claimed. `pres_ex_id` is printed into the public
login page, so anyone able to reach the portal could lift it and POST a
fabricated *"presentation verified"* event.

Demonstrated end to end before fixing: a single forged POST produced a working
session reading **"Faculty Dashboard / Signed in as ATTACKER"** — no credential,
no wallet. The firewall rule opening port 8000 made this reachable from any
device on the network.

Two independent layers now:

- **The endpoint requires a shared secret.** ACA-Py sends it as `x-api-key` via
  `--webhook-url <url>#<key>`; anything else gets 401, compared in constant time.
- **The payload is only a notification.** `_on_presentation` re-fetches the
  authoritative record from ACA-Py's admin API, so even a webhook holding the
  secret cannot assert a verification that never happened.

### Fixed: anyone could issue themselves a faculty credential

`/issue/` was open. Anyone on the network could mint themselves a *faculty*
credential and then log in with it completely legitimately — the credential
would be genuine, so no downstream proof check could catch it. Issuance is the
root of trust and now requires a faculty session.

There is a deliberate bootstrap exception: while no faculty credential exists,
nobody could log in to authorise the first one, so the first issuance is open
and the page says so.

### Other hardening

| Risk | Mitigation |
|---|---|
| Someone else completing your login (`pres_ex_id` is public) | Login sessions are bound to the browser that requested the proof |
| Replaying a verified proof after logout | Single-use — marked consumed on first completion |
| Session fixation | `cycle_key()` on login |
| Reading another pair's messages | Threads scoped to the logged-in member's `id_number` |
| A second login form bypassing credentials | Django admin and the auth app removed entirely — `/admin/` 404s |
| Cookie theft / clickjacking / token leakage | HttpOnly, SameSite=Lax, `X-Frame-Options: DENY`, nosniff, same-origin referrer |
| Shipping demo secrets | Startup refuses `DEBUG=0` while any secret holds its default |

### Known limits

Honest about what this is — a LAN demo, not a deployment.

- **Plain HTTP.** The phone reaches the PC over `http://`, so DIDComm payloads
  are encrypted but portal traffic is not. `PORTAL_HTTPS=1` turns on the Secure
  cookie flags once you have TLS.
- **`ALLOWED_HOSTS = ["*"]`** so the phone can use the LAN IP.
- **No revocation.** Credentials are issued without a revocation registry, so a
  credential cannot be withdrawn once issued.
- **No rate limiting** on login attempts.
- **Ledger is the public BCovrin test net** — fine for a demo, not for real
  identities.

---

# Part 2 — How to use it

## Starting up

Three terminals, in this order (fourth only for tests):

```powershell
.\.venv\Scripts\python.exe agent\run_agent.py                             # 1
.\.venv\Scripts\python.exe agent\run_mediator.py                          # 2
cd portal; ..\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000   # 3
.\.venv\Scripts\python.exe agent\run_holder.py                            # 4, tests only
```

Open <http://127.0.0.1:8000>. Both status rows green means you are ready.

**Check the IP the agent prints each session** — DHCP moves it, and a stale
address fails silently.

## The pages

| Page | Who | Protected |
|---|---|---|
| `/` | anyone — system status | no |
| `/issue/` | faculty (open on first run) | **yes** |
| `/login/` | anyone | no |
| `/dashboard/` | logged in — role-specific | **yes** |
| `/profile/` | logged in — role-specific | **yes** |
| `/messages/` | logged in — directory + chat | **yes** |
| `/logout/` | — | — |

## Issuing a credential

`/issue/` → pick **Student** or **Faculty** → fill in details → **Generate
invitation QR** → scan → accept the connection → accept the credential offer.

The page tracks progress live:

```
waiting for scan → wallet connected → credential offered → credential issued
```

## Logging in

`/login/` → scan → review → **Share**. You land on the Dashboard. Then move
between Dashboard and Profile freely — nothing is presented again; that is the
session doing its job. **Logout** ends it.

## What the role changes

| | Student | Faculty |
|---|---|---|
| Dashboard | enrolled courses, notices | courses taught, grading queue, staff tools |
| Profile | *Student ID*, programme, year, credits | *Employee ID*, position, office, supervision |
| Nav | no Issue link | Issue link |

## Messaging

`/messages/` → pick a person → **Show QR** → they scan → type and send. Both
sides poll, so replies appear without refreshing.

## The two QR codes

Every QR page offers two encodings with a **switch** link:

- **Compact** (default) — a short `/i/<token>/` URL the wallet fetches. ~41
  bytes, scans instantly.
- **Full** — the whole invitation inline (~1.8 KB, a dense grid). For wallets
  that do not implement out-of-band URL shortening.

Start with compact; switch if the wallet does not recognise it.

---

## Recording the demo

The required sequence is **issue → login → both protected pages → logout**.

A run that films well:

1. **`/`** — show the status rows, issuer DID and schema ids. These are real
   ledger objects, not local config.
2. **Empty wallet first** — `/login/`, scan, and it **fails**. Nothing to
   present. (Use `scripts/reset_phone_wallet.py` to get here.)
3. **`/issue/`** — issue a Student ID, scan, accept, wait for *credential
   issued*.
4. **`/login/`** — scan the *same kind* of request. Now it succeeds. The only
   thing that changed is that the wallet holds a credential the university
   signed.
5. **Profile** — the four attributes came from the presentation, not a database.
   The panel below names the issuer DID they were checked against.
6. **Dashboard** — no re-authentication.
7. **Logout**, then click Dashboard to show it bounces to Login.

Worth filming too: **`scripts/test_security.py`**. Showing an impostor
credential being *rejected* is more convincing than showing the happy path
twice.

### Before you record

- Run both test scripts — if they pass, the backend is good
- Check the agent's printed IP still matches
- Empty the phone wallet so the login screen does not offer a choice
- Do **not** run `test_security.py` mid-recording — it temporarily empties the
  wallet

---

## Testing

```powershell
.\.venv\Scripts\python.exe scripts\demo_end_to_end.py   # 5 steps, happy path
.\.venv\Scripts\python.exe scripts\test_security.py     # 19 attack tests
```

`demo_end_to_end.py` drives the whole journey with the software holder standing
in for the phone. `test_security.py` attacks the login: anonymous access, forged
exchange ids, unanswered proofs replayed, a credential from another cred-def,
forged webhooks, cross-browser session theft, and replay after logout.

> `test_security.py` temporarily empties the holder wallet and restores a
> credential afterwards. Do not run it mid-demo.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Phone cannot load the portal | different WiFi, wrong IP, or firewall | open `http://<ip>:8000` in the phone browser first |
| QR scans then nothing happens | reached :8000 but not :8020 | check `http://<ip>:8020` responds |
| Wallet stuck on loading | cannot reach the mediator | check terminal 2 and ports 8040/8042 |
| Wallet will not recognise the QR | no URL-shortening support | click **switch** for the full QR |
| "Agent unreachable" on `/` | terminal 1 died | restart `run_agent.py` |
| Login says not verified | credential predates the current schema | re-issue it |
| `/issue/` redirects to login | working as intended — faculty only | log in as faculty, or `reset_demo` |
| Everything breaks after moving networks | IP changed | restart the agent; `auto` re-detects |

## Resetting

| Goal | Command |
|---|---|
| Clear credentials, logins, chats | `python portal/manage.py reset_demo` |
| Wipe the phone wallet | `python scripts/reset_phone_wallet.py` |
| Wipe the agent wallet | stop agent, delete `agent/wallet/`, restart |
| Start completely fresh | delete `portal/db.sqlite3`, `migrate`, `ssi_setup` |

`reset_demo` keeps the ledger artifacts — they live on BCovrin and republishing
would only create duplicates.

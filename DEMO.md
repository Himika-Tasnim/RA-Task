# Testing and Demonstrating the Portal

Two ways to show this works:

- **Part 1 — automated**, no phone needed. Proves the SSI flow *and* that it
  rejects invalid credentials. Run this first; it isolates backend problems
  from wallet problems.
- **Part 2 — live demo** with the phone wallet. This is what the screen
  recording should show.

---

## Start everything

Four terminals, all from the project root. Start them in this order.

```powershell
# 1. Issuer + verifier agent
.\.venv\Scripts\python.exe agent\run_agent.py

# 2. DIDComm mediator (the phone needs this to receive messages)
.\.venv\Scripts\python.exe agent\run_mediator.py

# 3. The portal
cd portal
..\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

```powershell
# 4. Software holder -- ONLY for the automated tests, not the live demo
.\.venv\Scripts\python.exe agent\run_holder.py
```

Open <http://127.0.0.1:8000>. Both status rows must be green before continuing.

Note the LAN address the agent prints. **Check it every session** — DHCP changes
it, and a stale address fails silently.

---

## Part 1 — Automated verification

### The happy path

```powershell
.\.venv\Scripts\python.exe scripts\demo_end_to_end.py
```

Drives the entire journey with the software holder standing in for the phone:

```
1. Registrar issues a Student ID credential          [OK]
2. Wallet scans the QR and accepts the credential    [OK]
     cred_def: WazjcnK7xmg2BwiGzStH1S:3:CL:3225245:university-portal
     student_name = Ayesha Rahman
     student_id   = STU-2024-0142
3. Student logs in by presenting the credential      [OK]  presentation VERIFIED
4. Dashboard / Profile / Dashboard again             [OK]  no re-authentication
5. Logout                                            [OK]  dashboard redirects to login
ALL STEPS PASSED
```

### That it rejects *invalid* credentials

The happy path alone doesn't prove the login is authentication — a portal that
let anyone in would also pass it. This attacks it:

```powershell
.\.venv\Scripts\python.exe scripts\test_security.py
```

```
1. Protected pages with no session          -> all redirect to login
2. Forged presentation-exchange id          -> no session created
3. Real proof request, never answered       -> refused (state=pending)
4. Credential from a DIFFERENT cred-def     -> login REJECTED
5. Logout                                   -> session destroyed
12 passed, 0 failed
```

**Test 4 is the one that matters.** It publishes a second credential definition
(`not-the-university`), removes the genuine credentials from the wallet, issues
the impostor one, and attempts a real login. It fails, because
[`create_proof_request`](portal/ssi/acapy.py) restricts every attribute to the
portal's own `cred_def_id` — a credential the university never signed cannot
satisfy it, even with identical attribute names and values.

> ⚠️ This test temporarily empties the holder's wallet and re-issues a genuine
> credential at the end. Don't run it in the middle of a recording.

---

## Part 2 — Live demo with the phone

### Before recording

- Phone on **the same WiFi** as this machine
- Confirm the agent's printed IP matches `ipconfig`
- Open `http://<that-ip>:8000` in the **phone's browser** first. If the portal
  doesn't load, the wallet won't connect either — fix that before recording
- Delete old credentials from Bifold so the login screen doesn't offer a choice
  mid-take
- Have `/` open on the PC, ready to start

### The sequence

**1. Show the system is real** — open `/`. The status rows show the agent
running and the credential definition published, with the issuer DID and schema
id from the BCovrin ledger on screen. Worth pausing on: these are real ledger
objects, not local config.

**2. Issue the credential** — `/issue/`, fill in the student's details, click
**Generate invitation QR**.

Scan with Bifold → accept the connection with *Demo University* → a credential
offer arrives on its own → **Accept**.

The page advances by itself:
`waiting for scan → wallet connected → credential offered → credential issued`

Nobody clicked anything between the scan and the offer — the agent's
`connections` webhook triggers the offer automatically.

**3. Log in with it** — `/login/`. Scan the QR, review what the portal is
asking for, tap **Share**.

The page flips to *verified — signing you in…* and lands on the Dashboard. No
password was ever typed, and the portal had no stored account for this student.

**4. Show the session works** — click **Profile**. Point out the four
attributes: the portal never stored them, they arrived inside the verified
presentation. The panel below names the issuer DID and credential definition the
proof was checked against.

Click back to **Dashboard**. No credential is presented again — that's the
session doing its job, which is the "two protected pages without
re-authenticating" requirement.

**5. Log out** — then click Dashboard and show it bounces straight back to
Login.

### Showing roles

Issue **two** credentials to the same wallet — one as Student, one as Faculty.
They appear as visibly different cards, because each role has its own schema
(`university_student_id` / `university_faculty_id`) and wallets name a card
after its schema.

Then log in with each in turn. The same login QR produces a different portal:

| | Student | Faculty |
|---|---|---|
| Dashboard | enrolled courses, notices | courses taught, grading queue, staff tools |
| Profile | Student ID, programme, year, credits | Employee ID, position, office, supervision |

Nothing switches server-side. `role` is an attribute inside the credential,
signed by the university and disclosed in the presentation.

### Bonus: faculty ↔ student messaging

`/messages/` is a directory, not a QR generator. Logged in as faculty you see
the students the university has issued to; as a student you see the faculty.

1. Pick a person → **Show QR**
2. They scan it with their wallet — that forms a direct DIDComm connection
   between the two of you, unrelated to credential issuance
3. Type a message; it goes to that person only

Both sides poll, so a reply appears without refreshing.

### Also worth filming

**Run `test_security.py` on camera.** Showing a credential from another issuer
being *rejected* is more convincing than showing the happy path twice.

---

## If something goes wrong mid-demo

| Symptom | Cause | Fix |
|---|---|---|
| QR scans, then nothing happens | wallet reached :8000 but not :8020 | check `http://<ip>:8020` from the phone's browser |
| Wallet won't recognise the QR | it doesn't do out-of-band URL shortening | click **switch** under the QR for the full-invitation code |
| "Agent unreachable" on `/` | terminal 1 died | restart `agent\run_agent.py` |
| Wallet stuck on a loading screen | can't reach the mediator | check terminal 2, and that ports 8040/8042 are open |
| Everything times out after a network change | your IP moved | restart the agent; `AGENT_HOST_IP=auto` re-detects it |

Full troubleshooting: [USER_MANUAL.md](USER_MANUAL.md#troubleshooting).

---

## What each piece proves

| Requirement | Shown by |
|---|---|
| Issue a Student ID VC | `/issue/` — real AnonCreds credential on BCovrin |
| Student holds it in a wallet | Bifold on the phone |
| Login by scanning a QR proof-request | `/login/` |
| Backend verifies, then creates a session | ACA-Py `verified: true` → [`login_complete`](portal/ssi/views.py) |
| Two protected pages, no re-auth | Dashboard ↔ Profile |
| Working logout | `/logout/` |
| **Only valid credentials work** | `scripts/test_security.py` test 4 |
| Bonus: 1-to-1 DIDComm messaging | `/messages/` |

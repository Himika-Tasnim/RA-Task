# Understanding SSI — a beginner's guide to this project

You do not need any background to read this. It starts from "what problem does
this even solve" and builds up to exactly how *your* portal works, using the
real values from your running system.

Read it top to bottom once. By the end you will know what a DID is, what a
credential is, where every piece of data is stored, and what actually happens
when someone logs in.

---

# Part 1 — The big idea

## The problem with normal login

When you sign up for a website today, this happens:

1. You type a username and password.
2. The website stores them in *its* database.
3. Every website does this separately, so your data is scattered across
   hundreds of databases you do not control.
4. When one of them gets hacked, your data leaks.

The website is in charge of your identity. You are just borrowing it.

## The SSI idea

**SSI = Self-Sovereign Identity.** "Self-sovereign" means *you* are in charge of
your identity, not the website.

The real-world analogy is a **physical ID card in your wallet**:

- Your university prints a student ID card and hands it to you.
- You keep it in your wallet. The university does not keep a copy of the physical
  card — they just keep a record that they issued you one.
- When a librarian needs to check you are a student, you *show* them the card.
  They look at it, trust the university's stamp on it, and let you in.
- The librarian does not phone the university. They do not store your card. They
  just verified it and moved on.

SSI is that exact model, done with cryptography instead of plastic:

| Physical world | SSI world |
|---|---|
| Plastic ID card | **Verifiable Credential** (a signed digital document) |
| Your leather wallet | **Digital wallet** (an app on your phone) |
| The university's official stamp | A **cryptographic signature** |
| Librarian glancing at the card | **Proof verification** |
| University's seal registered somewhere everyone trusts | The **ledger** |

The whole point: **you hold your own credential, and you decide when to show it.**

## The three roles

Every SSI interaction has three roles. One organisation can play more than one.

```
   ISSUER  ──── gives you a credential ────►  HOLDER  ──── shows a proof ────►  VERIFIER
 (university)                              (you, on your phone)            (the portal)
```

- **Issuer** — creates and signs a credential. *"I certify this person is a
  student."*
- **Holder** — receives the credential, stores it, and later presents it.
  *That's you.*
- **Verifier** — asks for a proof and checks it. *"Prove you have a valid
  student credential."*

> In **this project**, the university portal is both the **issuer** (it issues
> Student/Faculty IDs) and the **verifier** (it checks them at login). Your phone
> is the **holder**. That is normal — a university both issues your ID and checks
> it at the library door.

---

# Part 2 — The building blocks

Five concepts. Each builds on the last.

## 2.1 DID — a Decentralized Identifier

A **DID** is a name for someone that nobody can take away, because *nobody issued
it* — it is derived from cryptography, not assigned by a company.

An email address (`you@gmail.com`) is issued by Google. Google can delete it. A
DID is different: it is generated from a **key pair** you create yourself.

**A key pair is two matching keys:**
- a **private key** — a secret only you know (like a password you never share)
- a **public key** — derived from the private one, safe to show anyone

The magic: anything signed with the private key can be *checked* with the public
key, but you cannot work backwards from the public key to the private one. So a
signature proves "the person holding the private key made this" without ever
revealing the private key.

A DID is basically a public identifier that points at a public key.

> **In your project**, the university's DID is:
> ```
> WazjcnK7xmg2BwiGzStH1S
> ```
> Its matching public key (called a "verkey") is:
> ```
> H8GzuRbD4VpwSCxPoURjFVkEQhYdw6fhLjy4vphvrYdC
> ```
> The private key that goes with it is **never shown anywhere** — it lives
> locked inside the agent's wallet on your PC. That secret is what lets the
> university sign credentials that everyone else can verify.

## 2.2 Schema — the shape of a credential

A **schema** is a template. It says *what fields a credential has*, but contains
no actual data. Like a blank form.

> **In your project** there are two schemas — one per role:
> ```
> university_student_id   -- fields: full_name, id_number, department, email, role
> university_faculty_id   -- same fields
> ```
> A schema is just that list of field names. It holds nobody's data.

## 2.3 Credential Definition — the issuer's specific stamp

A **credential definition** (cred-def) links a schema to *a specific issuer's
signing keys*. It says: "when the University of X issues a credential using this
schema, here are the exact public keys to check its signature against."

Think of the schema as "the design of a £20 note" and the cred-def as "the
Bank of England's specific anti-forgery features on the notes *it* prints." Two
different banks could use the same design but have different security features.

> **In your project**:
> ```
> Student cred-def:  WazjcnK7xmg2BwiGzStH1S:3:CL:3225339:university-portal
> Faculty cred-def:  WazjcnK7xmg2BwiGzStH1S:3:CL:3225341:university-portal
> ```
> Notice they both start with `WazjcnK7xmg2BwiGzStH1S` — the university's DID.
> That is how anyone verifying a credential knows *the university* signed it.

## 2.4 Verifiable Credential — the actual signed document

Now put it together. A **Verifiable Credential (VC)** is:

- the actual data (full_name = "Ayesha Rahman", role = "student", …)
- **plus a cryptographic signature** made with the issuer's private key
- referencing the schema and cred-def, so a verifier knows how to check it

The signature is what makes it "verifiable." Anyone can check it is genuine and
unaltered, using only public information — they never contact the university.

> **In your project**, a real student credential in the holder's wallet looks
> like this:
> ```
> schema   : WazjcnK7xmg2BwiGzStH1S:2:university_student_id:1.0
> cred_def : WazjcnK7xmg2BwiGzStH1S:3:CL:3225339:university-portal
> attrs    : full_name  = Ayesha Rahman
>            id_number  = STU-2024-0142
>            department = Computer Science
>            email      = ayesha@demo-university.edu
>            role       = student
> ```
> That whole thing, signed by the university, sits in the wallet on the phone.
> **The university does not keep a copy.**

## 2.5 Verifiable Presentation — showing the credential

You rarely hand over the whole credential. Instead you create a **Verifiable
Presentation**: a one-time, signed answer to a specific request.

When the portal says *"prove you have a valid student or faculty credential,"*
the wallet builds a presentation that:

- proves the credential is genuine (signature checks out),
- proves *you* are the holder (it is signed with your holder key too),
- and is tied to *this one login request* so it cannot be reused.

A powerful feature (called **selective disclosure** / zero-knowledge proofs):
the wallet can prove things *without revealing everything*. It could prove "I am
over 18" without revealing your birth date. This project discloses all five
attributes, but the machinery underneath supports hiding them.

---

# Part 3 — Where is everything stored?

This is the question that confuses everyone, so here it is very explicitly.

There are **three separate storage places**, and keeping them straight is the
key to understanding SSI.

```
┌─────────────────────────────┐   ┌──────────────────────────┐   ┌────────────────────────┐
│  1. THE LEDGER               │   │  2. THE WALLETS           │   │  3. THE PORTAL DB       │
│     (public, shared)         │   │     (private, per-owner)  │   │     (this app only)     │
│                              │   │                           │   │                        │
│  • DIDs                      │   │  • private keys (secret!) │   │  • who was issued what │
│  • schemas                   │   │  • the signed credentials │   │  • login attempts      │
│  • credential definitions    │   │  • connections            │   │  • chat messages       │
│                              │   │                           │   │  • published id lookup │
│  NO personal data.           │   │  The actual identity.     │   │  App bookkeeping only. │
│  NO credentials.             │   │  Never leaves the device. │   │  NOT the credential.   │
└─────────────────────────────┘   └──────────────────────────┘   └────────────────────────┘
```

## 3.1 The Ledger — the public noticeboard

A **ledger** is a shared, append-only, public database that everyone trusts and
nobody controls alone. (A blockchain is one kind of ledger.) It is the
"registered somewhere everyone trusts" from the wallet analogy.

**Critically, it stores NO personal data and NO credentials.** It only stores
the *public reference information* a verifier needs:

- **DIDs** and their public keys — so you can check a signature
- **schemas** — the field templates
- **credential definitions** — the issuer's signing-key fingerprints

When the portal verifies your login, it reads the cred-def *from the ledger* to
check the signature. It never needs to phone the university.

> **In your project** the ledger is the **BCovrin test network** — a free, public
> Indy ledger hosted on the internet at `test.bcovrin.vonx.io`. You did not
> install it; you just wrote to it. The things your project put on it:
> ```
> DID       WazjcnK7xmg2BwiGzStH1S              (+ its public key)
> schema    university_student_id 1.0
> schema    university_faculty_id 1.0
> cred-def  ...:CL:3225339:university-portal    (student)
> cred-def  ...:CL:3225341:university-portal    (faculty)
> ```
> Anyone in the world can read these. None of them contains "Ayesha Rahman" or
> any student's data — just the public plumbing.

> **Why a "test" ledger?** Real identity ledgers cost money to write to and are
> meant for production identities. BCovrin test is a free sandbox that behaves
> the same way, perfect for a demo. Nothing on it is trusted for real use.

## 3.2 The Wallets — the private vaults

A **wallet** is where the *secrets and the actual credentials* live. Each party
has its own, and **a wallet never sends its private keys anywhere.**

There is no single "wallet" — there is one per participant:

> **In your project** the wallets are SQLite files created by the Askar library
> on your PC:
> ```
> ~/.aries_cloudagent/wallet/university_portal/sqlite.db   <- issuer/verifier (the portal's agent)
> ~/.aries_cloudagent/wallet/student_wallet/sqlite.db      <- the test holder ("phone stand-in")
> ~/.aries_cloudagent/wallet/portal_mediator/sqlite.db     <- the mediator
> ```
> On the real demo, the **holder wallet is Bifold on the phone**, not the
> `student_wallet` file — that file is only the software stand-in used for
> automated testing.

Each wallet holds:
- the owner's **private keys** (never leave the device)
- for a holder: the **signed credentials** they have received
- **connections** to other parties

> The university's *private* signing key is in `university_portal/sqlite.db`.
> That single secret is the whole basis of trust: whoever holds it can issue
> credentials as the university. That is why the audit moved the admin API to
> loopback-only — so nothing on the network can reach in and use it.

## 3.3 The Portal Database — the app's own notebook

This is an ordinary Django SQLite database. It is **not** part of SSI at all —
it is just this particular web app keeping notes for itself.

> **In your project**:
> ```
> e:\RA Project\portal\db.sqlite3
> ```
> It stores app bookkeeping:
>
> | Table | What it keeps | Is this the credential? |
> |---|---|---|
> | `ssi_issuancerequest` | "we issued a student ID to Ayesha" — for the registrar screen | No — a *record that we issued one* |
> | `ssi_ledgerartifacts` | the ids of what we published, so we don't re-derive them | No — just pointers to the ledger |
> | `ssi_loginsession` | each login attempt and whether it verified | No |
> | `ssi_chatinvitation` | messaging connections | No |
> | `ssi_basicmessage` | the chat text | No |

The subtle but important point: when Ayesha logs in, the portal learns her
details **from the presentation she sends**, not from this database. The portal
never stored her name to check against. That is the whole difference from
password login — **there is no user table to steal.**

---

# Part 4 — The technologies, named

Now the actual software, and which job each does.

| Name | What it is | Its job here |
|---|---|---|
| **ACA-Py** | "Aries Cloud Agent — Python." An SSI *agent* — software that does all the crypto: making DIDs, signing credentials, verifying proofs, talking to the ledger. | The engine. The portal never does crypto itself; it asks ACA-Py. |
| **Aries** | A set of open standards for how SSI agents talk to each other. | The rulebook ACA-Py follows. |
| **Indy** | The ledger technology (BCovrin is an Indy network) and the credential format (AnonCreds). | Where DIDs/schemas/cred-defs live, and the maths behind the signatures. |
| **AnonCreds** | "Anonymous Credentials" — the specific credential format with selective disclosure. | The shape of the signed credentials. |
| **DIDComm** | A secure, encrypted messaging protocol between agents. | How the phone and the portal actually exchange messages. |
| **Askar** | A secure storage library. | Creates the wallet `sqlite.db` files and encrypts the keys inside. |
| **Bifold** | An open-source mobile wallet app (React Native). | The holder — the app on the phone. |
| **Django** | A Python web framework. | The website: pages, sessions, the portal database. |
| **Mediator** | A relay agent with a public-ish address. | A phone has no fixed address, so the mediator holds DIDComm messages for it. |
| **QR code** | Just a picture of a URL. | How the phone receives an "invitation" without typing anything. |

The one-line mental model:

> **Django** shows the web pages. **ACA-Py** does all the identity crypto.
> **Bifold** on the phone holds the credential. They talk over **DIDComm**. The
> public references live on the **Indy/BCovrin ledger**. The secrets live in
> **Askar** wallet files.

---

# Part 5 — How YOUR project actually runs

Now we connect all of it to the four programs you start.

## 5.1 The four programs

When you run the project, four separate programs are running:

```
  ┌──────────────────────────┐        ┌──────────────────────────┐
  │  agent  (run_agent.py)    │        │  portal (Django)         │
  │  ACA-Py, ports 8020/8021  │◄──────►│  the website, port 8000  │
  │  ISSUER + VERIFIER        │  asks  │  what you see in browser │
  │  wallet: university_portal│        │  db: portal/db.sqlite3   │
  └────────────┬─────────────┘        └──────────────────────────┘
               │ DIDComm
               ▼
  ┌──────────────────────────┐        ┌──────────────────────────┐
  │  mediator (run_mediator)  │        │  holder (run_holder.py)  │
  │  ACA-Py, ports 8040/8042  │        │  ACA-Py, ports 8030/8031 │
  │  relays msgs to the phone │        │  TEST-ONLY phone stand-in │
  └──────────────────────────┘        └──────────────────────────┘
```

- **agent** — the university's ACA-Py. Issues and verifies. This is the issuer +
  verifier. Its wallet holds the university's private signing key.
- **portal** — the Django website. Everything you click. Talks to the agent over
  its admin API (port 8021) to ask for SSI operations.
- **mediator** — a helper so the phone can receive messages (explained below).
- **holder** — a *second* ACA-Py pretending to be a phone, used only by the
  automated tests. In a real demo the phone (Bifold) is the holder and this is
  not needed.

## 5.2 Why the mediator exists

A website has a fixed address. A phone does not — its address changes, and it is
usually behind other networks. So the university's agent cannot just "send a
message to the phone."

The **mediator** solves this. It is an agent at a reachable address that:
1. the phone connects *out* to (outgoing connections always work),
2. holds any incoming messages for the phone,
3. forwards them when the phone checks in.

Like a PO box: mail can't reach your moving location, so it goes to a fixed box
and you collect it. Your Bifold wallet is configured to use *your* mediator.

## 5.3 What happens when a credential is issued

Follow the data. Say a faculty member issues Ayesha a Student ID.

1. **Faculty fills the form** at `/issue/` (Django page) and clicks generate.
2. **Portal asks the agent** (over admin API 8021): "make an invitation."
3. **Agent returns an invitation**; portal draws it as a **QR code**.
4. **Ayesha scans it** with Bifold. Her phone and the agent now have a **DIDComm
   connection** (encrypted channel).
5. **Agent sends a credential offer** down that channel. Bifold shows "Demo
   University wants to give you a Student ID — Accept?"
6. **Ayesha taps Accept.** Now the agent:
   - takes the field values,
   - **signs them with the university's private key** (the secret in
     `university_portal/sqlite.db`),
   - references the student cred-def,
   - sends the finished signed credential to the phone.
7. **Bifold stores the credential** in the phone's wallet. It is now hers.

Where did data land?
- **Phone wallet:** the signed credential (the real thing).
- **Portal DB:** a row in `ssi_issuancerequest` saying "issued a student ID to
  Ayesha" — bookkeeping, not the credential.
- **Ledger:** *nothing new.* The schema and cred-def were already there; issuing
  to an individual writes nothing public. (This is good for privacy — the ledger
  never learns who holds credentials.)

## 5.4 What happens when someone logs in

This is the heart of the project. Ayesha logs in.

1. **Ayesha opens `/login/`.** The portal asks the agent for a **proof request**:
   *"prove you hold a credential from DID `WazjcnK7xmg2BwiGzStH1S`, and disclose
   full_name, id_number, department, email, role."* The portal shows it as a QR.
2. **Ayesha scans it** with Bifold. The wallet sees what is being asked and which
   of her credentials can answer.
3. **Ayesha taps Share.** Her wallet builds a **Verifiable Presentation**:
   - it proves her Student ID credential is genuine (signature valid),
   - it proves she is the holder,
   - it is bound to *this* request so it can't be replayed.
4. **The agent verifies the presentation.** To do this it reads the **cred-def
   from the ledger** and checks the maths. No contact with anyone.
5. **The agent tells the portal "verified: true,"** plus the disclosed values.
6. **The portal double-checks** the credential came from one of its own cred-defs
   (the `from_allowed_cred_def` step), then **creates a login session** — a
   normal browser cookie.
7. **Ayesha is in.** Dashboard and Profile now load from that session cookie, no
   scanning needed, until she logs out.

Where did data land?
- **Portal DB:** a `ssi_loginsession` row (verified = true), and a browser
  session. The disclosed attributes are put in the session so the pages can show
  them — but they came *from Ayesha's presentation*, they were never stored
  before she logged in.
- **Nothing** was written to the ledger or to any wallet.

The thing to sit with: **the portal had no account for Ayesha before she logged
in, and cannot log anyone in who does not physically hold a university-signed
credential on their device.** That is what makes it authentication and not a
form.

## 5.5 Why this is more secure than passwords

| Password login | This SSI login |
|---|---|
| Website stores your secret | Website stores no secret about you |
| One database breach leaks everyone | No user table to breach |
| You prove identity by *revealing* a secret | You prove it *without revealing* the secret key |
| Same password reused everywhere = one leak breaks all | Each credential is cryptographically unique |
| Website decides your identity | The university signs it; you hold it; you present it |

---

# Part 6 — A glossary you can skim

| Term | Plain meaning |
|---|---|
| **SSI** | You control your own digital identity, not a company |
| **DID** | A self-owned identifier backed by a key pair |
| **Key pair** | A secret private key + a shareable public key that match |
| **Verkey** | The public key attached to a DID |
| **Schema** | The list of fields a credential has (a blank template) |
| **Credential definition (cred-def)** | A schema tied to one issuer's signing keys |
| **Verifiable Credential (VC)** | Signed data you hold — a digital ID card |
| **Verifiable Presentation** | A one-time signed answer proving you hold a VC |
| **Holder / Issuer / Verifier** | Who holds / who signs / who checks |
| **Ledger** | Public shared noticeboard for DIDs, schemas, cred-defs — no personal data |
| **Wallet** | Private encrypted store for keys and credentials |
| **ACA-Py** | The agent software that does all the crypto |
| **AnonCreds** | The credential format (supports hiding fields) |
| **DIDComm** | Encrypted messaging between agents |
| **Askar** | The library that stores wallets on disk |
| **Bifold** | The phone wallet app (the holder) |
| **Mediator** | Relay so a phone can receive messages |
| **BCovrin** | The free public test ledger this project uses |

---

# Part 7 — See it with your own eyes

With the project running, prove each storage claim to yourself.

**The ledger holds only public references (open in a browser):**
```
http://test.bcovrin.vonx.io/browse/domain?page=1&query=WazjcnK7xmg2BwiGzStH1S
```
You will see DIDs, schemas and cred-defs — and no student names.

**The wallet holds the real credential (with the agents running):**
```powershell
# The test holder's actual stored credentials, attributes and all:
curl.exe -s -H "X-API-KEY: demo-admin-api-key" http://127.0.0.1:8031/credentials
```

**The portal DB holds only bookkeeping:**
```powershell
cd portal
..\.venv\Scripts\python.exe manage.py shell -c "from ssi.models import IssuanceRequest; [print(r.role, r.full_name, r.state) for r in IssuanceRequest.objects.all()]"
```

**The university's private key is nowhere you can read it** — Askar keeps it
encrypted inside `~/.aries_cloudagent/wallet/university_portal/sqlite.db`, and
even the admin API will not hand it out. That secrecy is the entire foundation
the trust rests on.

---

Once this all makes sense, [HOW_IT_WORKS.md](HOW_IT_WORKS.md) covers the same
system from the engineering side — the security design, the API calls, and how
to demo it — and [SETUP_GUIDE.md](SETUP_GUIDE.md) is how it was built.

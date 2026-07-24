# SSI University Portal

A university portal where students and faculty log in by **presenting a
verifiable credential from a phone wallet** — no passwords, and no user table.

Built with **ACA-Py** for every SSI operation and **Django** for the portal.
Runs natively on Windows: no Docker, no WSL.

---

## Documentation

| | |
|---|---|
| **[LEARN_SSI.md](LEARN_SSI.md)** | New to SSI? Start here. What DIDs, credentials and ledgers are, where every piece of data is stored, and how this project runs — assumes zero background |
| **[SETUP_GUIDE.md](SETUP_GUIDE.md)** | Build it from nothing, step by step, with every trap called out |
| **[HOW_IT_WORKS.md](HOW_IT_WORKS.md)** | The system from the engineering side: security design, and how to use and demo it |

---

## What it does

- Issues **Student ID** and **Faculty ID** verifiable credentials to a mobile wallet
- Logs people in by scanning a QR proof-request and presenting the credential
- Serves role-specific **Dashboard** and **Profile** pages off one session
- **Bonus:** 1-to-1 encrypted messaging between a faculty member and a student
  over a direct DIDComm connection

The `role` lives *inside* the credential, signed by the university — so
presenting the other credential from the same wallet changes the whole portal,
with no server-side account switch.

## Quick start

Full instructions in [SETUP_GUIDE.md](SETUP_GUIDE.md). Once set up:

```powershell
.\.venv\Scripts\python.exe agent\run_agent.py                             # issuer + verifier
.\.venv\Scripts\python.exe agent\run_mediator.py                          # so the phone can receive
cd portal; ..\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000   # the portal
```

Then open <http://127.0.0.1:8000>.

## Verifying

```powershell
.\.venv\Scripts\python.exe agent\run_holder.py            # software wallet, testing only
.\.venv\Scripts\python.exe scripts\demo_end_to_end.py     # the happy path
.\.venv\Scripts\python.exe scripts\test_security.py       # 19 attack tests
```

The security suite covers, among others, two real vulnerabilities found and
fixed during development: an **authentication bypass** through an
unauthenticated webhook endpoint, and **unauthenticated credential issuance**
that let anyone mint themselves a faculty credential. Both are described in
[HOW_IT_WORKS.md](HOW_IT_WORKS.md#security).

## Layout

```
agent/     ACA-Py launchers: issuer/verifier, mediator, test holder, DID registration
portal/    Django project -- the ssi app holds all portal logic
scripts/   End-to-end and security tests, plus wallet helpers
lanip.py   Shared LAN-address detection, so agent and portal agree on the host
```

## References

- [ACA-Py](https://github.com/openwallet-foundation/acapy) · [docs](https://aca-py.org/latest/)
- [Aries Bifold](https://github.com/openwallet-foundation/bifold-wallet)

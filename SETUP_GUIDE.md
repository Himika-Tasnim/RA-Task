# Setup Guide — building this from nothing

Every step that worked, in order, with the traps called out. Follow it top to
bottom and you should not hit the dead ends I did.

Written for **Windows**, because that is the awkward case — no Docker and no WSL
were available. On macOS/Linux everything is simpler; the differences are noted
inline.

**Time:** roughly 45 minutes for the portal, plus 1–2 hours if you also build
the mobile wallet.

---

## What you are building

| Piece | What it is |
|---|---|
| **ACA-Py agent** | Issues credentials and verifies proofs. Ports 8020 (DIDComm) / 8021 (admin) |
| **ACA-Py mediator** | Lets the phone receive DIDComm. Ports 8040 / 8042 |
| **Django portal** | The website. Port 8000 |
| **Bifold wallet** | The phone app that holds credentials |
| **BCovrin test ledger** | Public Indy ledger. Hosted — nothing to run |

---

## Part 1 — Prerequisites

```powershell
python --version    # 3.9 - 3.12
git --version
```

**Python version matters.** This project pins `aries-cloudagent==0.12.8`, the
last ACA-Py release supporting Python 3.9. The 1.x rename (`acapy-agent`)
requires 3.12+. On 3.13 neither is reliable — use 3.12 or below.

You do **not** need Docker, WSL, or a local ledger.

---

## Part 2 — The portal

### 2.1 Virtualenv and dependencies

```powershell
cd "E:\RA Project"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

macOS/Linux: `.venv/bin/python` everywhere instead of `.venv\Scripts\python.exe`.

**Verify the native libraries load** — this is the step most likely to fail on
an unusual platform, and it fails loudly here rather than confusingly later:

```powershell
.\.venv\Scripts\python.exe -c "import aries_askar, indy_vdr, anoncreds; print('native libs OK')"
.\.venv\Scripts\aca-py.exe --version
```

Expect `native libs OK` and `0.12.8`.

> If the imports fail there is no prebuilt wheel for your Python/platform.
> Either switch Python version, or run ACA-Py in Docker and point
> `ACAPY_ADMIN_URL` at it — the portal only talks to the agent over HTTP.

### 2.2 Configuration

```powershell
Copy-Item .env.example .env
```

The defaults work as-is locally. One setting matters:

```ini
AGENT_HOST_IP=auto
```

This is the address your **phone** uses to reach the PC. `auto` detects it at
startup. Leave it on `auto` — a hard-coded address breaks the moment DHCP moves
you, and it fails *silently*: the agent starts, the QR renders, the wallet just
times out.

Before anything beyond a local demo, change `WALLET_KEY`,
`ACAPY_ADMIN_API_KEY`, `WEBHOOK_API_KEY` and `DJANGO_SECRET_KEY`. The portal
refuses to start with `DEBUG=0` while any of them still hold demo values.

### 2.3 Register the issuer DID on the ledger

```powershell
.\.venv\Scripts\python.exe agent\register_did.py
```

Writes a DID for your `AGENT_SEED` to the BCovrin test ledger with an ENDORSER
role — that role is what later permits publishing a schema and cred-def. The
DID derives from the seed, so re-running is harmless. Keep `AGENT_SEED` stable.

### 2.4 Database

```powershell
cd portal
..\.venv\Scripts\python.exe manage.py migrate
cd ..
```

### 2.5 Start the agent

Own terminal, leave running:

```powershell
.\.venv\Scripts\python.exe agent\run_agent.py
```

It prints the address the phone must reach:

```
  DIDComm endpoint : http://192.168.0.121:8020   <- your phone must reach this
  Admin API        : http://127.0.0.1:8021
```

> **Windows trap.** ACA-Py's `run_loop()` registers a SIGTERM handler, which
> asyncio only implements on Unix — on Windows `aca-py start` dies immediately
> with `NotImplementedError`. `agent/run_agent.py` makes that registration a
> no-op. Nothing is lost: SIGTERM is not a Windows signal, and Ctrl-C still
> shuts down cleanly. This is why you launch via `run_agent.py`, not `aca-py`.

### 2.6 Start the mediator

Second terminal, leave running:

```powershell
.\.venv\Scripts\python.exe agent\run_mediator.py
.\.venv\Scripts\python.exe agent\mediator_invitation.py --write-env
```

> **Why your own mediator.** A phone has no public address, so it needs a
> mediator to receive DIDComm. Bifold's README points at Indicio's public one,
> but its WebSocket host `ws.us-east.public.mediator.indiciotech.io` **no longer
> resolves** — verified against three independent DNS resolvers. Credo prefers
> that transport, fails, and reports the opaque *"error 1045 … module
> 'didcomm'"*. Running your own also removes the internet from the demo path
> entirely.

### 2.7 Publish schema and credential definitions

Agent must be running:

```powershell
cd portal
..\.venv\Scripts\python.exe manage.py ssi_setup
cd ..
```

Publishes **two** schemas — one per role — and a cred-def for each. Idempotent.

> **Why two schemas.** Wallets name a credential card after its schema. If
> student and faculty share one schema the holder sees two identical cards and
> cannot tell which to present. Separate schemas make them visibly different.

### 2.8 Start the portal

Third terminal:

```powershell
cd portal
..\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

`0.0.0.0` is required — the default binds to localhost only and the phone could
not reach it.

Open <http://127.0.0.1:8000>. Both status rows should be green.

### 2.9 Verify without a phone

Fourth terminal — a software wallet, used only for testing:

```powershell
.\.venv\Scripts\python.exe agent\run_holder.py
```

Then:

```powershell
.\.venv\Scripts\python.exe scripts\demo_end_to_end.py    # the happy path
.\.venv\Scripts\python.exe scripts\test_security.py      # 19 attack tests
```

Both must pass before you involve a phone. If they do, any later failure is
wallet or network related, not backend.

---

## Part 3 — Network access for the phone

### 3.1 Firewall

Windows blocks inbound connections by default. **Administrator** PowerShell:

```powershell
New-NetFirewallRule -DisplayName "SSI Portal"   -Direction Inbound -LocalPort 8000      -Protocol TCP -Action Allow -Profile Public,Private
New-NetFirewallRule -DisplayName "SSI Agent"    -Direction Inbound -LocalPort 8020      -Protocol TCP -Action Allow -Profile Public,Private
New-NetFirewallRule -DisplayName "SSI Mediator" -Direction Inbound -LocalPort 8040,8042 -Protocol TCP -Action Allow -Profile Public,Private
```

In **Command Prompt** instead:

```
netsh advfirewall firewall add rule name="SSI Portal" dir=in action=allow protocol=TCP localport=8000,8020,8040,8042
```

All four ports are needed. 8000 serves pages and invitations, 8020 is DIDComm
with the agent, 8040/8042 is the mediator. Opening only 8000 gives you a QR that
scans and then hangs.

### 3.2 Prove reachability before touching the wallet

Phone on the **same WiFi**, then in the phone's *browser*: `http://<the-ip>:8000`

The portal should load. If it does not, no wallet will connect either — fix this
first. `http://<ip>:8020` returning a blank page or "download failed" is
**correct**: it is a DIDComm endpoint, not a website, and the response proves
the port is open.

---

## Part 4 — The mobile wallet (Aries Bifold)

Skip if you only need the automated tests.

> **BC Wallet does not work.** It is Bifold-based and on the app stores, but it
> allowlists BC Government services — scanning our QR gives *"This QR code
> doesn't work with BC Wallet."* Not fixable from our side.

### 4.1 Toolchain

Bifold pins its tools tightly. Mismatches fail confusingly.

| Tool | Required | Note |
|---|---|---|
| Node | **20.19.2** (`>=20.19.2 <21`) | Node 22 is rejected |
| Yarn | **4.9.2** | via `corepack`, not `npm i -g yarn` |
| JDK | **17** | Temurin or Zulu |
| Android SDK | platform **36**, build-tools **36.0.0** | |
| Android NDK | **27.1.12297006** | required — the crypto libs are native |

Android Studio is **not** needed; the command-line tools suffice and are far
smaller. Everything below installs to `E:\` to keep the system drive free.

```powershell
curl.exe -L -o E:\tools\node20.zip   https://nodejs.org/dist/v20.19.2/node-v20.19.2-win-x64.zip
curl.exe -L -o E:\tools\jdk17.zip    "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse"
curl.exe -L -o E:\tools\cmdtools.zip https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip

Expand-Archive E:\tools\node20.zip   -DestinationPath E:\tools\node20
Expand-Archive E:\tools\jdk17.zip    -DestinationPath E:\tools\jdk17
Expand-Archive E:\tools\cmdtools.zip -DestinationPath E:\tools\cmdtools
New-Item -ItemType Directory -Force E:\Android\Sdk\cmdline-tools | Out-Null
Copy-Item -Recurse E:\tools\cmdtools\cmdline-tools E:\Android\Sdk\cmdline-tools\latest
```

Set this in every shell that builds:

```powershell
$env:JAVA_HOME        = "E:\tools\jdk17\jdk-17.0.19+10"
$env:ANDROID_HOME     = "E:\Android\Sdk"
$env:ANDROID_SDK_ROOT = "E:\Android\Sdk"
$env:GRADLE_USER_HOME = "E:\gradle"
$env:PATH = "E:\tools\node20\node-v20.19.2-win-x64;$env:JAVA_HOME\bin;E:\Android\Sdk\platform-tools;$env:PATH"
```

> `GRADLE_USER_HOME` matters. Gradle's cache reaches ~6 GB and defaults to
> `C:\Users\<you>\.gradle`. Mine filled the system drive to 1.4 GB free.

SDK packages:

```powershell
$sdkm = "E:\Android\Sdk\cmdline-tools\latest\bin\sdkmanager.bat"
& $sdkm --sdk_root=E:/Android/Sdk --licenses
& $sdkm --sdk_root=E:/Android/Sdk "platform-tools" "platforms;android-36" "build-tools;36.0.0" "ndk;27.1.12297006"
```

> **Use forward slashes in `--sdk_root`.** With backslashes, Git Bash strips
> them and the path resolves drive-relative — the SDK silently installs into
> your *current directory*. Also keep the SDK out of any path containing a
> space; the NDK build does not handle them.

### 4.2 Clone and install

```powershell
git clone https://github.com/openwallet-foundation/bifold-wallet.git E:\bifold-wallet
cd E:\bifold-wallet
corepack enable
corepack prepare yarn@4.9.2 --activate
yarn install
```

> **`yarn install` will fail** on `askar`, `anoncreds` and `indy-vdr`. Each
> downloads a 70–95 MB tarball of prebuilt native libraries using Node's `fetch`
> with **no retry and no resume**, so one `ECONNRESET` kills the install.
>
> Fetch them with curl instead, then pre-populate:
>
> ```powershell
> mkdir E:\tools\native-cache; cd E:\tools\native-cache
> curl.exe -L --retry 8 --retry-all-errors -C - -o askar.tar.gz     https://github.com/openwallet-foundation/askar/releases/download/v0.5.0/library-ios-android.tar.gz
> curl.exe -L --retry 8 --retry-all-errors -C - -o anoncreds.tar.gz https://github.com/hyperledger/anoncreds-rs/releases/download/v0.2.3/library-ios-android.tar.gz
> curl.exe -L --retry 8 --retry-all-errors -C - -o indyvdr.tar.gz   https://github.com/hyperledger-indy/indy-vdr/releases/download/v0.4.5/library-ios-android.tar.gz
> ```
>
> Then run [scripts/place_native_binaries.py](scripts/place_native_binaries.py)
> from the portal repo. It extracts each into **every** workspace copy yarn
> made (12 of them) and writes the `version.json` that makes the installer skip
> downloading. Re-run `yarn install` — it completes.

Then build the shared packages:

```powershell
yarn run build
```

### 4.3 Point the wallet at your mediator

```powershell
cd "E:\RA Project"
.\.venv\Scripts\python.exe agent\mediator_invitation.py --write-env
```

Writes `MEDIATOR_URL` into `E:\bifold-wallet\samples\app\.env`. The invitation
carries `goal_code: aries.vc.mediate` — Bifold requires that to treat it as a
mediator rather than an ordinary connection.

### 4.4 Two edits Bifold needs

**A. Allow cleartext HTTP.** React Native sets `usesCleartextTraffic="false"`
for release builds, so Android silently drops every plain-`http://` request.
Our agent and mediator are `http://` on the LAN, so mediation times out and you
get *error 1045* again — with the mediator logging **zero** inbound requests.

In `samples/app/android/app/src/main/AndroidManifest.xml`:

```diff
- android:usesCleartextTraffic="${usesCleartextTraffic}"
+ android:usesCleartextTraffic="true"
```

Edit the manifest directly. Setting `manifestPlaceholders` in `build.gradle`
does **not** work — React Native's Gradle plugin configures it later and
overwrites yours.

**B. Fix credential deletion.** `packages/core/src/screens/CredentialDetails.tsx`
calls a module namespace that does not exist, so removing a credential always
fails with error 1032:

```diff
- await agent.modules.credentials.deleteById(credential.id)
+ await agent.modules.didcomm.credentials.deleteById(credential.id)
```

Same bug in `packages/core/src/components/listItems/NotificationListItem.tsx`
(`declineOffer`). The rest of the codebase already uses the `didcomm` namespace.

Rebuild the core after editing: `yarn run build`.

### 4.5 Build and install the APK

```powershell
cd E:\bifold-wallet\samples\app\android
"sdk.dir=E:/Android/Sdk" | Out-File -Encoding ascii local.properties
.\gradlew.bat assembleRelease --no-daemon
```

Output: `app/build/outputs/apk/release/app-release.apk` (~180 MB).

> **Verify before installing.** Gradle happily reports `BUILD SUCCESSFUL`
> without repackaging when it thinks nothing changed — and it does not track
> files in `packages/core`, so a change there is invisible to it. If the APK
> timestamp did not move, delete these and rebuild:
> ```
> app/build/generated/assets/createBundleReleaseJsAndAssets
> app/build/intermediates/assets/release
> app/build/outputs/apk/release
> ```
>
> Also note the release bundle is **Hermes bytecode**, so grepping it for
> `didcomm.credentials.deleteById` will never match — identifiers are stored as
> separate string-table entries. Check the manifest flag with
> `aapt2 dump xmltree --file AndroidManifest.xml <apk>`.

Install:

```powershell
adb devices
adb install -r app-release.apk
```

No cable? Copy the APK into `portal/ssi/static/` and download it on the phone
from `http://<your-ip>:8000/static/<name>.apk`.

---

## Part 5 — First run

1. Open Bifold, choose **English** (it ships en/fr/pt-BR and asks), set a PIN,
   allow camera. It registers with your mediator here — watch that terminal.
2. On the PC open `/issue/`. On a fresh database it is in **bootstrap mode**:
   issuing is open because no faculty exists yet to authorise it.
3. Issue a **Faculty** credential, scan, accept.
4. From then on `/issue/` requires a faculty login.

---

## Resetting

| Goal | Command |
|---|---|
| Clear credentials, logins, chats | `python portal/manage.py reset_demo` |
| Also forget the ledger records | `python portal/manage.py reset_demo --ledger` then `ssi_setup` |
| Wipe the agent wallet | stop the agent, delete `agent/wallet/`, restart |
| Wipe the phone wallet | `python scripts/reset_phone_wallet.py` |
| Start completely fresh | delete `portal/db.sqlite3`, `migrate`, `ssi_setup` |

`reset_phone_wallet.py` falls back to uninstall+reinstall because Realme/ColorOS
(and MIUI) deny adb the `CLEAR_APP_USER_DATA` permission.

---

## Traps, in one place

| Symptom | Cause |
|---|---|
| `aca-py start` dies with `NotImplementedError` | Windows has no SIGTERM — use `run_agent.py` |
| Wallet scans, then nothing | port 8020 or 8040 closed in the firewall |
| Wallet stuck loading, error 1045 | mediator unreachable, or cleartext HTTP blocked |
| Everything times out after moving networks | IP changed — `AGENT_HOST_IP=auto` re-detects on restart |
| `yarn install` fails on askar/anoncreds/indy-vdr | ECONNRESET; pre-populate with curl |
| Gradle "BUILD SUCCESSFUL" but nothing changed | stale bundle cache; delete the outputs above |
| SDK installed into the wrong folder | backslashes in `--sdk_root` |
| Login fails after re-publishing schemas | old credentials lack the new attributes — re-issue |

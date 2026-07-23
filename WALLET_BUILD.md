# Building the Aries Bifold Wallet

The task specifies **Aries Bifold** as the holder's mobile wallet. Bifold is
distributed as source, not as an app-store download, so you compile it yourself.
This document records exactly how it was built for this project on Windows,
including the two things that don't work out of the box.

Repo: <https://github.com/openwallet-foundation/bifold-wallet>

> **Why not an app-store wallet?**
> **BC Wallet** is built on Bifold and is on both stores, but it refuses any
> agent that isn't a BC Government "participating service" — scanning our QR
> gives *"This QR code doesn't work with BC Wallet."* That is an allowlist, not
> a configuration problem, so it can't be used here. **Orbit Edge** is a
> workable alternative if you don't want to build. Building Bifold is the option
> that actually matches the task.

---

## Why Bifold works with this project

Bifold ships the **BCovrin Test** ledger by default —
`packages/core/src/configs/ledgers/indy/ledgers.json` contains:

```json
{ "id": "BCovrinTest", "isProduction": false, "indyNamespace": "bcovrin:test" }
```

That is the same ledger this portal publishes its schema and credential
definition to, so the wallet can resolve our credential definition with no
ledger changes.

---

## Toolchain

Bifold pins its tools tightly (`.tool-versions`, `package.json` `engines`).
Mismatched versions fail in confusing ways, so match them:

| Tool | Required | Note |
|---|---|---|
| Node | **20.19.2** (`>=20.19.2 <21`) | Node 22 is **not** accepted |
| Yarn | **4.9.2** | via `corepack`, not `npm i -g yarn` |
| JDK | **17** | Temurin/Zulu both fine |
| Android SDK | platform **36**, build-tools **36.0.0** | from `android/build.gradle` |
| Android NDK | **27.1.12297006** | required — the crypto libs are native |
| Gradle | 8.14.3 | downloaded by the wrapper |

Android Studio is **not** required to produce an APK; the command-line tools are
enough and much smaller.

### Install without touching your system Python/Node

Everything here went to `E:\tools` and `E:\Android\Sdk`, leaving the system
Node 22 and Python 3.9 (used by the portal) untouched:

```powershell
# Node 20 + JDK 17 + Android command-line tools
curl.exe -L -o E:\tools\node20.zip   https://nodejs.org/dist/v20.19.2/node-v20.19.2-win-x64.zip
curl.exe -L -o E:\tools\jdk17.zip    "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse"
curl.exe -L -o E:\tools\cmdtools.zip https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip

Expand-Archive E:\tools\node20.zip   -DestinationPath E:\tools\node20
Expand-Archive E:\tools\jdk17.zip    -DestinationPath E:\tools\jdk17
Expand-Archive E:\tools\cmdtools.zip -DestinationPath E:\tools\cmdtools

New-Item -ItemType Directory -Force E:\Android\Sdk\cmdline-tools | Out-Null
Copy-Item -Recurse E:\tools\cmdtools\cmdline-tools E:\Android\Sdk\cmdline-tools\latest
```

Set the environment for every shell that builds:

```powershell
$env:JAVA_HOME        = "E:\tools\jdk17\jdk-17.0.19+10"
$env:ANDROID_HOME     = "E:\Android\Sdk"
$env:ANDROID_SDK_ROOT = "E:\Android\Sdk"
$env:PATH = "E:\tools\node20\node-v20.19.2-win-x64;$env:JAVA_HOME\bin;E:\Android\Sdk\platform-tools;$env:PATH"
```

Then the SDK packages:

```powershell
$sdkm = "E:\Android\Sdk\cmdline-tools\latest\bin\sdkmanager.bat"
& $sdkm --sdk_root=E:/Android/Sdk --licenses          # accept all
& $sdkm --sdk_root=E:/Android/Sdk "platform-tools" "platforms;android-36" "build-tools;36.0.0" "ndk;27.1.12297006"
```

> ⚠️ **Use forward slashes in `--sdk_root`.** With backslashes, Git Bash strips
> them and `E:\Android\Sdk` resolves drive-relative — the SDK silently installs
> into your *current directory* instead. Also avoid SDK paths containing spaces;
> the NDK build does not handle them reliably.

---

## Building

```powershell
git clone https://github.com/openwallet-foundation/bifold-wallet.git E:\bifold-wallet
cd E:\bifold-wallet

corepack enable
corepack prepare yarn@4.9.2 --activate

yarn install
yarn run build          # transpiles the workspace packages
```

### Configure the mediator

A phone has no public address, so it cannot receive DIDComm directly — Bifold
requires a mediator to hold messages for it. Create `samples/app/.env` with the
`MEDIATOR_URL` line from Bifold's own README (the Indicio public mediator):

```powershell
# the exact value is in bifold-wallet/README.md
"MEDIATOR_URL=https://us-east.public.mediator.indiciotech.io/message?oob=..." | Out-File -Encoding utf8 samples\app\.env
```

**This means your PC needs internet during the demo, not just LAN.** Your phone
reaches our agent over WiFi; our agent reaches your phone through that mediator.

### Point Gradle at the SDK

`samples/app/android/local.properties`:

```properties
sdk.dir=E:/Android/Sdk
```

Forward slashes again — a Java properties file treats `\` as an escape character.

### Build the APK

```powershell
cd samples\app\android
.\gradlew.bat assembleDebug
```

Output: `samples/app/android/app/build/outputs/apk/debug/app-debug.apk`

---

## The one failure you should expect

`yarn install` fails on three packages:

```
@openwallet-foundation/askar-react-native   couldn't be built successfully
@hyperledger/anoncreds-react-native         couldn't be built successfully
@hyperledger/indy-vdr-react-native          couldn't be built successfully
```

Each downloads a ~70–95 MB tarball of prebuilt native libraries from GitHub
releases during its postinstall. Their downloader (`installBinary.js`) uses
Node's `fetch` with **no retry and no resume**, so a single `ECONNRESET` on a
less-than-perfect connection kills the install.

The fix is to fetch the tarballs with a tool that retries, then pre-populate the
`native/` directories. `installBinary.js` skips the download when
`native/version.json` already records the expected version:

```powershell
mkdir E:\tools\native-cache; cd E:\tools\native-cache
curl.exe -L --retry 8 --retry-delay 3 --retry-all-errors -C - -o askar.tar.gz `
  https://github.com/openwallet-foundation/askar/releases/download/v0.5.0/library-ios-android.tar.gz
curl.exe -L --retry 8 --retry-delay 3 --retry-all-errors -C - -o anoncreds.tar.gz `
  https://github.com/hyperledger/anoncreds-rs/releases/download/v0.2.3/library-ios-android.tar.gz
curl.exe -L --retry 8 --retry-delay 3 --retry-all-errors -C - -o indyvdr.tar.gz `
  https://github.com/hyperledger-indy/indy-vdr/releases/download/v0.4.5/library-ios-android.tar.gz
```

Then run [scripts/place_native_binaries.py](scripts/place_native_binaries.py),
which extracts each tarball (with `strip=1`, matching what `installBinary.js`
does) into **every** copy yarn's workspaces created — there were 12 — and writes
the matching `version.json`. Re-run `yarn install` afterwards; it completes.

Verify before building:

```powershell
Get-ChildItem -Recurse E:\bifold-wallet\samples\app\node_modules\@openwallet-foundation\askar-react-native\native -Filter *.so
```

You should see `libaries_askar.so` for `arm64-v8a`, `armeabi-v7a`, `x86` and
`x86_64`, and the equivalents for `libanoncreds.so` and `libindy_vdr.so`.

---

## Installing on the phone

Enable **Developer options → USB debugging**, connect by USB, then:

```powershell
adb devices                     # confirm the phone is listed and authorised
adb install -r app-debug.apk
```

No cable? Copy the APK to the phone and open it with a file manager; allow
"install from unknown sources" for that app.

---

## Using it with this portal

1. Phone on **the same WiFi** as the PC running the agent.
2. Open Bifold and complete onboarding (PIN etc.). It connects to the mediator
   on first launch — this needs internet and takes a few seconds.
3. On the PC, open `/issue/`, fill in the student details, and scan the QR.
4. Accept the connection, then accept the credential offer.
5. Open `/login/`, scan that QR, and tap **Share**.

If a QR isn't recognised, use the **switch** link under it to try the other
encoding — the compact one is a short URL the wallet must fetch, the full one
carries the whole invitation inline.

Troubleshooting for connectivity and ledger issues is in
[USER_MANUAL.md](USER_MANUAL.md#troubleshooting).

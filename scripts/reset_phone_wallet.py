
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ADB = Path(r"E:\Android\Sdk\platform-tools\adb.exe")
PACKAGE = "com.ariesbifold"
APK = Path(
    r"E:\bifold-wallet\samples\app\android\app\build\outputs\apk\release\app-release.apk"
)


def adb(*args, timeout=120):
    return subprocess.run(
        [str(ADB), *args], capture_output=True, text=True, timeout=timeout
    )


def connected_device() -> str:
    """An attached device, reconnecting over mDNS if wireless debugging dropped."""
    out = adb("devices").stdout
    for line in out.splitlines()[1:]:
        if "\tdevice" in line:
            return line.split("\t")[0]

    # Wireless debugging rotates its port; rediscover rather than guess.
    services = adb("mdns", "services").stdout
    match = re.search(r"(\S+)\s+_adb-tls-connect\._tcp\s+(\S+:\d+)", services)
    if match:
        target = match.group(2)
        print(f"  reconnecting to {target} ...")
        adb("connect", target)
        out = adb("devices").stdout
        for line in out.splitlines()[1:]:
            if "\tdevice" in line:
                return line.split("\t")[0]
    return ""


def main() -> int:
    if not ADB.exists():
        return fail(f"adb not found at {ADB}")

    device = connected_device()
    if not device:
        return fail(
            "No device.\n"
            "  USB     : plug in and enable USB debugging\n"
            "  Wireless: Settings > Developer options > Wireless debugging (on)"
        )
    print(f"  device: {device}")

    installed = adb("-s", device, "shell", "pm", "list", "packages", PACKAGE).stdout
    if PACKAGE not in installed:
        return fail(f"{PACKAGE} is not installed on this device.")

    print(f"  clearing all data for {PACKAGE} ...")
    result = adb("-s", device, "shell", "pm", "clear", PACKAGE, timeout=180)

    if "Success" not in result.stdout:
        # Some vendor ROMs (Realme/ColorOS, Xiaomi/MIUI) deny adb the
        # CLEAR_APP_USER_DATA permission. Reinstalling wipes the same data.
        detail = (result.stdout + result.stderr).strip()
        if "SecurityException" not in detail and "permission" not in detail:
            return fail(f"clear failed: {detail[:300]}")

        print("  pm clear denied by this ROM -- reinstalling instead")
        if not APK.exists():
            return fail(
                f"cannot reinstall: APK not found at {APK}\n"
                "  Build it with: cd samples\\app\\android && .\\gradlew.bat assembleRelease"
            )
        adb("-s", device, "uninstall", PACKAGE, timeout=300)
        install = adb("-s", device, "install", str(APK), timeout=900)
        if "Success" not in install.stdout:
            return fail(f"reinstall failed: {(install.stdout + install.stderr).strip()[:300]}")

    print("  wallet wiped -- credentials, connections and PIN are gone")

    if "--launch" in sys.argv:
        adb("-s", device, "shell", "monkey", "-p", PACKAGE,
            "-c", "android.intent.category.LAUNCHER", "1")
        print("  app launched -- complete onboarding on the phone")

    print("")
    print("Demo order that shows this off:")
    print("  1. /login/  -> scan. The wallet has nothing to present: login fails.")
    print("  2. /issue/  -> issue a Student ID and accept it in the wallet.")
    print("  3. /login/  -> scan again. Same request, now it succeeds.")
    return 0


def fail(msg: str) -> int:
    print(f"ERROR: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

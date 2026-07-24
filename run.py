
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from lanip import primary_host_ip  # noqa: E402

PYTHON = sys.executable
API_KEY = os.getenv("ACAPY_ADMIN_API_KEY", "demo-admin-api-key")

procs: list[subprocess.Popen] = []


def env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def stream(proc: subprocess.Popen, tag: str) -> None:
    for line in proc.stdout:
        print(f"[{tag}] {line.rstrip()}")


def spawn(tag: str, args: list[str], cwd: Path | None = None) -> subprocess.Popen:
    proc = subprocess.Popen(
        args,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    procs.append(proc)
    threading.Thread(target=stream, args=(proc, tag), daemon=True).start()
    return proc


def die(msg: str) -> None:
    print(f"\nERROR: {msg}", file=sys.stderr)
    shutdown()
    sys.exit(1)


def wait_healthy(proc: subprocess.Popen, name: str, url: str, headers: dict, timeout: int) -> None:
    print(f"  waiting for {name}", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            print()
            die(f"{name} exited before it came up (code {proc.returncode}) -- see its log above")
        try:
            if requests.get(url, headers=headers, timeout=5).ok:
                print(" ready")
                return
        except requests.RequestException:
            pass
        print(".", end="", flush=True)
        time.sleep(2)
    print()
    die(f"timed out waiting for {name} at {url}")


def shutdown() -> None:
    live = [p for p in procs if p.poll() is None]
    if not live:
        return
    print("\nStopping agent, mediator, portal...")
    deadline = time.time() + 15
    for proc in reversed(live):
        if proc.poll() is None:
            proc.terminate()
    for proc in reversed(live):
        remaining = max(0, deadline - time.time())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> None:
    if not (ROOT / ".env").exists():
        die("No .env found. Copy .env.example to .env first (see SETUP_GUIDE.md).")

    admin_port = env("AGENT_ADMIN_PORT", "8021")
    mediator_admin_port = env("MEDIATOR_ADMIN_PORT", "8041")
    portal_port = env("PORTAL_PORT", "8000")
    headers = {"X-API-KEY": API_KEY}

    print("=" * 66)
    print("  SSI University Portal -- starting agent, mediator, portal")
    print("=" * 66)

    print("\n1. ACA-Py issuer/verifier agent")
    agent = spawn("agent", [PYTHON, str(ROOT / "agent" / "run_agent.py")])
    wait_healthy(agent, "agent", f"http://127.0.0.1:{admin_port}/status", headers, timeout=120)

    print("\n2. DIDComm mediator")
    mediator = spawn("mediator", [PYTHON, str(ROOT / "agent" / "run_mediator.py")])
    wait_healthy(mediator, "mediator", f"http://127.0.0.1:{mediator_admin_port}/status", headers, timeout=90)

    print("\n3. Django portal")
    portal = spawn(
        "portal",
        [PYTHON, str(ROOT / "portal" / "manage.py"), "runserver", f"0.0.0.0:{portal_port}"],
        cwd=ROOT / "portal",
    )
    wait_healthy(portal, "portal", f"http://127.0.0.1:{portal_port}/", {}, timeout=30)

    host_ip = primary_host_ip(env("AGENT_HOST_IP", "auto"))
    print("\n" + "=" * 66)
    print("  Everything is up.")
    print("=" * 66)
    print(f"  Portal (this PC) : http://127.0.0.1:{portal_port}")
    print(f"  Portal (phone)   : http://{host_ip}:{portal_port}")
    print("  Ctrl-C stops all three.\n")

    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        for proc, tag in zip(procs, ("agent", "mediator", "portal")):
            if proc.poll() is not None:
                print(f"\n[{tag}] exited unexpectedly (code {proc.returncode})")
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()


if __name__ == "__main__":
    main()

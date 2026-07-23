<#
    Starts the ACA-Py agent for the University Portal demo.

    This single agent plays BOTH roles in the demo:
      - Issuer   : publishes the Student ID schema/cred-def and issues credentials
      - Verifier : sends proof requests and verifies the presentations

    Run `python agent/register_did.py` once before the first start.

    Usage:   .\agent\start_agent.ps1
             .\agent\start_agent.ps1 --log-level debug     # args pass through
#>

$ErrorActionPreference = "Stop"

$Root   = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Runner = Join-Path $PSScriptRoot "run_agent.py"

if (-not (Test-Path $Python)) {
    Write-Error "No virtualenv at $Python. Create it and install requirements.txt first."
}
if (-not (Test-Path (Join-Path $Root ".env"))) {
    Write-Error "No .env file found. Copy .env.example to .env first."
}

& $Python $Runner @args

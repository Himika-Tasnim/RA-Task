"""
Django settings for the SSI University Portal.

Configuration that the ACA-Py agent also needs (ports, API key, LAN IP) is read
from the project-root .env so there is exactly one place to change it.
"""

import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# portal/portal/settings.py -> portal/portal -> portal -> <repo root>
BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

load_dotenv(REPO_ROOT / ".env")

# Shared with the agent launcher so the QR codes and the agent's DIDComm
# endpoint always name the same host.
sys.path.insert(0, str(REPO_ROOT))
from lanip import primary_host_ip  # noqa: E402

AGENT_HOST_IP = primary_host_ip(os.getenv("AGENT_HOST_IP", "auto"))

DEFAULT_SECRET = "django-insecure-demo-key-replace-in-production"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", DEFAULT_SECRET)
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"

# The demo defaults are fine on a laptop on your own WiFi. They are not fine
# anywhere else, and the difference is easy to miss -- so refuse to run with
# DEBUG off (the "this is real now" signal) while still using them.
if not DEBUG:
    _weak = []
    if SECRET_KEY == DEFAULT_SECRET:
        _weak.append("DJANGO_SECRET_KEY")
    if os.getenv("ACAPY_ADMIN_API_KEY", "demo-admin-api-key") == "demo-admin-api-key":
        _weak.append("ACAPY_ADMIN_API_KEY")
    if os.getenv("WEBHOOK_API_KEY", "demo-webhook-api-key") == "demo-webhook-api-key":
        _weak.append("WEBHOOK_API_KEY")
    if os.getenv("WALLET_KEY", "demo-wallet-key-change-me") == "demo-wallet-key-change-me":
        _weak.append("WALLET_KEY")
    if _weak:
        raise ImproperlyConfigured(
            "Refusing to start with DEBUG=0 while these still hold their demo "
            f"defaults: {', '.join(_weak)}. Set real values in .env."
        )

# The phone browser may hit this over the LAN, and ACA-Py posts webhooks to it,
# so accept any Host header. Fine for a local demo; tighten for real deployments.
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = [
    f"http://{AGENT_HOST_IP}:{os.getenv('PORTAL_PORT', '8000')}",
    f"http://127.0.0.1:{os.getenv('PORTAL_PORT', '8000')}",
]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "ssi",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "portal.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "ssi.context_processors.pending_chat_requests",
            ],
        },
    },
]

WSGI_APPLICATION = "portal.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# The login session is what the whole task is about: it is created only after a
# verifiable presentation is verified, and it is what lets the student move
# between Dashboard and Profile without re-authenticating.
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 60 * 60  # 1 hour
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Hardening that costs nothing over plain HTTP. The Secure flag is deliberately
# left off: the demo runs on http:// over the LAN so the phone can reach it, and
# setting it would stop the cookie being sent at all. Turn both on behind TLS.
SESSION_COOKIE_HTTPONLY = True          # not readable from JavaScript
SESSION_COOKIE_SAMESITE = "Lax"         # not sent on cross-site POSTs
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = os.getenv("PORTAL_HTTPS", "0") == "1"
CSRF_COOKIE_SECURE = os.getenv("PORTAL_HTTPS", "0") == "1"

X_FRAME_OPTIONS = "DENY"                # no framing, so no clickjacked QR scans
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"  # keep invitation tokens out of Referer

# ---------------------------------------------------------------------------
# ACA-Py wiring
# ---------------------------------------------------------------------------
# Base URL the *phone* uses to reach this portal. Short-form invitation QR codes
# point here, so it must be the LAN address, not 127.0.0.1.
PORTAL_PUBLIC_BASE = f"http://{AGENT_HOST_IP}:{os.getenv('PORTAL_PORT', '8000')}"

ACAPY_ADMIN_URL = f"http://127.0.0.1:{os.getenv('AGENT_ADMIN_PORT', '8021')}"
ACAPY_ADMIN_API_KEY = os.getenv("ACAPY_ADMIN_API_KEY", "demo-admin-api-key")

# Shared secret ACA-Py sends with every webhook, configured as
# `--webhook-url <url>#<key>`. Without it the webhook endpoint is an
# unauthenticated write path into the login state: anyone able to reach the
# portal could POST a fabricated "presentation verified" event and log in as
# anybody. Requests without a matching x-api-key are rejected.
WEBHOOK_API_KEY = os.getenv("WEBHOOK_API_KEY", "demo-webhook-api-key")

# Student ID credential definition
ROLE_STUDENT = "student"
ROLE_FACULTY = "faculty"

# Attribute names are role-neutral: the same set describes a student and a
# faculty member. Earlier versions used student_name/student_id, which read
# wrongly on a faculty credential in the wallet.
SCHEMA_ATTRIBUTES = ["full_name", "id_number", "department", "email", "role"]
CRED_DEF_TAG = "university-portal"

# A SEPARATE schema per role, so the two credentials are visibly different in
# the wallet. A holder carrying both needs to tell them apart when choosing
# which to present, and wallets label a card from its schema name -- two
# credentials sharing one schema look identical.
CREDENTIAL_TYPES = {
    ROLE_STUDENT: {
        "schema_name": "university_student_id",
        "schema_version": "1.0",
        "label": "Student ID",
    },
    ROLE_FACULTY: {
        "schema_name": "university_faculty_id",
        "schema_version": "1.0",
        "label": "Faculty ID",
    },
}

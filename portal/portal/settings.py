"""
Django settings for the SSI University Portal.

Configuration that the ACA-Py agent also needs (ports, API key, LAN IP) is read
from the project-root .env so there is exactly one place to change it.
"""

import os
import sys
from pathlib import Path

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

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-demo-key-replace-in-production")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"

# The phone browser may hit this over the LAN, and ACA-Py posts webhooks to it,
# so accept any Host header. Fine for a local demo; tighten for real deployments.
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = [
    f"http://{AGENT_HOST_IP}:{os.getenv('PORTAL_PORT', '8000')}",
    f"http://127.0.0.1:{os.getenv('PORTAL_PORT', '8000')}",
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
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
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
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

AUTH_PASSWORD_VALIDATORS = []

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

# ---------------------------------------------------------------------------
# ACA-Py wiring
# ---------------------------------------------------------------------------
# Base URL the *phone* uses to reach this portal. Short-form invitation QR codes
# point here, so it must be the LAN address, not 127.0.0.1.
PORTAL_PUBLIC_BASE = f"http://{AGENT_HOST_IP}:{os.getenv('PORTAL_PORT', '8000')}"

ACAPY_ADMIN_URL = f"http://127.0.0.1:{os.getenv('AGENT_ADMIN_PORT', '8021')}"
ACAPY_ADMIN_API_KEY = os.getenv("ACAPY_ADMIN_API_KEY", "demo-admin-api-key")

# Student ID credential definition
SCHEMA_NAME = "student_id_card"
SCHEMA_VERSION = "1.0"
SCHEMA_ATTRIBUTES = ["student_name", "student_id", "department", "email"]
CRED_DEF_TAG = "university-portal"

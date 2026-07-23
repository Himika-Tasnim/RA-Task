"""
URL routing.

Django's admin is deliberately not mounted. Nothing in the portal uses it, and
a username/password login form is exactly the thing this project exists to do
without -- leaving it enabled would add an authentication path that bypasses
the credential entirely.
"""

from django.urls import include, path

urlpatterns = [
    path("", include("ssi.urls")),
]

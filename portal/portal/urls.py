"""
URL routing.

"""

from django.urls import include, path

urlpatterns = [
    path("", include("ssi.urls")),
]

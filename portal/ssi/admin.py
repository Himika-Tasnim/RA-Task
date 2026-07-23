from django.contrib import admin

from .models import IssuanceRequest, LedgerArtifacts, LoginSession


@admin.register(LedgerArtifacts)
class LedgerArtifactsAdmin(admin.ModelAdmin):
    list_display = ("cred_def_id", "schema_id", "issuer_did", "created_at")


@admin.register(IssuanceRequest)
class IssuanceRequestAdmin(admin.ModelAdmin):
    list_display = ("student_name", "student_id", "department", "state", "created_at")
    list_filter = ("state", "department")


@admin.register(LoginSession)
class LoginSessionAdmin(admin.ModelAdmin):
    list_display = ("pres_ex_id", "state", "verified", "created_at")
    list_filter = ("state", "verified")

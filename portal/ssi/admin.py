from django.contrib import admin

from .models import IssuanceRequest, LedgerArtifacts, LoginSession


@admin.register(LedgerArtifacts)
class LedgerArtifactsAdmin(admin.ModelAdmin):
    list_display = ("role", "cred_def_id", "schema_id", "issuer_did", "created_at")


@admin.register(IssuanceRequest)
class IssuanceRequestAdmin(admin.ModelAdmin):
    list_display = ("full_name", "id_number", "role", "department", "state", "created_at")
    list_filter = ("state", "role", "department")


@admin.register(LoginSession)
class LoginSessionAdmin(admin.ModelAdmin):
    list_display = ("pres_ex_id", "state", "verified", "created_at")
    list_filter = ("state", "verified")

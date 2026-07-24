"""
Clear demo data and return the portal to a first-run state.

Wipes issued credentials, login attempts, conversations and browser sessions,
but keeps the schema and credential definition -- those live on the ledger and
republishing them would only create duplicates. Also un-claims the entire
enrollment registry (MemberRecord.issued -> False) rather than deleting it,
so every student and faculty record -- including the ones seeded already
issued -- goes back to being claimable through /request/.

Run `manage.py seed_members` afterwards if you want Himika/Sadika back in
their pre-seeded "already issued" state rather than reclaiming them by hand.

    python manage.py reset_demo
    python manage.py reset_demo --ledger    # also forget the ledger artifacts
"""

from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand

from ssi.models import (
    BasicMessage,
    ChatInvitation,
    IssuanceRequest,
    LedgerArtifacts,
    LoginSession,
    MemberRecord,
)


class Command(BaseCommand):
    help = "Clear issued credentials, logins, chats and sessions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--ledger",
            action="store_true",
            help="also clear the recorded schema/cred-def (re-run ssi_setup after)",
        )

    def handle(self, *args, **options):
        counts = {
            "messages": BasicMessage.objects.count(),
            "chats": ChatInvitation.objects.count(),
            "logins": LoginSession.objects.count(),
            "issuances": IssuanceRequest.objects.count(),
            "browser sessions": Session.objects.count(),
        }

        BasicMessage.objects.all().delete()
        ChatInvitation.objects.all().delete()
        LoginSession.objects.all().delete()
        IssuanceRequest.objects.all().delete()
        Session.objects.all().delete()

        for label, n in counts.items():
            self.stdout.write(f"  cleared {n} {label}")

        reopened = MemberRecord.objects.filter(issued=True).update(
            issued=False, issued_at=None
        )
        self.stdout.write(f"  re-opened {reopened} enrollment registry record(s)")

        if options["ledger"]:
            n = LedgerArtifacts.objects.count()
            LedgerArtifacts.objects.all().delete()
            self.stdout.write(f"  cleared {n} ledger artifact record(s)")
            self.stdout.write(
                self.style.WARNING("  run `manage.py ssi_setup` before issuing again")
            )
        else:
            self.stdout.write("  kept the published schema and credential definition")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Reset complete."))
        self.stdout.write(
            "Run `manage.py seed_members` to restore Himika/Sadika as already "
            "issued, or leave the registry fully open and claim anyone via /request/."
        )

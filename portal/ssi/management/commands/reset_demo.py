"""
Clear demo data and return the portal to a first-run state.

Wipes issued credentials, login attempts, conversations and browser sessions,
but keeps the schema and credential definition -- those live on the ledger and
republishing them would only create duplicates.

Afterwards no faculty credential exists, so `/issue/` is in bootstrap mode and
the first credential can be issued without logging in. That is also what the
automated tests expect.

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
            "No faculty credential exists, so /issue/ is open for the first one."
        )

"""
One-time SSI bootstrap: publish the Student ID schema and credential definition.

Run this AFTER the ACA-Py agent is up:

    python manage.py ssi_setup

It is idempotent -- if the schema and cred-def already exist on the ledger for
our DID, it reuses them instead of publishing duplicates.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ssi.acapy import AcaPyClient, AcaPyError
from ssi.models import LedgerArtifacts


class Command(BaseCommand):
    help = "Publish the Student ID schema and credential definition to the ledger."

    def handle(self, *args, **options):
        client = AcaPyClient()

        try:
            client.status()
        except AcaPyError as exc:
            raise CommandError(
                f"ACA-Py is not reachable at {client.base_url}.\n"
                f"Start it first with:  .\\agent\\start_agent.ps1\n\n{exc}"
            )

        did = client.public_did()
        if not did or not did.get("did"):
            raise CommandError(
                "The agent has no public DID. Run `python agent/register_did.py` "
                "to write the seed's DID to the BCovrin ledger, then restart the agent."
            )
        issuer_did = did["did"]
        self.stdout.write(f"Issuer public DID: {self.style.SUCCESS(issuer_did)}")

        # --- schema -------------------------------------------------------
        schema_id = client.find_schema_id(settings.SCHEMA_NAME, settings.SCHEMA_VERSION)
        if schema_id:
            self.stdout.write(f"Schema already on ledger: {schema_id}")
        else:
            self.stdout.write("Publishing schema ...")
            schema_id = client.create_schema(
                settings.SCHEMA_NAME,
                settings.SCHEMA_VERSION,
                settings.SCHEMA_ATTRIBUTES,
            )
            self.stdout.write(self.style.SUCCESS(f"Schema published: {schema_id}"))

        # --- credential definition ---------------------------------------
        cred_def_id = client.find_cred_def_id(schema_id, settings.CRED_DEF_TAG)
        if cred_def_id:
            self.stdout.write(f"Cred-def already on ledger: {cred_def_id}")
        else:
            self.stdout.write("Publishing credential definition (this can take ~10s) ...")
            cred_def_id = client.create_cred_def(schema_id, settings.CRED_DEF_TAG)
            self.stdout.write(self.style.SUCCESS(f"Cred-def published: {cred_def_id}"))

        LedgerArtifacts.objects.update_or_create(
            cred_def_id=cred_def_id,
            defaults={"schema_id": schema_id, "issuer_did": issuer_did},
        )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("SSI setup complete."))
        self.stdout.write("Next: open http://127.0.0.1:8000/issue/ to issue a Student ID.")

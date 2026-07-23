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

        # One schema + cred-def per role. Separate schemas are deliberate: a
        # wallet names a credential card after its schema, so sharing one would
        # give the holder two identical-looking cards to choose between.
        for role, spec in settings.CREDENTIAL_TYPES.items():
            self.stdout.write("")
            self.stdout.write(f"--- {spec['label']} ({role}) ---")

            schema_id = client.find_schema_id(spec["schema_name"], spec["schema_version"])
            if schema_id:
                self.stdout.write(f"  schema already on ledger: {schema_id}")
            else:
                self.stdout.write("  publishing schema ...")
                schema_id = client.create_schema(
                    spec["schema_name"],
                    spec["schema_version"],
                    settings.SCHEMA_ATTRIBUTES,
                )
                self.stdout.write(self.style.SUCCESS(f"  schema published: {schema_id}"))

            cred_def_id = client.find_cred_def_id(schema_id, settings.CRED_DEF_TAG)
            if cred_def_id:
                self.stdout.write(f"  cred-def already on ledger: {cred_def_id}")
            else:
                self.stdout.write("  publishing credential definition (~10s) ...")
                cred_def_id = client.create_cred_def(schema_id, settings.CRED_DEF_TAG)
                self.stdout.write(self.style.SUCCESS(f"  cred-def published: {cred_def_id}"))

            LedgerArtifacts.objects.update_or_create(
                role=role,
                defaults={
                    "schema_id": schema_id,
                    "cred_def_id": cred_def_id,
                    "issuer_did": issuer_did,
                },
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("SSI setup complete."))
        self.stdout.write("Next: open http://127.0.0.1:8000/issue/ to issue a credential.")

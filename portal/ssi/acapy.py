"""
Thin wrapper over the ACA-Py Admin API.

Every SSI operation in this project -- creating the schema, publishing the
credential definition, building invitations, issuing credentials and verifying
presentations -- goes through ACA-Py via this client. The portal itself never
touches keys, DIDs or the ledger directly.

ACA-Py 0.12.x admin API reference: https://aca-py.org/0.12.1/
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings

log = logging.getLogger(__name__)

# Message families used below. v2 of each protocol is what modern wallets speak.
ISSUE_CREDENTIAL_V2 = "/issue-credential-2.0"
PRESENT_PROOF_V2 = "/present-proof-2.0"
DIDEXCHANGE_V1 = "https://didcomm.org/didexchange/1.0"


class AcaPyError(RuntimeError):
    """Raised when the admin API returns a non-2xx response."""


class AcaPyClient:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = (base_url or settings.ACAPY_ADMIN_URL).rstrip("/")
        self.api_key = api_key or settings.ACAPY_ADMIN_API_KEY

    # -- plumbing ----------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        headers = {"X-API-KEY": self.api_key, "Accept": "application/json"}
        kwargs.setdefault("timeout", 30)
        try:
            resp = requests.request(method, url, headers=headers, **kwargs)
        except requests.RequestException as exc:
            raise AcaPyError(
                f"Could not reach ACA-Py at {url}. Is the agent running? ({exc})"
            ) from exc

        if not resp.ok:
            raise AcaPyError(f"{method} {path} -> {resp.status_code}: {resp.text}")
        if not resp.content:
            return None
        return resp.json()

    def get(self, path: str, **kw) -> Any:
        return self._request("GET", path, **kw)

    def post(self, path: str, json: Optional[Dict] = None, **kw) -> Any:
        return self._request("POST", path, json=json or {}, **kw)

    # -- agent / ledger ----------------------------------------------------
    def status(self) -> Dict:
        return self.get("/status")

    def public_did(self) -> Optional[Dict]:
        """The issuer DID written to the ledger, derived from AGENT_SEED."""
        result = self.get("/wallet/did/public")
        return (result or {}).get("result")

    # -- schema & credential definition ------------------------------------
    def find_schema_id(self, name: str, version: str) -> Optional[str]:
        did = (self.public_did() or {}).get("did")
        params = {"schema_name": name, "schema_version": version}
        if did:
            params["schema_issuer_did"] = did
        found = self.get("/schemas/created", params=params) or {}
        ids = found.get("schema_ids") or []
        return ids[0] if ids else None

    def create_schema(self, name: str, version: str, attributes: List[str]) -> str:
        payload = {
            "schema_name": name,
            "schema_version": version,
            "attributes": attributes,
        }
        result = self.post("/schemas", payload)
        # Response shape differs slightly between endorsement modes.
        return result.get("schema_id") or result["sent"]["schema_id"]

    def find_cred_def_id(self, schema_id: str, tag: str) -> Optional[str]:
        found = self.get(
            "/credential-definitions/created",
            params={"schema_id": schema_id},
        ) or {}
        for cred_def_id in found.get("credential_definition_ids") or []:
            # cred-def ids end with the tag: <did>:3:CL:<seq_no>:<tag>
            if cred_def_id.rsplit(":", 1)[-1] == tag:
                return cred_def_id
        return None

    def create_cred_def(self, schema_id: str, tag: str) -> str:
        payload = {
            "schema_id": schema_id,
            "tag": tag,
            "support_revocation": False,
        }
        result = self.post("/credential-definitions", payload)
        return (
            result.get("credential_definition_id")
            or result["sent"]["credential_definition_id"]
        )

    # -- connections -------------------------------------------------------
    def create_connection_invitation(self, alias: str) -> Dict:
        """
        Out-of-band invitation with a DID-exchange handshake.

        Used for issuance: the student scans it, a real connection is formed,
        and we then push the credential offer down that connection.
        """
        return self.post(
            "/out-of-band/create-invitation",
            {
                "alias": alias,
                "handshake_protocols": [DIDEXCHANGE_V1],
                "use_public_did": False,
                "my_label": "Demo University",
            },
            params={"auto_accept": "true"},
        )

    def get_connection(self, connection_id: str) -> Dict:
        return self.get(f"/connections/{connection_id}")

    # -- issuance ----------------------------------------------------------
    def issue_credential(
        self, connection_id: str, cred_def_id: str, attributes: Dict[str, str]
    ) -> Dict:
        payload = {
            "connection_id": connection_id,
            "auto_remove": False,
            "comment": "Your Student ID credential from Demo University",
            "credential_preview": {
                "@type": "issue-credential/2.0/credential-preview",
                "attributes": [
                    {"name": k, "value": str(v)} for k, v in attributes.items()
                ],
            },
            "filter": {"indy": {"cred_def_id": cred_def_id}},
        }
        return self.post(f"{ISSUE_CREDENTIAL_V2}/send", payload)

    def get_credential_exchange(self, cred_ex_id: str) -> Dict:
        return self.get(f"{ISSUE_CREDENTIAL_V2}/records/{cred_ex_id}")

    # -- proof / login -----------------------------------------------------
    def create_proof_request(
        self, cred_def_id: str, attributes: List[str], name: str = "University Portal Login"
    ) -> Dict:
        """
        Build a *connectionless* proof request.

        Returns the presentation-exchange record. Restricting the request to our
        own cred_def_id is what makes this authentication rather than a
        self-asserted claim: only a credential this university actually issued
        can satisfy it.

        All attributes are requested as a single *group* (`names`) rather than
        one referent each, for two reasons:
          - Security: a group forces every attribute to come from the SAME
            credential. With separate referents a holder could satisfy each one
            from a different credential.
          - Size: one restriction block instead of four keeps the invitation
            small enough to fit in a QR code a phone can actually scan.
        """
        requested_attributes = {
            "student_id_card": {
                "names": list(attributes),
                "restrictions": [{"cred_def_id": cred_def_id}],
            }
        }
        payload = {
            "auto_verify": True,
            "comment": "Login to the University Portal",
            "presentation_request": {
                "indy": {
                    "name": name,
                    "version": "1.0",
                    "requested_attributes": requested_attributes,
                    "requested_predicates": {},
                }
            },
        }
        return self.post(f"{PRESENT_PROOF_V2}/create-request", payload)

    def bind_proof_to_invitation(self, pres_ex_id: str) -> Dict:
        """
        Wrap an existing proof request in an out-of-band invitation.

        The wallet scans one QR code and immediately gets the proof request --
        no connection needs to be established first, which is exactly what you
        want for a login screen.
        """
        return self.post(
            "/out-of-band/create-invitation",
            {
                "attachments": [{"id": pres_ex_id, "type": "present-proof"}],
                "handshake_protocols": [],
                "use_public_did": False,
                "my_label": "Demo University Portal Login",
            },
            params={"auto_accept": "true"},
        )

    def get_presentation_exchange(self, pres_ex_id: str) -> Dict:
        return self.get(f"{PRESENT_PROOF_V2}/records/{pres_ex_id}")

    # -- basic message (bonus: 1-to-1 DIDComm messaging) -------------------
    def send_basic_message(self, connection_id: str, content: str) -> Dict:
        return self.post(
            f"/connections/{connection_id}/send-message", {"content": content}
        )

    def list_connections(self) -> List[Dict]:
        return (self.get("/connections") or {}).get("results", [])


def revealed_attributes(pres_ex_record: Dict) -> Dict[str, str]:
    """
    Pull the disclosed attribute values out of a verified presentation.

    ACA-Py reports these under by_format.pres.indy.requested_proof. Because we
    request the attributes as a group, they arrive in `revealed_attr_groups`
    (keyed by referent, then by attribute name). Single-attribute referents
    would land in `revealed_attrs` instead, so both shapes are handled -- that
    keeps this working if the request format is ever changed back.
    """
    try:
        proof = pres_ex_record["by_format"]["pres"]["indy"]["requested_proof"]
    except (KeyError, TypeError):
        return {}

    values: Dict[str, str] = {}

    # Grouped form: {"student_id_card": {"values": {"email": {"raw": "..."}}}}
    for group in (proof.get("revealed_attr_groups") or {}).values():
        for name, entry in (group.get("values") or {}).items():
            values[name] = entry.get("raw", "")

    # Single-referent form: {"email": {"raw": "..."}}
    for referent, entry in (proof.get("revealed_attrs") or {}).items():
        values.setdefault(referent, entry.get("raw", ""))

    # Attributes the wallet self-attested (should be none, given our restrictions)
    for referent, raw in (proof.get("self_attested_attrs") or {}).items():
        values.setdefault(referent, raw)

    return values


def is_verified(pres_ex_record: Dict) -> bool:
    """ACA-Py reports `verified` as the *string* "true"/"false"."""
    return (
        pres_ex_record.get("state") in ("done", "presentation-received", "verified")
        and str(pres_ex_record.get("verified", "")).lower() == "true"
    )

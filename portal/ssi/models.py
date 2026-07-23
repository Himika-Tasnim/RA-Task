import uuid

from django.db import models


def short_token() -> str:
    """Short opaque id used in QR-friendly invitation URLs."""
    return uuid.uuid4().hex[:12]


class LedgerArtifacts(models.Model):
    """
    A schema + credential definition published to the ledger, one per role.

    There is a separate schema for students and faculty rather than a shared
    one, because a wallet names a credential card after its schema. Sharing a
    schema means a holder carrying both credentials sees two identical cards and
    cannot tell which to present at login.

    Written by `manage.py ssi_setup`, read by issuance and login.
    """

    role = models.CharField(max_length=20, unique=True)
    schema_id = models.CharField(max_length=255)
    cred_def_id = models.CharField(max_length=255)
    issuer_did = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Ledger artifacts"

    def __str__(self) -> str:
        return f"{self.role}: {self.cred_def_id}"

    @classmethod
    def for_role(cls, role: str):
        return cls.objects.filter(role=role).first()

    @classmethod
    def cred_def_ids(cls) -> list:
        """Every cred-def the login will accept -- one per role."""
        return list(cls.objects.values_list("cred_def_id", flat=True))

    @classmethod
    def any(cls):
        """Any published artifact, for 'is setup complete' checks."""
        return cls.objects.order_by("role").first()


class IssuanceRequest(models.Model):
    """
    One student's credential being issued.

    Created when the registrar submits the form; we then wait for the student
    to scan the QR. The connection webhook matches back to this row via
    `invitation_msg_id`, at which point the credential is offered automatically.
    """

    STATE_AWAITING_SCAN = "awaiting_scan"
    STATE_CONNECTED = "connected"
    STATE_OFFERED = "offered"
    STATE_ISSUED = "issued"
    STATE_ERROR = "error"

    full_name = models.CharField(max_length=120)
    id_number = models.CharField(max_length=60)
    department = models.CharField(max_length=120)
    email = models.EmailField()
    # Asserted inside the credential, so the holder can prove which they are.
    role = models.CharField(max_length=20, default="student")

    invitation_msg_id = models.CharField(max_length=120, db_index=True)
    invitation_url = models.TextField(blank=True)
    # Stored so the short URL below can hand the invitation to a wallet that
    # fetches it instead of decoding a large QR.
    invitation_json = models.JSONField(default=dict, blank=True)
    token = models.CharField(max_length=32, default=short_token, db_index=True)
    connection_id = models.CharField(max_length=120, blank=True, db_index=True)
    cred_ex_id = models.CharField(max_length=120, blank=True, db_index=True)

    state = models.CharField(max_length=32, default=STATE_AWAITING_SCAN)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.full_name} ({self.id_number}) - {self.state}"

    def attributes(self):
        return {
            "full_name": self.full_name,
            "id_number": self.id_number,
            "department": self.department,
            "email": self.email,
            "role": self.role,
        }


class LoginSession(models.Model):
    """
    One attempted login via proof presentation.

    The browser polls this row while the student presents their credential in
    the wallet. Only when ACA-Py reports the presentation as cryptographically
    verified do we let the view create a Django session.
    """

    STATE_PENDING = "pending"
    STATE_VERIFIED = "verified"
    STATE_FAILED = "failed"

    pres_ex_id = models.CharField(max_length=120, unique=True, db_index=True)
    invitation_url = models.TextField(blank=True)
    invitation_json = models.JSONField(default=dict, blank=True)
    token = models.CharField(max_length=32, default=short_token, db_index=True)

    # Bound to the browser that requested the login, and usable once.
    # pres_ex_id appears in the public login page's polling URL, so without
    # these anyone who observed it could complete the login in their own
    # browser after the real holder presented -- stealing the session.
    browser_key = models.CharField(max_length=64, blank=True, db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    state = models.CharField(max_length=32, default=STATE_PENDING)
    verified = models.BooleanField(default=False)
    attributes = models.JSONField(default=dict, blank=True)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.pres_ex_id} - {self.state}"


class ChatInvitation(models.Model):
    """
    A direct DIDComm connection created purely for messaging.

    The bonus task asks for a student and a faculty member to form a connection
    by scanning a QR, then exchange text. This is that invitation: the faculty
    member opens the messaging page, the student scans the code with their
    wallet, and the resulting connection carries Basic Messages both ways.

    Deliberately separate from IssuanceRequest -- this connection is not tied to
    any credential, which is what makes it a *direct* connection between two
    parties rather than a by-product of issuance.
    """

    STATE_AWAITING_SCAN = "awaiting_scan"
    STATE_CONNECTED = "connected"

    label = models.CharField(max_length=120, default="Faculty")
    # Who this conversation is with. A chat is always between two named people,
    # so the QR is generated for a specific person rather than "whoever scans".
    counterparty = models.ForeignKey(
        "IssuanceRequest",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="chats",
    )
    initiated_by_role = models.CharField(max_length=20, blank=True)
    # Whose conversation this is, by the id_number in their credential. Without
    # it any logged-in member could open any other pair's thread.
    owner_id_number = models.CharField(max_length=60, blank=True, db_index=True)
    invitation_msg_id = models.CharField(max_length=120, db_index=True)
    invitation_url = models.TextField(blank=True)
    invitation_json = models.JSONField(default=dict, blank=True)
    token = models.CharField(max_length=32, default=short_token, db_index=True)
    connection_id = models.CharField(max_length=120, blank=True, db_index=True)
    their_label = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=32, default=STATE_AWAITING_SCAN)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.label} chat - {self.state}"


class BasicMessage(models.Model):
    """
    Bonus feature: 1-to-1 DIDComm messages over an established connection.

    Both directions land here -- outgoing ones when we call ACA-Py, incoming
    ones from the `basicmessages` webhook.
    """

    connection_id = models.CharField(max_length=120, db_index=True)
    content = models.TextField()
    outgoing = models.BooleanField(default=False)
    sent_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sent_time"]

    def __str__(self) -> str:
        direction = "->" if self.outgoing else "<-"
        return f"{direction} {self.content[:40]}"

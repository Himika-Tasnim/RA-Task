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


class MemberRecord(models.Model):
    """
    The university's own enrollment record -- what a self-service request at
    `/request/` is checked against instead of a human reviewer. Covers both
    students and faculty: there is no separate privileged "faculty issues
    directly" path any more, so a faculty credential is just a MemberRecord
    with role="faculty" going through the exact same pipeline.

    Stands in for a real records system (admissions/SIS/HR). Seeded with
    `manage.py seed_members`. A row starts unissued; once it's matched by a
    verified self-service submission and a credential goes out, it's flipped
    to issued so the same enrollment record can't be claimed a second time --
    that's the real "already has a credential" guard, independent of whatever
    IssuanceRequest bookkeeping happens to exist (which can be cleared by
    `reset_demo` without this record becoming claimable again).
    """

    full_name = models.CharField(max_length=120)
    id_number = models.CharField(max_length=60, unique=True)
    department = models.CharField(max_length=120)
    email = models.EmailField()
    role = models.CharField(max_length=20, default="student")
    issued = models.BooleanField(default=False)
    issued_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.id_number}, {self.role}) - {'issued' if self.issued else 'unissued'}"

    @staticmethod
    def _normalise(value: str) -> str:
        return " ".join(value.split()).casefold()

    @classmethod
    def find_match(cls, submitted: dict):
        """
        The unissued record matching all four submitted fields, or None.

        Exact-on-all-four-fields deliberately: confirming "the ID exists but
        the name is wrong" would let someone probe real ID numbers by trial
        and error. Restricted to `issued=False` so a record already claimed
        can never be matched again.
        """
        fields = ("full_name", "id_number", "department", "email")
        for record in cls.objects.filter(issued=False):
            if all(
                cls._normalise(submitted.get(field, "")) == cls._normalise(getattr(record, field))
                for field in fields
            ):
                return record
        return None


class IssuanceRequest(models.Model):
    """
    One member's credential being issued -- student or faculty, same pipeline.

    Starts at `/request/` with no details yet, just a fresh connection
    invitation (AWAITING_SCAN). Once the applicant's wallet connects
    (CONNECTED), they submit their details on their own status page; the
    portal checks those against `MemberRecord` (the seeded enrollment table)
    and only a match gets issued. No human reviews these -- the registry
    match is the gate, for everyone, regardless of role.

    The connection webhook matches back to this row via `invitation_msg_id`.
    """

    STATE_AWAITING_SCAN = "awaiting_scan"
    STATE_CONNECTED = "connected"
    STATE_REJECTED = "rejected"
    STATE_OFFERED = "offered"
    STATE_ISSUED = "issued"
    STATE_ERROR = "error"

    # States in which an id_number is "live" -- has an in-progress or already-
    # issued claim on it. Used to stop two requests colliding on the same
    # id_number and bleeding into each other's session/messages once both are
    # logged in. Deliberately excludes REJECTED and ERROR so a declined or
    # failed applicant can be re-tried.
    ACTIVE_STATES = (
        STATE_AWAITING_SCAN,
        STATE_CONNECTED,
        STATE_OFFERED,
        STATE_ISSUED,
    )

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


class ChatInvitation(models.Model):
    """
    One connection attempt between one student and one faculty member, for
    the messaging bonus feature -- a real DID Exchange (RFC 0023) handshake,
    not just a database flag.

    Either side can press Connect first -- `initiated_by_role` records who
    did. The invitation is then shown to the OTHER party, who scans it with
    their OWN wallet. That scan is where consent actually lives: the wallet
    itself (not this app) is what prompts "connect to Demo University?"
    before it ever sends a request, and declining there means our agent
    never receives one. This app's own Reject button (see `messages_reject`)
    covers the same decision made from the portal instead of the wallet.

    This also matters for a reason beyond consent: whoever's wallet actually
    scans is the one whose device the resulting connection_id reaches. If
    the initiator scanned their own invitation instead (the previous design
    here), the connection would run to the initiator's OWN wallet -- useless
    for reaching the other party once they're on a genuinely separate phone.

    `student_id_number` + `faculty_id_number` identify the pair regardless
    of who initiated, so both people's directory queries find the same row
    (messaging is strictly one student <-> one faculty member, enforced by
    `_counterparty_or_404`).

    States, in order: AWAITING_SCAN (invitation created, nobody's scanned
    it) -> REQUESTED (their wallet scanned it and sent a DID Exchange
    request -- RFC 0023 calls this "request-received"; auto_accept=true
    means our agent answers automatically, so this is normally momentary)
    -> CONNECTED (response sent and acknowledged -- a real, usable DIDComm
    connection). REJECTED/CANCELLED/DISCONNECTED/ERROR are all terminal and
    all equally clear the way for a fresh Connect, but mean different
    things: REJECTED is the other party explicitly declining (via this app,
    without ever scanning); CANCELLED is the sender giving up on one sitting
    unanswered and sending a new one instead (`messages_resend`);
    DISCONNECTED is either party deliberately ending a working connection
    (`messages_disconnect`); ERROR is the protocol itself failing.
    """

    STATE_AWAITING_SCAN = "awaiting_scan"
    STATE_REQUESTED = "requested"
    STATE_CONNECTED = "connected"
    STATE_REJECTED = "rejected"
    STATE_CANCELLED = "cancelled"
    STATE_DISCONNECTED = "disconnected"
    STATE_ERROR = "error"

    label = models.CharField(max_length=120, default="Faculty")
    invitation_msg_id = models.CharField(max_length=120, db_index=True)
    invitation_url = models.TextField(blank=True)
    invitation_json = models.JSONField(default=dict, blank=True)
    token = models.CharField(max_length=32, default=short_token, db_index=True)
    connection_id = models.CharField(max_length=120, blank=True, db_index=True)

    student_id_number = models.CharField(max_length=60, default="", db_index=True)
    faculty_id_number = models.CharField(max_length=60, default="", db_index=True)
    initiated_by_role = models.CharField(max_length=20, default="student")

    state = models.CharField(max_length=32, default=STATE_AWAITING_SCAN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.student_id_number} <-> {self.faculty_id_number} - {self.state}"


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


class BasicMessage(models.Model):
    """
    Bonus feature: 1-to-1 DIDComm messages between one student and one
    faculty member, over the dedicated connection their `ChatInvitation`
    formed -- not the one either of them used to receive their own
    credential. Reusing the issuance connection would let any two issued
    members message each other the instant both hold a credential, with no
    consent step; a separate `ChatInvitation` per pair is what makes an
    explicit accept/reject the gate for messaging, not just for issuance.

    Both directions land here -- outgoing ones when we call ACA-Py, incoming
    ones from the `basicmessages` webhook -- keyed by `connection_id`, which
    is `ChatInvitation.connection_id` for that pair once it reaches
    `STATE_CONNECTED`.
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

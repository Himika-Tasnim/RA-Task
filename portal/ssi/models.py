import uuid

from django.db import models


def short_token() -> str:
    """Short opaque id used in QR-friendly invitation URLs."""
    return uuid.uuid4().hex[:12]


class LedgerArtifacts(models.Model):

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
        return cls.objects.order_by("role").first()


class MemberRecord(models.Model):
   

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
        
        fields = ("full_name", "id_number", "department", "email")
        for record in cls.objects.filter(issued=False):
            if all(
                cls._normalise(submitted.get(field, "")) == cls._normalise(getattr(record, field))
                for field in fields
            ):
                return record
        return None


class IssuanceRequest(models.Model):
  
    STATE_AWAITING_SCAN = "awaiting_scan"
    STATE_CONNECTED = "connected"
    STATE_SUBMITTING = "submitting"
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
        STATE_SUBMITTING,
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
    

    STATE_AWAITING_SCAN = "awaiting_scan"
    STATE_CONNECTED = "connected"
    STATE_DISCONNECTED = "disconnected"
    STATE_ERROR = "error"

    label = models.CharField(max_length=120, default="Faculty")

    # The initiator's own invitation/connection -- they scan this one.
    invitation_msg_id = models.CharField(max_length=120, db_index=True)
    invitation_url = models.TextField(blank=True)
    invitation_json = models.JSONField(default=dict, blank=True)
    token = models.CharField(max_length=32, default=short_token, db_index=True)
    connection_id = models.CharField(max_length=120, blank=True, db_index=True)

    # The counterparty's connection -- copied from their existing issuance
    # connection at creation time, never scanned or deleted by this chat.
    counterparty_connection_id = models.CharField(max_length=120, blank=True, db_index=True)

    student_id_number = models.CharField(max_length=60, default="", db_index=True)
    faculty_id_number = models.CharField(max_length=60, default="", db_index=True)
    initiated_by_role = models.CharField(max_length=20, default="student")

    state = models.CharField(max_length=32, default=STATE_AWAITING_SCAN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.student_id_number} <-> {self.faculty_id_number} - {self.state}"

    def connection_id_for(self, role: str) -> str:
        """Which connection_id belongs to `role` -- theirs or the counterparty's."""
        return self.connection_id if role == self.initiated_by_role else self.counterparty_connection_id


class LoginSession(models.Model):
    
  

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


    chat = models.ForeignKey("ChatInvitation", on_delete=models.CASCADE, related_name="messages")
    sender_role = models.CharField(max_length=20)
    content = models.TextField()
    sent_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sent_time"]

    def __str__(self) -> str:
        return f"{self.sender_role}: {self.content[:40]}"

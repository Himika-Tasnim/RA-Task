"""
University Portal views.

The authentication story here has no passwords anywhere:

  1. /issue/   -- the registrar issues a Student ID credential into a wallet.
  2. /login/   -- the portal shows a QR-encoded proof request. The student
                  presents their credential from the wallet.
  3. ACA-Py verifies the presentation cryptographically against the credential
     definition we published, and only then does `login_complete` create a
     Django session.
  4. /dashboard/ and /profile/ are served off that session -- no re-auth.
  5. /logout/ flushes it.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from functools import wraps

import qrcode
from django.conf import settings
from django.contrib import messages as flash
from django.db import models
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .acapy import (
    AcaPyClient,
    AcaPyError,
    from_allowed_cred_def,
    is_verified,
    revealed_attributes,
)
from .models import (
    BasicMessage,
    ChatInvitation,
    IssuanceRequest,
    LedgerArtifacts,
    LoginSession,
    MemberRecord,
)

log = logging.getLogger(__name__)

SESSION_KEY = "member"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def qr_data_uri(text: str) -> str:
    """
    Render `text` as a QR code PNG embedded directly in the page.

    Error correction is set to L deliberately. Out-of-band invitations that
    carry a proof request run to ~1.8 KB, and at the default (M) that either
    overflows QR capacity outright or produces a grid so dense a phone camera
    can't lock onto it. L buys the extra capacity and a lower version number.
    """
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=3,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def short_invitation_url(token: str) -> str:
    """
    A tiny URL that resolves to the invitation.

    Per the out-of-band spec a wallet may scan a plain URL and GET the
    invitation from it. That turns a ~1.8 KB version-31 QR into a ~45 byte
    version-3 one, which scans instantly. Wallets that don't implement URL
    shortening can still use the full `oob=` QR we render alongside it.
    """
    return f"{settings.PORTAL_PUBLIC_BASE}/i/{token}/"


def ssi_login_required(view):
    """Gate a page on a session that was created by a verified presentation."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.session.get(SESSION_KEY):
            flash.info(request, "Please log in with your university credential.")
            return redirect("login")
        return view(request, *args, **kwargs)

    return wrapper


def _artifacts_or_redirect(request):
    artifacts = LedgerArtifacts.any()
    if not artifacts:
        flash.error(
            request,
            "No credential definition found. Start the agent and run "
            "`python manage.py ssi_setup` first.",
        )
    return artifacts


def _active_id_number_conflict(id_number: str, exclude_pk=None) -> bool:
    """
    Is this id_number already live on another request?

    Prevents two different people (or an attacker re-requesting on a real
    person's id_number) ending up with rows sharing one id_number -- since
    messaging reaches people by their IssuanceRequest.connection_id, a
    collision there would mean two different physical wallets both "are"
    that id_number, and messages meant for one could reach the other.
    """
    qs = IssuanceRequest.objects.filter(
        id_number=id_number, state__in=IssuanceRequest.ACTIVE_STATES
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def _counterparty_or_404(request, pk):
    """
    The IssuanceRequest for the other role's pk, or 404.

    Messaging is meant strictly for one student and one faculty member to
    reach each other. Without the role/state filter here, a logged-in student
    could POST straight to a message-thread URL for another student's pk (pks
    are small sequential ints) and open a conversation the directory never
    would have offered.
    """
    me = request.session[SESSION_KEY]
    my_role = me.get("role", settings.ROLE_STUDENT)
    other_role = (
        settings.ROLE_STUDENT if my_role == settings.ROLE_FACULTY else settings.ROLE_FACULTY
    )
    return get_object_or_404(
        IssuanceRequest, pk=pk, role=other_role, state=IssuanceRequest.STATE_ISSUED
    )


def _sync_issuance_state(req: IssuanceRequest) -> None:
    """
    Fallback poll of ACA-Py for one request's credential exchange.

    Webhooks drive this normally; this is what keeps a status page moving if
    the agent couldn't reach the portal's webhook endpoint.
    """
    if req.cred_ex_id and req.state != IssuanceRequest.STATE_ISSUED:
        try:
            record = AcaPyClient().get_credential_exchange(req.cred_ex_id)
            if record.get("cred_ex_record", record).get("state") == "done":
                req.state = IssuanceRequest.STATE_ISSUED
                req.save(update_fields=["state"])
        except AcaPyError:
            pass


def _chats_for_pair(me: dict, person: IssuanceRequest):
    """
    Every ChatInvitation between `me` and `person`, newest first.

    Keyed by (student_id_number, faculty_id_number) rather than "whichever
    role clicked Connect", so the same row is found from either side of the
    conversation -- messaging is strictly one student <-> one faculty member
    (see `_counterparty_or_404`), so that pair is a stable, direction-
    independent identity for the chat.
    """
    my_role = me.get("role", settings.ROLE_STUDENT)
    if my_role == settings.ROLE_STUDENT:
        student_id_number, faculty_id_number = me["id_number"], person.id_number
    else:
        student_id_number, faculty_id_number = person.id_number, me["id_number"]
    return ChatInvitation.objects.filter(
        student_id_number=student_id_number, faculty_id_number=faculty_id_number
    ).order_by("-created_at")


def _latest_chat_for_pair(me: dict, person: IssuanceRequest):
    """
    The current connection attempt (if any) between `me` and `person`.

    Only the newest row matters -- an older rejected/errored attempt stays
    in the table as history but never blocks a fresh Connect.
    """
    return _chats_for_pair(me, person).first()


# ---------------------------------------------------------------------------
# public pages
# ---------------------------------------------------------------------------
def home(request):
    artifacts = LedgerArtifacts.any()
    agent_ok, agent_error = True, ""
    try:
        AcaPyClient().status()
    except AcaPyError as exc:
        agent_ok, agent_error = False, str(exc)

    return render(
        request,
        "ssi/home.html",
        {
            "artifacts": artifacts,
            "agent_ok": agent_ok,
            "agent_error": agent_error,
            "member": request.session.get(SESSION_KEY),
        },
    )


# ---------------------------------------------------------------------------
# credential requests: connect first, then verify against the enrollment
# registry -- no human reviewer, and no separate "faculty issues directly"
# path. Everyone -- student or faculty -- goes through the same pipeline:
#
#   /request/ (click Start) --> invitation created, AWAITING_SCAN
#     --> applicant scans, wallet connects --> CONNECTED
#     --> applicant submits name/id/department/email on their status page
#     --> checked against MemberRecord (seeded via `manage.py seed_members`)
#           no unissued match -> stays CONNECTED, form re-shown with an error
#           id already claimed -> REJECTED (terminal)
#           match     -> credential offered -> OFFERED -> ISSUED, record
#                        flipped to issued=True so it can't be reused. The
#                        matched record's own `role` decides which credential
#                        (student or faculty) gets issued.
# ---------------------------------------------------------------------------
def request_credential(request):
    """
    Public. No login -- an applicant has no credential to log in with yet.

    GET shows the explainer + start button. POST creates the connection
    invitation immediately, with no identity fields filled in -- those are
    collected (and verified) only after the wallet connects, on the
    /request/<token>/ status page.
    """
    if request.method == "POST":
        if not LedgerArtifacts.any():
            flash.error(
                request,
                "No credential definition is published yet. Ask an "
                "administrator to run `python manage.py ssi_setup`.",
            )
            return render(request, "ssi/request_credential.html")

        try:
            invitation = AcaPyClient().create_connection_invitation(
                alias="Credential applicant"
            )
        except AcaPyError as exc:
            flash.error(request, f"Could not create the invitation: {exc}")
            return render(request, "ssi/request_credential.html")

        # This is only which form of the request/status pages to show --
        # "Student ID" vs "Faculty ID" wording -- not a trust decision.
        # request_submit_details always overwrites it from the matched
        # MemberRecord's own role before anything is issued, since only the
        # registry (not the applicant) gets to say who they are.
        role = request.POST.get("role")
        if role not in (settings.ROLE_STUDENT, settings.ROLE_FACULTY):
            role = settings.ROLE_STUDENT

        req = IssuanceRequest.objects.create(
            role=role,
            invitation_msg_id=invitation.get("invi_msg_id", ""),
            invitation_url=invitation.get("invitation_url", ""),
            invitation_json=invitation.get("invitation", {}),
            detail="Waiting for your wallet to scan and connect.",
        )
        return redirect("request_status", token=req.token)

    return render(request, "ssi/request_credential.html")


def request_status(request, token):
    """
    Public, but scoped by an unguessable token rather than a sequential id --
    the same pattern LoginSession and the /i/<token>/ invitation route use, so
    this can be safely public without leaking one applicant's request to
    another the way a small int pk would.
    """
    req = get_object_or_404(IssuanceRequest, token=token)
    context = {"req": req}
    if req.state == IssuanceRequest.STATE_AWAITING_SCAN and req.invitation_url:
        short_url = short_invitation_url(req.token)
        context.update(
            qr_short=qr_data_uri(short_url),
            qr_full=qr_data_uri(req.invitation_url),
            short_url=short_url,
        )
    return render(request, "ssi/request_status.html", context)


def request_status_poll(request, token):
    """Polled by the status page: connected yet? offered? issued?"""
    req = get_object_or_404(IssuanceRequest, token=token)
    _sync_issuance_state(req)
    return JsonResponse(
        {
            "state": req.state,
            "detail": req.detail,
            "done": req.state == IssuanceRequest.STATE_ISSUED,
        }
    )


@require_POST
def request_submit_details(request, token):
    """
    The applicant's name/id/department/email, checked against MemberRecord
    -- the university's own (seeded) enrollment table, students and faculty
    alike. A match is what stands in for a human approving the request; see
    MemberRecord.find_match. The matched record's own `role` decides which
    credential (student or faculty) gets issued -- the applicant never gets
    to assert that themselves.
    """
    req = get_object_or_404(
        IssuanceRequest, token=token, state=IssuanceRequest.STATE_CONNECTED
    )

    submitted = {
        k: request.POST.get(k, "").strip()
        for k in ("full_name", "id_number", "department", "email")
    }
    if not all(submitted.values()):
        flash.error(request, "Please fill in every field.")
        return redirect("request_status", token=token)

    record = MemberRecord.find_match(submitted)
    if record is None:
        flash.error(
            request,
            "Those details don't match an unissued record we have on file. "
            "Check them and try again.",
        )
        return redirect("request_status", token=token)

    if _active_id_number_conflict(record.id_number):
        req.state = IssuanceRequest.STATE_REJECTED
        req.detail = f"{record.id_number} already has an active or issued credential."
        req.save(update_fields=["state", "detail"])
        flash.error(request, "That ID number already has a credential in progress.")
        return redirect("request_status", token=token)

    artifacts = LedgerArtifacts.for_role(record.role)
    if not artifacts:
        flash.error(
            request,
            f"No credential definition published for role '{record.role}'. Try again shortly.",
        )
        return redirect("request_status", token=token)

    # Use the record's own values, not the applicant's raw input, so the
    # credential always carries what's on file regardless of stray casing or
    # whitespace in what they typed.
    req.full_name = record.full_name
    req.id_number = record.id_number
    req.department = record.department
    req.email = record.email
    req.role = record.role
    req.save(update_fields=["full_name", "id_number", "department", "email", "role"])

    try:
        result = AcaPyClient().issue_credential(
            connection_id=req.connection_id,
            cred_def_id=artifacts.cred_def_id,
            attributes=req.attributes(),
        )
        req.cred_ex_id = result.get("cred_ex_id", "")
        req.state = IssuanceRequest.STATE_OFFERED
        req.detail = "Verified against university records. Accept the offer in your wallet."
    except AcaPyError as exc:
        req.state = IssuanceRequest.STATE_ERROR
        req.detail = str(exc)
    req.save(update_fields=["cred_ex_id", "state", "detail"])

    # Mark the enrollment record claimed regardless of whether the ACA-Py
    # call above succeeded -- an ACA-Py error here is an infrastructure
    # hiccup on OUR side, not evidence the record is free to try again with;
    # the applicant already proved they're this person. Can still be re-opened
    # by hand (MemberRecord.issued = False) if genuinely needed.
    record.issued = True
    record.issued_at = timezone.now()
    record.save(update_fields=["issued", "issued_at"])

    return redirect("request_status", token=token)


# ---------------------------------------------------------------------------
# login by verifiable presentation
# ---------------------------------------------------------------------------
def login_page(request):
    if request.session.get(SESSION_KEY):
        return redirect("dashboard")

    artifacts = _artifacts_or_redirect(request)
    if not artifacts:
        return render(request, "ssi/login.html", {"artifacts": None})

    client = AcaPyClient()
    try:
        pres_ex = client.create_proof_request(
            issuer_did=artifacts.issuer_did,
            attributes=settings.SCHEMA_ATTRIBUTES,
        )
        pres_ex_id = pres_ex["pres_ex_id"]
        invitation = client.bind_proof_to_invitation(pres_ex_id)
    except (AcaPyError, KeyError) as exc:
        flash.error(request, f"Could not build the login request: {exc}")
        return render(request, "ssi/login.html", {"artifacts": artifacts})

    # Give this browser a session key first, so the login can be tied to it.
    if not request.session.session_key:
        request.session.create()

    session = LoginSession.objects.create(
        pres_ex_id=pres_ex_id,
        invitation_url=invitation.get("invitation_url", ""),
        invitation_json=invitation.get("invitation", {}),
        browser_key=request.session.session_key or "",
    )
    short_url = short_invitation_url(session.token)

    return render(
        request,
        "ssi/login.html",
        {
            "artifacts": artifacts,
            "login_session": session,
            "qr_short": qr_data_uri(short_url),
            "qr_full": qr_data_uri(session.invitation_url),
            "short_url": short_url,
        },
    )


def login_status(request, pres_ex_id):
    """Polled by the login page until the presentation is verified."""
    session = get_object_or_404(LoginSession, pres_ex_id=pres_ex_id)

    if session.state == LoginSession.STATE_PENDING:
        # Fallback to direct polling if the webhook hasn't landed.
        try:
            record = AcaPyClient().get_presentation_exchange(pres_ex_id)
            _apply_presentation(session, record)
        except AcaPyError:
            pass

    return JsonResponse(
        {
            "state": session.state,
            "verified": session.verified,
            "detail": session.detail,
        }
    )


def login_complete(request, pres_ex_id):
    """
    Turn a verified presentation into a logged-in session.

    Re-checks verification server-side rather than trusting the poller, so
    hitting this URL directly can't fake a login.
    """
    session = get_object_or_404(LoginSession, pres_ex_id=pres_ex_id)

    if not session.verified:
        try:
            _apply_presentation(session, AcaPyClient().get_presentation_exchange(pres_ex_id))
        except AcaPyError as exc:
            flash.error(request, f"Could not confirm the presentation: {exc}")
            return redirect("login")

    if not session.verified:
        flash.error(request, "That presentation was not verified. Please try again.")
        return redirect("login")

    # Only the browser that asked for this proof may complete it. pres_ex_id is
    # visible in the public login page, so without this anyone who saw it could
    # claim the session once the real holder presented.
    if session.browser_key and session.browser_key != request.session.session_key:
        log.warning("login_complete from a different browser for %s", pres_ex_id)
        flash.error(request, "This login request belongs to a different browser.")
        return redirect("login")

    # One presentation, one login. Stops the same proof being replayed.
    if session.consumed_at:
        flash.error(request, "That login request has already been used.")
        return redirect("login")

    attributes = session.attributes
    session.consumed_at = timezone.now()
    session.save(update_fields=["consumed_at"])

    # New session id now that privileges change, so a session fixed before
    # login cannot be reused after it.
    request.session.cycle_key()

    request.session[SESSION_KEY] = attributes
    request.session["pres_ex_id"] = pres_ex_id
    request.session.set_expiry(settings.SESSION_COOKIE_AGE)

    flash.success(
        request, f"Welcome, {attributes.get('full_name', 'there')}!"
    )
    return redirect("dashboard")


def oob_invitation(request, token):
    """
    Resolve a short invitation URL to the actual out-of-band invitation.

    A wallet that scans the compact QR lands here and reads the invitation as
    JSON, which is the behaviour the out-of-band spec defines for shortened
    URLs. Anything that isn't asking for JSON (a curious browser) gets bounced
    to the full `oob=` URL instead so the invitation still resolves.

    A chat has two invitations (see `ChatInvitation`), each with its own
    token, so both `token` and `counterparty_token` are checked.
    """
    invitation_json, invitation_url = None, ""

    record = (
        LoginSession.objects.filter(token=token).first()
        or IssuanceRequest.objects.filter(token=token).first()
    )
    if record:
        invitation_json, invitation_url = record.invitation_json, record.invitation_url
    else:
        chat = ChatInvitation.objects.filter(token=token).first()
        if chat:
            invitation_json, invitation_url = chat.invitation_json, chat.invitation_url
        else:
            chat = ChatInvitation.objects.filter(counterparty_token=token).first()
            if chat:
                invitation_json = chat.counterparty_invitation_json
                invitation_url = chat.counterparty_invitation_url

    if not invitation_json:
        raise Http404("Unknown or expired invitation.")

    accept = request.headers.get("Accept", "")
    if "application/json" in accept or "*/*" in accept or not accept:
        response = JsonResponse(invitation_json)
        response["Content-Type"] = "application/json"
        return response
    return redirect(invitation_url)


def logout_view(request):
    request.session.flush()
    flash.success(request, "You have been logged out.")
    return redirect("home")


def _apply_presentation(session: LoginSession, record: dict) -> None:
    """
    Copy verification result + revealed attributes onto the LoginSession.

    Two things to be careful about, both learned the hard way:

    - A verified login is final. ACA-Py cleans up completed exchange records
      and emits a follow-up webhook with state "deleted"; without this guard
      that tidy-up would overwrite a good login with a failure.
    - "deleted" therefore means "ACA-Py tidied up", not "the student was
      rejected". Only "abandoned" is a real rejection.
    """
    if session.verified:
        return

    record = record.get("pres_ex_record", record)

    if is_verified(record):
        # The proof request could only pin the issuer DID, so confirm here that
        # the credential actually presented is one of ours -- otherwise any
        # other cred-def published under the same DID would be accepted.
        if not from_allowed_cred_def(record, LedgerArtifacts.cred_def_ids()):
            session.state = LoginSession.STATE_FAILED
            session.detail = "That credential was not issued by this portal."
            session.save()
            return

        session.state = LoginSession.STATE_VERIFIED
        session.verified = True
        session.attributes = revealed_attributes(record)
        session.detail = ""
    elif record.get("state") == "abandoned":
        session.state = LoginSession.STATE_FAILED
        session.detail = record.get("error_msg") or "The wallet declined the request."
    else:
        return
    session.save()


# ---------------------------------------------------------------------------
# protected pages
# ---------------------------------------------------------------------------
@ssi_login_required
def dashboard(request):
    return render(
        request,
        "ssi/dashboard.html",
        {"member": request.session[SESSION_KEY]},
    )


@ssi_login_required
def profile(request):
    artifacts = LedgerArtifacts.any()
    return render(
        request,
        "ssi/profile.html",
        {
            "member": request.session[SESSION_KEY],
            "artifacts": artifacts,
            "pres_ex_id": request.session.get("pres_ex_id", ""),
        },
    )


# ---------------------------------------------------------------------------
# bonus: 1-to-1 DIDComm messaging
#
# Messaging between a student and a faculty member runs over TWO dedicated
# DID Exchange (RFC 0023) connections -- not the one either of them used to
# receive their own credential, and not just one connection shared between
# them. A DIDComm connection is inherently pairwise (one wallet, one agent),
# and the portal's agent is a single shared endpoint, so reaching two
# different phones means two independent connections to it, one per phone:
#
#   /messages/ (press Connect) --> invitation #1 created, AWAITING_SCAN
#     --> shown to the person who pressed Connect -- they scan it with
#         THEIR OWN wallet, same shape as issuance/login
#     --> REQUESTED (their connection is active; the OTHER party decides)
#           reject -> REJECTED (terminal; either side can Connect again)
#           accept -> invitation #2 created, COUNTERPARTY_SCAN
#             --> shown to the accepter -- they scan it with THEIR OWN wallet
#             --> CONNECTED once #2 is also active: two real connections,
#                 messaging enabled in both directions
#
# Consent lives entirely on the portal, not in either wallet: Bifold (the
# wallet this project targets) auto-accepts every connection with no
# accept/decline screen of its own, so both invitations use
# `auto_accept=true` (see AcaPyClient.create_chat_invitation) and the real
# gate is simply that invitation #2 is never created unless the counterparty
# presses Accept.
#
# Either side can withdraw a request that's sitting unanswered and send a
# fresh one (`messages_resend`), or end a working connection
# (`messages_disconnect`).
# ---------------------------------------------------------------------------
@ssi_login_required
def messages_page(request):
    """A directory of people you can message -- click straight into a thread."""
    me = request.session[SESSION_KEY]
    my_role = me.get("role", settings.ROLE_STUDENT)
    other_role = (
        settings.ROLE_STUDENT if my_role == settings.ROLE_FACULTY else settings.ROLE_FACULTY
    )

    directory = []
    for person in IssuanceRequest.objects.filter(
        role=other_role, state=IssuanceRequest.STATE_ISSUED
    ).order_by("full_name"):
        chat = _latest_chat_for_pair(me, person)
        connected = bool(chat and chat.state == ChatInvitation.STATE_CONNECTED)
        requested = bool(chat and chat.state == ChatInvitation.STATE_REQUESTED)
        counterparty_scan = bool(chat and chat.state == ChatInvitation.STATE_COUNTERPARTY_SCAN)
        directory.append(
            {
                "person": person,
                "unread": chat.messages.exclude(sender_role=my_role).count() if connected else 0,
                "connected": connected,
                # Someone scanned and it's on ME to accept/reject.
                "awaiting_my_decision": requested and chat.initiated_by_role != my_role,
                # I clicked Connect and I'm waiting on them to decide.
                "pending_their_decision": requested and chat.initiated_by_role == my_role,
                "awaiting_scan": bool(
                    chat
                    and chat.state == ChatInvitation.STATE_AWAITING_SCAN
                    and chat.initiated_by_role == my_role
                ),
                # I accepted and now need to scan MY OWN invitation.
                "counterparty_scan_needed": counterparty_scan and chat.initiated_by_role != my_role,
                # They accepted and are scanning theirs -- nothing for me to do yet.
                "counterparty_scan_waiting": counterparty_scan and chat.initiated_by_role == my_role,
            }
        )

    return render(
        request,
        "ssi/messages.html",
        {
            "member": me,
            "my_role": my_role,
            "other_role_label": "students" if other_role == settings.ROLE_STUDENT else "faculty",
            "directory": directory,
        },
    )


@ssi_login_required
@require_POST
def messages_start(request, pk):
    """
    Send a connection request to the selected person.

    Blocked while a connection attempt is already in flight or connected;
    always allowed again once the latest attempt was rejected, cancelled,
    disconnected, or errored. Use `messages_resend` instead to replace one
    that's still awaiting_scan/requested but sitting unanswered.
    """
    me = request.session[SESSION_KEY]
    person = _counterparty_or_404(request, pk)
    chat = _latest_chat_for_pair(me, person)
    if chat and chat.state in (
        ChatInvitation.STATE_AWAITING_SCAN,
        ChatInvitation.STATE_REQUESTED,
        ChatInvitation.STATE_CONNECTED,
    ):
        return redirect("messages_thread", pk=pk)

    try:
        _send_chat_invitation(me, person)
    except AcaPyError as exc:
        flash.error(request, f"Could not create the connection invitation: {exc}")
        return redirect("messages")
    return redirect("messages_thread", pk=pk)


def _send_chat_invitation(me: dict, person: IssuanceRequest) -> ChatInvitation:
    """Create a fresh chat invitation + ChatInvitation row for this pair."""
    invitation = AcaPyClient().create_chat_invitation(alias=f"Chat with {person.full_name}")

    my_role = me.get("role", settings.ROLE_STUDENT)
    return ChatInvitation.objects.create(
        label=person.full_name,
        invitation_msg_id=invitation.get("invi_msg_id", ""),
        invitation_url=invitation.get("invitation_url", ""),
        invitation_json=invitation.get("invitation", {}),
        student_id_number=me["id_number"] if my_role == settings.ROLE_STUDENT else person.id_number,
        faculty_id_number=person.id_number if my_role == settings.ROLE_STUDENT else me["id_number"],
        initiated_by_role=my_role,
    )


def _send_counterparty_invitation(chat: ChatInvitation, person: IssuanceRequest) -> None:
    """
    Create the counterparty's own invitation for THEM to scan.

    `person` here is the initiator, from the accepter's point of view (that
    is what `_counterparty_or_404` returns for whoever is calling this).
    Moves the chat to COUNTERPARTY_SCAN -- `_on_connection` promotes it the
    rest of the way to CONNECTED once this second connection goes active.
    """
    invitation = AcaPyClient().create_chat_invitation(alias=f"Chat with {person.full_name}")
    chat.counterparty_invitation_msg_id = invitation.get("invi_msg_id", "")
    chat.counterparty_invitation_url = invitation.get("invitation_url", "")
    chat.counterparty_invitation_json = invitation.get("invitation", {})
    chat.counterparty_connection_id = ""
    chat.state = ChatInvitation.STATE_COUNTERPARTY_SCAN
    chat.save(
        update_fields=[
            "counterparty_invitation_msg_id",
            "counterparty_invitation_url",
            "counterparty_invitation_json",
            "counterparty_connection_id",
            "state",
        ]
    )


@ssi_login_required
@require_POST
def messages_resend(request, pk):
    """
    Get a new QR when one's sitting unscanned -- for a wallet that never
    scanned, lost connectivity, scanned the wrong thing, or a request just
    sitting too long.

    From COUNTERPARTY_SCAN, the accepter can ask for a fresh invitation of
    their own without disturbing the initiator's already-active connection.
    From AWAITING_SCAN or REQUESTED, EITHER party can restart the whole
    exchange from scratch -- not restricted to the original sender, since
    whoever is stuck looking at a dead end should be able to get things
    moving again without needing the other person to do anything first.
    """
    me = request.session[SESSION_KEY]
    my_role = me.get("role", settings.ROLE_STUDENT)
    person = _counterparty_or_404(request, pk)
    chat = _latest_chat_for_pair(me, person)

    if not chat or chat.state not in (
        ChatInvitation.STATE_AWAITING_SCAN,
        ChatInvitation.STATE_REQUESTED,
        ChatInvitation.STATE_COUNTERPARTY_SCAN,
    ):
        flash.error(request, "There is no outgoing request to resend.")
        return redirect("messages_thread", pk=pk)

    if chat.state == ChatInvitation.STATE_COUNTERPARTY_SCAN and chat.initiated_by_role != my_role:
        try:
            _send_counterparty_invitation(chat, person)
        except AcaPyError as exc:
            flash.error(request, f"Could not create a new connection invitation: {exc}")
            return redirect("messages_thread", pk=pk)
        flash.success(request, "Sent you a new QR to scan.")
        return redirect("messages_thread", pk=pk)

    for cid in (chat.connection_id, chat.counterparty_connection_id):
        if cid:
            try:
                AcaPyClient().delete_connection(cid)
            except AcaPyError:
                pass  # best effort -- a stale agent-side connection doesn't block a fresh one
    chat.state = ChatInvitation.STATE_CANCELLED
    chat.save(update_fields=["state"])

    try:
        _send_chat_invitation(me, person)
    except AcaPyError as exc:
        flash.error(request, f"Could not create a new connection invitation: {exc}")
        return redirect("messages_thread", pk=pk)

    flash.success(request, f"Sent a new connection request to {person.full_name}.")
    return redirect("messages_thread", pk=pk)


@ssi_login_required
def messages_thread(request, pk):
    """One conversation with one person, over their dedicated chat connection."""
    me = request.session[SESSION_KEY]
    my_role = me.get("role", settings.ROLE_STUDENT)
    person = _counterparty_or_404(request, pk)
    chat = _latest_chat_for_pair(me, person)

    context = {"member": me, "person": person, "chat_state": "none"}

    if chat and chat.state == ChatInvitation.STATE_CONNECTED:
        thread = list(chat.messages.all())
        for m in thread:
            m.outgoing = m.sender_role == my_role
        context.update(chat_state="connected", thread=thread)
    elif chat and chat.state == ChatInvitation.STATE_REQUESTED:
        if chat.initiated_by_role == my_role:
            context["chat_state"] = "pending_their_decision"
        else:
            context["chat_state"] = "awaiting_my_decision"
    elif chat and chat.state == ChatInvitation.STATE_COUNTERPARTY_SCAN:
        if chat.initiated_by_role == my_role:
            context["chat_state"] = "counterparty_scan_waiting"
        else:
            context.update(
                chat_state="counterparty_scan_needed",
                short_url=short_invitation_url(chat.counterparty_token),
                qr=qr_data_uri(chat.counterparty_invitation_url),
            )
    elif (
        chat
        and chat.state == ChatInvitation.STATE_AWAITING_SCAN
        and chat.initiated_by_role == my_role
    ):
        context.update(
            chat_state="awaiting_scan",
            short_url=short_invitation_url(chat.token),
            qr=qr_data_uri(chat.invitation_url),
        )
    elif chat and chat.state == ChatInvitation.STATE_REJECTED:
        context["chat_state"] = "rejected"
    elif chat and chat.state == ChatInvitation.STATE_DISCONNECTED:
        context["chat_state"] = "disconnected"
    elif chat and chat.state == ChatInvitation.STATE_ERROR:
        context["chat_state"] = "error"

    return render(request, "ssi/message_thread.html", context)


@ssi_login_required
def messages_status(request, pk):
    """Polled for connection-state changes and new incoming messages."""
    me = request.session[SESSION_KEY]
    person = _counterparty_or_404(request, pk)
    chat = _latest_chat_for_pair(me, person)
    connected = bool(chat and chat.state == ChatInvitation.STATE_CONNECTED)
    message_count = chat.messages.count() if connected else 0
    return JsonResponse(
        {
            "state": chat.state if chat else "none",
            "message_count": message_count,
        }
    )


@ssi_login_required
@require_POST
def messages_accept(request, pk):
    """
    The receiving party accepts a pending connection request by generating
    their OWN invitation to scan -- see the module docstring above for why
    this needs a second, independent connection rather than a bare flag.
    """
    me = request.session[SESSION_KEY]
    my_role = me.get("role", settings.ROLE_STUDENT)
    person = _counterparty_or_404(request, pk)
    chat = _latest_chat_for_pair(me, person)

    if not chat or chat.state != ChatInvitation.STATE_REQUESTED or chat.initiated_by_role == my_role:
        flash.error(request, "There is no pending connection request to accept.")
        return redirect("messages_thread", pk=pk)

    try:
        _send_counterparty_invitation(chat, person)
    except AcaPyError as exc:
        flash.error(request, f"Could not create your connection invitation: {exc}")
        return redirect("messages_thread", pk=pk)

    flash.success(request, "Scan the QR with your own wallet to finish connecting.")
    return redirect("messages_thread", pk=pk)


@ssi_login_required
@require_POST
def messages_reject(request, pk):
    """
    The receiving party declines a pending connection request, or backs out
    before finishing their own scan.
    """
    me = request.session[SESSION_KEY]
    my_role = me.get("role", settings.ROLE_STUDENT)
    person = _counterparty_or_404(request, pk)
    chat = _latest_chat_for_pair(me, person)

    if (
        not chat
        or chat.state not in (ChatInvitation.STATE_REQUESTED, ChatInvitation.STATE_COUNTERPARTY_SCAN)
        or chat.initiated_by_role == my_role
    ):
        flash.error(request, "There is no pending connection request to reject.")
        return redirect("messages_thread", pk=pk)

    for cid in (chat.connection_id, chat.counterparty_connection_id):
        if cid:
            try:
                AcaPyClient().delete_connection(cid)
            except AcaPyError:
                pass  # best effort -- still mark it rejected locally so a retry isn't blocked

    chat.state = ChatInvitation.STATE_REJECTED
    chat.save(update_fields=["state"])
    flash.success(request, f"Declined the connection request from {person.full_name}.")
    return redirect("messages_thread", pk=pk)


@ssi_login_required
@require_POST
def messages_disconnect(request, pk):
    """
    End a working connection. Either party can do this.

    There's no "goodbye" message in DID Exchange itself -- ending a
    connection is a local decision each side makes about its own agent, so
    this only removes both of OUR sides: the initiator's connection AND the
    counterparty's (see `ChatInvitation` -- a chat is two connections, one
    per phone). Each wallet keeps its own copy until it separately acts on
    it, but any further message relayed down the now-deleted connection ids
    will simply fail.
    """
    me = request.session[SESSION_KEY]
    person = _counterparty_or_404(request, pk)
    chat = _latest_chat_for_pair(me, person)

    if not chat or chat.state != ChatInvitation.STATE_CONNECTED:
        flash.error(request, "There is no active connection to end.")
        return redirect("messages_thread", pk=pk)

    for cid in (chat.connection_id, chat.counterparty_connection_id):
        if cid:
            try:
                AcaPyClient().delete_connection(cid)
            except AcaPyError:
                pass  # best effort -- still mark it disconnected locally

    chat.state = ChatInvitation.STATE_DISCONNECTED
    chat.save(update_fields=["state"])
    flash.success(request, f"Disconnected from {person.full_name}.")
    return redirect("messages_thread", pk=pk)


@ssi_login_required
@require_POST
def messages_send(request, pk):
    """
    Send a message typed on the website.

    Delivered straight to the RECIPIENT's own connection, not the sender's
    -- each phone only ever receives what's sent down ITS OWN connection
    (see `ChatInvitation`). A message typed directly on a wallet instead of
    the website arrives here via `_on_basic_message`, which relays it the
    same way in the other direction.
    """
    me = request.session[SESSION_KEY]
    my_role = me.get("role", settings.ROLE_STUDENT)
    person = _counterparty_or_404(request, pk)
    content = request.POST.get("content", "").strip()
    chat = _latest_chat_for_pair(me, person)

    if not chat or chat.state != ChatInvitation.STATE_CONNECTED:
        flash.error(request, "That person is not connected for messaging yet.")
        return redirect("messages_thread", pk=pk)

    their_connection_id = (
        chat.counterparty_connection_id if my_role == chat.initiated_by_role else chat.connection_id
    )

    if content and their_connection_id:
        try:
            AcaPyClient().send_basic_message(their_connection_id, content)
            BasicMessage.objects.create(chat=chat, sender_role=my_role, content=content)
        except AcaPyError as exc:
            flash.error(request, f"Could not send: {exc}")
    return redirect("messages_thread", pk=pk)


# ---------------------------------------------------------------------------
# ACA-Py webhooks
# ---------------------------------------------------------------------------
@csrf_exempt
def webhook(request, topic):
    """
    ACA-Py POSTs protocol state changes here (configured via --webhook-url).

    This is what makes the demo feel automatic: the moment a student's wallet
    finishes connecting, we push the credential offer without anyone clicking.

    SECURITY: this endpoint is a write path into login state, so it is
    authenticated with a shared secret ACA-Py appends to its webhook URL as
    `#<key>` and sends as x-api-key. Left open, anyone able to reach the portal
    could POST a fabricated "presentation verified" event -- with the
    pres_ex_id lifted straight out of the public login page -- and log in as
    anyone they liked. `_on_presentation` additionally refuses to trust the
    payload's own verification claim.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    if not constant_time_compare(
        request.headers.get("x-api-key", ""), settings.WEBHOOK_API_KEY
    ):
        log.warning("rejected unauthenticated webhook from %s", request.META.get("REMOTE_ADDR"))
        return JsonResponse({"error": "unauthorized"}, status=401)

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)

    log.info("webhook %s -> state=%s", topic, payload.get("state"))

    handler = {
        "connections": _on_connection,
        "issue_credential_v2_0": _on_credential,
        "present_proof_v2_0": _on_presentation,
        "basicmessages": _on_basic_message,
    }.get(topic)

    if handler:
        try:
            handler(payload)
        except Exception:  # never 500 back at the agent
            log.exception("webhook handler failed for topic %s", topic)

    return JsonResponse({"ok": True})


_CHAT_NONTERMINAL = (
    ChatInvitation.STATE_AWAITING_SCAN,
    ChatInvitation.STATE_REQUESTED,
    ChatInvitation.STATE_COUNTERPARTY_SCAN,
)


def _on_connection(payload: dict) -> None:
    """
    A DID-exchange connection changed state.

    Issuance connections auto-accept (see AcaPyClient.create_connection_
    invitation), so for those we only ever care about the terminal state:
    mark CONNECTED and stop; `request_submit_details` does the registry
    check and issues once the applicant submits their details.

    A chat is two independent connections, one per phone (see
    `ChatInvitation`), both auto-accepting the instant their owner scans.
    This fires once per connection, so it may match either the initiator's
    `invitation_msg_id` or the counterparty's `counterparty_invitation_msg_id`
    -- whichever matches, that side's connection_id is recorded, and the
    chat only reaches CONNECTED once BOTH sides are active.
    """
    state = payload.get("state")
    invitation_msg_id = payload.get("invitation_msg_id")
    connection_id = payload.get("connection_id")
    if not invitation_msg_id or not connection_id:
        return

    if state in ("active", "completed"):
        req = IssuanceRequest.objects.filter(
            invitation_msg_id=invitation_msg_id,
            state=IssuanceRequest.STATE_AWAITING_SCAN,
        ).first()
        if req:
            req.connection_id = connection_id
            req.state = IssuanceRequest.STATE_CONNECTED
            req.detail = "Connected. Enter your details to continue."
            req.save(update_fields=["connection_id", "state", "detail"])
            return

        chat = ChatInvitation.objects.filter(
            invitation_msg_id=invitation_msg_id, state__in=_CHAT_NONTERMINAL
        ).first()
        if chat:
            chat.connection_id = connection_id
            if chat.counterparty_connection_id:
                chat.state = ChatInvitation.STATE_CONNECTED
            elif chat.state == ChatInvitation.STATE_AWAITING_SCAN:
                chat.state = ChatInvitation.STATE_REQUESTED
            chat.save(update_fields=["connection_id", "state"])
            return

        chat = ChatInvitation.objects.filter(
            counterparty_invitation_msg_id=invitation_msg_id, state__in=_CHAT_NONTERMINAL
        ).first()
        if chat:
            chat.counterparty_connection_id = connection_id
            if chat.connection_id:
                chat.state = ChatInvitation.STATE_CONNECTED
            chat.save(update_fields=["counterparty_connection_id", "state"])
        return

    if state in ("error", "abandoned"):
        chat = ChatInvitation.objects.filter(
            models.Q(invitation_msg_id=invitation_msg_id)
            | models.Q(counterparty_invitation_msg_id=invitation_msg_id),
            state__in=_CHAT_NONTERMINAL,
        ).first()
        if chat:
            chat.state = ChatInvitation.STATE_ERROR
            chat.save(update_fields=["state"])


def _on_credential(payload: dict) -> None:
    """Credential exchange reached `done` -> the wallet holds it now."""
    cred_ex_id = payload.get("cred_ex_id")
    if not cred_ex_id:
        return
    req = IssuanceRequest.objects.filter(cred_ex_id=cred_ex_id).first()
    if not req:
        return

    if payload.get("state") == "done":
        req.state = IssuanceRequest.STATE_ISSUED
        req.detail = "Credential accepted and stored in the wallet."
    elif payload.get("state") == "abandoned":
        req.state = IssuanceRequest.STATE_ERROR
        req.detail = payload.get("error_msg", "The wallet declined the credential.")
    else:
        return
    req.save(update_fields=["state", "detail"])


def _on_presentation(payload: dict) -> None:
    """
    A presentation exchange changed state.

    The payload is treated purely as a *notification*: the authoritative record
    is re-fetched from ACA-Py's admin API, which is itself protected by the
    admin key. So even a webhook that somehow reached us with a forged
    "verified": "true" cannot create a login -- the only thing that counts is
    what the agent says when we ask it directly.
    """
    pres_ex_id = payload.get("pres_ex_id")
    if not pres_ex_id:
        return

    session = LoginSession.objects.filter(pres_ex_id=pres_ex_id).first()
    if not session:
        return

    try:
        record = AcaPyClient().get_presentation_exchange(pres_ex_id)
    except AcaPyError:
        # Record already cleaned up, or the agent is briefly unreachable. The
        # polling fallback will retry; never fall back to the payload.
        return

    _apply_presentation(session, record)


def _on_basic_message(payload: dict) -> None:
    """
    A message arrived on one of a chat's two connections -- could be either
    side's phone, sent from their wallet's own chat feature rather than the
    website. Record it, then relay it onto the OTHER connection so the
    other person's phone receives it too; the website textbox
    (`messages_send`) already delivers straight to the recipient, so this
    is only needed for wallet-to-wallet traffic.
    """
    connection_id = payload.get("connection_id")
    content = payload.get("content")
    if not connection_id or not content:
        return

    chat = ChatInvitation.objects.filter(
        models.Q(connection_id=connection_id) | models.Q(counterparty_connection_id=connection_id),
        state=ChatInvitation.STATE_CONNECTED,
    ).first()
    if not chat:
        return

    sender_role = chat.role_for_connection(connection_id)
    BasicMessage.objects.create(chat=chat, sender_role=sender_role, content=content)

    relay_to = (
        chat.counterparty_connection_id if connection_id == chat.connection_id else chat.connection_id
    )
    if relay_to:
        try:
            AcaPyClient().send_basic_message(relay_to, content)
        except AcaPyError:
            log.warning("could not relay message on chat %s to %s", chat.pk, relay_to)

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
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .acapy import AcaPyClient, AcaPyError, is_verified, revealed_attributes
from .models import BasicMessage, IssuanceRequest, LedgerArtifacts, LoginSession

log = logging.getLogger(__name__)

SESSION_KEY = "student"


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
            flash.info(request, "Please log in with your Student ID credential.")
            return redirect("login")
        return view(request, *args, **kwargs)

    return wrapper


def _artifacts_or_redirect(request):
    artifacts = LedgerArtifacts.current()
    if not artifacts:
        flash.error(
            request,
            "No credential definition found. Start the agent and run "
            "`python manage.py ssi_setup` first.",
        )
    return artifacts


# ---------------------------------------------------------------------------
# public pages
# ---------------------------------------------------------------------------
def home(request):
    artifacts = LedgerArtifacts.current()
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
            "student": request.session.get(SESSION_KEY),
        },
    )


# ---------------------------------------------------------------------------
# issuance
# ---------------------------------------------------------------------------
def issue_page(request):
    return render(
        request,
        "ssi/issue.html",
        {"artifacts": _artifacts_or_redirect(request)},
    )


@require_POST
def issue_start(request):
    artifacts = _artifacts_or_redirect(request)
    if not artifacts:
        return redirect("issue")

    data = {k: request.POST.get(k, "").strip() for k in settings.SCHEMA_ATTRIBUTES}
    missing = [k for k, v in data.items() if not v]
    if missing:
        flash.error(request, f"Please fill in: {', '.join(missing)}")
        return redirect("issue")

    client = AcaPyClient()
    try:
        invitation = client.create_connection_invitation(
            alias=f"{data['student_name']} ({data['student_id']})"
        )
    except AcaPyError as exc:
        flash.error(request, f"Could not create the invitation: {exc}")
        return redirect("issue")

    req = IssuanceRequest.objects.create(
        student_name=data["student_name"],
        student_id=data["student_id"],
        department=data["department"],
        email=data["email"],
        invitation_msg_id=invitation.get("invi_msg_id", ""),
        invitation_url=invitation.get("invitation_url", ""),
        invitation_json=invitation.get("invitation", {}),
    )
    return redirect("issue_wait", pk=req.pk)


def issue_wait(request, pk):
    req = get_object_or_404(IssuanceRequest, pk=pk)
    short_url = short_invitation_url(req.token)
    return render(
        request,
        "ssi/issue_wait.html",
        {
            "req": req,
            "qr_short": qr_data_uri(short_url),
            "qr_full": qr_data_uri(req.invitation_url),
            "short_url": short_url,
        },
    )


def issue_status(request, pk):
    """Polled by the issue_wait page while the student scans and accepts."""
    req = get_object_or_404(IssuanceRequest, pk=pk)

    # Webhooks drive this normally; poll ACA-Py as a fallback so the demo still
    # works if the agent can't reach the portal's webhook endpoint.
    if req.cred_ex_id and req.state != IssuanceRequest.STATE_ISSUED:
        try:
            record = AcaPyClient().get_credential_exchange(req.cred_ex_id)
            if record.get("cred_ex_record", record).get("state") == "done":
                req.state = IssuanceRequest.STATE_ISSUED
                req.save(update_fields=["state"])
        except AcaPyError:
            pass

    return JsonResponse(
        {
            "state": req.state,
            "detail": req.detail,
            "student_name": req.student_name,
            "done": req.state == IssuanceRequest.STATE_ISSUED,
        }
    )


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
            cred_def_id=artifacts.cred_def_id,
            attributes=settings.SCHEMA_ATTRIBUTES,
        )
        pres_ex_id = pres_ex["pres_ex_id"]
        invitation = client.bind_proof_to_invitation(pres_ex_id)
    except (AcaPyError, KeyError) as exc:
        flash.error(request, f"Could not build the login request: {exc}")
        return render(request, "ssi/login.html", {"artifacts": artifacts})

    session = LoginSession.objects.create(
        pres_ex_id=pres_ex_id,
        invitation_url=invitation.get("invitation_url", ""),
        invitation_json=invitation.get("invitation", {}),
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

    request.session[SESSION_KEY] = session.attributes
    request.session["pres_ex_id"] = pres_ex_id
    request.session.set_expiry(settings.SESSION_COOKIE_AGE)

    flash.success(
        request, f"Welcome, {session.attributes.get('student_name', 'student')}!"
    )
    return redirect("dashboard")


def oob_invitation(request, token):
    """
    Resolve a short invitation URL to the actual out-of-band invitation.

    A wallet that scans the compact QR lands here and reads the invitation as
    JSON, which is the behaviour the out-of-band spec defines for shortened
    URLs. Anything that isn't asking for JSON (a curious browser) gets bounced
    to the full `oob=` URL instead so the invitation still resolves.
    """
    record = (
        LoginSession.objects.filter(token=token).first()
        or IssuanceRequest.objects.filter(token=token).first()
    )
    if not record or not record.invitation_json:
        raise Http404("Unknown or expired invitation.")

    accept = request.headers.get("Accept", "")
    if "application/json" in accept or "*/*" in accept or not accept:
        response = JsonResponse(record.invitation_json)
        response["Content-Type"] = "application/json"
        return response
    return redirect(record.invitation_url)


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
        {"student": request.session[SESSION_KEY]},
    )


@ssi_login_required
def profile(request):
    artifacts = LedgerArtifacts.current()
    return render(
        request,
        "ssi/profile.html",
        {
            "student": request.session[SESSION_KEY],
            "artifacts": artifacts,
            "pres_ex_id": request.session.get("pres_ex_id", ""),
        },
    )


# ---------------------------------------------------------------------------
# bonus: 1-to-1 DIDComm messaging
# ---------------------------------------------------------------------------
@ssi_login_required
def messages_page(request):
    try:
        connections = [
            c
            for c in AcaPyClient().list_connections()
            if c.get("state") in ("active", "completed")
        ]
    except AcaPyError as exc:
        flash.error(request, str(exc))
        connections = []

    selected = request.GET.get("connection_id") or (
        connections[0]["connection_id"] if connections else ""
    )
    return render(
        request,
        "ssi/messages.html",
        {
            "student": request.session[SESSION_KEY],
            "connections": connections,
            "selected": selected,
            "thread": BasicMessage.objects.filter(connection_id=selected),
        },
    )


@ssi_login_required
@require_POST
def messages_send(request):
    connection_id = request.POST.get("connection_id", "")
    content = request.POST.get("content", "").strip()
    if connection_id and content:
        try:
            AcaPyClient().send_basic_message(connection_id, content)
            BasicMessage.objects.create(
                connection_id=connection_id, content=content, outgoing=True
            )
        except AcaPyError as exc:
            flash.error(request, f"Could not send: {exc}")
    return redirect(f"/messages/?connection_id={connection_id}")


# ---------------------------------------------------------------------------
# ACA-Py webhooks
# ---------------------------------------------------------------------------
@csrf_exempt
def webhook(request, topic):
    """
    ACA-Py POSTs protocol state changes here (configured via --webhook-url).

    This is what makes the demo feel automatic: the moment a student's wallet
    finishes connecting, we push the credential offer without anyone clicking.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

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


def _on_connection(payload: dict) -> None:
    """Student scanned the issuance QR and the connection came up -> issue."""
    if payload.get("state") not in ("active", "completed"):
        return

    invitation_msg_id = payload.get("invitation_msg_id")
    connection_id = payload.get("connection_id")
    if not invitation_msg_id or not connection_id:
        return

    req = IssuanceRequest.objects.filter(
        invitation_msg_id=invitation_msg_id,
        state=IssuanceRequest.STATE_AWAITING_SCAN,
    ).first()
    if not req:
        return

    req.connection_id = connection_id
    req.state = IssuanceRequest.STATE_CONNECTED
    req.save(update_fields=["connection_id", "state"])

    artifacts = LedgerArtifacts.current()
    if not artifacts:
        req.state = IssuanceRequest.STATE_ERROR
        req.detail = "No credential definition published."
        req.save(update_fields=["state", "detail"])
        return

    try:
        result = AcaPyClient().issue_credential(
            connection_id=connection_id,
            cred_def_id=artifacts.cred_def_id,
            attributes=req.attributes(),
        )
        req.cred_ex_id = result.get("cred_ex_id", "")
        req.state = IssuanceRequest.STATE_OFFERED
        req.detail = "Credential offered - accept it in your wallet."
    except AcaPyError as exc:
        req.state = IssuanceRequest.STATE_ERROR
        req.detail = str(exc)
    req.save(update_fields=["cred_ex_id", "state", "detail"])


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
    """Presentation arrived -- ACA-Py has already auto-verified it."""
    pres_ex_id = payload.get("pres_ex_id")
    if not pres_ex_id:
        return
    session = LoginSession.objects.filter(pres_ex_id=pres_ex_id).first()
    if session:
        _apply_presentation(session, payload)


def _on_basic_message(payload: dict) -> None:
    connection_id = payload.get("connection_id")
    content = payload.get("content")
    if connection_id and content:
        BasicMessage.objects.create(
            connection_id=connection_id, content=content, outgoing=False
        )

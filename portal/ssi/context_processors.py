from .models import ChatInvitation


def pending_chat_requests(request):
    """
    How many connection invitations are waiting on the logged-in member to
    scan them with their own wallet.

    Surfaced as a badge on the Messages nav link (see base.html) so a
    pending request is visible on every page the moment someone logs in,
    rather than only discoverable by opening Messages and finding the right
    person in the directory. A pair can have at most one non-terminal
    ChatInvitation at a time (messages_start refuses a new one while the
    latest is awaiting_scan/requested/connected), so filtering on state
    alone -- without also picking "latest per pair" -- can't double count.

    Only counts awaiting_scan, not requested: requested means their wallet
    already scanned it, so there's nothing left for them to go and do.
    """
    member = request.session.get("member")
    if not member:
        return {}

    my_role = member.get("role", "student")
    id_number = member.get("id_number", "")
    if my_role == "faculty":
        qs = ChatInvitation.objects.filter(faculty_id_number=id_number)
    else:
        qs = ChatInvitation.objects.filter(student_id_number=id_number)

    count = (
        qs.filter(state=ChatInvitation.STATE_AWAITING_SCAN)
        .exclude(initiated_by_role=my_role)
        .count()
    )
    return {"pending_chat_requests": count}

from .models import ChatInvitation


def pending_chat_requests(request):
    """
    How many chats are waiting on the logged-in member to scan their own QR.

    Surfaced as a badge on the Messages nav link (see base.html) so it's
    visible on every page, not just discoverable by opening Messages and
    finding the right person in the directory. A pair can have at most one
    non-terminal ChatInvitation at a time (messages_start refuses a new one
    while the latest is awaiting_scan/connected), so filtering on state alone
    -- without also picking "latest per pair" -- can't double count.
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

    count = sum(
        1
        for chat in qs.filter(state=ChatInvitation.STATE_AWAITING_SCAN)
        if not chat.connection_id_for(my_role)
    )
    return {"pending_chat_requests": count}

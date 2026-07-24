# How messaging works — DIDComm, protocol by protocol

This covers one thing in depth: the 1-to-1 messaging bonus feature, and
exactly which DIDComm/Aries protocols it uses, why, and where the design
choices are. If you haven't read [LEARN_SSI.md](LEARN_SSI.md) yet, do that
first — this assumes you already know what a DID, a connection and an agent
are. [HOW_IT_WORKS.md](HOW_IT_WORKS.md) covers the rest of the system.

---

## Part 1 — The three protocols in play

Messaging is built from three separate, standard Aries protocols — nothing
here is a custom message type invented for this app. ACA-Py implements all
three; the portal just drives them through the admin API.

| Protocol | RFC | What it does here |
|---|---|---|
| **Out-of-Band** | [0434](https://github.com/decentralized-identity/aries-rfcs/tree/main/features/0434-outofband) | Wraps an invitation (a URL/QR) that names which protocol to start once scanned |
| **DID Exchange 1.0** | [0023](https://github.com/decentralized-identity/aries-rfcs/tree/main/features/0023-did-exchange) | The actual handshake that establishes a connection: request → response → complete |
| **Basic Message 1.0** | [0095](https://github.com/decentralized-identity/aries-rfcs/tree/main/features/0095-basic-message) | Plain encrypted text sent over an already-established connection |

Two more show up indirectly:

- **Mediator Coordination ([0211](https://github.com/decentralized-identity/aries-rfcs/tree/main/features/0211-route-coordination))** — how the phone, which has no fixed address, still receives these messages. Covered in [LEARN_SSI.md §5.2](LEARN_SSI.md).
- **Connections Protocol ([0160](https://github.com/decentralized-identity/aries-rfcs/tree/main/features/0160-connection-protocol))** — the older, pre-0023 connection protocol. ACA-Py's connection-state naming still carries its vocabulary (`"active"` alongside 0023's `"completed"`) for historical reasons — see the state table below.

Issuance and login use the *same* Out-of-Band and DID Exchange machinery —
messaging isn't special at the protocol level. What's actually specific to
messaging is entirely in *how the portal drives them* (below).

---

## Part 2 — The topology: one agent, not peer-to-peer

It matters that there is exactly **one ACA-Py agent** in this whole system
— "Demo University"'s. Every wallet, whichever identity it holds, connects
*to that one agent*, never to each other directly:

```
   Student's phone                                    Faculty's phone
   (Bifold wallet)                                     (Bifold wallet)
         │                                                    │
         │  DIDComm, via the mediator                         │  DIDComm, via the mediator
         ▼                                                    ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                    ACA-Py agent ("Demo University")           │
   │   one connection_id per wallet that has ever connected to it  │
   └─────────────────────────────┬───────────────────────────────┘
                                 │ admin API (loopback only)
                                 ▼
                       Django portal — website
                    (this is what students/faculty
                     actually read/write messages in)
```

A DID Exchange connection is always **agent ↔ one specific wallet** — never
wallet-to-wallet. So when the portal wants Karim (faculty) to message Tanvir
(student), it needs a connection whose *other end is Tanvir's actual phone*,
and it relays through the website UI, not the wallet's own chat screen. This
single fact drives almost every design decision below.

---

## Part 3 — The connect handshake, step by step

Say Karim presses **Connect** on Tanvir's row in the Messages directory.

```
 Karim (faculty)         Django portal              ACA-Py agent           Tanvir (student)
      │                       │                          │                       │
      │  POST .../start/      │                          │                       │
      ├──────────────────────►│  POST /out-of-band/       │                       │
      │                       │  create-invitation        │                       │
      │                       │  (handshake=didexchange/1.0,                     │
      │                       │   auto_accept=true)        │                       │
      │                       ├─────────────────────────►│                       │
      │                       │◄─────────────────────────┤ invitation             │
      │                       │  saves ChatInvitation      │                       │
      │                       │  state=AWAITING_SCAN       │                       │
      │◄──────────────────────┤  "waiting for them         │                       │
      │  (waiting_on_them)    │   to scan"                 │                       │
      │                       │                          │                       │
      │                       │                          │      Tanvir opens      │
      │                       │                          │      his own Messages  │
      │                       │                          │      page, sees the QR │
      │                       │                          │◄──────────────────────┤
      │                       │                          │      scans it with     │
      │                       │                          │      HIS OWN wallet    │
      │                       │                          │                       │
      │                       │                          │◄──────────────────────┤
      │                       │                          │  DIDExchange REQUEST   │
      │                       │                          │  (RFC 0023)            │
      │                       │  webhook: connections,    │                       │
      │                       │  state=request             │                       │
      │                       │◄─────────────────────────┤                       │
      │                       │  ChatInvitation →          │                       │
      │                       │  STATE_REQUESTED           │                       │
      │                       │                          │  auto_accept=true →    │
      │                       │                          │  agent sends RESPONSE  │
      │                       │                          │───────────────────────►│
      │                       │                          │◄──────────────────────┤
      │                       │                          │  DIDExchange COMPLETE  │
      │                       │  webhook: connections,    │  (Tanvir's wallet acks)│
      │                       │  state=completed           │                       │
      │                       │◄─────────────────────────┤                       │
      │                       │  ChatInvitation →          │                       │
      │◄──────────────────────┤  STATE_CONNECTED           ├──────────────────────►│
      │   "connected"         │                          │   "connected"          │
```

The step that matters most: **Tanvir's own wallet is what decides whether
to send that DIDExchange request at all.** Every Aries wallet, Bifold
included, shows its own "connect to Demo University?" prompt the moment it
scans *any* out-of-band invitation — before it sends anything. That prompt
*is* the consent step the whole feature is built around, and it happens on
Tanvir's device, in Tanvir's wallet, not as a button on a website.

This is also exactly why it has to be **Tanvir** scanning and not Karim
(who clicked Connect): the connection that results belongs to whoever's
wallet sent the request. If Karim scanned his own invitation instead, the
connection would run to Karim's own phone — useless for ever reaching
Tanvir once they're on separate devices, and no different from having
implicit self-connections.

---

## Part 4 — Where "accept" and "reject" really live

There is deliberately **no manual admin-side accept step** in this design
(`auto_accept=true` on the invitation — `create_chat_invitation` in
[acapy.py](portal/ssi/acapy.py)). An earlier version of this feature set
`auto_accept=false` and made the
*portal* decide whether to complete the connection, with an Accept/Reject
button on the website. That was protocol-legal (ACA-Py exposes
`POST /didexchange/{conn_id}/accept-request` for exactly this), but it put
the consent decision in the wrong place: a database flag flipped by a web
button, once the wallet had *already* sent a real cryptographic request —
i.e., after the point where genuine consent should have been asked.

So now:

- **Accepting** = scanning the invitation and letting your own wallet send
  the DID Exchange request. Nothing else has to happen — once that request
  exists, there's nothing left for the portal to decide, so it completes
  automatically.
- **Rejecting without scanning** is still available on the portal
  (`messages_reject` in [views.py](portal/ssi/views.py)) for a clean,
  explicit "no" — it just marks the row `REJECTED` locally (and calls
  `POST /didexchange/{conn_id}/reject` if a connection record happens to
  already exist). Declining is *also* legitimate by simply never scanning;
  the explicit button just avoids leaving the other person waiting forever.

---

## Part 5 — State machine

`ChatInvitation.state` ([models.py](portal/ssi/models.py)) tracks the
webhook-reported ACA-Py connection state (`payload["state"]` on the
`connections` topic), translated into what it means for messaging:

| ChatInvitation state | ACA-Py / RFC 0023 state | What's actually happened | Who can act |
|---|---|---|---|
| `AWAITING_SCAN` | *(invitation created, no connection record yet)* | Invitation exists; nobody has scanned it | The other party scans it (or declines/resends) |
| `REQUESTED` | `request` (`rfc23_state: request-received`) | Their wallet scanned it and sent a DID Exchange **request** | Nobody — auto-accept resolves this automatically within moments |
| `CONNECTED` | `completed` (older ACA-Py records may say `active` — see below) | Response sent, **complete** acknowledged by their wallet — a real, working connection | Either party: send messages, or disconnect |
| `REJECTED` | *(no connection record — declined before a request existed)* | Explicitly declined via the portal, without ever scanning | Either party can Connect again |
| `CANCELLED` | connection deleted via `DELETE /connections/{id}` | Someone withdrew a stuck request and sent a fresh one | Either party can Connect again |
| `DISCONNECTED` | connection deleted via `DELETE /connections/{id}` | Either party deliberately ended a working connection | Either party can Connect again |
| `ERROR` | `abandoned` / `error` | The protocol itself failed (wallet declined mid-handshake, etc.) | Either party can Connect again |

**Why ACA-Py reports both `"active"` and `"completed"` for the same thing:**
`ConnRecord.State.COMPLETED` in ACA-Py is literally the tuple
`("active", "completed")` — `"active"` is the terminal state name from the
older RFC 0160 Connections Protocol, `"completed"` is RFC 0023's own name
for the same idea (a full request → response → complete round-trip). Both
values mean the same thing and both are treated identically here
(`_on_connection` in [views.py](portal/ssi/views.py)).

Every terminal state except `CONNECTED` clears the way for a fresh
`Connect` (`messages_start` only blocks while the latest row is
`AWAITING_SCAN`/`REQUESTED`/`CONNECTED`).

---

## Part 6 — Sending messages (RFC 0095)

Once `CONNECTED`, `messages_send` (in [views.py](portal/ssi/views.py))
calls `POST /connections/{connection_id}/send-message` with the plain text
— that's the entire Basic Message protocol; it has no state machine of its
own, no delivery receipts, just "send this text down this connection."

A DID Exchange connection is bidirectional by construction, so the **same**
`connection_id` carries messages both ways, regardless of who scanned:

- Karim → Tanvir: the portal calls `send-message` on `connection_id` (which
  reaches Tanvir's real wallet, since Tanvir's wallet is the one that
  formed it).
- Tanvir → Karim: Tanvir's wallet sends a Basic Message back down the same
  connection; ACA-Py fires a `basicmessages` webhook
  (`_on_basic_message` in [views.py](portal/ssi/views.py)), and the
  portal stores it.

Both people read and write this conversation through the **portal's own
chat UI** ([message_thread.html](portal/ssi/templates/ssi/message_thread.html)),
not through anything native in the wallet — Bifold has no chat screen of its
own for arbitrary Basic Messages. The wallet's only two jobs are: form the
connection (Part 3), and silently carry the encrypted bytes back and forth.

---

## Part 7 — Ending a connection

DID Exchange (RFC 0023) has no "goodbye" message — there's no protocol step
where one party formally tells the other "we're done." Ending a connection
is a purely local decision each side makes about its own agent:
`DELETE /connections/{connection_id}` just removes *our* record of it
(`delete_connection` in [acapy.py](portal/ssi/acapy.py)). The other
party's wallet keeps its own copy of the connection until it independently
decides to remove it — any further message sent down a connection_id we've
deleted will simply fail on our side, which is the correct behavior for "we
consider this over."

Two features use this the same way:

- **Resend** (`messages_resend` in [views.py](portal/ssi/views.py)) —
  deletes a stuck, unanswered connection attempt and creates a brand new
  invitation. Either party can do this now, not just whoever clicked
  Connect first.
- **Disconnect** (`messages_disconnect` in [views.py](portal/ssi/views.py))
  — deletes a working connection outright. Either party can do this too.
  Connecting again afterwards is a completely fresh handshake (Part 3),
  with a new invitation and a new connection_id.

---

## Part 8 — Known limitations

Being direct about what this design does *not* do:

- **Hub-and-spoke, not peer-to-peer.** Every "connection" is really
  agent↔wallet, twice over, relayed by the portal — never a direct
  wallet-to-wallet channel the way two independent Aries agents on the open
  network would connect. That's a consequence of there being one shared
  ACA-Py agent for the whole university, not a limitation of DIDComm itself.
- **Single-use invitations.** Each `Connect` press creates one out-of-band
  invitation for exactly one counterpart pair; it isn't a standing,
  reusable "add me" QR code the way a personal contact code would be.
- **No delivery receipts.** Basic Message (RFC 0095) doesn't have any —
  the portal only knows a message was *sent* to ACA-Py, not that the
  wallet actually rendered it to the person holding the phone.
- **Deleting a connection is one-sided.** Disconnecting removes it from our
  agent; the other party's wallet may still show it as connected until
  they separately remove it there too.

---

## Code map

| Concern | File |
|---|---|
| ACA-Py admin API calls (invitation, reject, delete, send-message) | [portal/ssi/acapy.py](portal/ssi/acapy.py) |
| `ChatInvitation` model + states | [portal/ssi/models.py](portal/ssi/models.py) |
| Views: directory, start, resend, thread, status, reject, disconnect, send | [portal/ssi/views.py](portal/ssi/views.py) |
| Webhook handlers (`connections`, `basicmessages` topics) | `_on_connection`, `_on_basic_message` in [portal/ssi/views.py](portal/ssi/views.py) |
| Directory + conversation pages | [portal/ssi/templates/ssi/messages.html](portal/ssi/templates/ssi/messages.html), [message_thread.html](portal/ssi/templates/ssi/message_thread.html) |
| Nav badge for "someone wants to connect" | [portal/ssi/context_processors.py](portal/ssi/context_processors.py) |

## References

- [RFC 0434 — Out-of-Band Protocol](https://github.com/decentralized-identity/aries-rfcs/tree/main/features/0434-outofband)
- [RFC 0023 — DID Exchange Protocol 1.0](https://github.com/decentralized-identity/aries-rfcs/tree/main/features/0023-did-exchange)
- [RFC 0095 — Basic Message Protocol 1.0](https://github.com/decentralized-identity/aries-rfcs/tree/main/features/0095-basic-message)
- [RFC 0160 — Connections Protocol (superseded by 0023)](https://github.com/decentralized-identity/aries-rfcs/tree/main/features/0160-connection-protocol)
- [RFC 0211 — Mediator Coordination Protocol](https://github.com/decentralized-identity/aries-rfcs/tree/main/features/0211-route-coordination)
- [ACA-Py admin API reference](https://aca-py.org/latest/)

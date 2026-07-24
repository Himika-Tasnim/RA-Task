from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),

    # Credential requests: connect first, then verify details against the
    # enrollment registry (see models.MemberRecord). Students and faculty
    # both go through this same pipeline -- there is no separate direct-
    # issue path.
    path("request/", views.request_credential, name="request_credential"),
    path("request/<str:token>/", views.request_status, name="request_status"),
    path("request/<str:token>/status/", views.request_status_poll, name="request_status_poll"),
    path("request/<str:token>/submit/", views.request_submit_details, name="request_submit_details"),

    # Login by verifiable presentation
    path("login/", views.login_page, name="login"),
    path("login/status/<str:pres_ex_id>/", views.login_status, name="login_status"),
    path("login/complete/<str:pres_ex_id>/", views.login_complete, name="login_complete"),
    path("logout/", views.logout_view, name="logout"),

    # Protected pages
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile, name="profile"),

    # Bonus: 1-to-1 DIDComm messaging over a dedicated, auto-accepted connection
    path("messages/", views.messages_page, name="messages"),
    path("messages/<int:pk>/start/", views.messages_start, name="messages_start"),
    path("messages/<int:pk>/resend/", views.messages_resend, name="messages_resend"),
    path("messages/<int:pk>/disconnect/", views.messages_disconnect, name="messages_disconnect"),
    path("messages/<int:pk>/", views.messages_thread, name="messages_thread"),
    path("messages/<int:pk>/status/", views.messages_status, name="messages_status"),
    path("messages/<int:pk>/send/", views.messages_send, name="messages_send"),

    # Short invitation URLs -- what the compact QR codes encode
    path("i/<str:token>/", views.oob_invitation, name="oob_invitation"),

    # ACA-Py pushes protocol state changes here
    path("webhooks/topic/<str:topic>/", views.webhook, name="webhook"),
]

from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),

    # Issuance (registrar side)
    path("issue/", views.issue_page, name="issue"),
    path("issue/start/", views.issue_start, name="issue_start"),
    path("issue/<int:pk>/", views.issue_wait, name="issue_wait"),
    path("issue/<int:pk>/status/", views.issue_status, name="issue_status"),

    # Login by verifiable presentation
    path("login/", views.login_page, name="login"),
    path("login/status/<str:pres_ex_id>/", views.login_status, name="login_status"),
    path("login/complete/<str:pres_ex_id>/", views.login_complete, name="login_complete"),
    path("logout/", views.logout_view, name="logout"),

    # Protected pages
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile, name="profile"),

    # Bonus: 1-to-1 DIDComm messaging
    path("messages/", views.messages_page, name="messages"),
    path("messages/start/", views.messages_start, name="messages_start"),
    path("messages/status/", views.messages_status, name="messages_status"),
    path("messages/send/", views.messages_send, name="messages_send"),

    # Short invitation URLs -- what the compact QR codes encode
    path("i/<str:token>/", views.oob_invitation, name="oob_invitation"),

    # ACA-Py pushes protocol state changes here
    path("webhooks/topic/<str:topic>/", views.webhook, name="webhook"),
]

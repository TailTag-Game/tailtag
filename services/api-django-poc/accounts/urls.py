"""URL routes owned by the accounts application."""

from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("csrf", views.CsrfView.as_view(), name="csrf"),
    path("signup", views.SignupView.as_view(), name="signup"),
    path("login", views.LoginView.as_view(), name="login"),
    path("logout", views.LogoutView.as_view(), name="logout"),
    path("me", views.CurrentUserView.as_view(), name="current-user"),
]

"""Acceptance contract for Django admin operator login labeling and authentication."""

from __future__ import annotations

from typing import cast

import pytest
from django.contrib.auth.forms import AuthenticationForm
from django.test import Client
from django.urls import reverse

from accounts.models import User


@pytest.mark.django_db
def test_admin_login_renders_operator_identifier_label() -> None:
    """AC-1/3: The admin login form labels the username field as 'Operator identifier'."""
    client = Client()
    response = client.get(reverse("admin:login"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")

    assert "Operator identifier:" in content
    assert "Clerk user id" not in content

    form = cast(AuthenticationForm, response.context["form"])
    assert form.fields["username"].label == "Operator identifier"


@pytest.mark.django_db
def test_admin_login_invalid_credentials_error_uses_operator_identifier() -> None:
    """AC-1/2: Invalid login error messages refer to 'operator identifier', not 'clerk user id'."""
    operator = User.objects.create_superuser(
        clerk_user_id="operator_login_test",
        password="valid-operator-password",
    )
    client = Client()
    response = client.post(
        reverse("admin:login"),
        {
            "username": operator.get_username(),
            "password": "wrong-password",
        },
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")

    assert "Please enter the correct operator identifier and password" in content
    assert "clerk user id" not in content.lower()


@pytest.mark.django_db
def test_admin_login_non_staff_rejection_error_uses_operator_identifier() -> None:
    """AC-1/2: Non-staff rejection error messages refer to 'operator identifier'."""
    user = User.objects.create_superuser(
        clerk_user_id="operator_revoked_staff",
        password="valid-password",
    )
    user.is_staff = False
    user.save(update_fields={"is_staff"})

    client = Client()
    response = client.post(
        reverse("admin:login"),
        {
            "username": user.get_username(),
            "password": "valid-password",
        },
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")

    assert "Please enter the correct operator identifier and password" in content
    assert "clerk user id" not in content.lower()


@pytest.mark.django_db
def test_admin_login_successful_authentication() -> None:
    """AC-2: Admin authentication and authorization are unchanged for operators."""
    operator = User.objects.create_superuser(
        clerk_user_id="operator_successful_login",
        password="correct-operator-password",
    )
    client = Client()
    response = client.post(
        reverse("admin:login"),
        {
            "username": operator.get_username(),
            "password": "correct-operator-password",
            "next": reverse("admin:index"),
        },
    )

    assert response.status_code == 302
    assert response.headers.get("Location") == reverse("admin:index")
    assert int(client.session["_auth_user_id"]) == operator.pk

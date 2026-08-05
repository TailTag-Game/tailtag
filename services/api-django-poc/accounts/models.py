"""Custom TailTag account identity model."""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class UserManager(BaseUserManager["User"]):
    """Create users with a canonical email identity."""

    @staticmethod
    def canonicalize_email(email: str) -> str:
        """Return the single stored representation for an email identity."""
        return BaseUserManager.normalize_email(email.strip()).lower()

    def _create_user(
        self,
        email: str,
        password: str | None,
        **extra_fields: object,
    ) -> User:
        canonical_email = self.canonicalize_email(email)
        if not canonical_email:
            message = "The email address must be set."
            raise ValueError(message)

        user = self.model(email=canonical_email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: object,
    ) -> User:
        """Create a non-privileged user."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: object,
    ) -> User:
        """Create a privileged user for Django administration."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            message = "Superuser must have is_staff=True."
            raise ValueError(message)
        if extra_fields.get("is_superuser") is not True:
            message = "Superuser must have is_superuser=True."
            raise ValueError(message)

        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """A password-authenticated account identified by canonical email."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(max_length=254, unique=True)
    display_name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = ["display_name"]

    def __str__(self) -> str:
        """Represent the account without exposing any credentials."""
        return self.email

"""TailTag-owned application identity."""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar, cast

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.hashers import UNUSABLE_PASSWORD_PREFIX
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models.base import ModelBase


class UserManager(BaseUserManager["User"]):
    """Create TailTag users linked to opaque Clerk identities."""

    def _create_user(
        self,
        clerk_user_id: str,
        password: str | None,
        **extra_fields: object,
    ) -> User:
        if not clerk_user_id:
            message = "The Clerk user ID must be set."
            raise ValueError(message)
        if password is not None and (
            extra_fields.get("is_staff") is not True
            or extra_fields.get("is_superuser") is not True
        ):
            message = "Local passwords require both staff and superuser flags."
            raise ValueError(message)

        user = self.model(clerk_user_id=clerk_user_id, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self,
        clerk_user_id: str,
        password: str | None = None,
        **extra_fields: object,
    ) -> User:
        """Create a TailTag application user without Django privileges."""
        if password is not None:
            message = "TailTag application users do not use Django passwords."
            raise ValueError(message)
        if extra_fields.get("is_staff"):
            message = "Application users must have is_staff=False."
            raise ValueError(message)
        if extra_fields.get("is_superuser"):
            message = "Application users must have is_superuser=False."
            raise ValueError(message)

        extra_fields["is_staff"] = False
        extra_fields["is_superuser"] = False
        return self._create_user(clerk_user_id, None, **extra_fields)

    def create_superuser(
        self,
        clerk_user_id: str,
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

        return self._create_user(clerk_user_id, password, **extra_fields)


class User(  # pyright: ignore[reportIncompatibleVariableOverride]
    AbstractBaseUser,
    PermissionsMixin,
):
    """The canonical TailTag identity used by application domains."""

    id: int
    pk: int
    clerk_user_id: models.CharField[str, str] = models.CharField(
        max_length=255,
        unique=True,
    )
    is_staff: models.BooleanField[bool, bool] = models.BooleanField(default=False)

    objects: ClassVar[UserManager] = UserManager()  # pyright: ignore[reportIncompatibleVariableOverride]

    USERNAME_FIELD = "clerk_user_id"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                condition=~models.Q(clerk_user_id=""),
                name="accounts_user_clerk_user_id_not_empty",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_staff=True, is_superuser=True)
                    | models.Q(
                        password__startswith=UNUSABLE_PASSWORD_PREFIX,
                    )
                ),
                name="accounts_user_local_password_requires_admin",
            ),
        ]

    def set_password(self, raw_password: str | None) -> None:
        """Reserve usable Django passwords for the superuser bootstrap path."""
        if raw_password is not None and not self._can_use_local_password():
            message = "Only Django superusers may use local passwords."
            raise ValueError(message)
        super().set_password(raw_password)

    def save(
        self,
        *,
        force_insert: bool | tuple[ModelBase, ...] = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        """Ensure every saved non-admin has an unusable password."""
        if not self._can_use_local_password() and self.has_usable_password():
            self.set_unusable_password()
            if update_fields is not None:
                update_fields = {*update_fields, "password"}

        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def _can_use_local_password(self) -> bool:
        """Return whether this instance satisfies the local-admin contract."""
        return self.is_staff and cast(
            bool,
            self.is_superuser,  # pyright: ignore[reportUnknownMemberType]
        )

    def __str__(self) -> str:
        """Represent this user by its TailTag-owned identity."""
        return f"TailTag user {self.pk}"

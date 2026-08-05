"""Request and public-response serialization for account endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from rest_framework import serializers

from .models import User, UserManager

if TYPE_CHECKING:
    AccountSerializer = serializers.Serializer[User]
    UserModelSerializer = serializers.ModelSerializer[User]
else:
    AccountSerializer = serializers.Serializer
    UserModelSerializer = serializers.ModelSerializer


class PublicUserSerializer(UserModelSerializer):
    """Expose only the fields safe for an account API response."""

    class Meta:
        """Configure the public user representation."""

        fields = ("id", "email", "display_name", "created_at", "updated_at")
        model = User
        read_only_fields = fields


class ErrorDetailSerializer(AccountSerializer):
    """Document the stable error shape returned by public account endpoints."""

    detail = serializers.CharField(read_only=True)


class SignupSerializer(AccountSerializer):
    """Validate public account creation without accepting privileges."""

    display_name = serializers.CharField(max_length=100, trim_whitespace=True)
    email = serializers.EmailField(max_length=254, trim_whitespace=True)
    password = serializers.CharField(trim_whitespace=False, write_only=True)

    def validate_display_name(self, value: str) -> str:
        """Reject a display name that becomes blank after trimming."""
        if not value:
            message = "This field may not be blank."
            raise serializers.ValidationError(message)
        return value

    def validate_email(self, value: str) -> str:
        """Canonicalize and reserve the one stored email representation."""
        email = UserManager.canonicalize_email(value)
        if User.objects.filter(email=email).exists():
            message = "An account with this email already exists."
            raise serializers.ValidationError(message)
        return email

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        """Apply Django's configured password policy before account creation."""
        email = str(attrs["email"])
        display_name = str(attrs["display_name"])
        password = str(attrs["password"])
        validate_password(password, User(email=email, display_name=display_name))
        return attrs

    def create(self, validated_data: dict[str, object]) -> User:
        """Create the user through the canonical-email manager."""
        email = str(validated_data["email"])
        try:
            with transaction.atomic():
                return User.objects.create_user(
                    email=email,
                    password=str(validated_data["password"]),
                    display_name=str(validated_data["display_name"]),
                )
        except IntegrityError:
            if User.objects.filter(email=email).exists():
                raise serializers.ValidationError(
                    {"email": "An account with this email already exists."}
                ) from None
            raise


class LoginSerializer(AccountSerializer):
    """Validate login input before authentication."""

    email = serializers.EmailField(max_length=254, trim_whitespace=True)
    password = serializers.CharField(trim_whitespace=False, write_only=True)

    def validate_email(self, value: str) -> str:
        """Use the same identity lookup representation as signup."""
        return UserManager.canonicalize_email(value)

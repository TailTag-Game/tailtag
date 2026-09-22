"""Django application configuration for operator audit evidence."""

from __future__ import annotations

from django.apps import AppConfig


class OperatorAuditConfig(AppConfig):
    """Configure the operator audit application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "operator_audit"

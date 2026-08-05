"""Fursuit profile persistence."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class Fursuit(models.Model):
    """A single profile that belongs to one participating account."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fursuits",
    )
    name = models.CharField(max_length=100)
    species = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        """Use the profile name in administrative interfaces."""
        return self.name

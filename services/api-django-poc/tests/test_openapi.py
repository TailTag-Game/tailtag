"""Published OpenAPI documentation behavior."""

from __future__ import annotations

import yaml
from django.test import Client


def test_openapi_schema_includes_account_and_fursuit_routes(client: Client) -> None:
    """The schema is public and includes the POC workflow."""
    response = client.get("/api/schema/")

    assert response.status_code == 200
    schema = yaml.safe_load(response.content)
    assert "/api/auth/signup" in schema["paths"]
    assert "/api/fursuits" in schema["paths"]

"""Import-free negative fixture for the Django mark_safe rule."""


def mark_safe(value: str) -> str:
    return value


# ok: tailtag.django.mark-safe
mark_safe("not Django")

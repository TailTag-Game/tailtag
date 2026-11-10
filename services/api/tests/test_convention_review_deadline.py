"""Acceptance tests for convention time zones and the catch request review deadline (#503)."""

from __future__ import annotations

import datetime
import zoneinfo
from typing import Any, cast

import pytest
from django.contrib.auth.models import Permission
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from conventions import services
from conventions.models import Convention, ConventionEnrollment, ConventionStatus
from conventions.review_deadline import (
    compute_review_deadline,
    database_now,
    review_window_open,
    time_zone_names,
)
from profiles.models import PlayerProfile
from tests.authentication_support import create_test_user, force_authenticated_client

UTC = datetime.UTC
NEW_YORK = "America/New_York"
# Dates far from the real clock, so open and closed windows need no clock control.
OPEN_END = datetime.date(2030, 6, 2)
OPEN_DEADLINE = datetime.datetime(2030, 6, 5, 4, tzinfo=UTC)
CLOSED_END = datetime.date(2020, 6, 2)
CLOSED_DEADLINE = datetime.datetime(2020, 6, 5, 4, tzinfo=UTC)


@pytest.mark.parametrize(
    ("end_date", "zone", "expected"),
    [
        pytest.param(
            datetime.date(2027, 1, 17),
            NEW_YORK,
            datetime.datetime(2027, 1, 20, 5, tzinfo=UTC),
            id="sunday-closes-wednesday-est",
        ),
        pytest.param(
            datetime.date(2027, 3, 12),
            NEW_YORK,
            datetime.datetime(2027, 3, 15, 4, tzinfo=UTC),
            id="across-dst-start-uses-local-days",
        ),
        pytest.param(
            datetime.date(2027, 9, 2),
            "America/Santiago",
            datetime.datetime(2027, 9, 5, 4, tzinfo=UTC),
            id="skipped-midnight-uses-first-instant-after",
        ),
        pytest.param(
            datetime.date(2027, 11, 4),
            "America/Havana",
            datetime.datetime(2027, 11, 7, 4, tzinfo=UTC),
            id="repeated-midnight-uses-first-occurrence",
        ),
    ],
)
def test_review_deadline_is_start_of_third_local_day_after_end(
    end_date: datetime.date, zone: str, expected: datetime.datetime
) -> None:
    """AC2, AC3: local calendar rules, not a fixed 72 hours."""
    assert compute_review_deadline(end_date, zone) == expected


@pytest.mark.parametrize(
    ("time_zone", "deadline", "at", "expected"),
    [
        pytest.param(None, None, OPEN_DEADLINE, False, id="unknown-zone"),
        pytest.param(
            NEW_YORK,
            OPEN_DEADLINE,
            OPEN_DEADLINE - datetime.timedelta(microseconds=1),
            True,
            id="before",
        ),
        pytest.param(NEW_YORK, OPEN_DEADLINE, OPEN_DEADLINE, False, id="tie-closes"),
        pytest.param(
            NEW_YORK,
            OPEN_DEADLINE,
            OPEN_DEADLINE + datetime.timedelta(days=1),
            False,
            id="after",
        ),
    ],
)
def test_review_window_open_predicate(
    time_zone: str | None,
    deadline: datetime.datetime | None,
    at: datetime.datetime,
    expected: bool,
) -> None:
    """AC16: an unknown zone or a reached deadline closes the window."""
    convention = Convention(time_zone=time_zone, review_deadline_at=deadline)
    assert review_window_open(convention, at) is expected


def test_zone_data_comes_only_from_the_pinned_tzdata_package() -> None:
    """AC6, AC7: one zone data source on every platform, legacy aliases included."""
    assert zoneinfo.TZPATH == ()
    names = time_zone_names()
    assert {NEW_YORK, "US/Eastern"} <= names
    assert "Mars/Olympus" not in names


def _zoned_convention(
    end_date: datetime.date, zone: str | None = NEW_YORK, **fields: Any
) -> Convention:
    return Convention.objects.create(
        name=fields.pop("name", "Deadline target"),
        status=fields.pop("status", ConventionStatus.DRAFT),
        start_date=end_date - datetime.timedelta(days=1),
        end_date=end_date,
        time_zone=zone,
        review_deadline_at=None
        if zone is None
        else compute_review_deadline(end_date, zone),
        **fields,
    )


def _edit(convention: Convention, **changes: Any) -> Convention:
    values: dict[str, Any] = {
        "name": convention.name,
        "status": convention.status,
        "start_date": convention.start_date,
        "end_date": convention.end_date,
        "time_zone": convention.time_zone,
    }
    values.update(changes)
    services.set_convention_admin_state(convention_id=convention.pk, **values)
    convention.refresh_from_db()
    return convention


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("initial_end", "initial_zone", "changes", "expected_deadline"),
    [
        pytest.param(
            OPEN_END,
            NEW_YORK,
            {"end_date": datetime.date(2030, 6, 9)},
            datetime.datetime(2030, 6, 12, 4, tzinfo=UTC),
            id="open-extension-recomputes",
        ),
        pytest.param(
            OPEN_END,
            NEW_YORK,
            {"time_zone": "America/Los_Angeles"},
            datetime.datetime(2030, 6, 5, 7, tzinfo=UTC),
            id="open-zone-change-recomputes",
        ),
        pytest.param(
            OPEN_END,
            NEW_YORK,
            {"start_date": datetime.date(2020, 6, 1), "end_date": CLOSED_END},
            CLOSED_DEADLINE,
            id="open-earlier-deadline-closes-at-once",
        ),
        pytest.param(
            OPEN_END,
            NEW_YORK,
            {"status": ConventionStatus.PAUSED, "name": "Renamed"},
            OPEN_DEADLINE,
            id="open-non-schedule-edit-keeps-deadline",
        ),
        pytest.param(
            CLOSED_END,
            NEW_YORK,
            {"end_date": datetime.date(2030, 6, 9)},
            CLOSED_DEADLINE,
            id="closed-extension-cannot-reopen",
        ),
        pytest.param(
            CLOSED_END,
            NEW_YORK,
            {"time_zone": "Pacific/Kiritimati"},
            CLOSED_DEADLINE,
            id="closed-zone-change-cannot-reopen",
        ),
        pytest.param(
            CLOSED_END,
            None,
            {"time_zone": NEW_YORK},
            CLOSED_DEADLINE,
            id="first-zone-with-past-deadline-closes-at-once",
        ),
    ],
)
def test_operator_edit_applies_the_deadline_change_rules(
    initial_end: datetime.date,
    initial_zone: str | None,
    changes: dict[str, Any],
    expected_deadline: datetime.datetime,
) -> None:
    """AC10 to AC14: recompute only while open; closure is permanent."""
    convention = _edit(_zoned_convention(initial_end, initial_zone), **changes)

    assert convention.review_deadline_at == expected_deadline
    for field, value in changes.items():
        assert getattr(convention, field) == value


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("stored_end", "old_image_end", "expected_deadline"),
    [
        pytest.param(
            OPEN_END,
            datetime.date(2030, 6, 20),
            datetime.datetime(2030, 6, 23, 4, tzinfo=UTC),
            id="open-stale-deadline-repaired",
        ),
        pytest.param(
            CLOSED_END,
            datetime.date(2030, 6, 20),
            CLOSED_DEADLINE,
            id="closed-stale-deadline-kept",
        ),
    ],
)
def test_resave_repairs_a_deadline_left_stale_by_an_older_image(
    stored_end: datetime.date,
    old_image_end: datetime.date,
    expected_deadline: datetime.datetime,
) -> None:
    """AC25 rollback remedy: a plain re-save recomputes an open stale deadline."""
    convention = _zoned_convention(stored_end)
    # An older image changes only the end date and leaves the deadline as it was.
    Convention.objects.filter(pk=convention.pk).update(end_date=old_image_end)
    convention.refresh_from_db()

    assert _edit(convention).review_deadline_at == expected_deadline


@pytest.mark.django_db
def test_database_now_reads_the_clock_not_the_transaction_start() -> None:
    """AC10: closure uses clock_timestamp(), which moves inside one transaction."""
    with transaction.atomic():
        first = database_now()
        second = database_now()
    assert second > first


@pytest.mark.django_db
def test_operator_edit_cannot_clear_a_set_time_zone() -> None:
    """AC8: a set zone can change but never return to null."""
    convention = _zoned_convention(OPEN_END)

    with pytest.raises(services.ConventionTimeZoneRequiredError):
        _edit(convention, time_zone=None)

    convention.refresh_from_db()
    assert (convention.time_zone, convention.review_deadline_at) == (
        NEW_YORK,
        OPEN_DEADLINE,
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("time_zone", "deadline"),
    [
        pytest.param(NEW_YORK, None, id="zone-without-deadline"),
        pytest.param(None, OPEN_DEADLINE, id="deadline-without-zone"),
        pytest.param("", OPEN_DEADLINE, id="empty-zone"),
    ],
)
def test_database_pairs_time_zone_and_deadline(
    time_zone: str | None, deadline: datetime.datetime | None
) -> None:
    """AC1: both null or both set, with one null representation."""
    with pytest.raises(IntegrityError):
        Convention.objects.create(
            name="Unpaired",
            start_date=OPEN_END,
            end_date=OPEN_END,
            time_zone=time_zone,
            review_deadline_at=deadline,
        )


def _staff(*codenames: str) -> Client:
    user = create_test_user()
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    user.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
        *[
            Permission.objects.get(content_type__app_label="conventions", codename=code)
            for code in codenames
        ]
    )
    client = Client()
    client.force_login(User.objects.get(pk=user.pk))
    return client


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("zone", "created"),
    [
        pytest.param("US/Eastern", True, id="legacy-alias-valid"),
        pytest.param("Mars/Olympus", False, id="unknown-name-rejected"),
    ],
)
def test_admin_create_stores_the_deadline_for_valid_zones_only(
    zone: str, created: bool
) -> None:
    """AC4, AC5, AC7: the create path computes the deadline from a known zone."""
    client = _staff("add_convention", "change_convention", "view_convention")
    response = client.post(
        reverse("admin:conventions_convention_add"),
        {
            "name": "Created with zone",
            "status": ConventionStatus.DRAFT,
            "start_date": "2020-06-01",
            "end_date": CLOSED_END.isoformat(),
            "time_zone": zone,
        },
    )

    assert response.status_code == (302 if created else 200)
    stored = Convention.objects.filter(name="Created with zone").first()
    if created:
        assert stored is not None
        assert (stored.time_zone, stored.review_deadline_at) == (zone, CLOSED_DEADLINE)
    else:
        assert stored is None


@pytest.mark.django_db
def test_admin_change_form_shows_the_deadline_and_keeps_a_set_zone() -> None:
    """AC8, AC20, AC21: read-only deadline display, no blank once set, zone filter."""
    zoned = _zoned_convention(OPEN_END, name="Zoned con")
    _zoned_convention(OPEN_END, None, name="Unzoned con")
    client = _staff("change_convention", "view_convention")
    url = reverse("admin:conventions_convention_change", args=(zoned.pk,))

    page = client.get(url).content.decode()
    assert '<option value="">' not in page
    assert '<option value="America/New_York" selected>' in page
    assert "2030-06-05" in page and "Open" in page

    cleared = client.post(
        url,
        {
            "name": zoned.name,
            "status": zoned.status,
            "start_date": zoned.start_date.isoformat(),
            "end_date": zoned.end_date.isoformat(),
            "time_zone": "",
        },
    )
    assert cleared.status_code == 200
    zoned.refresh_from_db()
    assert (zoned.time_zone, zoned.review_deadline_at) == (NEW_YORK, OPEN_DEADLINE)

    listing = client.get(
        reverse("admin:conventions_convention_changelist"),
        {"time_zone__isempty": "0"},
    ).content.decode()
    assert "Zoned con" in listing and "Unzoned con" not in listing


@pytest.mark.django_db
def test_playability_only_operator_cannot_change_the_time_zone() -> None:
    """AC22: the zone is read-only metadata for the narrow playability role."""
    convention = _zoned_convention(OPEN_END)
    client = _staff("set_convention_playability", "view_convention")
    url = reverse("admin:conventions_convention_change", args=(convention.pk,))

    assert 'name="time_zone"' not in client.get(url).content.decode()
    forged = client.post(
        url,
        {
            "status": ConventionStatus.ACTIVE,
            "time_zone": "Pacific/Kiritimati",
            "_save": "Save",
        },
    )

    assert forged.status_code == 403
    convention.refresh_from_db()
    assert (convention.status, convention.time_zone) == (
        ConventionStatus.DRAFT,
        NEW_YORK,
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("end_date", "deadline_text", "local_date", "review_open"),
    [
        pytest.param(OPEN_END, "2030-06-05T04:00:00Z", "2030-06-05", True, id="open"),
        pytest.param(
            CLOSED_END, "2020-06-05T04:00:00Z", "2020-06-05", False, id="closed"
        ),
    ],
)
def test_convention_reads_return_the_review_deadline_fields(
    end_date: datetime.date, deadline_text: str, local_date: str, review_open: bool
) -> None:
    """AC17, AC18: detail and nested enrollment reads carry the server deadline."""
    user = create_test_user()
    PlayerProfile.objects.create(
        user=user,
        handle="deadline_reader",
        display_name="Deadline Reader",
        is_enabled=True,
        onboarding_completed_at=timezone.now(),
    )
    convention = _zoned_convention(end_date, status=ConventionStatus.ACTIVE)
    ConventionEnrollment.objects.create(user=user, convention=convention)
    client = force_authenticated_client(user=user)
    expected = {
        "time_zone": NEW_YORK,
        "review_deadline_at": deadline_text,
        "review_deadline_local_date": local_date,
        "review_open": review_open,
    }

    detail = cast(
        dict[str, Any], client.get(f"/api/conventions/{convention.pk}/").json()
    )
    enrollments = cast(
        list[dict[str, Any]], client.get("/api/conventions/enrollments/").json()
    )

    assert {key: detail[key] for key in expected} == expected
    nested = enrollments[0]["convention"]
    assert {key: nested[key] for key in expected} == expected

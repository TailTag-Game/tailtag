import uuid
from typing import Any

from django.db import migrations, models


def backfill_tailtag_ids(apps: Any, schema_editor: Any) -> None:
    Fursuit = apps.get_model("fursuits", "Fursuit")
    for fursuit in Fursuit.objects.all().iterator():
        fursuit.tailtag_id = uuid.uuid4()
        fursuit.save(update_fields=["tailtag_id"])


def reverse_backfill_tailtag_ids(apps: Any, schema_editor: Any) -> None:
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("fursuits", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="fursuit",
            name="tailtag_id",
            field=models.UUIDField(null=True),
        ),
        migrations.RunPython(backfill_tailtag_ids, reverse_backfill_tailtag_ids),
        migrations.AlterField(
            model_name="fursuit",
            name="tailtag_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]

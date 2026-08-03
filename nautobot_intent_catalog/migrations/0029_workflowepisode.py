# Generated manually, following 0027_desiredworkspace.py's shape.

import django.core.serializers.json
import nautobot.core.models.fields
import nautobot.extras.models.mixins
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('extras', '0142_remove_scheduledjob_approval_required'),
        ('nautobot_intent_catalog', '0028_remove_desirednodeoperationaloverride_declared_host_os'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkflowEpisode',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('_custom_field_data', models.JSONField(blank=True, default=dict, encoder=django.core.serializers.json.DjangoJSONEncoder)),
                ('title', models.CharField(max_length=255)),
                ('status', models.CharField(choices=[('candidate', 'Candidate'), ('selected', 'Selected'), ('resolved', 'Resolved'), ('dismissed', 'Dismissed')], default='candidate', max_length=16)),
                ('raw_data', models.JSONField(blank=True, default=dict)),
                ('tags', nautobot.core.models.fields.TagsField(through='extras.TaggedItem', to='extras.Tag')),
            ],
            options={
                'verbose_name': 'workflow episode',
                'verbose_name_plural': 'workflow episodes',
                'ordering': ('-last_updated', 'title'),
            },
            bases=(nautobot.extras.models.mixins.DataComplianceModelMixin, nautobot.extras.models.mixins.DynamicGroupMixin, nautobot.extras.models.mixins.NotesMixin, models.Model),
        ),
    ]

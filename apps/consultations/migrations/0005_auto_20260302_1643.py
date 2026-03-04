from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('consultations', '0004_auto_20260302_1636'),
    ]

    operations = [
        migrations.AddField(
            model_name='symptom',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default='2026-03-02 00:00:00'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='symptom',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, default='2026-03-02 00:00:00'),
            preserve_default=False,
        ),
    ]
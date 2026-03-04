from django.db import migrations, models
import uuid

class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Patient',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('medical_history', models.TextField(blank=True)),
                ('emergency_contact', models.CharField(blank=True, max_length=100)),
                ('emergency_phone', models.CharField(blank=True, max_length=15)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(blank=True, null=True, on_delete=models.CASCADE, related_name='patient_profile', to='users.user')),
            ],
            options={
                'db_table': 'patients',
            },
        ),
        migrations.CreateModel(
            name='Consultation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('current_state', models.CharField(choices=[('initial', 'Initial'), ('symptoms_collected', 'Symptoms Collected'), ('diagnosis_pending', 'Diagnosis Pending'), ('diagnosis_complete', 'Diagnosis Complete'), ('lab_tests_ordered', 'Lab Tests Ordered'), ('lab_results_received', 'Lab Results Received'), ('prescription_ready', 'Prescription Ready'), ('completed', 'Completed'), ('failed', 'Failed')], default='initial', max_length=30)),
                ('symptoms_data', models.JSONField(blank=True, default=dict, null=True)),
                ('symptom_analysis', models.JSONField(blank=True, default=dict, null=True)),
                ('diagnosis_data', models.JSONField(blank=True, default=dict, null=True)),
                ('lab_tests_data', models.JSONField(blank=True, default=list, null=True)),
                ('lab_results_data', models.JSONField(blank=True, default=list, null=True)),
                ('prescription_data', models.JSONField(blank=True, default=dict, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('patient', models.ForeignKey(null=True, on_delete=models.CASCADE, related_name='consultations', to='consultations.patient')),
            ],
            options={
                'db_table': 'consultations',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Symptom',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('description', models.TextField()),
                ('duration', models.CharField(blank=True, max_length=100)),
                ('severity', models.IntegerField(blank=True, null=True)),
                ('input_type', models.CharField(choices=[('text', 'Text'), ('voice', 'Voice')], default='text', max_length=10)),
                ('audio_file', models.FileField(blank=True, null=True, upload_to='symptoms/audio/')),
                ('transcript', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('consultation', models.ForeignKey(on_delete=models.CASCADE, related_name='symptom_list', to='consultations.consultation')),
            ],
            options={
                'db_table': 'symptoms',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Prescription',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('medications', models.JSONField(default=list)),
                ('instructions', models.TextField(blank=True)),
                ('duration', models.CharField(blank=True, max_length=100)),
                ('prescribed_by', models.CharField(default='ai_system', max_length=100)),
                ('prescribed_date', models.DateTimeField(auto_now_add=True)),
                ('sent_to_pharmacy', models.BooleanField(default=False)),
                ('pharmacy_response', models.JSONField(blank=True, default=dict, null=True)),
                ('sent_date', models.DateTimeField(blank=True, null=True)),
                ('consultation', models.ForeignKey(on_delete=models.CASCADE, related_name='prescription_list', to='consultations.consultation')),
            ],
            options={
                'db_table': 'prescriptions',
                'ordering': ['-prescribed_date'],
            },
        ),
        migrations.CreateModel(
            name='LabTest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('test_name', models.CharField(max_length=200)),
                ('test_type', models.CharField(default='blood', max_length=50)),
                ('priority', models.CharField(choices=[('routine', 'Routine'), ('urgent', 'Urgent'), ('stat', 'STAT')], default='routine', max_length=20)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='pending', max_length=20)),
                ('results', models.JSONField(blank=True, default=dict, null=True)),
                ('clinical_indication', models.TextField(blank=True)),
                ('ordered_by', models.CharField(default='system', max_length=100)),
                ('ordered_date', models.DateTimeField(auto_now_add=True)),
                ('completed_date', models.DateTimeField(blank=True, null=True)),
                ('consultation', models.ForeignKey(on_delete=models.CASCADE, related_name='lab_test_list', to='consultations.consultation')),
            ],
            options={
                'db_table': 'lab_tests',
                'ordering': ['-ordered_date'],
            },
        ),
        migrations.CreateModel(
            name='ClarificationQuestion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('question', models.TextField()),
                ('answer', models.TextField(blank=True)),
                ('answered_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('consultation', models.ForeignKey(on_delete=models.CASCADE, related_name='clarification_questions', to='consultations.consultation')),
            ],
            options={
                'db_table': 'clarification_questions',
                'ordering': ['created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='consultation',
            index=models.Index(fields=['current_state'], name='consultatio_current_5c55cd_idx'),
        ),
        migrations.AddIndex(
            model_name='consultation',
            index=models.Index(fields=['patient', '-created_at'], name='consultatio_patient_301a8e_idx'),
        ),
    ]
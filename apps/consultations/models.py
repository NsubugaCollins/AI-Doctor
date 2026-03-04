from django.db import models
import uuid
from django.contrib.postgres.fields import JSONField
from apps.users.models import User

class Patient(models.Model):
    """Patient information"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='patient_profile', null=True, blank=True)
    medical_history = models.TextField(blank=True)
    allergies = models.TextField(blank=True, default='')
    blood_type = models.CharField(max_length=10, blank=True, null=True)
    emergency_contact = models.CharField(max_length=100, blank=True)
    emergency_phone = models.CharField(max_length=15, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'patients'
    
    def __str__(self):
        return f"Patient {self.id}"

class Consultation(models.Model):
    """Main consultation model"""
    STATE_CHOICES = [
        ('initial', 'Initial'),
        ('symptoms_collected', 'Symptoms Collected'),
        ('diagnosis_pending', 'Diagnosis Pending'),
        ('diagnosis_complete', 'Diagnosis Complete'),
        ('lab_tests_ordered', 'Lab Tests Ordered'),
        ('lab_tests_complete', 'Lab Tests Complete'),
        ('lab_results_received', 'Lab Results Received'),
        ('final_diagnosis_ready', 'Final Diagnosis Ready'),
        ('prescription_ready', 'Prescription Ready'),
        ('prescription_sent', 'Prescription Sent'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='consultations', null=True)
    current_state = models.CharField(max_length=35, choices=STATE_CHOICES, default='initial')
    
    # JSON fields for flexible data storage
    # JSON fields for flexible data storage
    symptoms = models.JSONField(null=True, blank=True, default=list)
    diagnosis = models.JSONField(null=True, blank=True, default=dict)
    lab_tests = models.JSONField(null=True, blank=True, default=list)
    prescription = models.JSONField(null=True, blank=True, default=dict)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'consultations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['current_state']),
            models.Index(fields=['patient', '-created_at']),
        ]
    
    def __str__(self):
        return f"Consultation {self.id} - {self.get_current_state_display()}"

class Symptom(models.Model):
    """Individual symptom records"""
    INPUT_TYPE_CHOICES = [
        ('text', 'Text'),
        ('voice', 'Voice'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name='symptom_list')
    description = models.TextField()
    duration = models.CharField(max_length=100, blank=True)
    severity = models.IntegerField(null=True, blank=True)
    input_type = models.CharField(max_length=10, choices=INPUT_TYPE_CHOICES, default='text')
    
    # For voice input
    audio_file = models.FileField(upload_to='symptoms/audio/', null=True, blank=True)
    transcript = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'symptoms'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Symptom for {self.consultation.id} - {self.description[:50]}"

class LabTest(models.Model):
    """Lab test records"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    PRIORITY_CHOICES = [
        ('routine', 'Routine'),
        ('urgent', 'Urgent'),
        ('stat', 'STAT'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name='lab_test_list')
    test_name = models.CharField(max_length=200)
    test_type = models.CharField(max_length=50, default='blood')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='routine')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    results = models.JSONField(null=True, blank=True, default=dict)
    clinical_indication = models.TextField(blank=True)
    
    # Tracking
    ordered_by = models.CharField(max_length=100, default='system')
    ordered_date = models.DateTimeField(auto_now_add=True)
    completed_date = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'lab_tests'
        ordering = ['-ordered_date']
    
    def __str__(self):
        return f"{self.test_name} - {self.status}"

class Prescription(models.Model):
    """Prescription records"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name='prescription_list')
    medications = models.JSONField(default=list)  # List of medications with dosage
    instructions = models.TextField(blank=True)
    duration = models.CharField(max_length=100, blank=True)
    prescribed_by = models.CharField(max_length=100, default='ai_system')
    prescribed_date = models.DateTimeField(auto_now_add=True)
    
    # Pharmacy info
    sent_to_pharmacy = models.BooleanField(default=False)
    pharmacy_response = models.JSONField(null=True, blank=True, default=dict)
    sent_date = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'prescriptions'
        ordering = ['-prescribed_date']
    
    def __str__(self):
        return f"Prescription for {self.consultation.id}"

class ClarificationQuestion(models.Model):
    """Store clarifying questions for symptoms"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name='clarification_questions')
    question = models.TextField()
    answer = models.TextField(blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'clarification_questions'
        ordering = ['created_at']
    
    def __str__(self):
        return f"Q: {self.question[:50]}"
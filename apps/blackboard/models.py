from django.db import models
import uuid
from django.contrib.postgres.fields import JSONField
from django.utils import timezone

class BlackboardEntry(models.Model):
    """
    Represents a consultation state in the blackboard
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consultation_id = models.UUIDField(db_index=True)
    agent_name = models.CharField(max_length=100)
    state = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    lock_acquired = models.BooleanField(default=False)
    lock_owner = models.CharField(max_length=100, null=True, blank=True)
    lock_expires_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'blackboard_entries'
        indexes = [
            models.Index(fields=['consultation_id', '-created_at']),
            models.Index(fields=['lock_acquired', 'lock_expires_at']),
        ]
        
    def __str__(self):
        return f"Entry for {self.consultation_id} by {self.agent_name}"

class BlackboardHistory(models.Model):
    """
    Audit trail of all blackboard changes
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consultation_id = models.UUIDField(db_index=True)
    agent_name = models.CharField(max_length=100)
    action = models.CharField(max_length=200)
    changes = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'blackboard_history'
        ordering = ['-created_at']
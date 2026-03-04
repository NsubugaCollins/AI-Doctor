"""
Agent models - re-export from agent_session for backwards compatibility.
AgentMemory for long-term agent learning.
"""
from django.db import models
from django.utils import timezone
import uuid

# Re-export for Django discovery and backwards compatibility
from .agent_session import AgentSession, GPTInteractionLog  # noqa: F401


class AgentMemory(models.Model):
    """Long-term memory for agent learning - symptom patterns to diagnosis mapping."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    symptom_pattern = models.TextField(db_index=True)
    diagnosis_result = models.JSONField(default=dict)
    success_rating = models.FloatField(default=1.0)
    use_count = models.IntegerField(default=1)
    last_used = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'agent_memory'

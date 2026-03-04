"""
Agent Session Management for tracking and persisting agent runs
"""

import uuid
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from django.utils import timezone
from django.db import models

logger = logging.getLogger(__name__)

class AgentSession(models.Model):
    """
    Model to save agent state and history - this is the database model
    """
    AGENT_TYPES = [
        ('symptom_agent', 'Symptom Agent'),
        ('diagnosis_agent', 'Diagnosis Agent'),
        ('lab_agent', 'Lab Agent'),
        ('controller', 'Controller'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('interrupted', 'Interrupted'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consultation_id = models.UUIDField(db_index=True)
    agent_type = models.CharField(max_length=20, choices=AGENT_TYPES)
    
    # Session data
    input_data = models.JSONField(default=dict, help_text="Input provided to the agent")
    output_data = models.JSONField(default=dict, help_text="Output produced by the agent")
    session_data = models.JSONField(default=dict, help_text="Internal session state")
    
    # Metrics
    tokens_used = models.IntegerField(default=0, help_text="Total tokens used in this session")
    cost = models.DecimalField(max_digits=10, decimal_places=6, default=0, help_text="Cost in USD")
    processing_time = models.FloatField(null=True, help_text="Processing time in seconds")
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'agent_sessions'
        indexes = [
            models.Index(fields=['consultation_id']),
            models.Index(fields=['agent_type']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.agent_type} - {self.consultation_id} - {self.created_at}"
    
    def mark_completed(self, output_data: Dict[str, Any], processing_time: float):
        """Mark session as completed"""
        self.output_data = output_data
        self.processing_time = processing_time
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['output_data', 'processing_time', 'status', 'completed_at'])
        logger.info(f"Session {self.id} completed in {processing_time:.2f}s")
    
    def mark_failed(self, error: str):
        """Mark session as failed"""
        self.status = 'failed'
        self.error_message = str(error)
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'error_message', 'completed_at'])
        logger.error(f"Session {self.id} failed: {error}")
    
    def update_tokens(self, tokens: int, cost: float):
        """Update token usage and cost"""
        self.tokens_used = tokens
        self.cost = cost
        self.save(update_fields=['tokens_used', 'cost'])


class GPTInteractionLog(models.Model):
    """
    Log all GPT interactions for audit and debugging
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(AgentSession, on_delete=models.CASCADE, null=True, related_name='gpt_logs')
    consultation_id = models.UUIDField(db_index=True, null=True)
    
    # Request/Response
    model_used = models.CharField(max_length=50)
    prompt = models.TextField()
    response = models.TextField()
    
    # Token usage
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    
    # Performance
    response_time = models.FloatField(help_text="Response time in seconds")
    
    # Status
    success = models.BooleanField(default=True)
    error = models.TextField(blank=True)
    
    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'gpt_interaction_logs'
        indexes = [
            models.Index(fields=['consultation_id']),
            models.Index(fields=['session']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"GPT Log {self.id} - {self.model_used} - {self.total_tokens} tokens"


class SessionManager:
    """
    Manager class for handling agent sessions
    """
    
    def __init__(self, agent_type: str, consultation_id: str):
        self.agent_type = agent_type
        # Ensure consultation_id is a string (will be converted to UUID by Django)
        self.consultation_id = str(consultation_id)
        self.session = None
        self.start_time = None
    
    def create_session(self, input_data: Dict[str, Any]) -> AgentSession:
        """Create a new session"""
        self.session = AgentSession.objects.create(
            consultation_id=self.consultation_id,
            agent_type=self.agent_type,
            input_data=input_data,
            status='processing'
        )
        self.start_time = timezone.now()
        logger.info(f"Created session {self.session.id} for {self.agent_type}")
        return self.session
    
    def log_gpt_interaction(self,
                           model: str,
                           prompt: str,
                           response: str,
                           prompt_tokens: int,
                           completion_tokens: int,
                           response_time: float,
                           success: bool = True,
                           error: str = '') -> GPTInteractionLog:
        """Log a GPT interaction"""
        
        total_tokens = prompt_tokens + completion_tokens
        
        # Calculate cost (GPT-4 pricing: $0.03/1K prompt, $0.06/1K completion)
        cost = (prompt_tokens / 1000 * 0.03) + (completion_tokens / 1000 * 0.06)
        
        log = GPTInteractionLog.objects.create(
            session=self.session,
            consultation_id=self.consultation_id,
            model_used=model,
            prompt=prompt[:5000],  # Truncate for storage
            response=response[:5000],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=cost,
            response_time=response_time,
            success=success,
            error=error
        )
        
        # Update session token count
        if self.session:
            self.session.tokens_used += total_tokens
            self.session.cost += cost
            self.session.save(update_fields=['tokens_used', 'cost'])
        
        return log
    
    def complete_session(self, output_data: Dict[str, Any]) -> AgentSession:
        """Mark session as completed"""
        if self.session and self.start_time:
            processing_time = (timezone.now() - self.start_time).total_seconds()
            self.session.mark_completed(output_data, processing_time)
        return self.session
    
    def fail_session(self, error: str) -> AgentSession:
        """Mark session as failed"""
        if self.session:
            self.session.mark_failed(error)
        return self.session
    
    @staticmethod
    def get_session(session_id: str) -> Optional[AgentSession]:
        """Get a session by ID"""
        try:
            return AgentSession.objects.get(id=session_id)
        except AgentSession.DoesNotExist:
            return None
    
    @staticmethod
    def get_consultation_sessions(consultation_id: str, 
                                  agent_type: Optional[str] = None,
                                  limit: int = 10) -> List[AgentSession]:
        """Get all sessions for a consultation"""
        queryset = AgentSession.objects.filter(consultation_id=consultation_id)
        if agent_type:
            queryset = queryset.filter(agent_type=agent_type)
        return queryset.order_by('-created_at')[:limit]
    
    @staticmethod
    def get_statistics(days: int = 7) -> Dict[str, Any]:
        """Get session statistics for last N days"""
        cutoff = timezone.now() - timezone.timedelta(days=days)
        sessions = AgentSession.objects.filter(created_at__gte=cutoff)
        
        total_sessions = sessions.count()
        completed = sessions.filter(status='completed').count()
        failed = sessions.filter(status='failed').count()
        
        # Cost statistics
        total_cost = sum(s.cost for s in sessions)
        avg_cost = total_cost / total_sessions if total_sessions > 0 else 0
        
        # Token statistics
        total_tokens = sum(s.tokens_used for s in sessions)
        
        # By agent type
        by_agent = {}
        for agent_type, _ in AgentSession.AGENT_TYPES:
            agent_sessions = sessions.filter(agent_type=agent_type)
            if agent_sessions.exists():
                by_agent[agent_type] = {
                    'count': agent_sessions.count(),
                    'cost': sum(s.cost for s in agent_sessions),
                    'tokens': sum(s.tokens_used for s in agent_sessions)
                }
        
        return {
            'period_days': days,
            'total_sessions': total_sessions,
            'completed': completed,
            'failed': failed,
            'success_rate': (completed / total_sessions * 100) if total_sessions > 0 else 0,
            'total_cost': float(total_cost),
            'average_cost': float(avg_cost),
            'total_tokens': total_tokens,
            'by_agent': by_agent
        }
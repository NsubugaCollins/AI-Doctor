from abc import ABC, abstractmethod
from django.utils import timezone

from typing import Dict, Any, Optional, List
from openai import OpenAI, APIError, RateLimitError
from django.conf import settings

import json
import logging
import time
import traceback
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from apps.agents.models import AgentSession, GPTInteractionLog, AgentMemory

logger = logging.getLogger(__name__)

class AgentContext:
    """Context shared between agents"""
    def __init__(self, consultation_id: str, patient_info: Dict[str, Any]):
        self.consultation_id = consultation_id
        self.patient_info = patient_info
        self.symptoms = None
        self.diagnosis = None
        self.lab_tests = []
        self.lab_results = []
        self.prescription = None
        self.current_state = "initial"
        self.pdf_sources = []
        self.history = []
        self.session_id = None  # Link to database session

class BaseAgent(ABC):
    """Base class for all GPT-4 agents with built-in saving and monitoring"""
    
    def __init__(self, name: str, system_prompt: str):
        self.name = name
        self.system_prompt = system_prompt
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
        self.temperature = getattr(settings, 'OPENAI_TEMPERATURE', 0.3)
        self.max_retries = getattr(settings, 'OPENAI_MAX_RETRIES', 3)
        
        # Current session tracking
        self.current_session = None
        self.current_context = None
        
    @abstractmethod
    def process(self, context: AgentContext) -> AgentContext:
        """Process method to be implemented by child classes"""
        pass
    
    def run_with_session(self, context: AgentContext, input_data: Dict[str, Any] = None) -> AgentContext:
        """
        Run agent with automatic session saving
        """
        start_time = time.time()
        
        # Create session record
        self.current_session = AgentSession.objects.create(
            consultation_id=context.consultation_id,
            agent_type=self.name,
            input_data=input_data or {},
            session_data={
                'patient_info': context.patient_info,
                'current_state': context.current_state,
                'history': context.history[-10:]  # Last 10 events
            },
            status='processing'
        )
        
        # Link session to context
        context.session_id = str(self.current_session.id)
        self.current_context = context
        
        logger.info(f"🤖 Agent {self.name} started for consultation {context.consultation_id}")
        
        try:
            # Run the actual agent logic
            result_context = self.process(context)
            
            # Calculate metrics
            processing_time = time.time() - start_time
            
            # Update session with results
            self.current_session.output_data = {
                'diagnosis': result_context.diagnosis,
                'lab_tests': result_context.lab_tests,
                'prescription': result_context.prescription,
                'current_state': result_context.current_state
            }
            self.current_session.processing_time = processing_time
            self.current_session.status = 'completed'
            self.current_session.save()
            
            logger.info(f"✅ Agent {self.name} completed in {processing_time:.2f}s")
            
            return result_context
            
        except Exception as e:
            # Save error state
            self.current_session.status = 'failed'
            self.current_session.error_message = str(e)
            self.current_session.save()
            
            logger.error(f"❌ Agent {self.name} failed: {e}")
            logger.error(traceback.format_exc())
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((RateLimitError, APIError))
    )
    def call_gpt4(self, 
                  messages: List[Dict[str, str]], 
                  response_format: Optional[Dict] = None,
                  temperature: Optional[float] = None) -> str:
        """
        Call GPT-4 with retry logic and automatic logging
        """
        start_time = time.time()
        
        # Prepare request parameters
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "max_tokens": getattr(settings, 'OPENAI_MAX_TOKENS', 4000)
        }
        
        if response_format:
            kwargs["response_format"] = {"type": "json_object"}
        
        # Count approximate tokens for logging
        prompt_text = json.dumps(messages)
        approx_tokens = len(prompt_text) // 4  # Rough estimate
        
        logger.debug(f"Calling GPT-4 with {approx_tokens} estimated tokens")
        
        try:
            # Make the API call
            response = self.client.chat.completions.create(**kwargs)
            
            # Extract response
            result = response.choices[0].message.content
            
            # Calculate metrics
            response_time = time.time() - start_time
            
            # Get token usage if available
            prompt_tokens = response.usage.prompt_tokens if hasattr(response, 'usage') else approx_tokens
            completion_tokens = response.usage.completion_tokens if hasattr(response, 'usage') else len(result) // 4
            total_tokens = prompt_tokens + completion_tokens
            
            # Save interaction log
            self._save_gpt_interaction(
                prompt=prompt_text[:5000],  # Truncate for storage
                response=result[:5000],
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                response_time=response_time,
                success=True
            )
            
            logger.info(f"GPT-4 call successful: {total_tokens} tokens in {response_time:.2f}s")
            
            return result
            
        except RateLimitError as e:
            logger.warning(f"Rate limit hit, retrying: {e}")
            self._save_gpt_interaction(
                prompt=prompt_text[:5000],
                response="",
                prompt_tokens=approx_tokens,
                completion_tokens=0,
                total_tokens=approx_tokens,
                response_time=time.time() - start_time,
                success=False,
                error=str(e)
            )
            raise
            
        except APIError as e:
            logger.error(f"OpenAI API error: {e}")
            self._save_gpt_interaction(
                prompt=prompt_text[:5000],
                response="",
                prompt_tokens=approx_tokens,
                completion_tokens=0,
                total_tokens=approx_tokens,
                response_time=time.time() - start_time,
                success=False,
                error=str(e)
            )
            raise
            
        except Exception as e:
            logger.error(f"Unexpected error in GPT call: {e}")
            self._save_gpt_interaction(
                prompt=prompt_text[:5000],
                response="",
                prompt_tokens=approx_tokens,
                completion_tokens=0,
                total_tokens=approx_tokens,
                response_time=time.time() - start_time,
                success=False,
                error=str(e)
            )
            raise
    
    def _save_gpt_interaction(self, 
                              prompt: str,
                              response: str,
                              prompt_tokens: int,
                              completion_tokens: int,
                              total_tokens: int,
                              response_time: float,
                              success: bool = True,
                              error: str = ''):
        """Save GPT interaction to database"""
        try:
            # Calculate cost (adjust based on your model)
            # GPT-4: $0.03 per 1K prompt tokens, $0.06 per 1K completion tokens
            cost = (prompt_tokens / 1000 * 0.03) + (completion_tokens / 1000 * 0.06)
            
            GPTInteractionLog.objects.create(
                consultation_id=self.current_context.consultation_id if self.current_context else None,
                session=self.current_session,
                model_used=self.model,
                prompt=prompt,
                response=response,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost=cost,
                response_time=response_time,
                success=success,
                error=error
            )
        except Exception as e:
            logger.error(f"Failed to save GPT interaction: {e}")
    
    def call_gpt4_structured(self, 
                              messages: List[Dict[str, str]], 
                              temperature: Optional[float] = None) -> Dict[str, Any]:
        """
        Call GPT-4 and parse JSON response
        """
        response = self.call_gpt4(messages, response_format={"type": "json_object"}, temperature=temperature)
        
        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {response[:500]}")
            
            # Try to extract JSON from text
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except:
                    pass
            
            return {
                "error": "Failed to parse response",
                "raw_response": response[:500],
                "diagnosis": [{"condition": "Unable to determine", "probability": 0.5}]
            }
    
    def update_context(self, context: AgentContext, updates: Dict[str, Any]) -> AgentContext:
        """Update context with new data"""
        for key, value in updates.items():
            if hasattr(context, key):
                setattr(context, key, value)
        
        # Add to history
        history_entry = {
            "timestamp": timezone.now().isoformat(),
            "agent": self.name,
            "action": updates.get("action", "update"),
            "state": context.current_state
        }
        
        # Add details if present
        if "details" in updates:
            history_entry["details"] = updates["details"]
        
        context.history.append(history_entry)
        
        # Keep history manageable
        if len(context.history) > 100:
            context.history = context.history[-100:]
        
        # Update session if active
        if self.current_session:
            self.current_session.session_data['history'] = context.history[-20:]
            self.current_session.save(update_fields=['session_data'])
        
        return context
    
    def find_similar_cases(self, symptoms: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Find similar cases from agent memory
        """
        try:
            # Simple keyword matching
            symptom_keywords = set(symptoms.lower().split())
            similar_cases = []
            
            # Get recent successful diagnoses from same agent type
            recent_sessions = AgentSession.objects.filter(
                agent_type=self.name,
                status='completed'
            ).order_by('-created_at')[:50]
            
            for session in recent_sessions:
                if session.output_data and 'diagnosis' in session.output_data:
                    # Get symptoms from session input
                    session_symptoms = session.input_data.get('symptoms', {}).get('description', '')
                    session_keywords = set(session_symptoms.lower().split())
                    
                    # Calculate similarity
                    overlap = len(symptom_keywords & session_keywords)
                    if overlap > 3:  # At least 3 matching keywords
                        similarity = overlap / max(len(symptom_keywords), len(session_keywords))
                        similar_cases.append({
                            'session': session,
                            'similarity': similarity,
                            'diagnosis': session.output_data.get('diagnosis')
                        })
            
            # Sort by similarity
            similar_cases.sort(key=lambda x: x['similarity'], reverse=True)
            
            return similar_cases[:limit]
            
        except Exception as e:
            logger.error(f"Error finding similar cases: {e}")
            return []
    
    def save_to_memory(self, symptoms: str, diagnosis: Dict[str, Any], success_rating: float = 1.0):
        """
        Save successful diagnosis to long-term memory
        """
        try:
            # Extract key symptoms (first 100 chars)
            key_symptoms = symptoms[:200]
            
            memory, created = AgentMemory.objects.get_or_create(
                symptom_pattern=key_symptoms,
                defaults={
                    'diagnosis_result': diagnosis,
                    'success_rating': success_rating
                }
            )
            
            if not created:
                memory.use_count += 1
                memory.success_rating = (memory.success_rating * memory.use_count + success_rating) / (memory.use_count + 1)
                memory.last_used = timezone.now()
                memory.save()
            
            logger.info(f"Saved to memory: {key_symptoms[:50]}... (new: {created})")
            
        except Exception as e:
            logger.error(f"Failed to save to memory: {e}")
    
    def get_session_history(self, consultation_id: str, limit: int = 5) -> List[AgentSession]:
        """
        Get previous agent sessions for this consultation
        """
        return AgentSession.objects.filter(
            consultation_id=consultation_id,
            agent_type=self.name
        ).order_by('-created_at')[:limit]
    
    def resume_from_session(self, session_id: str) -> Optional[AgentContext]:
        """
        Resume agent from a saved session
        """
        try:
            session = AgentSession.objects.get(id=session_id)
            
            # Reconstruct context
            context = AgentContext(
                consultation_id=str(session.consultation_id),
                patient_info=session.session_data.get('patient_info', {})
            )
            
            # Restore state
            context.current_state = session.session_data.get('current_state', 'initial')
            context.history = session.session_data.get('history', [])
            
            if session.output_data:
                context.diagnosis = session.output_data.get('diagnosis')
                context.lab_tests = session.output_data.get('lab_tests', [])
                context.prescription = session.output_data.get('prescription')
            
            logger.info(f"Resumed session {session_id}")
            
            return context
            
        except AgentSession.DoesNotExist:
            logger.error(f"Session {session_id} not found")
            return None
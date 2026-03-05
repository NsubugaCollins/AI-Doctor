"""
Symptom Agent with GPT-4 for symptom analysis and clarification
Integrated with autonomous system
"""

import logging
from typing import Dict, Any, Optional
from django.utils import timezone

from asgiref.sync import sync_to_async

from apps.agents.open_ai_service import get_openai_service
from apps.blackboard.services import BlackboardService
from apps.agents.agent_session import SessionManager
from apps.consultations.models import Symptom

logger = logging.getLogger(__name__)

class SymptomAgent:
    """
    Agent responsible for processing and analyzing symptoms
    Can use GPT-4 to extract structured information and ask clarifying questions
    Integrated with autonomous controller
    """
    
    def __init__(self):
        self.openai = get_openai_service()
        self.blackboard = BlackboardService()
        self.session_manager = None
    
    async def run(self, consultation_id: str) -> Dict[str, Any]:
        """
        Main entry point for autonomous controller
        Processes symptoms and stores analysis in blackboard
        """
        # Ensure consultation_id is a string
        consultation_id = str(consultation_id)
        
        logger.info(f"🤒 SymptomAgent running for consultation {consultation_id}")
        
        # Initialize session
        self.session_manager = SessionManager('symptom_agent', consultation_id)
        await sync_to_async(self.session_manager.create_session)({
            'consultation_id': consultation_id,
            'action': 'symptom_analysis'
        })
        
        try:
            # Get consultation data from blackboard
            consultation_data = await sync_to_async(self.blackboard.read)(consultation_id)
            if not consultation_data:
                error_msg = f"Consultation {consultation_id} not found"
                logger.error(error_msg)
                await sync_to_async(self.session_manager.fail_session)(error_msg)
                return {'status': 'error', 'error': error_msg}
            
            # Get symptoms from blackboard
            symptoms = consultation_data.get('symptoms')
            if not symptoms:
                # Recovery path: symptoms may exist in DB but not yet written to blackboard
                latest_symptom = await sync_to_async(
                    lambda: Symptom.objects.filter(consultation_id=consultation_id).order_by('-created_at').first()
                )()

                if latest_symptom:
                    symptoms = {
                        "description": latest_symptom.description,
                        "duration": latest_symptom.duration,
                        "severity": latest_symptom.severity,
                        "input_type": latest_symptom.input_type,
                    }
                    await sync_to_async(self.blackboard.write)(
                        consultation_id,
                        {"symptoms": symptoms, "current_state": "initial"},
                        "symptom_agent",
                    )
                    logger.info(f"Recovered symptoms from DB for {consultation_id}")
                else:
                    logger.info(f"No symptoms yet for {consultation_id}, waiting...")
                    await sync_to_async(self.session_manager.complete_session)({
                        'status': 'waiting',
                        'message': 'No symptoms available'
                    })
                    return {'status': 'waiting', 'message': 'Waiting for symptoms'}
            
            # Analyze symptoms with GPT-4
            analysis = await self._analyze_symptoms(symptoms)
            
            # Store analysis in blackboard
            await sync_to_async(self.blackboard.write)(
                consultation_id,
                {
                    'symptom_analysis': analysis,
                    'current_state': 'symptoms_collected'
                },
                'symptom_agent'
            )
            
            # Complete session
            await sync_to_async(self.session_manager.complete_session)({
                'symptoms': symptoms,
                'analysis': analysis,
                'needs_clarification': analysis.get('needs_more_info', False)
            })
            
            logger.info(f"✅ SymptomAgent completed for {consultation_id}")
            
            # Persist session summary locally for future use
            try:
                from .persistence import save_agent_session_summary
                save_agent_session_summary('symptom_agent', consultation_id, {
                    'symptoms': symptoms,
                    'analysis': analysis,
                })
            except Exception as e:
                logger.debug(f"Could not persist symptom session: {e}")
            
            # Check if we need more information
            if analysis.get('needs_more_info', False):
                return {
                    'status': 'needs_clarification',
                    'questions': analysis.get('clarifying_questions', []),
                    'analysis': analysis
                }
            
            return {
                'status': 'success',
                'analysis': analysis,
                'session_id': str(self.session_manager.session.id) if self.session_manager.session else None
            }
            
        except Exception as e:
            logger.error(f"❌ SymptomAgent failed: {e}")
            await sync_to_async(self.session_manager.fail_session)(str(e))
            return {'status': 'error', 'error': str(e)}
    
    async def process_symptoms(
        self,
        consultation_id: str,
        symptoms: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process raw symptoms and extract structured information
        Called from views when user submits symptoms
        """
        logger.info(f"Processing symptoms for consultation {consultation_id}")
        
        # Store raw symptoms in blackboard
        await sync_to_async(self.blackboard.write)(
            consultation_id,
            {"symptoms": symptoms},
            "symptom_agent"
        )
        
        # Analyze symptoms with GPT-4
        analysis = await self._analyze_symptoms(symptoms)
        
        # Store analysis in blackboard
        await sync_to_async(self.blackboard.write)(
            consultation_id,
            {
                "symptom_analysis": analysis,
                "current_state": "symptoms_collected"  # This will trigger the controller
            },
            "symptom_agent"
        )
        
        # Send WebSocket notification
        await self._send_websocket_update(consultation_id, {
            'event': 'symptoms_processed',
            'analysis': analysis
        })
        
        # Check if we need more information
        if analysis.get('needs_more_info', False):
            return {
                "status": "needs_clarification",
                "questions": analysis.get('clarifying_questions', []),
                "symptoms": symptoms,
                "analysis": analysis
            }
        
        return {
            "status": "complete",
            "analysis": analysis,
            "symptoms": symptoms
        }
    
    async def _analyze_symptoms(self, symptoms: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use GPT-4 to analyze and structure symptoms
        """
        messages = [
            {
                "role": "system",
                "content": """You are a medical symptom analysis AI. Extract structured information from symptom descriptions.
Identify key symptoms, duration, severity, and determine if more information is needed."""
            },
            {
                "role": "user",
                "content": f"""
Analyze these symptoms:
Description: {symptoms.get('description', '')}
Duration: {symptoms.get('duration', 'Not specified')}
Severity: {symptoms.get('severity', 'Not specified')}/10

Return a JSON object with:
- primary_symptoms: list of main symptoms identified
- duration_days: estimated duration in days (or null if unclear)
- severity_level: confirmed severity (1-10)
- urgent_indicators: list of any urgent symptoms detected
- needs_more_info: boolean indicating if clarifying questions are needed
- clarifying_questions: list of questions if more info needed
- structured_summary: a clean summary of the symptoms
- possible_conditions: list of possible conditions based on symptoms (preliminary)
"""
            }
        ]
        
        try:
            # Run OpenAI call in thread pool since it's sync
            from asgiref.sync import sync_to_async
            result = await sync_to_async(self.openai.structured_completion)(messages)
            return result
        except Exception as e:
            logger.error(f"Failed to analyze symptoms: {e}")
            return {
                "primary_symptoms": [symptoms.get('description', '')],
                "needs_more_info": False,
                "error": str(e),
                "structured_summary": symptoms.get('description', '')
            }
    
    async def extract_from_voice(self, transcript: str) -> Dict[str, Any]:
        """
        Extract structured symptoms from voice transcript
        """
        messages = [
            {
                "role": "system",
                "content": "Extract medical symptoms from voice transcript. Return structured JSON."
            },
            {
                "role": "user",
                "content": f"""
Extract symptoms from this transcript:
"{transcript}"

Return JSON with:
- description: cleaned symptom description
- duration: estimated duration if mentioned
- severity: estimated severity (1-10) if mentioned
- primary_symptoms: list of main symptoms
- confidence: high/medium/low
"""
            }
        ]
        
        try:
            from asgiref.sync import sync_to_async
            result = await sync_to_async(self.openai.structured_completion)(messages)
            result['input_type'] = 'voice'
            result['original_transcript'] = transcript
            return result
        except Exception as e:
            logger.error(f"Failed to extract from voice: {e}")
            return {
                "description": transcript,
                "input_type": "voice",
                "confidence": "low",
                "primary_symptoms": [transcript[:100]]
            }
    
    async def add_clarification(
        self,
        consultation_id: str,
        answers: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Add clarifying answers to symptoms
        """
        logger.info(f"Adding clarification for consultation {consultation_id}")
        
        # Get current consultation data
        consultation_data = await sync_to_async(self.blackboard.read)(consultation_id)
        if not consultation_data:
            return {'status': 'error', 'error': 'Consultation not found'}
        
        # Get current symptoms
        current_symptoms = consultation_data.get('symptoms', {})
        current_analysis = consultation_data.get('symptom_analysis', {})
        
        # Enhance symptoms with answers
        enhanced_description = current_symptoms.get('description', '')
        for question, answer in answers.items():
            enhanced_description += f" [Additional info: {answer}]"
        
        # Create enhanced symptoms
        enhanced_symptoms = current_symptoms.copy()
        enhanced_symptoms['description'] = enhanced_description
        enhanced_symptoms['clarification_answers'] = answers
        enhanced_symptoms['clarified_at'] = timezone.now().isoformat()
        
        # Re-analyze with new information
        new_analysis = await self._analyze_symptoms(enhanced_symptoms)
        
        # Update blackboard
        await sync_to_async(self.blackboard.write)(
            consultation_id,
            {
                'symptoms': enhanced_symptoms,
                'symptom_analysis': new_analysis,
                'current_state': 'symptoms_collected'
            },
            'symptom_agent'
        )
        
        # Send WebSocket update
        await self._send_websocket_update(consultation_id, {
            'event': 'symptoms_clarified',
            'analysis': new_analysis
        })
        
        return {
            'status': 'success',
            'analysis': new_analysis,
            'symptoms': enhanced_symptoms
        }
    
    async def _send_websocket_update(self, consultation_id: str, data: Dict[str, Any]):
        """
        Send real-time update via WebSocket
        """
        try:
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            await channel_layer.group_send(
                f"consultation_{consultation_id}",
                {
                    'type': 'consultation_update',
                    'data': data
                }
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket update: {e}")
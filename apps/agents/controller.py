

import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import random
from asgiref.sync import async_to_sync, sync_to_async

from apps.blackboard.services import BlackboardService
from apps.consultations.models import Consultation
from .symptom_agent import SymptomAgent
from .diagnosis_agent import DiagnosisAgent
from .lab_agent import LabAgent
from .models import AgentSession

logger = logging.getLogger(__name__)


def _get_channel_layer():
    """Get channel layer; return None if channels_redis not installed or misconfigured."""
    try:
        from channels.layers import get_channel_layer
        return get_channel_layer()
    except Exception as e:
        logger.warning("Channel layer unavailable (install channels-redis for WebSocket updates): %s", e)
        return None


class AsyncAutonomousController:
    """
    Async controller that autonomously orchestrates agents based on blackboard state
    Runs continuously in the background
    """
    
    def __init__(self):
        self.blackboard = BlackboardService()
        self.symptom_agent = SymptomAgent()
        self.diagnosis_agent = DiagnosisAgent()
        self.lab_agent = LabAgent()
        
        self.channel_layer = _get_channel_layer()
        self.running = True
        self.worker_task = None
        
        # State machine - defines which agent runs for each state
        self.workflow = {
            # State -> (agent, next_state_if_success, next_state_if_failure)
            'initial': ('symptom_agent', 'symptoms_collected', 'failed'),
            'symptoms_collected': ('diagnosis_agent', 'diagnosis_complete', 'diagnosis_failed'),
            'diagnosis_complete': ('lab_agent', 'lab_tests_ordered', 'lab_failed'),
            'lab_tests_ordered': ('lab_agent', 'lab_tests_complete', 'lab_failed'),
            'lab_tests_complete': ('diagnosis_agent', 'final_diagnosis_ready', 'diagnosis_failed'),
            'final_diagnosis_ready': ('lab_agent', 'prescription_sent', 'prescription_failed'),
            'prescription_sent': (None, 'completed', 'completed'),  # End state
        }
        
        # Persist agent registry locally for future use
        try:
            from .persistence import persist_agents_on_shutdown, list_saved_agents
            saved = list_saved_agents()
            if saved:
                logger.info(f"Loaded saved agents: {saved}")
        except Exception as e:
            logger.debug(f"Agent persistence check: {e}")
        
        logger.info(" Async Autonomous Controller initialized")
    
    def start(self):
        """Start the autonomous controller in an async background task"""
        if not self.worker_task or self.worker_task.done():
            self.running = True
            self.worker_task = asyncio.create_task(self._run_loop())
            logger.info(" Async Autonomous Controller started")
    
    async def stop(self):
        """Stop the autonomous controller"""
        self.running = False
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
            logger.info(" Async Autonomous Controller stopped")
    
    async def _run_loop(self):
        logger.info("Controller loop started (offline mode)")
        while self.running:
            try:
                # Process consultations
                await self._process_pending_consultations()
                
                # Simulate lab results for offline testing
                await self._check_lab_results()
                
                await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Controller loop error: {e}")
                await asyncio.sleep(5)
    
    async def _process_pending_consultations(self):
        """Process all consultations that need attention"""
        # Get all active consultations
        for state in self.workflow.keys():
            if state in ['completed', 'failed']:
                continue
                
            consultations = await sync_to_async(self.blackboard.get_consultations_by_state)(state)
            
            for consultation_id in consultations:
                # Ensure consultation_id is a string
                await self._process_consultation(str(consultation_id))
    
    async def _process_consultation(self, consultation_id: str):
        """Process a single consultation through its next step"""
        try:
            # Get current state
            consultation_data = await sync_to_async(self.blackboard.read)(consultation_id)
            if not consultation_data:
                return
            
            current_state = consultation_data.get('current_state', 'initial')
            
            # Check if we're at a terminal state
            if current_state in ['completed', 'failed']:
                return
            
            # Get next step from workflow
            workflow_step = self.workflow.get(current_state)
            if not workflow_step:
                logger.warning(f"No workflow step for state {current_state}")
                return
            
            agent_name, success_state, failure_state = workflow_step
            
            if not agent_name:
                # End of workflow
                await sync_to_async(self.blackboard.write)(consultation_id, {
                    'current_state': 'completed',
                    'completed_at': datetime.now().isoformat()
                }, 'controller')
                try:
                    await sync_to_async(Consultation.objects.filter(id=consultation_id).update)(
                        current_state='completed',
                        completed_at=datetime.now()
                    )
                except Exception:
                    pass
                logger.info(f"Consultation {consultation_id} completed")
                await self._send_websocket_update(consultation_id, {
                    'event': 'consultation_completed',
                    'state': 'completed'
                })
                return
            
            # Get the agent
            agent = self._get_agent(agent_name)
            if not agent:
                logger.error(f"Agent {agent_name} not found")
                return
            
            # Try to acquire lock
            lock_acquired = await sync_to_async(self.blackboard.acquire_lock)(consultation_id, agent_name)
            if not lock_acquired:
                logger.debug(f"Could not acquire lock for {consultation_id}, another agent is processing")
                return
            
            try:
                # Run the agent (agents need to be async)
                logger.info(f" Running {agent_name} for consultation {consultation_id}")

                await self._send_websocket_update(consultation_id, {
                    "type": "agent_started",
                    "agent": agent_name,
                    "message": f"{self._format_agent_name(agent_name)} started",
                })
                
                if asyncio.iscoroutinefunction(agent.run):
                    result = await agent.run(consultation_id)
                else:
                    # Run sync agent in thread pool
                    result = await sync_to_async(agent.run)(consultation_id)

                status = result.get('status')

                # If agent is waiting (e.g. no symptoms yet), do not treat as failure.
                if status in ('waiting', 'needs_clarification'):
                    logger.info(
                        f" {agent_name} returned non-terminal status '{status}' "
                        f"for {consultation_id}, keeping state as {current_state}"
                    )
                    await self._send_websocket_update(consultation_id, {
                        "type": "agent_progress",
                        "agent": agent_name,
                        "message": result.get("message") or f"{self._format_agent_name(agent_name)} is waiting",
                        "progress": 5,
                    })
                    await self._send_websocket_update(consultation_id, {
                        "type": "consultation_update",
                        "data": {
                            "event": f"{agent_name}_{status}",
                            "state": current_state,
                            "result": result,
                        },
                    })
                    return
                
                if status == 'success':
                    # Update to next state
                    await sync_to_async(self.blackboard.write)(consultation_id, {
                        'current_state': success_state,
                        f'{agent_name}_completed_at': datetime.now().isoformat()
                    }, 'controller')
                    
                    logger.info(f" {agent_name} succeeded for {consultation_id} -> {success_state}")
                    
                    await self._send_websocket_update(consultation_id, {
                        "type": "agent_completed",
                        "agent": agent_name,
                        "message": f"{self._format_agent_name(agent_name)} completed",
                        "data": result,
                    })

                    await self._send_websocket_update(consultation_id, {
                        "type": "state_changed",
                        "old_state": current_state,
                        "new_state": success_state,
                        "message": f"Moved to {success_state}",
                    })

                    # Send real-time update (generic payload)
                    await self._send_websocket_update(consultation_id, {
                        "type": "consultation_update",
                        "data": {
                            "event": f"{agent_name}_completed",
                            "state": success_state,
                            "result": result,
                        },
                    })
                    
                else:
                    # Handle failure
                    error_msg = result.get('error', 'Unknown error')
                    errors = consultation_data.get('errors', []) + [{
                        'timestamp': datetime.now().isoformat(),
                        'agent': agent_name,
                        'error': error_msg
                    }]
                    
                    await sync_to_async(self.blackboard.write)(consultation_id, {
                        'current_state': failure_state,
                        'errors': errors
                    }, 'controller')
                    
                    logger.error(f" {agent_name} failed for {consultation_id}: {error_msg}")

                    await self._send_websocket_update(consultation_id, {
                        "type": "agent_completed",
                        "agent": agent_name,
                        "message": f"{self._format_agent_name(agent_name)} failed: {error_msg}",
                        "data": {"status": "error", "error": error_msg},
                    })
                    await self._send_websocket_update(consultation_id, {
                        "type": "state_changed",
                        "old_state": current_state,
                        "new_state": failure_state,
                        "message": f"Moved to {failure_state}",
                    })
                    
                    await self._send_websocket_update(consultation_id, {
                        "type": "consultation_update",
                        "data": {
                            "event": f"{agent_name}_failed",
                            "state": failure_state,
                            "error": error_msg,
                        },
                    })
                    
            except Exception as e:
                logger.error(f"Exception in {agent_name} for {consultation_id}: {e}")
                errors = consultation_data.get('errors', []) + [{
                    'timestamp': datetime.now().isoformat(),
                    'agent': agent_name,
                    'error': str(e)
                }]
                
                await sync_to_async(self.blackboard.write)(consultation_id, {
                    'current_state': failure_state,
                    'errors': errors
                }, 'controller')

                await self._send_websocket_update(consultation_id, {
                    "type": "agent_completed",
                    "agent": agent_name,
                    "message": f"{self._format_agent_name(agent_name)} crashed: {str(e)}",
                    "data": {"status": "error", "error": str(e)},
                })
                await self._send_websocket_update(consultation_id, {
                    "type": "state_changed",
                    "old_state": current_state,
                    "new_state": failure_state,
                    "message": f"Moved to {failure_state}",
                })
                
                await self._send_websocket_update(consultation_id, {
                    "type": "consultation_update",
                    "data": {
                        "event": f"{agent_name}_failed",
                        "state": failure_state,
                        "error": str(e),
                    },
                })
                
            finally:
                # Always release the lock
                await sync_to_async(self.blackboard.release_lock)(consultation_id, agent_name)
                
        except Exception as e:
            logger.error(f"Error processing consultation {consultation_id}: {e}")
    
    def _get_agent(self, agent_name: str):
        """Get agent by name"""
        agents = {
            'symptom_agent': self.symptom_agent,
            'diagnosis_agent': self.diagnosis_agent,
            'lab_agent': self.lab_agent,
        }
        return agents.get(agent_name)
    
    async def _check_lab_results(self):
        """Simulate checking for lab results from external systems"""
        consultations = await sync_to_async(self.blackboard.get_consultations_by_state)('lab_tests_ordered')
        
        for consultation_id in consultations:
            consultation_data = await sync_to_async(self.blackboard.read)(consultation_id)
            if not consultation_data:
                continue
            
            lab_tests = consultation_data.get('lab_tests', [])
            
            # Check if any tests are still pending
            pending_tests = [t for t in lab_tests if t.get('status') == 'pending']
            
            if pending_tests:
                # Simulate lab processing
                for test in pending_tests:
                    if random.random() < 0.3:  # 30% chance test is complete
                        test['status'] = 'completed'
                        test['results'] = self._generate_mock_results(test['test_name'])
                        test['completed_date'] = datetime.now().isoformat()
                
                await sync_to_async(self.blackboard.write)(consultation_id, {
                    'lab_tests': lab_tests
                }, 'lab_simulator')
                
                # Check if all tests are complete
                if all(t.get('status') == 'completed' for t in lab_tests):
                    await sync_to_async(self.blackboard.write)(consultation_id, {
                        'current_state': 'lab_tests_complete',
                        'lab_results': [t for t in lab_tests if t.get('status') == 'completed']
                    }, 'lab_simulator')
                    
                    logger.info(f"🔬 All lab tests complete for {consultation_id}")
                    
                    await self._send_websocket_update(consultation_id, {
                        'event': 'lab_tests_complete',
                        'state': 'lab_tests_complete'
                    })
    
    def _generate_mock_results(self, test_name: str) -> Dict[str, Any]:
        """Generate mock lab results for testing"""
        test_name_lower = test_name.lower()
        
        if 'blood' in test_name_lower or 'cbc' in test_name_lower:
            return {
                'wbc': '7.5 K/uL',
                'rbc': '4.8 M/uL',
                'hemoglobin': '14.2 g/dL',
                'hematocrit': '42%',
                'platelets': '250 K/uL',
                'interpretation': 'Within normal limits'
            }
        elif 'glucose' in test_name_lower:
            return {
                'fasting_glucose': '95 mg/dL',
                'interpretation': 'Normal'
            }
        elif 'lipid' in test_name_lower:
            return {
                'total_cholesterol': '180 mg/dL',
                'hdl': '45 mg/dL',
                'ldl': '110 mg/dL',
                'triglycerides': '150 mg/dL',
                'interpretation': 'Borderline high LDL'
            }
        else:
            return {
                'result': 'Normal',
                'interpretation': 'No abnormalities detected'
            }
    
    def _format_agent_name(self, agent_name: str) -> str:
        """Format agent name for display"""
        return agent_name.replace('_', ' ').title()
    
    async def _send_websocket_update(self, consultation_id: str, data: Dict[str, Any]):
        """Send real-time update via WebSocket"""
        if not self.channel_layer:
            return
        try:
            await self.channel_layer.group_send(
                f"consultation_{consultation_id}",
                {
                    'type': data.get('type', 'consultation_update').replace('-', '_'),
                    **data
                }
            )
        except Exception as e:
            logger.error(f"Failed to send WebSocket update: {e}")
    
    async def trigger_consultation(self, consultation_id: str):
        """Manually trigger processing for a consultation"""
        await self._process_consultation(consultation_id)
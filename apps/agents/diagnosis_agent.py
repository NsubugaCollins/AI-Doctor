"""
Diagnosis Agent powered by GPT-4 with RAG integration and session management
"""

import json
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

from apps.agents.open_ai_service import get_openai_service
from .agent_session import SessionManager
from apps.blackboard.services import BlackboardService
from apps.rag.services import PDFRAGService
from apps.consultations.models import Consultation, LabTest

logger = logging.getLogger(__name__)

class DiagnosisAgent:
    """
    Agent responsible for medical diagnosis using GPT-4 and RAG
    with built-in session management and cost tracking
    """
    
    def __init__(self):
        self.openai = get_openai_service()
        self.blackboard = BlackboardService()
        self.rag = PDFRAGService()
        self.session_manager = None
        
        # System prompt for the diagnosis agent
        self.system_prompt = """You are an expert medical diagnosis AI assistant. Your role is to:
1. Analyze patient symptoms carefully and systematically
2. Use the provided medical knowledge from PDFs to inform your decisions
3. Provide a differential diagnosis with probabilities
4. Recommend specific lab tests to confirm or rule out conditions
5. Assess urgency level (low/medium/high/critical)
6. Always cite your sources from the medical literature
7. Include clear reasoning steps

Remember: This is a clinical decision support tool. Always include appropriate medical disclaimers."""
    
    def run(self, consultation_id: str) -> Dict[str, Any]:
        """
        Main entry point - runs in two modes:
        1. Initial: symptoms + RAG -> diagnosis + lab test DOC
        2. After lab results: lab results + RAG -> prescription
        """
        # Ensure consultation_id is a string
        consultation_id = str(consultation_id)
        
        logger.info(f"DiagnosisAgent running for consultation {consultation_id}")
        
        self.session_manager = SessionManager('diagnosis_agent', consultation_id)
        # BlackboardService methods are synchronous; this agent runs in a worker thread.
        consultation_data = self.blackboard.read(consultation_id)
        if not consultation_data:
            logger.error(f"Consultation {consultation_id} not found")
            return {"status": "error", "error": "Consultation not found"}
        
        lab_results = consultation_data.get('lab_results') or consultation_data.get('lab_results_data')
        if lab_results:
            return self._run_prescription_phase(consultation_id, consultation_data)
        else:
            return self._run_initial_diagnosis_phase(consultation_id, consultation_data)
    
    def _run_initial_diagnosis_phase(self, consultation_id: str, consultation_data: Dict) -> Dict[str, Any]:
        """Reason with RAG to find disease and generate lab test DOC"""
        symptoms = consultation_data.get('symptoms', {}) or consultation_data.get('symptom_analysis', {})
        if not symptoms and not consultation_data.get('symptom_analysis'):
            return {"status": "error", "error": "No symptoms provided"}
        
        symptoms = symptoms or {}
        session = self.session_manager.create_session({
            'consultation_data': consultation_data,
            'symptoms': symptoms,
            'phase': 'initial_diagnosis',
            'timestamp': datetime.now().isoformat()
        })
        
        try:
            symptoms_text = symptoms.get('description', '') or str(symptoms.get('structured_summary', ''))
            rag_results = self.rag.search_similar_sync(symptoms_text, k=5) if symptoms_text else []
            
            messages = self._prepare_diagnosis_messages(consultation_data, symptoms, rag_results)
            diagnosis_result = self.openai.structured_completion(messages)
            
            processed_diagnosis = self._process_diagnosis_result(diagnosis_result, consultation_id)
            lab_tests = self._generate_lab_tests(processed_diagnosis, consultation_data)
            lab_tests_document = self._generate_lab_test_document(lab_tests, consultation_data)
            
            self.blackboard.write(
                consultation_id,
                {
                    "diagnosis": processed_diagnosis,
                    "lab_tests": lab_tests,
                    "lab_tests_document": lab_tests_document,
                    "rag_results": rag_results,
                    "diagnosis_completed_at": datetime.now().isoformat(),
                },
                "diagnosis_agent",
            )
            
            try:
                consultation = Consultation.objects.get(id=consultation_id)
                consultation.diagnosis_data = processed_diagnosis
                consultation.lab_tests_data = lab_tests
                consultation.current_state = 'diagnosis_complete'
                consultation.save()
            except Consultation.DoesNotExist:
                pass
            
            self.session_manager.complete_session({
                'diagnosis': processed_diagnosis,
                'lab_tests': lab_tests,
                'lab_tests_document': lab_tests_document
            })
            
            try:
                from .persistence import save_agent_session_summary
                save_agent_session_summary('diagnosis_agent', consultation_id, {
                    'phase': 'initial',
                    'diagnosis': processed_diagnosis,
                    'lab_tests': lab_tests,
                })
            except Exception as e:
                logger.debug(f"Could not persist diagnosis session: {e}")
            
            return {
                "consultation_id": consultation_id,
                "session_id": str(session.id),
                "diagnosis": processed_diagnosis,
                "lab_tests": lab_tests,
                "lab_tests_document": lab_tests_document,
                "status": "success"
            }
        except Exception as e:
            logger.error(f"Initial diagnosis failed: {e}")
            self.session_manager.fail_session(str(e))
            return {"status": "error", "error": str(e), "session_id": str(session.id)}
    
    def _run_prescription_phase(self, consultation_id: str, consultation_data: Dict) -> Dict[str, Any]:
        """Reason with lab results + RAG to generate prescription"""
        lab_results = consultation_data.get('lab_results') or consultation_data.get('lab_results_data', [])
        diagnosis = consultation_data.get('diagnosis', {})
        symptoms = consultation_data.get('symptoms', {}) or {}
        
        session = self.session_manager.create_session({
            'consultation_data': consultation_data,
            'phase': 'prescription',
            'lab_results': lab_results,
            'timestamp': datetime.now().isoformat()
        })
        
        try:
            context_text = f"Symptoms: {symptoms.get('description', '')}. Diagnosis: {diagnosis.get('primary_suspicion', '')}"
            rag_results = self.rag.search_similar_sync(context_text, k=5) if context_text else []
            
            messages = self._prepare_prescription_messages(
                consultation_data, diagnosis, lab_results, rag_results
            )
            prescription_result = self.openai.structured_completion(messages)
            
            prescription = self._process_prescription_result(prescription_result, consultation_id)
            
            self.blackboard.write(
                consultation_id,
                {
                    "prescription": prescription,
                    "prescription_completed_at": datetime.now().isoformat(),
                },
                "diagnosis_agent",
            )
            
            try:
                consultation = Consultation.objects.get(id=consultation_id)
                consultation.prescription_data = prescription
                consultation.current_state = 'final_diagnosis_ready'
                consultation.save()
            except Consultation.DoesNotExist:
                pass
            
            self.session_manager.complete_session({'prescription': prescription})
            
            try:
                from .persistence import save_agent_session_summary
                save_agent_session_summary('diagnosis_agent', consultation_id, {
                    'phase': 'prescription',
                    'prescription': prescription,
                })
            except Exception as e:
                logger.debug(f"Could not persist prescription session: {e}")
            
            return {
                "consultation_id": consultation_id,
                "session_id": str(session.id),
                "prescription": prescription,
                "status": "success"
            }
        except Exception as e:
            logger.error(f"Prescription phase failed: {e}")
            self.session_manager.fail_session(str(e))
            return {"status": "error", "error": str(e), "session_id": str(session.id)}
    
    def _generate_lab_test_document(
        self,
        lab_tests: List[Dict],
        consultation_data: Dict
    ) -> str:
        """Generate formal lab test order document for the lab"""
        patient = consultation_data.get('patient', {})
        diagnosis = consultation_data.get('diagnosis', {})
        
        doc_lines = [
            "LABORATORY TEST ORDER",
            "=" * 40,
            f"Patient ID: {patient.get('patient_id', 'N/A')}",
            f"Ordered by: Diagnosis Agent (AI Clinical Support)",
            f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"Clinical Indication: {diagnosis.get('primary_suspicion', 'Preliminary diagnosis')}",
            "",
            "TESTS REQUESTED:",
            "-" * 40,
        ]
        for i, test in enumerate(lab_tests, 1):
            doc_lines.append(f"{i}. {test.get('test_name', 'Unknown')}")
            doc_lines.append(f"   Type: {test.get('test_type', 'N/A')} | Priority: {test.get('priority', 'routine')}")
            doc_lines.append(f"   Rationale: {test.get('rationale', 'As per differential diagnosis')}")
            doc_lines.append("")
        
        doc_lines.append("=" * 40)
        doc_lines.append("This is an AI-generated lab order. Please process per standard protocols.")
        return "\n".join(doc_lines)
    
    def _prepare_prescription_messages(
        self,
        consultation_data: Dict,
        diagnosis: Dict,
        lab_results: List,
        rag_results: List[Dict]
    ) -> List[Dict[str, str]]:
        """Prepare messages for prescription generation"""
        rag_context = ""
        for i, doc in enumerate(rag_results[:3]):
            rag_context += f"\n[Source {i+1}]: {doc.get('content', '')[:500]}...\n"
        
        lab_results_str = json.dumps(lab_results, indent=2) if isinstance(lab_results, list) else str(lab_results)
        
        user_prompt = f"""
PATIENT: {consultation_data.get('patient', {})}
DIAGNOSIS: {diagnosis.get('primary_suspicion', '')}
DIFFERENTIAL: {json.dumps(diagnosis.get('differential_diagnosis', [])[:3])}

LAB RESULTS:
{lab_results_str}

MEDICAL KNOWLEDGE:
{rag_context}

TASK: Generate a treatment prescription based on the diagnosis and lab results.

Return JSON:
{{
    "medications": [
        {{"name": "...", "dosage": "...", "frequency": "...", "duration": "...", "instructions": "..."}}
    ],
    "treatment_plan": "Brief summary of treatment approach",
    "follow_up": "When to follow up",
    "disclaimer": "AI-generated. Consult healthcare professional."
}}
"""
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    
    def _process_prescription_result(self, result: Dict, consultation_id: str) -> Dict:
        """Process and validate prescription result"""
        result['consultation_id'] = consultation_id
        result['generated_at'] = datetime.now().isoformat()
        result.setdefault('medications', [])
        result.setdefault('treatment_plan', '')
        result.setdefault('follow_up', '')
        result.setdefault('disclaimer', 'AI-generated. Consult healthcare professional.')
        return result
    
    def _prepare_diagnosis_messages(
        self,
        consultation_data: Dict,
        symptoms: Dict,
        rag_results: List[Dict]
    ) -> List[Dict[str, str]]:
        """
        Prepare messages for GPT-4 diagnosis
        """
        # Format RAG results for the prompt
        rag_context = ""
        for i, doc in enumerate(rag_results):
            rag_context += f"\n[Source {i+1}: {doc.get('source', 'Unknown')}]\n"
            rag_context += f"Relevance: {doc.get('similarity_score', 0):.2f}\n"
            rag_context += f"Content: {doc.get('content', '')[:1000]}...\n"
        
        # Get patient info
        patient = consultation_data.get('patient', {})
        
        # Build the user prompt
        user_prompt = f"""
PATIENT INFORMATION:
- Age: {patient.get('age', 'Unknown')}
- Gender: {patient.get('gender', 'Unknown')}
- Medical History: {patient.get('medical_history', 'None reported')}

SYMPTOMS:
- Description: {symptoms.get('description', '')}
- Duration: {symptoms.get('duration', 'Not specified')}
- Severity: {symptoms.get('severity', 'Not specified')}/10
- Input Type: {symptoms.get('input_type', 'text')}

MEDICAL KNOWLEDGE FROM PDFs:
{rag_context}

TASK:
Based on the symptoms and medical knowledge above, provide a comprehensive diagnosis.

Return a JSON object with the following structure:
{{
    "differential_diagnosis": [
        {{
            "condition": "Name of condition",
            "probability": 0.0-1.0,
            "supporting_evidence": ["evidence from symptoms or PDFs"],
            "ruling_out_factors": ["what would rule this out"],
            "recommended_tests": ["test1", "test2"]
        }}
    ],
    "primary_suspicion": "Most likely condition",
    "reasoning_chain": [
        "Step 1: ...",
        "Step 2: ...",
        "Step 3: ..."
    ],
    "recommended_tests": [
        {{
            "test_name": "Name of test",
            "test_type": "blood/urine/imaging/other",
            "rationale": "Why this test is needed",
            "priority": "routine/urgent/stat"
        }}
    ],
    "urgency_level": "low/medium/high/critical",
    "red_flags": ["any urgent symptoms to watch for"],
    "pdf_sources_used": ["list of PDF sources referenced"],
    "disclaimer": "This is an AI-generated preliminary diagnosis. Please consult a healthcare professional."
}}
"""
        
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    
    def _process_diagnosis_result(
        self,
        result: Dict[str, Any],
        consultation_id: str
    ) -> Dict[str, Any]:
        """
        Process and validate the diagnosis result
        """
        # Ensure required fields exist
        required_fields = ['differential_diagnosis', 'reasoning_chain', 'urgency_level']
        for field in required_fields:
            if field not in result:
                result[field] = [] if field != 'urgency_level' else 'medium'
        
        # Add metadata
        result['consultation_id'] = consultation_id
        result['generated_at'] = datetime.now().isoformat()
        result['agent_version'] = 'diagnosis_agent_v1'
        
        return result
    
    def _generate_lab_tests(
        self,
        diagnosis: Dict[str, Any],
        consultation_data: Dict
    ) -> List[Dict[str, Any]]:
        """
        Generate structured lab test orders from diagnosis recommendations
        """
        lab_tests = []
        
        # Get recommended tests from diagnosis
        recommended = diagnosis.get('recommended_tests', [])
        
        for i, test in enumerate(recommended):
            # If test is a string, convert to dict
            if isinstance(test, str):
                test_dict = {
                    'test_name': test,
                    'test_type': self._infer_test_type(test),
                    'priority': diagnosis.get('urgency_level', 'medium'),
                    'rationale': f"Recommended based on differential diagnosis"
                }
            else:
                test_dict = test
            
            # Add required fields
            test_dict.update({
                'test_id': f"LAB_{i+1:03d}",
                'patient_id': consultation_data.get('patient', {}).get('patient_id'),
                'ordered_by': 'Diagnosis Agent',
                'status': 'pending',
                'created_at': datetime.now().isoformat()
            })
            
            lab_tests.append(test_dict)
        
        return lab_tests
    
    def _infer_test_type(self, test_name: str) -> str:
        """Infer test type from test name"""
        test_name_lower = test_name.lower()
        
        if any(word in test_name_lower for word in ['x-ray', 'mri', 'ct', 'ultrasound', 'imaging']):
            return 'imaging'
        elif 'urine' in test_name_lower:
            return 'urine'
        elif any(word in test_name_lower for word in ['blood', 'cbc', 'panel', 'glucose', 'lipid']):
            return 'blood'
        else:
            return 'other'
    
    def get_explanation(self, consultation_id: str, condition: str) -> Optional[str]:
        """
        Get detailed explanation for a specific condition
        """
        consultation_data = self.blackboard.read(consultation_id)
        if not consultation_data:
            return None
        
        diagnosis = consultation_data.get('diagnosis', {})
        differential = diagnosis.get('differential_diagnosis', [])
        
        # Find the condition
        for item in differential:
            if item.get('condition', '').lower() == condition.lower():
                # Prepare explanation messages
                messages = [
                    {"role": "system", "content": "You are a medical educator. Explain this condition in simple terms."},
                    {"role": "user", "content": f"""
Explain this condition to the patient:
Condition: {item.get('condition')}
Supporting Evidence: {item.get('supporting_evidence', [])}
Probability: {item.get('probability', 0.5) * 100}%

Provide:
1. Simple explanation of the condition
2. Common symptoms
3. Typical treatment approach
4. What to expect next
"""}
                ]
                
                try:
                    explanation = self.openai.chat_completion(messages)
                    
                    # Log this explanation
                    if self.session_manager:
                        self.session_manager.log_gpt_interaction(
                            model=self.openai.model,
                            prompt=json.dumps(messages),
                            response=explanation,
                            prompt_tokens=len(json.dumps(messages)) // 4,
                            completion_tokens=len(explanation) // 4,
                            response_time=0,  # Not timing explanations
                            success=True
                        )
                    
                    return explanation
                except Exception as e:
                    logger.error(f"Failed to get explanation: {e}")
                    return None
        
        return None
    
    def get_session_stats(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a specific session"""
        from .agent_session import SessionManager
        session = SessionManager.get_session(session_id)
        
        if not session:
            return None
        
        # Get GPT logs for this session
        gpt_logs = session.gpt_logs.all()
        
        return {
            'session_id': str(session.id),
            'consultation_id': str(session.consultation_id),
            'agent_type': session.agent_type,
            'status': session.status,
            'created_at': session.created_at.isoformat(),
            'processing_time': session.processing_time,
            'tokens_used': session.tokens_used,
            'cost': float(session.cost),
            'gpt_calls': gpt_logs.count(),
            'gpt_calls_successful': gpt_logs.filter(success=True).count(),
            'error': session.error_message if session.status == 'failed' else None
        }
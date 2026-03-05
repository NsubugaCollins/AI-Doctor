import json
import logging
from django.utils import timezone

from typing import Dict, Any, List, Optional

from apps.blackboard.services import BlackboardService
from apps.consultations.models import Consultation
from .agent_session import SessionManager
from apps.agents.services import medical_agent  # <- Groq + local embeddings
from apps.rag.services import PDFRAGService

logger = logging.getLogger(__name__)

class DiagnosisAgent:
    """
    Diagnosis Agent using free-tier Groq LLM + local RAG
    Maintains session management and Blackboard integration
    """

    def __init__(self):
        self.blackboard = BlackboardService()
        self.rag = PDFRAGService()
        self.session_manager = None
        self.system_prompt = (
            "You are an expert medical diagnosis AI assistant. "
            "Analyze symptoms and lab results using provided PDFs, generate differential diagnosis, "
            "recommend tests, and generate prescriptions. Always include reasoning and disclaimers."
        )

    def run(self, consultation_id: str) -> Dict[str, Any]:
        consultation_id = str(consultation_id)
        logger.info(f"DiagnosisAgent running for consultation {consultation_id}")
        self.session_manager = SessionManager('diagnosis_agent', consultation_id)

        consultation_data = self.blackboard.read(consultation_id)
        if not consultation_data:
            return {"status": "error", "error": "Consultation not found"}

        lab_results = consultation_data.get('lab_results') or consultation_data.get('lab_results_data')
        if lab_results:
            return self._run_prescription_phase(consultation_id, consultation_data)
        else:
            return self._run_initial_diagnosis_phase(consultation_id, consultation_data)

    def _run_initial_diagnosis_phase(self, consultation_id: str, consultation_data: Dict) -> Dict[str, Any]:
        symptoms = consultation_data.get('symptoms', {}) or consultation_data.get('symptom_analysis', {})
        if not symptoms:
            return {"status": "error", "error": "No symptoms provided"}

        session = self.session_manager.create_session({
            'consultation_data': consultation_data,
            'symptoms': symptoms,
            'phase': 'initial_diagnosis',
            'timestamp': timezone.now().isoformat()
        })

        try:
            symptoms_text = symptoms.get('description', '') or str(symptoms.get('structured_summary', ''))
            rag_results = self.rag.search_similar_sync(symptoms_text, k=5) if symptoms_text else []

            # Prepare the prompt for Groq LLM
            prompt = f"{self.system_prompt}\nPatient Symptoms:\n{symptoms_text}\nMedical PDFs Context:\n{json.dumps(rag_results)[:2000]}"

            diagnosis_result = medical_agent(prompt)  # Free-tier llama3 + RAG

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
                    "diagnosis_completed_at": timezone.now().isoformat(),
                },
                "diagnosis_agent",
            )

            try:
                consultation = Consultation.objects.get(id=consultation_id)
                # Persist a copy to DB for dashboards/status endpoints.
                consultation.diagnosis = processed_diagnosis
                consultation.lab_tests = lab_tests
                consultation.current_state = 'diagnosis_complete'
                consultation.save()
            except Consultation.DoesNotExist:
                pass

            self.session_manager.complete_session({
                'diagnosis': processed_diagnosis,
                'lab_tests': lab_tests,
                'lab_tests_document': lab_tests_document
            })

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
        lab_results = consultation_data.get('lab_results') or consultation_data.get('lab_results_data', [])
        diagnosis = consultation_data.get('diagnosis', {})
        symptoms = consultation_data.get('symptoms', {}) or {}

        session = self.session_manager.create_session({
            'consultation_data': consultation_data,
            'phase': 'prescription',
            'lab_results': lab_results,
            'timestamp': timezone.now().isoformat()
        })

        try:
            context_text = f"Symptoms: {symptoms.get('description', '')}. Diagnosis: {diagnosis.get('primary_suspicion', '')}"
            rag_results = self.rag.search_similar_sync(context_text, k=5) if context_text else []

            prompt = f"{self.system_prompt}\nPatient Data:\n{json.dumps(consultation_data, default=str)}\nRAG Context:\n{json.dumps(rag_results)[:2000]}\nGenerate a treatment prescription."

            prescription_result = medical_agent(prompt)

            prescription = self._process_prescription_result(prescription_result, consultation_id)

            self.blackboard.write(
                consultation_id,
                {"prescription": prescription, "prescription_completed_at": timezone.now().isoformat()},
                "diagnosis_agent",
            )

            try:
                consultation = Consultation.objects.get(id=consultation_id)
                # Persist a copy to DB for dashboards/status endpoints.
                consultation.prescription = prescription
                consultation.current_state = 'final_diagnosis_ready'
                consultation.save()
            except Consultation.DoesNotExist:
                pass

            self.session_manager.complete_session({'prescription': prescription})

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

    # --- Helpers ---
    def _ensure_dict(self, raw: Any, context: str) -> Dict[str, Any]:
        """
        Ensure the LLM result is a dict. If it's a string, try to parse JSON,
        otherwise wrap it in a structure under 'raw_text'.
        """
        if isinstance(raw, dict):
            return raw

        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                logger.warning(f"{context}: LLM response was non‑JSON string; wrapping as raw_text.")
            return {"raw_text": raw}

        logger.warning(f"{context}: Unexpected result type {type(raw)}; wrapping.")
        return {"raw_result": raw}

    def _process_diagnosis_result(self, result: Any, consultation_id: str) -> Dict[str, Any]:
        result_dict = self._ensure_dict(result, "diagnosis")
        result_dict['consultation_id'] = consultation_id
        result_dict['generated_at'] = timezone.now().isoformat()
        result_dict.setdefault('differential_diagnosis', [])
        result_dict.setdefault('reasoning_chain', [])
        result_dict.setdefault('urgency_level', 'medium')
        result_dict.setdefault('pdf_sources_used', [])
        return result_dict

    def _process_prescription_result(self, result: Any, consultation_id: str) -> Dict[str, Any]:
        result_dict = self._ensure_dict(result, "prescription")
        result_dict['consultation_id'] = consultation_id
        result_dict['generated_at'] = timezone.now().isoformat()
        result_dict.setdefault('medications', [])
        result_dict.setdefault('treatment_plan', '')
        result_dict.setdefault('follow_up', '')
        result_dict.setdefault('disclaimer', 'AI-generated. Consult healthcare professional.')
        return result_dict

    def _generate_lab_tests(self, diagnosis: Dict[str, Any], consultation_data: Dict) -> List[Dict[str, Any]]:
        lab_tests = []
        recommended = diagnosis.get('recommended_tests', [])
        for i, test in enumerate(recommended):
            test_dict = {'test_name': test if isinstance(test, str) else test.get('test_name', 'Unknown')}
            test_dict.update({
                'test_id': f"LAB_{i+1:03d}",
                'patient_id': consultation_data.get('patient', {}).get('patient_id'),
                'ordered_by': 'Diagnosis Agent',
                'status': 'pending',
                'priority': diagnosis.get('urgency_level', 'medium'),
                'created_at': timezone.now().isoformat()
            })
            lab_tests.append(test_dict)
        return lab_tests

    def _generate_lab_test_document(self, lab_tests: List[Dict], consultation_data: Dict) -> str:
        patient = consultation_data.get('patient', {})
        doc_lines = [
            "LABORATORY TEST ORDER",
            "="*40,
            f"Patient ID: {patient.get('patient_id','N/A')}",
            f"Ordered by: Diagnosis Agent",
            f"Date: {timezone.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "TESTS REQUESTED:",
            "-"*40
        ]
        for i, test in enumerate(lab_tests, 1):
            doc_lines.append(f"{i}. {test.get('test_name','Unknown')} | Priority: {test.get('priority','routine')}")
        doc_lines.append("="*40)
        doc_lines.append("AI-generated lab order. Process per standard protocols.")
        return "\n".join(doc_lines)
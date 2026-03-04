"""
Lab Agent - Sends lab test DOC to lab, retrieves results, sends prescription to pharmacy and patient.
Integrated with autonomous controller.
"""

import json
import logging
import random
from typing import Dict, Any, List
from datetime import datetime

from apps.agents.open_ai_service import get_openai_service
from apps.blackboard.services import BlackboardService
from apps.consultations.models import Consultation
from .agent_session import SessionManager

logger = logging.getLogger(__name__)


class LabAgent:
    """Agent responsible for lab coordination and pharmacy communication."""

    def __init__(self):
        self.openai = get_openai_service()
        self.blackboard = BlackboardService()
        self.session_manager = None

        self.system_prompt = """You are a medical laboratory coordination AI. Your role is to:
1. Process lab test orders and send them to the laboratory
2. Format lab order documents for lab systems
3. Interpret lab results when received
4. Send prescriptions to pharmacy and patient
5. Be precise and follow medical protocols."""

    def run(self, consultation_id: str) -> Dict[str, Any]:
        """
        Main entry point for autonomous controller.
        Handles: (1) Send lab doc to lab, (2) Retrieve results, (3) Send prescription to pharmacy + patient.
        """
        # Ensure consultation_id is a string
        consultation_id = str(consultation_id)
        
        logger.info(f"LabAgent running for consultation {consultation_id}")

        # BlackboardService methods are synchronous; this agent runs in a worker thread.
        consultation_data = self.blackboard.read(consultation_id)
        if not consultation_data:
            return {"status": "error", "error": "Consultation not found"}

        current_state = consultation_data.get("current_state", "")

        if current_state == "diagnosis_complete":
            return self._send_lab_doc_to_lab(consultation_id, consultation_data)
        elif current_state == "lab_tests_ordered":
            return self._retrieve_lab_results(consultation_id, consultation_data)
        elif current_state == "final_diagnosis_ready":
            return self._send_prescription_to_pharmacy_and_patient(
                consultation_id, consultation_data
            )

        return {"status": "error", "error": f"Unexpected state: {current_state}"}

    def _send_lab_doc_to_lab(
        self, consultation_id: str, consultation_data: Dict
    ) -> Dict[str, Any]:
        """Send lab test document to lab and mark tests as ordered."""
        lab_tests_document = consultation_data.get("lab_tests_document")
        lab_tests = consultation_data.get("lab_tests", [])

        if not lab_tests_document and not lab_tests:
            return {"status": "error", "error": "No lab tests to send"}

        self.session_manager = SessionManager("lab_agent", consultation_id)
        session = self.session_manager.create_session(
            {
                "action": "send_to_lab",
                "lab_tests": lab_tests,
                "timestamp": datetime.now().isoformat(),
            }
        )

        try:
            doc = lab_tests_document or self._generate_lab_doc(lab_tests, consultation_data)

            for test in lab_tests:
                test["status"] = "pending"
                test["sent_to_lab_at"] = datetime.now().isoformat()
                test["lab_order_id"] = f"LAB-{consultation_id[:8]}-{test.get('test_id', '')}"

            self.blackboard.write(
                consultation_id,
                {
                    "lab_tests": lab_tests,
                    "lab_tests_document": doc,
                    "lab_order_sent_at": datetime.now().isoformat(),
                    "current_state": "lab_tests_ordered",
                },
                "lab_agent",
            )

            try:
                consultation = Consultation.objects.get(id=consultation_id)
                consultation.lab_tests_data = lab_tests
                consultation.current_state = "lab_tests_ordered"
                consultation.save()
            except Consultation.DoesNotExist:
                pass

            self.session_manager.complete_session(
                {"lab_order_sent": True, "lab_tests": lab_tests}
            )

            logger.info(f"Lab order sent for {consultation_id}")

            return {
                "status": "success",
                "consultation_id": consultation_id,
                "session_id": str(session.id),
                "lab_order_sent": True,
            }
        except Exception as e:
            logger.error(f"Failed to send lab order: {e}")
            self.session_manager.fail_session(str(e))
            return {"status": "error", "error": str(e), "session_id": str(session.id)}

    def _retrieve_lab_results(
        self, consultation_id: str, consultation_data: Dict
    ) -> Dict[str, Any]:
        """Retrieve lab results (simulate - in production would call lab API)."""
        lab_tests = consultation_data.get("lab_tests", [])

        if not lab_tests:
            return {"status": "error", "error": "No lab tests found"}

        pending = [t for t in lab_tests if t.get("status") == "pending"]
        if not pending:
            pending = lab_tests

        all_complete = True
        for test in lab_tests:
            if test.get("status") != "completed":
                test["status"] = "completed"
                test["results"] = self._generate_mock_results(
                    test.get("test_name", "Unknown")
                )
                test["completed_date"] = datetime.now().isoformat()
            else:
                all_complete = all_complete and True

        lab_results = [
            {
                "test_name": t.get("test_name"),
                "results": t.get("results", {}),
                "completed_date": t.get("completed_date"),
            }
            for t in lab_tests
        ]

        self.blackboard.write(
            consultation_id,
            {
                "lab_tests": lab_tests,
                "lab_results": lab_results,
                "current_state": "lab_tests_complete",
            },
            "lab_agent",
        )

        try:
            consultation = Consultation.objects.get(id=consultation_id)
            consultation.lab_tests_data = lab_tests
            consultation.lab_results_data = lab_results
            consultation.current_state = "lab_tests_complete"
            consultation.save()
        except Consultation.DoesNotExist:
            pass

        logger.info(f"Lab results retrieved for {consultation_id}")

        return {
            "status": "success",
            "consultation_id": consultation_id,
            "lab_results": lab_results,
        }

    def _send_prescription_to_pharmacy_and_patient(
        self, consultation_id: str, consultation_data: Dict
    ) -> Dict[str, Any]:
        """Send prescription to pharmacy and patient."""
        prescription = consultation_data.get("prescription")

        if not prescription:
            return {"status": "error", "error": "No prescription to send"}

        self.session_manager = SessionManager("lab_agent", consultation_id)
        session = self.session_manager.create_session(
            {
                "action": "send_prescription",
                "prescription": prescription,
                "timestamp": datetime.now().isoformat(),
            }
        )

        try:
            pharmacy_order = self._format_pharmacy_order(prescription, consultation_data)

            prescription["sent_to_pharmacy"] = True
            prescription["sent_to_patient"] = True
            prescription["pharmacy_order"] = pharmacy_order
            prescription["sent_date"] = datetime.now().isoformat()

            self.blackboard.write(
                consultation_id,
                {"prescription": prescription, "current_state": "prescription_sent"},
                "lab_agent",
            )

            try:
                consultation = Consultation.objects.get(id=consultation_id)
                consultation.prescription_data = prescription
                consultation.current_state = "prescription_sent"
                consultation.save()
            except Consultation.DoesNotExist:
                pass

            self.session_manager.complete_session(
                {"prescription_sent": True, "sent_to_pharmacy": True, "sent_to_patient": True}
            )

            logger.info(f"Prescription sent to pharmacy and patient for {consultation_id}")

            return {
                "status": "success",
                "consultation_id": consultation_id,
                "session_id": str(session.id),
                "prescription_sent": True,
            }
        except Exception as e:
            logger.error(f"Failed to send prescription: {e}")
            self.session_manager.fail_session(str(e))
            return {"status": "error", "error": str(e), "session_id": str(session.id)}

    def _generate_lab_doc(
        self, lab_tests: List[Dict], consultation_data: Dict
    ) -> str:
        """Generate lab order document."""
        patient = consultation_data.get("patient", {})
        doc_lines = [
            "LABORATORY TEST ORDER",
            "=" * 40,
            f"Patient ID: {patient.get('patient_id', 'N/A')}",
            f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "TESTS REQUESTED:",
            "-" * 40,
        ]
        for i, test in enumerate(lab_tests, 1):
            doc_lines.append(f"{i}. {test.get('test_name', 'Unknown')}")
        doc_lines.append("=" * 40)
        return "\n".join(doc_lines)

    def _format_pharmacy_order(self, prescription: Dict, consultation_data: Dict) -> str:
        """Format prescription for pharmacy."""
        patient = consultation_data.get("patient", {})
        meds = prescription.get("medications", [])
        lines = [
            "PHARMACY PRESCRIPTION",
            "=" * 40,
            f"Patient: {patient.get('patient_id', 'N/A')}",
            f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "MEDICATIONS:",
        ]
        for m in meds:
            lines.append(
                f"- {m.get('name', '')}: {m.get('dosage', '')} {m.get('frequency', '')} x {m.get('duration', '')}"
            )
        lines.append(f"\nInstructions: {prescription.get('treatment_plan', '')}")
        lines.append("=" * 40)
        return "\n".join(lines)

    def _generate_mock_results(self, test_name: str) -> Dict[str, Any]:
        """Generate mock lab results for testing."""
        test_name_lower = test_name.lower()
        if "blood" in test_name_lower or "cbc" in test_name_lower:
            return {
                "wbc": "7.5 K/uL",
                "rbc": "4.8 M/uL",
                "hemoglobin": "14.2 g/dL",
                "interpretation": "Within normal limits",
            }
        elif "glucose" in test_name_lower:
            return {"fasting_glucose": "95 mg/dL", "interpretation": "Normal"}
        elif "lipid" in test_name_lower:
            return {
                "total_cholesterol": "180 mg/dL",
                "hdl": "45 mg/dL",
                "ldl": "110 mg/dL",
                "interpretation": "Borderline high LDL",
            }
        return {"result": "Normal", "interpretation": "No abnormalities detected"}

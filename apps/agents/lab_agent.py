import logging
import random

from typing import Dict, Any, List
from django.utils import timezone
from django.conf import settings

from apps.blackboard.services import BlackboardService
from apps.consultations.models import Consultation
from .agent_session import SessionManager
from apps.consultations.notifications import (
    send_lab_order_email,
    send_prescription_email,
)

# Groq LLM + local embeddings
from apps.agents.services import medical_agent  # <- RAG + Groq llama3 function

logger = logging.getLogger(__name__)

class LabAgent:
    """Agent responsible for lab coordination and pharmacy communication."""
    
    def __init__(self):
        self.blackboard = BlackboardService()
        self.session_manager = None

    def run(self, consultation_id: str) -> Dict[str, Any]:
        consultation_id = str(consultation_id)
        logger.info(f"LabAgent running for consultation {consultation_id}")

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

    # --- Lab order ---
    def _send_lab_doc_to_lab(self, consultation_id: str, consultation_data: Dict) -> Dict[str, Any]:
        lab_tests_document = consultation_data.get("lab_tests_document")
        lab_tests = consultation_data.get("lab_tests", [])

        if not lab_tests_document and not lab_tests:
            return {"status": "error", "error": "No lab tests to send"}

        self.session_manager = SessionManager("lab_agent", consultation_id)
        session = self.session_manager.create_session(
            {"action": "send_to_lab", "lab_tests": lab_tests, "timestamp": timezone.now().isoformat()}
        )

        try:
            # Use RAG Groq LLM to optionally enrich lab doc
            lab_doc_text = lab_tests_document or self._generate_lab_doc(lab_tests, consultation_data)
            enriched_doc = medical_agent(f"Generate lab order doc:\n{lab_doc_text}")

            for test in lab_tests:
                test["status"] = "pending"
                test["sent_to_lab_at"] = timezone.now().isoformat()
                test["lab_order_id"] = f"LAB-{consultation_id[:8]}-{test.get('test_id', '')}"

            self.blackboard.write(
                consultation_id,
                {
                    "lab_tests": lab_tests,
                    "lab_tests_document": enriched_doc,
                    "lab_order_sent_at": timezone.now().isoformat(),
                    "current_state": "lab_tests_ordered",
                },
                "lab_agent",
            )

            # Update Django model if exists
            try:
                consultation = Consultation.objects.get(id=consultation_id)
                # Persist a copy to DB for dashboards/status endpoints.
                consultation.lab_tests = lab_tests
                consultation.current_state = "lab_tests_ordered"
                consultation.save()
            except Consultation.DoesNotExist:
                pass

            self.session_manager.complete_session({"lab_order_sent": True, "lab_tests": lab_tests})

            # Email lab order (optional, depends on settings)
            try:
                consultation = Consultation.objects.get(id=consultation_id)
                send_lab_order_email(consultation=consultation, lab_order_text=str(enriched_doc))
            except Exception:
                pass

            logger.info(f"Lab order sent for {consultation_id}")
            return {"status": "success", "consultation_id": consultation_id, "session_id": str(session.id), "lab_order_sent": True}
        except Exception as e:
            logger.error(f"Failed to send lab order: {e}")
            self.session_manager.fail_session(str(e))
            return {"status": "error", "error": str(e), "session_id": str(session.id)}

    # --- Lab results ---
    def _retrieve_lab_results(self, consultation_id: str, consultation_data: Dict) -> Dict[str, Any]:
        lab_tests = consultation_data.get("lab_tests", [])
        if not lab_tests:
            return {"status": "error", "error": "No lab tests found"}

        # If we're in upload mode, wait for lab portal to upload a PDF.
        if getattr(settings, "LAB_RESULTS_MODE", "mock") == "upload":
            existing = consultation_data.get("lab_results") or consultation_data.get("lab_results_pdf")
            if not existing:
                return {"status": "waiting", "message": "Waiting for lab PDF upload"}

        for test in lab_tests:
            if test.get("status") != "completed":
                test["status"] = "completed"
                test["results"] = self._generate_mock_results(test.get("test_name", "Unknown"))
                test["completed_date"] = timezone.now().isoformat()

        lab_results = [{"test_name": t.get("test_name"), "results": t.get("results", {}), "completed_date": t.get("completed_date")} for t in lab_tests]

        self.blackboard.write(
            consultation_id,
            {"lab_tests": lab_tests, "lab_results": lab_results, "current_state": "lab_tests_complete"},
            "lab_agent",
        )

        try:
            consultation = Consultation.objects.get(id=consultation_id)
            # Persist lab_tests to DB (Consultation has no lab_results field).
            consultation.lab_tests = lab_tests
            consultation.current_state = "lab_tests_complete"
            consultation.save()
        except Consultation.DoesNotExist:
            pass

        logger.info(f"Lab results retrieved for {consultation_id}")
        return {"status": "success", "consultation_id": consultation_id, "lab_results": lab_results}

    # --- Prescription ---
    def _send_prescription_to_pharmacy_and_patient(self, consultation_id: str, consultation_data: Dict) -> Dict[str, Any]:
        prescription = consultation_data.get("prescription")
        if not prescription:
            return {"status": "error", "error": "No prescription to send"}

        self.session_manager = SessionManager("lab_agent", consultation_id)
        session = self.session_manager.create_session(
            {"action": "send_prescription", "prescription": prescription, "timestamp": timezone.now().isoformat()}
        )

        try:
            pharmacy_order = self._format_pharmacy_order(prescription, consultation_data)

            prescription["sent_to_pharmacy"] = True
            prescription["sent_to_patient"] = True
            prescription["pharmacy_order"] = pharmacy_order
            prescription["sent_date"] = timezone.now().isoformat()

            self.blackboard.write(
                consultation_id,
                {"prescription": prescription, "current_state": "prescription_sent"},
                "lab_agent",
            )

            try:
                consultation = Consultation.objects.get(id=consultation_id)
                # Persist a copy to DB for dashboards/status endpoints.
                consultation.prescription = prescription
                consultation.current_state = "prescription_sent"
                consultation.save()
            except Consultation.DoesNotExist:
                pass

            self.session_manager.complete_session({"prescription_sent": True})

            # Email prescription (optional)
            try:
                consultation = Consultation.objects.get(id=consultation_id)
                patient_email = None
                try:
                    if consultation.patient and consultation.patient.user:
                        patient_email = consultation.patient.user.email
                except Exception:
                    patient_email = None
                pharmacy_email = getattr(settings, "PHARMACY_INBOX_EMAIL", "") or None
                send_prescription_email(
                    consultation=consultation,
                    prescription_text=str(pharmacy_order),
                    patient_email=patient_email,
                    pharmacy_email=pharmacy_email,
                )
            except Exception:
                pass

            logger.info(f"Prescription sent for {consultation_id}")
            return {"status": "success", "consultation_id": consultation_id, "session_id": str(session.id), "prescription_sent": True}
        except Exception as e:
            logger.error(f"Failed to send prescription: {e}")
            self.session_manager.fail_session(str(e))
            return {"status": "error", "error": str(e), "session_id": str(session.id)}

    # --- Helpers ---
    def _generate_lab_doc(self, lab_tests: List[Dict], consultation_data: Dict) -> str:
        patient = consultation_data.get("patient", {})
        lines = ["LABORATORY TEST ORDER", "="*40, f"Patient ID: {patient.get('patient_id','N/A')}", f"Date: {timezone.now().strftime('%Y-%m-%d %H:%M')}", "", "TESTS REQUESTED:", "-"*40]
        for i, test in enumerate(lab_tests, 1):
            lines.append(f"{i}. {test.get('test_name', 'Unknown')}")
        lines.append("="*40)
        return "\n".join(lines)

    def _format_pharmacy_order(self, prescription: Dict, consultation_data: Dict) -> str:
        patient = consultation_data.get("patient", {})
        meds = prescription.get("medications", [])
        lines = ["PHARMACY PRESCRIPTION", "="*40, f"Patient: {patient.get('patient_id','N/A')}", f"Date: {timezone.now().strftime('%Y-%m-%d %H:%M')}", "", "MEDICATIONS:"]
        for m in meds:
            lines.append(f"- {m.get('name','')}: {m.get('dosage','')} {m.get('frequency','')} x {m.get('duration','')}")
        lines.append(f"\nInstructions: {prescription.get('treatment_plan','')}")
        lines.append("="*40)
        return "\n".join(lines)

    def _generate_mock_results(self, test_name: str) -> Dict[str, Any]:
        test_name_lower = test_name.lower()
        if "blood" in test_name_lower or "cbc" in test_name_lower:
            return {"wbc": "7.5 K/uL", "rbc": "4.8 M/uL", "hemoglobin": "14.2 g/dL", "interpretation": "Within normal limits"}
        elif "glucose" in test_name_lower:
            return {"fasting_glucose": "95 mg/dL", "interpretation": "Normal"}
        elif "lipid" in test_name_lower:
            return {"total_cholesterol": "180 mg/dL", "hdl": "45 mg/dL", "ldl": "110 mg/dL", "interpretation": "Borderline high LDL"}
        return {"result": "Normal", "interpretation": "No abnormalities detected"}
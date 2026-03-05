import json
import logging

from asgiref.sync import sync_to_async
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from django.conf import settings
from django.core.files.storage import default_storage

from .models import Consultation, Symptom, Patient, LabResultUpload
from apps.blackboard.services import BlackboardService
from apps.agents.models import AgentSession
from apps.consultations.notifications import send_lab_results_email

from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)


# =====================================================
# Sync page views (safe for templates)
# =====================================================

@login_required
def home(request):
    return render(request, "index.html")


@login_required
def dashboard(request):
    consultations = Consultation.objects.filter(
        patient__user=request.user
    ).order_by("-created_at")

    # Total lab tests across all consultations for this patient
    from .models import LabTest
    lab_tests_count = LabTest.objects.filter(
        consultation__in=consultations
    ).count()

    context = {
        "consultations": consultations,
        "completed_count": consultations.filter(current_state="completed").count(),
        "in_progress_count": consultations.exclude(current_state="completed").count(),
        "lab_tests_count": lab_tests_count,
    }
    return render(request, "dashboard.html", context)


@login_required
def new_consultation(request):
    return render(request, "consultation.html")


@login_required
def consultation_detail(request, consultation_id):
    try:
        consultation = Consultation.objects.select_related("patient").get(
            id=consultation_id,
            patient__user=request.user
        )

        blackboard = BlackboardService()
        blackboard_data = blackboard.read(str(consultation.id))

        context = {
            "consultation": consultation,
            "blackboard_data": blackboard_data or {},
        }

        return render(request, "consultation_detail.html", context)

    except Consultation.DoesNotExist:
        return redirect("dashboard")


@login_required
@require_POST
def add_symptoms_ui(request, consultation_id):
    try:
        consultation = Consultation.objects.get(
            id=consultation_id,
            patient__user=request.user
        )

        description = request.POST.get("description", "")
        duration = request.POST.get("duration", "")
        severity = int(request.POST.get("severity", 5))

        Symptom.objects.create(
            consultation=consultation,
            description=description,
            duration=duration,
            severity=severity,
            input_type="text"
        )

        # Also write symptoms into the blackboard (shared memory) so the
        # autonomous controller + symptom_agent can pick them up.
        try:
            blackboard = BlackboardService()
            ok = blackboard.write(
                str(consultation.id),
                {
                    "symptoms": {
                        "description": description,
                        "duration": duration,
                        "severity": severity,
                        "input_type": "text",
                    },
                    # Keep/force initial so controller runs symptom_agent next
                    "current_state": "initial",
                },
                "ui",
            )
            if not ok:
                # Ensure blackboard state exists, then retry once.
                try:
                    patient = consultation.patient
                    patient_data = {
                        "patient_id": str(patient.id) if patient else None,
                        "name": getattr(getattr(patient, "user", None), "username", None),
                    }
                except Exception:
                    patient_data = {}
                blackboard.create_consultation(patient_data, str(consultation.id))
                blackboard.write(
                    str(consultation.id),
                    {
                        "symptoms": {
                            "description": description,
                            "duration": duration,
                            "severity": severity,
                            "input_type": "text",
                        },
                        "current_state": "initial",
                    },
                    "ui",
                )
        except Exception as e:
            logger.error(f"Blackboard symptom write failed: {e}")

        return redirect("consultation_detail", consultation_id=consultation.id)

    except Exception as e:
        logger.error(f"Add symptoms error: {e}")
        return redirect("dashboard")


# =====================================================
# Async ORM helpers
# =====================================================

@sync_to_async
def get_or_create_patient(user, defaults):
    return Patient.objects.get_or_create(user=user, defaults=defaults)


@sync_to_async
def create_consultation(patient, symptoms, lab_tests, diagnosis, prescription):
    return Consultation.objects.create(
        patient=patient,
        current_state="initial",
        symptoms=symptoms,
        lab_tests=lab_tests,
        diagnosis=diagnosis,
        prescription=prescription
    )


@sync_to_async
def get_consultation_for_user(consultation_id, user):
    return Consultation.objects.select_related("patient").get(
        id=consultation_id,
        patient__user=user
    )


@sync_to_async
def symptom_exists(consultation):
    return consultation.symptom_list.exists()


@sync_to_async
def create_blackboard_consultation(patient_id, username, consultation_id):
    blackboard = BlackboardService()
    return blackboard.create_consultation(
        {
            "patient_id": str(patient_id),
            "name": username,
        },
        str(consultation_id),
    )


@sync_to_async
def read_blackboard_data(consultation_id):
    blackboard = BlackboardService()
    return blackboard.read(str(consultation_id))


@sync_to_async
def get_user_info(user):
    """Get user info in async-safe way - force evaluation of user object"""
    # Force evaluation of user object to avoid lazy loading issues
    return {
        'is_authenticated': user.is_authenticated,
        'username': user.username,
        'id': user.id,
        'user_obj': user
    }


# =====================================================
# Async APIs
# =====================================================

@require_POST
@csrf_exempt
async def start_consultation_api(request):
    try:
        # Get user info in async-safe way
        user_info = await get_user_info(request.user)
        
        if not user_info['is_authenticated']:
            return JsonResponse({"error": "Authentication required"}, status=401)
        
        user = user_info['user_obj']
        username = user_info['username']

        data = json.loads(request.body or "{}")

        symptoms = data.get("symptoms") if isinstance(data.get("symptoms"), list) else []
        lab_tests = data.get("lab_tests") if isinstance(data.get("lab_tests"), list) else []
        diagnosis = data.get("diagnosis") if isinstance(data.get("diagnosis"), dict) else {}
        prescription = data.get("prescription") if isinstance(data.get("prescription"), dict) else {}

        # Note: DB column for allergies is an array; use '{}' (empty array literal)
        # instead of '' to avoid malformed array literal errors.
        patient, _ = await get_or_create_patient(
            user,
            {
                "medical_history": data.get("medical_history", ""),
                "allergies": data.get("allergies", "{}") or "{}",
                "blood_type": data.get("blood_type", "unknown"),
            },
        )

        consultation = await create_consultation(
            patient,
            symptoms,
            lab_tests,
            diagnosis,
            prescription,
        )
        
        # Create blackboard consultation
        await create_blackboard_consultation(
            patient.id,
            username,
            consultation.id,
        )

        return JsonResponse(
            {"consultation_id": str(consultation.id), "status": "created"},
            status=201,
        )

    except Exception as e:
        logger.error(f"Failed to start consultation: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
async def consultation_status_api(request, consultation_id):
    try:
        consultation = await get_consultation_for_user(
            consultation_id, request.user
        )

        blackboard_data = await read_blackboard_data(consultation.id)

        has_symptoms = await symptom_exists(consultation)

        # Blackboard is the source-of-truth for agent outputs and state transitions.
        bb = blackboard_data or {}
        bb_state = bb.get("current_state")

        return JsonResponse(
            {
                "id": str(consultation.id),
                # Prefer blackboard state so the UI reflects real-time progress,
                # even if DB fields lag behind.
                "current_state": bb_state or consultation.current_state,
                "db_state": consultation.current_state,
                "has_symptoms": has_symptoms,
                # Prefer blackboard payloads (agents primarily write there).
                "diagnosis": bb.get("diagnosis") or consultation.diagnosis,
                "lab_tests": bb.get("lab_tests") or consultation.lab_tests,
                "lab_results": bb.get("lab_results") or [],
                "prescription": bb.get("prescription") or consultation.prescription,
                "blackboard_state": bb_state,
                "blackboard_updated_at": bb.get("updated_at"),
            }
        )

    except Exception as e:
        logger.error(f"Status error: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_GET
async def consultation_activity_api(request, consultation_id):
    """
    Polling-friendly activity API.
    Returns the latest agent sessions for this consultation so the frontend can
    show progress even when WebSockets don't bridge processes.
    """
    try:
        consultation = await get_consultation_for_user(consultation_id, request.user)

        sessions = await sync_to_async(list)(
            AgentSession.objects.filter(consultation_id=consultation.id)
            .order_by("-created_at")[:50]
        )

        # Return oldest -> newest for easy appending
        sessions.reverse()

        payload = []
        for s in sessions:
            payload.append(
                {
                    "id": str(s.id),
                    "agent_type": s.agent_type,
                    "status": s.status,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    "processing_time": s.processing_time,
                    "error_message": s.error_message,
                }
            )

        return JsonResponse(
            {
                "consultation_id": str(consultation.id),
                "sessions": payload,
            }
        )
    except Exception as e:
        logger.error(f"Activity error: {e}")
        return JsonResponse({"error": str(e)}, status=500)


def _is_lab_user(user) -> bool:
    try:
        return bool(getattr(user, "is_authenticated", False)) and (
            getattr(user, "is_staff", False) or getattr(user, "user_type", "") == "lab"
        )
    except Exception:
        return False


@login_required
def lab_dashboard(request):
    if not _is_lab_user(request.user):
        return redirect("dashboard")

    blackboard = BlackboardService()
    pending_ids = blackboard.get_consultations_by_state("lab_tests_ordered")
    consultations = Consultation.objects.filter(id__in=pending_ids).select_related("patient", "patient__user")

    rows = []
    for c in consultations.order_by("-created_at")[:100]:
        bb = blackboard.read(str(c.id)) or {}
        rows.append(
            {
                "consultation": c,
                "blackboard": bb,
                "lab_tests_document": bb.get("lab_tests_document"),
                "lab_tests": bb.get("lab_tests") or [],
            }
        )

    return render(request, "lab_dashboard.html", {"rows": rows})


@login_required
def lab_upload_results(request, consultation_id):
    if not _is_lab_user(request.user):
        return redirect("dashboard")

    try:
        consultation = Consultation.objects.select_related("patient", "patient__user").get(id=consultation_id)
    except Consultation.DoesNotExist:
        return redirect("lab_dashboard")

    if request.method != "POST":
        blackboard = BlackboardService()
        bb = blackboard.read(str(consultation.id)) or {}
        uploads = LabResultUpload.objects.filter(consultation=consultation).order_by("-created_at")[:10]
        return render(
            request,
            "lab_upload.html",
            {
                "consultation": consultation,
                "blackboard": bb,
                "uploads": uploads,
            },
        )

    pdf = request.FILES.get("pdf_file")
    if not pdf:
        return redirect("lab_upload_results", consultation_id=consultation.id)

    # Save upload model + file
    upload = LabResultUpload.objects.create(
        consultation=consultation,
        uploaded_by=request.user,
        pdf_file=pdf,
    )

    # Extract text
    extracted_text = ""
    try:
        reader = PdfReader(upload.pdf_file.path)
        parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        extracted_text = "\n\n".join(parts)
    except Exception as e:
        logger.warning("Failed to extract PDF text for %s: %s", upload.id, e)
        extracted_text = ""

    upload.extracted_text = extracted_text
    upload.save(update_fields=["extracted_text"])

    # Update blackboard so controller can continue
    blackboard = BlackboardService()
    bb_updates = {
        "lab_results_pdf": upload.pdf_file.url,
        "lab_results_text": extracted_text[:20000],  # keep bounded
        "lab_results": [
            {
                "test_name": "Uploaded PDF",
                "results": {"text_excerpt": extracted_text[:2000]},
                "completed_date": timezone.now().isoformat(),
            }
        ],
        "current_state": "lab_tests_complete",
    }
    blackboard.write(str(consultation.id), bb_updates, "lab_portal")

    # Email patient (optional)
    try:
        patient_email = consultation.patient.user.email if consultation.patient and consultation.patient.user else None
        pdf_bytes = upload.pdf_file.read()
        upload.pdf_file.seek(0)
        send_lab_results_email(
            consultation=consultation,
            patient_email=patient_email,
            pdf_name=pdf.name or f"lab_results_{consultation.id}.pdf",
            pdf_bytes=pdf_bytes,
        )
    except Exception:
        pass

    return redirect("lab_upload_results", consultation_id=consultation.id)
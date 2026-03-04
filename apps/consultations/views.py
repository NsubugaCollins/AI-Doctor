import json
import logging

from asgiref.sync import sync_to_async
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from .models import Consultation, Symptom, Patient
from apps.blackboard.services import BlackboardService

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
            blackboard.write(
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

        return JsonResponse(
            {
                "id": str(consultation.id),
                "current_state": consultation.current_state,
                "has_symptoms": has_symptoms,
                "diagnosis": consultation.diagnosis,
                "lab_tests": consultation.lab_tests,
                "prescription": consultation.prescription,
                "blackboard_state": blackboard_data.get("current_state")
                if blackboard_data
                else None,
            }
        )

    except Exception as e:
        logger.error(f"Status error: {e}")
        return JsonResponse({"error": str(e)}, status=500)
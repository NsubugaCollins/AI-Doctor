import logging
from typing import Optional

from django.conf import settings
from django.core.mail import EmailMessage

from .models import Consultation

logger = logging.getLogger(__name__)


def _safe_send(msg: EmailMessage) -> bool:
    try:
        sent = msg.send(fail_silently=False)
        return bool(sent)
    except Exception as e:
        logger.warning("Email send failed: %s", e)
        return False


def send_lab_order_email(*, consultation: Consultation, lab_order_text: str) -> bool:
    to_email = getattr(settings, "LAB_INBOX_EMAIL", "") or ""
    if not to_email:
        return False

    subject = f"Lab order for consultation {consultation.id}"
    body = (
        "A new lab order was generated.\n\n"
        f"Consultation: {consultation.id}\n"
        f"Current state: {consultation.current_state}\n\n"
        "Lab order text is attached.\n"
    )

    msg = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to_email],
    )
    msg.attach(filename=f"lab_order_{consultation.id}.txt", content=lab_order_text, mimetype="text/plain")
    return _safe_send(msg)


def send_prescription_email(
    *,
    consultation: Consultation,
    prescription_text: str,
    patient_email: Optional[str] = None,
    pharmacy_email: Optional[str] = None,
) -> bool:
    recipients = []
    if patient_email:
        recipients.append(patient_email)
    if pharmacy_email:
        recipients.append(pharmacy_email)
    if not recipients:
        return False

    subject = f"Prescription for consultation {consultation.id}"
    body = (
        "A prescription was generated.\n\n"
        f"Consultation: {consultation.id}\n\n"
        "Prescription text is attached.\n"
    )

    msg = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=recipients,
    )
    msg.attach(
        filename=f"prescription_{consultation.id}.txt",
        content=prescription_text,
        mimetype="text/plain",
    )
    return _safe_send(msg)


def send_lab_results_email(
    *,
    consultation: Consultation,
    patient_email: Optional[str],
    pdf_name: str,
    pdf_bytes: bytes,
) -> bool:
    if not patient_email:
        return False

    subject = f"Lab results for consultation {consultation.id}"
    body = (
        "Lab results were uploaded.\n\n"
        f"Consultation: {consultation.id}\n\n"
        "The uploaded PDF is attached.\n"
    )
    msg = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[patient_email],
    )
    msg.attach(filename=pdf_name, content=pdf_bytes, mimetype="application/pdf")
    return _safe_send(msg)


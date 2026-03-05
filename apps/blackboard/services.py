import logging
import json
import uuid
from typing import Optional, Dict, Any
from django.core.cache import cache
from django.utils import timezone
from .models import BlackboardEntry, BlackboardHistory
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class BlackboardService:
    """
    Blackboard service for consultations.
    Synchronous internally, async-safe via sync_to_async.
    """

    def __init__(self):
        self.cache = cache
        self.lock_timeout = 30  # seconds

    # -------------------------
    # Core synchronous methods
    # -------------------------

    def create_consultation(self, patient_data: Dict[str, Any], consultation_id: str = None) -> str:
        # Ensure consultation_id is a string
        consultation_id = str(consultation_id or uuid.uuid4())

        initial_state = {
            "consultation_id": consultation_id,
            "patient": patient_data,
            "current_state": "initial",
            "symptoms": {},
            "symptom_analysis": {},
            "diagnosis": {},
            "lab_tests": [],
            "lab_tests_document": {},
            "lab_results": [],
            "prescription": {},
            "history": [{
                "timestamp": timezone.now().isoformat(),
                "action": "consultation_created",
                "agent": "system"
            }]
        }

        # Cache (Redis). If unavailable, fall back to DB only.
        try:
            self.cache.set(f"consultation:{consultation_id}", json.dumps(initial_state), timeout=3600)
        except Exception as e:
            logger.warning("Cache set failed in create_consultation (%s): %s", consultation_id, e)

        # PostgreSQL
        BlackboardEntry.objects.create(
            consultation_id=consultation_id,
            agent_name="system",
            state=initial_state
        )

        return consultation_id

    def read(self, consultation_id: str) -> Optional[Dict[str, Any]]:
        # Ensure consultation_id is a string
        consultation_id = str(consultation_id)
        
        try:
            cached = self.cache.get(f"consultation:{consultation_id}")
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning("Cache read failed (%s): %s", consultation_id, e)

        try:
            entry = BlackboardEntry.objects.filter(
                consultation_id=consultation_id
            ).latest("created_at")
            return entry.state
        except BlackboardEntry.DoesNotExist:
            return None

    def write(self, consultation_id: str, updates: Dict[str, Any], agent_name: str) -> bool:
        # Ensure consultation_id is a string
        consultation_id = str(consultation_id)
        
        current_state = self.read(consultation_id)
        if not current_state:
            # Auto-initialize if missing so UI/agents can always write.
            logger.warning("Auto-initializing missing blackboard state for %s", consultation_id)
            current_state = {
                "consultation_id": consultation_id,
                "patient": {},
                "current_state": "initial",
                "symptoms": {},
                "symptom_analysis": {},
                "diagnosis": {},
                "lab_tests": [],
                "lab_tests_document": {},
                "lab_results": [],
                "prescription": {},
                "history": [{
                    "timestamp": timezone.now().isoformat(),
                    "action": "blackboard_auto_initialized",
                    "agent": agent_name,
                }],
            }

        current_state.update(updates)

        if "history" not in current_state:
            current_state["history"] = []

        current_state["history"].append({
            "timestamp": timezone.now().isoformat(),
            "action": f"updated_by_{agent_name}",
            "agent": agent_name,
            "updates": list(updates.keys())
        })

        current_state["updated_at"] = timezone.now().isoformat()

        # Cache (Redis). If unavailable, keep DB as source-of-truth.
        try:
            self.cache.set(f"consultation:{consultation_id}", json.dumps(current_state), timeout=3600)
        except Exception as e:
            logger.warning("Cache set failed (%s): %s", consultation_id, e)

        # PostgreSQL
        BlackboardEntry.objects.create(
            consultation_id=consultation_id,
            agent_name=agent_name,
            state=current_state
        )

        BlackboardHistory.objects.create(
            consultation_id=consultation_id,
            agent_name=agent_name,
            action="update",
            changes=updates
        )

        return True

    def acquire_lock(self, consultation_id: str, agent_name: str) -> bool:
        lock_key = f"lock:{consultation_id}"
        try:
            acquired = self.cache.add(lock_key, agent_name, timeout=self.lock_timeout)
        except Exception as e:
            logger.warning("Cache lock add failed (%s): %s", consultation_id, e)
            return False
        if acquired:
            BlackboardEntry.objects.filter(
                consultation_id=consultation_id
            ).update(
                lock_acquired=True,
                lock_owner=agent_name,
                lock_expires_at=timezone.now() + timezone.timedelta(seconds=self.lock_timeout)
            )
        return acquired

    def release_lock(self, consultation_id: str, agent_name: str):
        lock_key = f"lock:{consultation_id}"
        try:
            current_owner = self.cache.get(lock_key)
        except Exception as e:
            logger.warning("Cache lock get failed (%s): %s", consultation_id, e)
            return

        if current_owner == agent_name:
            try:
                self.cache.delete(lock_key)
            except Exception as e:
                logger.warning("Cache lock delete failed (%s): %s", consultation_id, e)
                # Still attempt to clear DB lock flags
            BlackboardEntry.objects.filter(
                consultation_id=consultation_id,
                lock_owner=agent_name
            ).update(
                lock_acquired=False,
                lock_owner=None,
                lock_expires_at=None
            )

    def get_consultations_by_state(self, state: str) -> list:
        """Return consultation_ids whose LATEST blackboard entry has current_state == state."""
        from django.db.models import Max
        result = []
        try:
            latest_entries = BlackboardEntry.objects.values("consultation_id").annotate(
                max_created=Max("created_at")
            )
            for item in latest_entries:
                cid = item["consultation_id"]
                latest = BlackboardEntry.objects.filter(
                    consultation_id=cid,
                    created_at=item["max_created"]
                ).first()
                if latest and latest.state and latest.state.get("current_state") == state:
                    result.append(str(cid))
            return result
        except Exception as e:
            logger.warning(f"get_consultations_by_state error: {e}")
            try:
                return [
                    str(x) for x in
                    BlackboardEntry.objects.filter(
                        state__current_state=state
                    ).values_list("consultation_id", flat=True).distinct()
                ]
            except Exception as e2:
                logger.warning(f"get_consultations_by_state fallback error: {e2}")
                return []


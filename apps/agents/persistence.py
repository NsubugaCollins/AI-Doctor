"""
Agent Persistence - Save and load agents locally for future use.
Stores agent configurations and session summaries to data/agents/
"""

import json
import logging
import os
from django.utils import timezone

from pathlib import Path
from typing import Dict, Any, Optional, List

from django.conf import settings

logger = logging.getLogger(__name__)

AGENTS_DATA_DIR = getattr(settings, 'AGENTS_DATA_DIR', 'data/agents')


def _ensure_dir(path: str) -> Path:
    """Ensure directory exists."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_agents_dir() -> Path:
    """Get the agents data directory."""
    base = getattr(settings, 'BASE_DIR', Path.cwd())
    if isinstance(base, str):
        base = Path(base)
    return _ensure_dir(base / AGENTS_DATA_DIR)


def save_agent_config(agent_name: str, config: Dict[str, Any]) -> str:
    """Save agent configuration to local JSON file."""
    agents_dir = get_agents_dir()
    filepath = agents_dir / f"{agent_name}_config.json"
    data = {
        "agent_name": agent_name,
        "config": config,
        "saved_at": timezone.now().isoformat(),
        "version": "1.0",
    }
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Saved agent config: {agent_name} -> {filepath}")
    return str(filepath)


def load_agent_config(agent_name: str) -> Optional[Dict[str, Any]]:
    """Load agent configuration from local file."""
    agents_dir = get_agents_dir()
    filepath = agents_dir / f"{agent_name}_config.json"
    if not filepath.exists():
        return None
    try:
        with open(filepath) as f:
            data = json.load(f)
        return data.get("config", data)
    except Exception as e:
        logger.warning(f"Failed to load agent config {agent_name}: {e}")
        return None


def save_agent_session_summary(
    agent_name: str,
    consultation_id: str,
    summary: Dict[str, Any],
) -> str:
    """Save agent session summary for audit/recovery."""
    agents_dir = get_agents_dir()
    sessions_dir = agents_dir / "sessions"
    _ensure_dir(str(sessions_dir))

    filepath = sessions_dir / f"{agent_name}_{consultation_id}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.json"
    data = {
        "agent_name": agent_name,
        "consultation_id": consultation_id,
        "summary": summary,
        "timestamp": timezone.now().isoformat(),
    }
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    return str(filepath)


def list_saved_agents() -> List[str]:
    """List agent names that have saved configs."""
    agents_dir = get_agents_dir()
    agents = []
    for f in agents_dir.glob("*_config.json"):
        agents.append(f.stem.replace("_config", ""))
    return agents


def persist_agents_on_shutdown(controller):
    """Save all agent configs when controller shuts down."""
    agents_dir = get_agents_dir()
    agents_data = {
        "symptom_agent": {
            "type": "SymptomAgent",
            "saved_at": timezone.now().isoformat(),
        },
        "diagnosis_agent": {
            "type": "DiagnosisAgent",
            "saved_at": timezone.now().isoformat(),
        },
        "lab_agent": {
            "type": "LabAgent",
            "saved_at": timezone.now().isoformat(),
        },
    }
    filepath = agents_dir / "agents_registry.json"
    with open(filepath, "w") as f:
        json.dump(agents_data, f, indent=2)
    logger.info(f"Persisted agents registry to {filepath}")

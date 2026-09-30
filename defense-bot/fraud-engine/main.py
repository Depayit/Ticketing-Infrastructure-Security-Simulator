import math
import sys
from pathlib import Path
from typing import Any, Dict, List

import joblib
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.config import AI_LAYER_ENABLED
from shared.events import log_event

app = FastAPI(title="Fraud Engine")

MODEL_PATH = Path(__file__).resolve().parent / "model.joblib"
_model = None


class ScoreRequest(BaseModel):
    session_id: str = ""
    token_issued_at: float = 0
    lock_at: float = 0
    api_only: bool = False
    telemetry_event_count: int = 0
    scroll_count: int = 0
    seat_hover_count: int = 0
    mousemove_count: int = 0
    checkout_attempts_per_min: int = 1


def load_model():
    global _model
    if _model is None and MODEL_PATH.exists():
        _model = joblib.load(MODEL_PATH)
    return _model


def extract_features(req: ScoreRequest) -> Dict[str, float]:
    token_to_lock_ms = max(0, (req.lock_at - req.token_issued_at) * 1000) if req.token_issued_at else 0
    api_only_ratio = 1.0 if req.api_only or req.telemetry_event_count == 0 else 0.0
    mouse_entropy = min(1.0, req.mousemove_count / 50.0)
    return {
        "token_to_lock_ms": token_to_lock_ms,
        "mouse_path_entropy": mouse_entropy,
        "scroll_count": float(req.scroll_count),
        "seat_hover_count": float(req.seat_hover_count),
        "api_only_ratio": api_only_ratio,
        "checkout_attempts_per_min": float(req.checkout_attempts_per_min),
        "session_event_count": float(req.telemetry_event_count),
    }


def rule_prefilter(f: Dict[str, float]) -> float | None:
    if f["api_only_ratio"] >= 1.0 and f["token_to_lock_ms"] < 1000:
        return 0.95
    if f["checkout_attempts_per_min"] >= 5:
        return 0.85
    if f["session_event_count"] == 0 and f["token_to_lock_ms"] < 2000:
        return 0.9
    return None


def ml_score(f: Dict[str, float]) -> float:
    model = load_model()
    if model is None:
        return 0.5 if f["api_only_ratio"] > 0.5 else 0.2
    vec = np.array([[f[k] for k in FEATURE_ORDER]])
    raw = -model.decision_function(vec)[0]
    return float(1 / (1 + math.exp(-raw)))


FEATURE_ORDER = [
    "token_to_lock_ms",
    "mouse_path_entropy",
    "scroll_count",
    "seat_hover_count",
    "api_only_ratio",
    "checkout_attempts_per_min",
    "session_event_count",
]


@app.get("/health")
def health():
    return {"status": "ok", "service": "fraud-engine", "model_loaded": MODEL_PATH.exists()}


@app.post("/score")
def score(req: ScoreRequest):
    if not AI_LAYER_ENABLED:
        return {"risk_score": 0.0, "decision": "allow", "layer": "ai", "disabled": True}

    features = extract_features(req)
    pre = rule_prefilter(features)
    risk = pre if pre is not None else ml_score(features)

    if risk < 0.4:
        decision = "allow"
    elif risk < 0.7:
        decision = "challenge"
    else:
        decision = "block"

    result = {"risk_score": round(risk, 4), "decision": decision, "layer": "ai", "features": features}
    if decision == "block":
        log_event("ai", "fraud_blocked", req.session_id, "", result, blocked=True)
    return result

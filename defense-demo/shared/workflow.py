"""Redis backed login and form CAPTCHA gates for the local Defense Lab."""

import hashlib
import json
import secrets

from shared.config import AUTH_SESSION_TTL_SEC, FORM_CAPTCHA_TTL_SEC, WORKFLOW_CONFIG_KEY, WORKFLOW_DEFAULTS, normalize_workflow
from shared.redis_client import r

GATE_POSITIONS = {"queue", "booking", "seat", "lock", "checkout"}


def get_workflow():
    raw = r.get(WORKFLOW_CONFIG_KEY)
    return normalize_workflow(json.loads(raw)) if raw else WORKFLOW_DEFAULTS.copy()


def sensor_score(session_id):
    raw = r.get(f"defense:sensor:{session_id}") if session_id else None
    return max(0, min(100, int(json.loads(raw).get("bot_score", 60)))) if raw else 60


def auth_key(token):
    return "defense:auth:" + hashlib.sha256(token.encode()).hexdigest()


def auth_user(token, session_id):
    if not token or not session_id:
        return None
    raw = r.get(auth_key(token))
    if not raw:
        return None
    meta = json.loads(raw)
    return meta.get("user_id") if meta.get("session_id") == session_id else None


def create_auth(email, session_id):
    token = secrets.token_urlsafe(32)
    user_id = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:24]
    r.setex(auth_key(token), AUTH_SESSION_TTL_SEC, json.dumps({"user_id": user_id, "session_id": session_id}))
    return token, user_id


def captcha_key(session_id, event_id, position):
    version = r.get("defense:config:captcha_version") or "0"
    value = f"{version}:{session_id}:{event_id}:{position}"
    return "defense:captcha:" + hashlib.sha256(value.encode()).hexdigest()


def captcha_required(workflow, session_id, event_id, position, bot_score):
    if position not in GATE_POSITIONS or not session_id:
        return False
    configured = workflow["CAPTCHA_POSITION"]
    if configured == "none":
        return False
    key = captcha_key(session_id, event_id, position)
    raw = r.get(key)
    if raw:
        return json.loads(raw)["required"]
    if configured == "random":
        score = max(0, min(100, int(bot_score)))
        probability = min(1.0, workflow["CAPTCHA_RANDOM_RATE"] * (0.5 + score / 100))
        required = secrets.randbelow(10000) < int(probability * 10000)
    else:
        required = configured == position
    r.setex(key, FORM_CAPTCHA_TTL_SEC, json.dumps({"required": required, "passed": False}))
    return required


def captcha_passed(session_id, event_id, position):
    raw = r.get(captcha_key(session_id, event_id, position))
    return bool(raw and json.loads(raw).get("passed"))


def challenge_key(session_id, event_id, position):
    return captcha_key(session_id, event_id, position) + ":challenge"


def new_challenge(session_id, event_id, position):
    previous = r.get(challenge_key(session_id, event_id, position))
    if previous:
        meta = json.loads(previous)
        return {"question": meta["question"], "position": position}
    a, b = secrets.randbelow(8) + 2, secrets.randbelow(8) + 2
    question = f"{a} + {b} = ?"
    r.setex(challenge_key(session_id, event_id, position), FORM_CAPTCHA_TTL_SEC,
            json.dumps({"answer": a + b, "question": question, "attempts": 0}))
    return {"question": question, "position": position}


def verify_challenge(session_id, event_id, position, answer):
    key = challenge_key(session_id, event_id, position)
    raw = r.get(key)
    if not raw:
        return False
    challenge = json.loads(raw)
    if challenge["attempts"] >= 3:
        return False
    challenge["attempts"] += 1
    if str(answer).strip() != str(challenge["answer"]):
        r.setex(key, FORM_CAPTCHA_TTL_SEC, json.dumps(challenge))
        return False
    r.delete(key)
    state_key = captcha_key(session_id, event_id, position)
    r.setex(state_key, FORM_CAPTCHA_TTL_SEC, json.dumps({"required": True, "passed": True}))
    return True

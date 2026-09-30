import os

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/1")
TOKEN_TTL_SEC = int(os.environ.get("TOKEN_TTL_SEC", "1200"))
SEAT_LOCK_TTL_SEC = int(os.environ.get("SEAT_LOCK_TTL_SEC", "300"))
ADMISSION_RATE = int(os.environ.get("ADMISSION_RATE", "50"))
FRAUD_ENGINE_URL = os.environ.get("FRAUD_ENGINE_URL", "http://localhost:8094")
QUEUE_SERVICE_URL = os.environ.get("QUEUE_SERVICE_URL", "http://localhost:8091")
SEAT_SERVICE_URL = os.environ.get("SEAT_SERVICE_URL", "http://localhost:8092")
PAYMENT_SERVICE_URL = os.environ.get("PAYMENT_SERVICE_URL", "http://localhost:8093")
MOCK_CAPTCHA_SITEKEY = "0xDEFENSE_DEMO_TURNSTILE"
DEFAULT_EVENT_ID = "demo-concert-2026"
DEFAULT_EVENT_NAME = "BANGKOK LIVE EXPERIENCE 2026"
PURCHASE_LIMIT_MINUTES = int(os.environ.get("PURCHASE_LIMIT_MINUTES", "10"))
AI_LAYER_ENABLED = os.environ.get("AI_LAYER_ENABLED", "true").lower() == "true"
THREE_DS_OTP = os.environ.get("THREE_DS_OTP", "123456")

# Akamai Bot Manager simulation
BOT_CHALLENGE_THRESHOLD = int(os.environ.get("BOT_CHALLENGE_THRESHOLD", "55"))
BOT_SCORE_ADMIT_MAX = int(os.environ.get("BOT_SCORE_ADMIT_MAX", "75"))
QUEUE_JOIN_TTL_SEC = int(os.environ.get("QUEUE_JOIN_TTL_SEC", "1800"))
SENSOR_SESSION_TTL_SEC = int(os.environ.get("SENSOR_SESSION_TTL_SEC", "3600"))
EDGE_DDOS_GLOBAL_RPS = int(os.environ.get("EDGE_DDOS_GLOBAL_RPS", "800"))

# Block bot GraphQL/API bypass (Ticket-bot workers). Browser funnel uses /api/funnel/* only.
GRAPHQL_ENABLED = os.environ.get("GRAPHQL_ENABLED", "false").lower() == "true"
BOT_BYPASS_BLOCK = os.environ.get("BOT_BYPASS_BLOCK", "true").lower() == "true"

# Workflow configuration is stored in Redis so every service sees changes without
# a container rebuild. Profiles describe the intended gates; enforcement is added
# in later phases. Keep the current sensor -> queue -> seat flow as the default.
WORKFLOW_CONFIG_KEY = "defense:config:workflow"
AUTH_SESSION_TTL_SEC = int(os.environ.get("AUTH_SESSION_TTL_SEC", "3600"))
FORM_CAPTCHA_TTL_SEC = int(os.environ.get("FORM_CAPTCHA_TTL_SEC", "300"))
WORKFLOW_DEFAULTS = {
    "WORKFLOW_PROFILE": "custom",
    "REQUIRE_LOGIN_BEFORE_QUEUE": False,
    "REQUIRE_LOGIN_BEFORE_SEAT": False,
    "REQUIRE_LOGIN_BEFORE_LOCK": False,
    "CAPTCHA_POSITION": "none",
    "CAPTCHA_RANDOM_RATE": 0.0,
    "QUEUE_MODE": "fifo_rate",
}
WORKFLOW_PROFILES = {
    "A": {"REQUIRE_LOGIN_BEFORE_SEAT": True},
    "B": {"REQUIRE_LOGIN_BEFORE_QUEUE": True},
    "C": {"CAPTCHA_POSITION": "random", "CAPTCHA_RANDOM_RATE": 0.25},
    "D": {
        "REQUIRE_LOGIN_BEFORE_QUEUE": True,
        "REQUIRE_LOGIN_BEFORE_SEAT": True,
        "REQUIRE_LOGIN_BEFORE_LOCK": True,
        "CAPTCHA_POSITION": "random",
        "CAPTCHA_RANDOM_RATE": 0.5,
        "QUEUE_MODE": "priority_score",
    },
}
CAPTCHA_POSITIONS = {"queue", "booking", "seat", "lock", "checkout", "random", "none"}
QUEUE_MODES = {"off", "fifo_rate", "priority_score"}


def normalize_workflow(data, base=None):
    """Validate a partial workflow update and return a complete configuration."""
    if not isinstance(data, dict):
        raise ValueError("workflow must be an object")
    unknown = set(data) - set(WORKFLOW_DEFAULTS)
    if unknown:
        raise ValueError(f"unknown workflow fields: {', '.join(sorted(unknown))}")
    result = {**WORKFLOW_DEFAULTS, **(base or {}), **data}
    profile = result["WORKFLOW_PROFILE"]
    if not isinstance(profile, str) or profile not in (*WORKFLOW_PROFILES, "custom"):
        raise ValueError("WORKFLOW_PROFILE must be A, B, C, D, or custom")
    if profile != "custom":
        result.update({key: WORKFLOW_DEFAULTS[key] for key in WORKFLOW_DEFAULTS if key != "WORKFLOW_PROFILE"})
        result.update(WORKFLOW_PROFILES[profile])
    for key in ("REQUIRE_LOGIN_BEFORE_QUEUE", "REQUIRE_LOGIN_BEFORE_SEAT", "REQUIRE_LOGIN_BEFORE_LOCK"):
        if type(result[key]) is not bool:
            raise ValueError(f"{key} must be a boolean")
    if not isinstance(result["CAPTCHA_POSITION"], str) or result["CAPTCHA_POSITION"] not in CAPTCHA_POSITIONS:
        raise ValueError("invalid CAPTCHA_POSITION")
    rate = result["CAPTCHA_RANDOM_RATE"]
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not 0 <= rate <= 1:
        raise ValueError("CAPTCHA_RANDOM_RATE must be between 0 and 1")
    if not isinstance(result["QUEUE_MODE"], str) or result["QUEUE_MODE"] not in QUEUE_MODES:
        raise ValueError("invalid QUEUE_MODE")
    return result

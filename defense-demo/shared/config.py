import os

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/1")
TOKEN_TTL_SEC = int(os.environ.get("TOKEN_TTL_SEC", "1200"))
SEAT_LOCK_TTL_SEC = int(os.environ.get("SEAT_LOCK_TTL_SEC", "900"))
ADMISSION_RATE = int(os.environ.get("ADMISSION_RATE", "50"))
FRAUD_ENGINE_URL = os.environ.get("FRAUD_ENGINE_URL", "http://localhost:8094")
QUEUE_SERVICE_URL = os.environ.get("QUEUE_SERVICE_URL", "http://localhost:8091")
SEAT_SERVICE_URL = os.environ.get("SEAT_SERVICE_URL", "http://localhost:8092")
PAYMENT_SERVICE_URL = os.environ.get("PAYMENT_SERVICE_URL", "http://localhost:8093")
MOCK_CAPTCHA_SITEKEY = "0xDEFENSE_DEMO_TURNSTILE"
DEFAULT_EVENT_ID = "demo-concert-2026"
DEFAULT_EVENT_NAME = "2026-27 JACOB WORLD TOUR IN BANGKOK"
PURCHASE_LIMIT_MINUTES = int(os.environ.get("PURCHASE_LIMIT_MINUTES", "10"))
AI_LAYER_ENABLED = os.environ.get("AI_LAYER_ENABLED", "true").lower() == "true"
THREE_DS_OTP = os.environ.get("THREE_DS_OTP", "123456")

# Akamai Bot Manager simulation
BOT_CHALLENGE_THRESHOLD = int(os.environ.get("BOT_CHALLENGE_THRESHOLD", "55"))
BOT_SCORE_ADMIT_MAX = int(os.environ.get("BOT_SCORE_ADMIT_MAX", "75"))
QUEUE_JOIN_TTL_SEC = int(os.environ.get("QUEUE_JOIN_TTL_SEC", "1800"))
SENSOR_SESSION_TTL_SEC = int(os.environ.get("SENSOR_SESSION_TTL_SEC", "3600"))
EDGE_DDOS_GLOBAL_RPS = int(os.environ.get("EDGE_DDOS_GLOBAL_RPS", "800"))

# Block bot GraphQL/API bypass (ttm-bot workers). Browser funnel uses /api/funnel/* only.
GRAPHQL_ENABLED = os.environ.get("GRAPHQL_ENABLED", "false").lower() == "true"
BOT_BYPASS_BLOCK = os.environ.get("BOT_BYPASS_BLOCK", "true").lower() == "true"

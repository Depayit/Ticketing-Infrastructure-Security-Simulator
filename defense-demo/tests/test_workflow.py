import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.config import normalize_workflow
from shared import workflow


class MemoryRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.redis = MemoryRedis()
        self.redis_patch = patch.object(workflow, "r", self.redis)
        self.redis_patch.start()
        self.addCleanup(self.redis_patch.stop)

    def test_profile_presets_and_invalid_input(self):
        profile = normalize_workflow({"WORKFLOW_PROFILE": "D"})
        self.assertTrue(profile["REQUIRE_LOGIN_BEFORE_QUEUE"])
        self.assertTrue(profile["REQUIRE_LOGIN_BEFORE_LOCK"])
        self.assertEqual(profile["CAPTCHA_POSITION"], "random")
        self.assertEqual(profile["QUEUE_MODE"], "priority_score")
        with self.assertRaises(ValueError):
            normalize_workflow({"CAPTCHA_RANDOM_RATE": 1.5})
        with self.assertRaises(ValueError):
            normalize_workflow({"WORKFLOW_PROFILE": []})

    def test_auth_is_bound_to_sensor_session(self):
        token, user_id = workflow.create_auth("USER@example.com", "sensor-a")
        self.assertEqual(workflow.auth_user(token, "sensor-a"), user_id)
        self.assertIsNone(workflow.auth_user(token, "sensor-b"))

    def test_random_captcha_decision_is_stable_and_score_weighted(self):
        config = normalize_workflow({"CAPTCHA_POSITION": "random", "CAPTCHA_RANDOM_RATE": 0.5})
        with patch.object(workflow.secrets, "randbelow", return_value=6000) as draw:
            self.assertFalse(workflow.captcha_required(config, "low", "event", "queue", 0))
            self.assertTrue(workflow.captcha_required(config, "high", "event", "queue", 100))
            self.assertFalse(workflow.captcha_required(config, "low", "event", "queue", 100))
            self.assertEqual(draw.call_count, 2)

    def test_challenge_is_server_checked_and_attempts_are_limited(self):
        challenge = workflow.new_challenge("sensor", "event", "lock")
        self.assertEqual(challenge, workflow.new_challenge("sensor", "event", "lock"))
        key = workflow.challenge_key("sensor", "event", "lock")
        answer = json.loads(self.redis.get(key))["answer"]
        for _ in range(3):
            self.assertFalse(workflow.verify_challenge("sensor", "event", "lock", "wrong"))
        self.assertFalse(workflow.verify_challenge("sensor", "event", "lock", answer))
        self.assertFalse(workflow.captcha_passed("sensor", "event", "lock"))

    def test_challenge_pass_is_position_scoped(self):
        workflow.new_challenge("sensor", "event", "seat")
        answer = json.loads(self.redis.get(workflow.challenge_key("sensor", "event", "seat")))["answer"]
        self.assertTrue(workflow.verify_challenge("sensor", "event", "seat", answer))
        self.assertTrue(workflow.captcha_passed("sensor", "event", "seat"))
        self.assertFalse(workflow.captcha_passed("sensor", "event", "lock"))


if __name__ == "__main__":
    unittest.main()

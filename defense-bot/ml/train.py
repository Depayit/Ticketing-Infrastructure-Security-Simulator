import json
import sys
import time
from pathlib import Path

import numpy as np
from sklearn.ensemble import IsolationForest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FEATURE_ORDER = [
    "token_to_lock_ms",
    "mouse_path_entropy",
    "scroll_count",
    "seat_hover_count",
    "api_only_ratio",
    "checkout_attempts_per_min",
    "session_event_count",
]

rng = np.random.default_rng(42)
rows = []
labels = []

for _ in range(400):
    rows.append([
        rng.uniform(3000, 45000),
        rng.uniform(0.4, 1.0),
        rng.integers(2, 10),
        rng.integers(1, 5),
        0.0,
        rng.integers(1, 3),
        rng.integers(20, 120),
    ])
    labels.append("human")

for _ in range(400):
    rows.append([
        rng.uniform(50, 500),
        0.0,
        0,
        0,
        1.0,
        rng.integers(5, 15),
        rng.integers(0, 2),
    ])
    labels.append("bot")

for _ in range(200):
    rows.append([
        rng.uniform(2000, 8000),
        rng.uniform(0.2, 0.6),
        rng.integers(1, 4),
        rng.integers(1, 3),
        0.0,
        rng.integers(1, 4),
        rng.integers(10, 40),
    ])
    labels.append("assisted")

X = np.array(rows)
model = IsolationForest(n_estimators=200, contamination=0.35, random_state=42)
model.fit(X)

out = Path(__file__).resolve().parent.parent / "fraud-engine" / "model.joblib"
import joblib
joblib.dump(model, out)
print(f"Saved model to {out} with {len(rows)} samples")

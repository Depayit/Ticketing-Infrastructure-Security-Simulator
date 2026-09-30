# Defensive Lab scenario matrix

Run only against the local Docker stack. `bot-loadgen` rejects a gateway hostname other than `gateway`, `localhost`, or `127.0.0.1`. The default small pack runs one actor for each selected scenario. `medium` runs five and `large` runs twenty per scenario; concurrency is capped at ten. Use `LOADGEN_COUNT` to override the per-scenario count up to 100 and `LOADGEN_SCENARIOS` to select a comma-separated subset.

| Workflow | Queue/Login order | CAPTCHA | Admission | Main expected gate |
| --- | --- | --- | --- | --- |
| A | Queue then Login | none | FIFO | Missing Auth Session after admission |
| B | Login then Queue | none | FIFO | Missing Auth Session before admission |
| C | Queue then Seat | random, score weighted | FIFO | Form CAPTCHA at selected positions |
| D | Login then Queue; login checks at Seat and Lock | random, score weighted | score priority | Auth, CAPTCHA, admission and fraud |

| Loadgen scenario | Sensor and browser | Booking behavior | Expected observation |
| --- | --- | --- | --- |
| `simple_http` | HTTP without sensor | Queue only | Sensor gate |
| `no_sensor` | HTTP without sensor | Queue only | Sensor gate |
| `browser_like` | Synthetic high-count sensor | Queue only | May be admitted; measures score weakness |
| `stealth_browser` | Real headless Chromium sensor | Attempts Seat Lock without behavior telemetry | Measures whether slow API-only booking bypasses current fraud rules |
| `full_behavioral` | Synthetic sensor and rich telemetry | Seat Lock and payment | Tests whether the simulated defense can be passed |
| `multi_account` | Distinct mock account per actor | Seat Lock | Tests queue and seat contention |
| `human_browser` | Real Chromium sensor with mouse/scroll | Seat Lock and payment | Synthetic human false-positive reference |

The scenario labels describe generated traffic, not ground truth about real users. `bot_block_rate` excludes `human_browser`; `synthetic_human_false_positive_rate` uses only that scenario. A harness error is reported separately and should invalidate conclusions about detection. `median_time_to_admit_ms`, `unpaid_hold_rate`, and `captcha_pass_rate` are included in the JSON report. Review per-actor results before interpreting aggregate rates.

```bash
docker compose -f docker-compose.defense.yml up -d --build gateway
docker compose -f docker-compose.defense.yml --profile test run --rm --build lab-smoke
docker compose -f docker-compose.defense.yml --profile loadgen run --rm --build bot-loadgen
```

Run the load generator after setting the desired profile through `/admin`. Reset seats and sessions between comparisons, and record the profile, pack size, toggles, and run timestamp in the after-action report. The load generator creates an order during successful payment, so reset before a new experiment.

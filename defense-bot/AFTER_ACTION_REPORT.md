# After-action report template

Copy this file for each simulated event run. Attach the matching `reports/loadgen-*.json` and record the `/admin` audit window or Prometheus snapshot used for the values.

## Run identity

| Field | Value |
| --- | --- |
| Event and UTC time | |
| Workflow Profile and overrides | |
| Queue mode and admit rate | |
| Scenario pack, actor count and concurrency | |
| Defense toggles and soft-open duration | |
| Code revision / container images | |
| Report JSON path | |

## Outcomes

| Metric | Value | Evidence / denominator |
| --- | --- | --- |
| Bot block rate | | Blocked synthetic bot actors / completed bot actors |
| Synthetic human false-positive rate | | Blocked `human_browser` actors / completed synthetic human actors |
| Median time to admit (bot) | | Admitted bot actors only |
| Median time to admit (human) | | Admitted `human_browser` actors only |
| Bot Seat Lock rate | | Bot actors with a Seat Lock / completed bot actors |
| Bot payment success rate | | Bot actors with an order / completed bot actors |
| Unpaid Hold rate | | Seat Locks without payment / Seat Locks |
| CAPTCHA pass rate by scenario | | Passed challenges / presented challenges |
| Expired holds and reserve-abuse blocks | | `/metrics` and Live Audit |
| Harness errors | | Errors / attempted actors; explain all errors |

## Layer findings

| Layer | Blocks / challenges | Representative audit event | False positives or bypasses |
| --- | --- | --- | --- |
| Edge / WAF | | | |
| Bot Manager | | | |
| Waiting Room | | | |
| Auth Gate | | | |
| Form CAPTCHA | | | |
| Booking / Seat Hold | | | |
| Fraud / payment verification | | | |

## Decision

- What changed from the last comparable run:
- Which result is supported by enough completed actors:
- Which result is limited by scenario design or harness errors:
- Configuration or code change to test next:

This is a local simulation. Its bot detection and false-positive figures are not measurements of a live ticketing service.

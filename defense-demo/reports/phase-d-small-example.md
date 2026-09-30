# Example after-action report: Profile D, small pack

This local run completed at 2026-09-29 23:58:06 UTC. The source is [loadgen-20260929T235806Z.json](loadgen-20260929T235806Z.json), with one actor in each of seven scenarios and zero harness errors. The active workflow was D: Login before Queue, Seat and Lock, random form CAPTCHA at rate 0.5, and `priority_score` admission. WAF, Bot Manager, bypass block, Queue and mock 3DS were enabled; GraphQL and background bot simulation were disabled.

| Metric | Observed | Denominator |
| --- | ---: | --- |
| Synthetic bot block rate | 33.3% | 2 / 6 |
| Synthetic human false-positive rate | 0% | 0 / 1 |
| Bot median time to admit | 2,568 ms | 4 admitted bots |
| Human median time to admit | 3,238 ms | 1 admitted synthetic human |
| Bot Seat Lock rate | 50% | 3 / 6 |
| Bot payment success | 16.7% | 1 / 6 |
| Unpaid Hold rate | 50% | 2 / 4 locks |
| Form CAPTCHA pass rate | 100% | 8 / 8 presentations |

The two traffic types without a sensor stopped at the sensor gate. The `stealth_browser` scenario held a seat without behavior telemetry, and `full_behavioral` completed payment. These are concrete gaps in this lab's current fraud rules. The synthetic human completed payment.

Each scenario had only one actor, so these rates are a smoke check, not an estimate of detection or real-user false positives. Repeat with larger packs and reset seats between runs before comparing configurations. The supplied arithmetic CAPTCHA is deliberately solvable by the test harness.

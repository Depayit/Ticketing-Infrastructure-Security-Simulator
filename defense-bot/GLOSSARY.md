# Defense Lab glossary

| Term | Meaning in this repository |
| --- | --- |
| Defense Lab | Isolated ticket sale simulation for testing defenses. |
| Edge / WAF | HTTP rate, IP and request rules at the gateway. |
| Bot Manager | Sensor scoring, cookies and sensor challenge. |
| Sensor / Telemetry | Browser signals submitted to the Bot Manager or Booking Layer. |
| Bot Score | Integer 0–100; higher means more bot-like. |
| Challenge | Additional sensor proof after a high Bot Score. |
| CAPTCHA | Separate server checked arithmetic gate at configurable positions. |
| Waiting Room | Admission layer before booking. |
| Admit Rate / Admission Window | Maximum admissions per second by the queue service. |
| Priority Queue | Score ordered Waiting Room; lower Bot Score is admitted first, with FIFO ties. |
| Queue Token / Admit Token | Short lived bearer value issued on admission. |
| Auth Gate / Login Gate | Mock account session check at a configured point in the route. |
| Sensor Session | Browser identity for scoring; no account assertion. |
| Auth Session | Redis backed mock account identity, separate from Sensor Session. |
| Workflow Profile | Preset ordering and gates for an event simulation. |
| Booking Layer | Seat selection and cart operations in `seat-service`. |
| Seat Lock / Hold | Temporary claim to a seat while checkout proceeds. |
| Hold Timeout | Expiry after which a held seat must be released. |
| Reserve Abuse | Holding seats repeatedly without completing checkout. |
| Live Audit | Redis backed recent defense events shown in `/admin`. |

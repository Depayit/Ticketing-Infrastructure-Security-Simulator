# Defense Lab architecture

```text
Browser → gateway (Edge/WAF, Bot Manager entry, routing)
             ├─ queue-service (Waiting Room, Admit Token)
             ├─ seat-service (Booking Layer, Seat Lock, telemetry)
             │    └─ fraud-engine (fraud score)
             └─ payment-service (Checkout, mock 3DS)
All services share Redis for short lived state and Live Audit.
```

| Service | Responsibility |
| --- | --- | --- |
| `gateway` | HTTP entry, WAF and sensor handling, Auth Gate, form CAPTCHA, funnel proxy, admin API |
| `queue-service` | Redis sorted Waiting Room, atomic rate limited admission, Queue Token issuance |
| `seat-service` | Atomic Seat Hold and expiry, telemetry and fraud request |
| `fraud-engine` | Transaction behavior score |
| `payment-service` | Checkout, mock 3DS/QR, atomic permanent seat confirmation after verification |

The simulated Akamai sensor and cookies are demo components. No real Huawei, Akamai, Queue-it, or ThaiTicketMajor service is used. The operational default is `fifo_rate`.

The shared workflow configuration is read and written through gateway APIs. Redis key `defense:config:workflow` stores the selected profile and its expanded flags. No rebuild is needed to change gates or admission mode. The optional Prometheus/Grafana profile reads gateway metrics; `bot-loadgen` writes local JSON reports.
